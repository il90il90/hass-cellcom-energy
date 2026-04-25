"""HTTP client for the Cellcom digital API."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    CLIENT_ID,
    ENDPOINT_ALL_INVOICES,
    ENDPOINT_ALL_PRODUCTS,
    ENDPOINT_FULL_MAIN,
    ENDPOINT_INVOICE_DATA,
    ENDPOINT_LOGIN_STEP1,
    ENDPOINT_LOGIN_STEP2,
    ENDPOINT_LOGIN_STEP3,
    ENDPOINT_ONBOARDING,
    ENERGY_BLOCK_ID,
    MAX_RETRIES,
    OTP_ORIGIN,
    RETRY_BACKOFF_BASE,
    SCOPE,
)
from .exceptions import (
    CellcomAPIError,
    CellcomAuthError,
    CellcomConnectionError,
    CellcomIDError,
    CellcomOTPError,
    CellcomTokenExpiredError,
)
from .models import (
    BillingPeriod,
    CellcomData,
    CustomerInfo,
    Invoice,
    InvoiceAmount,
    MeterInfo,
    MonthlyHistory,
    TariffPlan,
    Tokens,
)

_LOGGER = logging.getLogger(__name__)


def _generate_device_id() -> str:
    """Generate a stable-looking DeviceId in the format used by the web portal."""
    raw = uuid.uuid4().hex
    return f"{raw[:6]}-{raw[6:9]}-{raw[9:12]}-{raw[12:16]}-{raw[16:28]}"


def _generate_tracking_id() -> str:
    """Generate a x-cell-tracking-id value (uppercase hex, 32 chars)."""
    return uuid.uuid4().hex.upper().replace("-", "")


def _generate_session_id() -> str:
    """Generate a SessionID UUID."""
    raw = uuid.uuid4().hex
    return f"{raw[:7]}-{raw[7:11]}-{raw[11:15]}-{raw[15:17]}-{raw[17:29]}"


def _parse_date_ddmmyy(value: str) -> str:
    """Convert 'dd.mm.yy' format to ISO 'yyyy-mm-dd'."""
    try:
        parts = value.strip().split(".")
        if len(parts) == 3:
            dd, mm, yy = parts
            return f"20{yy}-{mm}-{dd}"
    except Exception:
        pass
    return value


def _parse_cycle_date(cycle_date: int) -> str:
    """Convert integer cycle date (yyyymmdd) to ISO format."""
    s = str(cycle_date)
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


class CellcomEnergyClient:
    """Async HTTP client for the Cellcom digital API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        device_id: str | None = None,
        session_id: str | None = None,
        recaptcha_token: str | None = None,
        client_id: str | None = None,
    ) -> None:
        """Initialise the client with an aiohttp session and optional persistent IDs.

        client_id: per-user CLIENT_ID extracted from their JWT claim.
                   Falls back to the module-level CLIENT_ID constant if not provided.
        recaptcha_token: a real browser-obtained reCAPTCHA v3 token for LoginStep1.
        When provided it is sent in the x-cell-recaptcha-token header.
        """
        self._session = session
        self._device_id = device_id or _generate_device_id()
        self._session_id = session_id or _generate_session_id()
        self._recaptcha_token: str | None = recaptcha_token
        self._client_id: str = client_id or CLIENT_ID

    @property
    def device_id(self) -> str:
        """Return the persistent device ID."""
        return self._device_id

    @property
    def session_id(self) -> str:
        """Return the session ID."""
        return self._session_id

    def _base_headers(self) -> dict[str, str]:
        """Return headers sent on every request."""
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
            "ClientID": self._client_id,
            "Content-Type": "application/json",
            "DeviceId": self._device_id,
            "Origin": "https://cellcom.co.il",
            "Referer": "https://cellcom.co.il/",
            "SessionID": self._session_id,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
        }

    async def async_prime_session(self) -> None:
        """Prime both domains with Imperva WAF cookies.

        The main site (cellcom.co.il) and the API subdomain (digital-api.cellcom.co.il)
        each have their own Imperva site IDs and cookie sets.  Without these cookies
        the PUT /api/otp/LoginStep1 request returns HTTP 403.
        """
        browser_headers = {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
        }
        for url in (
            "https://cellcom.co.il/",
            "https://digital-api.cellcom.co.il/",
            "https://cellcom.co.il/my-cellcom/",
        ):
            try:
                async with self._session.get(
                    url,
                    headers=browser_headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                    allow_redirects=True,
                ) as resp:
                    _LOGGER.debug("Session prime %s → HTTP %s", url, resp.status)
            except Exception as err:
                _LOGGER.warning("Session prime failed for %s: %s (continuing)", url, err)

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
        bearer: str | None = None,
        extra_headers: dict[str, str] | None = None,
        retry: int = 0,
    ) -> dict[str, Any]:
        """Send a single API request and return the parsed JSON body."""
        headers = self._base_headers()
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if extra_headers:
            headers.update(extra_headers)

        url = f"{BASE_URL}{endpoint}"

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 401:
                    raise CellcomAuthError("Access token rejected (HTTP 401)")

                if resp.status == 403:
                    # 403 is usually an Imperva WAF block, not an auth issue.
                    # Raise as CellcomConnectionError so the UI shows "cannot connect"
                    # rather than misleading the user about their credentials.
                    _LOGGER.warning(
                        "Cellcom API returned 403 for %s — likely WAF block (Imperva). "
                        "Check that the HA server IP is not rate-limited.",
                        endpoint,
                    )
                    raise CellcomConnectionError("Request blocked by server (HTTP 403)")

                if resp.status >= 500 and retry < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE ** retry
                    _LOGGER.warning(
                        "Cellcom API returned %s, retrying in %ss (attempt %s/%s)",
                        resp.status, wait, retry + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    return await self._request(
                        method, endpoint, json=json, bearer=bearer,
                        extra_headers=extra_headers, retry=retry + 1
                    )

                resp.raise_for_status()
                data: dict[str, Any] = await resp.json(content_type=None)

        except aiohttp.ClientConnectionError as err:
            raise CellcomConnectionError(f"Connection error: {err}") from err
        except aiohttp.ClientResponseError as err:
            raise CellcomConnectionError(f"HTTP error {err.status}") from err

        # The API can return a bare JSON null (or a non-dict) — normalise to {}
        # so every subsequent .get() call is safe.
        if not isinstance(data, dict):
            _LOGGER.warning(
                "Unexpected response type %s for %s — treating as empty",
                type(data).__name__, endpoint,
            )
            return {}

        header = data.get("Header", {})
        return_code = header.get("ReturnCode", -1)
        if return_code != 0:
            msg = header.get("ReturnCodeMessage", "Unknown error")
            _LOGGER.error("Cellcom API error [%s]: %s", return_code, msg)
            raise CellcomAPIError(return_code, msg)

        body = data.get("Body", data)
        # Guard against "Body": null responses — always return a dict so callers
        # can safely call .get() without AttributeError.
        return body if isinstance(body, dict) else {}

    # ── Authentication ─────────────────────────────────────────────────────────

    async def async_login_step1(self, phone: str) -> str:
        """Start OTP login. Returns the GUID needed for step 2.

        Requires a real browser-obtained reCAPTCHA v3 token (set via constructor).
        The session is primed with WAF cookies automatically before the call.
        """
        await self.async_prime_session()

        extra_headers: dict[str, str] = {
            "sec-ch-ua": (
                '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"'
            ),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "x-cell-tracking-id": _generate_tracking_id(),
        }
        if self._recaptcha_token:
            extra_headers["x-cell-recaptcha-token"] = self._recaptcha_token
            _LOGGER.debug("LoginStep1: sending reCAPTCHA token")
        else:
            _LOGGER.warning(
                "LoginStep1: no reCAPTCHA token provided — server may reject with ReturnCode=99"
            )

        body = await self._request(
            "PUT",
            ENDPOINT_LOGIN_STEP1,
            json={
                "Subscriber": phone,
                "IsExtended": False,
                "ProcessType": "",
                "OtpOrigin": OTP_ORIGIN,
            },
            extra_headers=extra_headers,
        )
        # The API returns the GUID in Body.message (confirmed via HAR analysis).
        # Fallback checks cover any undocumented response variants.
        guid = (
            body.get("message")
            or body.get("Guid")
            or body.get("guid")
            or body.get("GUID")
        )
        if not guid:
            _LOGGER.error("LoginStep1 unexpected body: %s", body)
            raise CellcomAuthError("LoginStep1 did not return a Guid")
        _LOGGER.debug("LoginStep1 succeeded, Guid received")
        return guid

    async def async_login_step2(self, guid: str, otp_code: str, phone: str) -> str:
        """Verify OTP code. Returns a preliminary JWT for step 3."""
        try:
            body = await self._request(
                "PUT",
                ENDPOINT_LOGIN_STEP2,
                json={
                    "Guid": guid,
                    "OtpCode": otp_code,
                    "Subscriber": phone,
                    "RestrictCode": "",
                    "TermsAccepted": False,
                    "CheckPhoneNumber": "",
                    "LoginType": "",
                    "idNumber": "",
                    "CustomerEmail": "",
                    "ProcessType": "",
                    "OtpOrigin": OTP_ORIGIN,
                    "OriginProcess": "",
                },
            )
        except CellcomAPIError as err:
            raise CellcomOTPError(f"OTP verification failed: {err}") from err

        # The preliminary JWT is returned directly in the body
        token = body.get("accessToken") or body.get("token") or body.get("Token")
        if not token and isinstance(body, dict):
            # Some responses wrap it differently
            for key in ("AccessToken", "preliminaryToken"):
                token = body.get(key)
                if token:
                    break
        if not token:
            # Try to use the raw body as the token (some API versions return token directly)
            raw = str(body) if not isinstance(body, str) else body
            if len(raw) > 100:  # Looks like a JWT
                token = raw
        if not token:
            raise CellcomOTPError("LoginStep2 did not return a token")

        _LOGGER.debug("LoginStep2 succeeded, preliminary token received")
        return token

    async def async_login_step3(
        self, preliminary_jwt: str, id_number: str, phone: str
    ) -> Tokens:
        """Verify ID number, return full production token pair."""
        try:
            body = await self._request(
                "PUT",
                ENDPOINT_LOGIN_STEP3,
                json={
                    "Subscriber": phone,
                    "IdNumber": id_number,
                    "Scope": SCOPE,
                    "Code": "",
                    "OtpOrigin": OTP_ORIGIN,
                },
                bearer=preliminary_jwt,
            )
        except CellcomAPIError as err:
            raise CellcomIDError(f"ID number verification failed: {err}") from err

        extra = body.get("extra", body)
        token_det = extra.get("tokenDet", {})

        access = extra.get("accessToken") or token_det.get("access_token")
        refresh = extra.get("refreshToken") or token_det.get("refresh_token")
        expires_in = token_det.get("expires_in", 71552)

        if not access or not refresh:
            raise CellcomAuthError("LoginStep3 did not return tokens")

        now = int(time.time())
        tokens = Tokens(
            access_token=access,
            refresh_token=refresh,
            access_expires_at=now + expires_in,
            refresh_expires_at=now + 10800,  # Observed ~3 hours
            device_id=self._device_id,
            session_id=self._session_id,
        )
        _LOGGER.debug("LoginStep3 succeeded, tokens received (expires in %ss)", expires_in)
        return tokens

    # ── Data endpoints ─────────────────────────────────────────────────────────

    async def async_get_customer_init(self, access_token: str) -> dict[str, Any]:
        """Fetch the subscriber product list (identifies Energy BAN and subscriber).

        Uses GET /api/SelfCare/GetSelfcareDataOnboarding which returns
        Body.subscribersByProduct.Energy[].
        """
        return await self._request(
            "GET", ENDPOINT_ONBOARDING, bearer=access_token
        )

    async def async_get_invoice_data(self, access_token: str) -> dict[str, Any]:
        """Fetch the invoice list per BAN.

        Returns Body.invoices — an array of {banPsId, invoices[], billCycle, ...}.
        Used to extract the invoiceId needed by the Ibill endpoints.
        """
        return await self._request(
            "GET", ENDPOINT_INVOICE_DATA, bearer=access_token
        )

    async def async_get_all_invoices(
        self, access_token: str, invoice_id: str
    ) -> dict[str, Any]:
        """Fetch detailed billing info for an invoice.

        Returns Body.{dataInvoices, customerPerBan}.
        """
        return await self._request(
            "POST",
            ENDPOINT_ALL_INVOICES,
            json={"blockId": ENERGY_BLOCK_ID, "invoiceId": invoice_id, "ticketId": None},
            bearer=access_token,
        )

    async def async_get_full_main(
        self, access_token: str, invoice_id: str
    ) -> dict[str, Any]:
        """Fetch the monthly consumption history.

        Returns Body.{history, main, generalTab, ...}.
        """
        return await self._request(
            "POST",
            ENDPOINT_FULL_MAIN,
            json={"blockId": ENERGY_BLOCK_ID, "invoiceId": invoice_id, "ticketId": None},
            bearer=access_token,
        )

    async def async_get_all_products(
        self, access_token: str, invoice_id: str
    ) -> dict[str, Any]:
        """Fetch meter and tariff plan details.

        Returns Body.{allDetailsCliProduct}.
        """
        return await self._request(
            "POST",
            ENDPOINT_ALL_PRODUCTS,
            json={"blockId": ENERGY_BLOCK_ID, "invoiceId": invoice_id, "ticketId": None},
            bearer=access_token,
        )

    async def async_fetch_all(
        self, access_token: str, ban: str, subscriber: str
    ) -> CellcomData:
        """Fetch all data endpoints and return a CellcomData instance.

        Flow:
          1. GET InvoiceData  → extract invoice_id for this BAN
          2. In parallel: GetAllInvoicesAuth + GetFullMainAuth + GetAllProductsAuth
        """
        # Step 1: get the invoice list to find the current invoice_id.
        # Auth and connection errors are intentionally NOT caught here — they must
        # propagate to the coordinator so it can raise ConfigEntryAuthFailed /
        # UpdateFailed and surface the problem to the user in the HA UI.
        invoice_list_raw: dict[str, Any] = {}
        invoice_id = ""
        try:
            invoice_list_raw = await self.async_get_invoice_data(access_token)
            invoice_id = _extract_invoice_id(invoice_list_raw, ban)
        except (CellcomAuthError, CellcomConnectionError):
            raise  # Let coordinator decide how to handle auth/connection failures
        except Exception as err:
            _LOGGER.warning("Failed to fetch InvoiceData (non-auth): %s", err)

        if not invoice_id:
            _LOGGER.warning(
                "No invoice_id found for BAN %s — Ibill endpoints skipped "
                "(account may have no invoices yet)",
                ban,
            )
            return _parse_cellcom_data(
                ban=ban,
                subscriber=subscriber,
                invoice_list_raw=invoice_list_raw,
                invoices_raw={},
                history_raw={},
                products_raw={},
            )

        # Step 2: fetch remaining endpoints in parallel
        results = await asyncio.gather(
            self.async_get_all_invoices(access_token, invoice_id),
            self.async_get_full_main(access_token, invoice_id),
            self.async_get_all_products(access_token, invoice_id),
            return_exceptions=True,
        )

        invoices_raw, history_raw, products_raw = results

        for name, result in zip(["all_invoices", "full_main", "all_products"], results):
            if isinstance(result, Exception):
                _LOGGER.warning("Cellcom API partial failure on %s: %s", name, result)

        def _safe_dict(value: Any) -> dict:
            """Return value if it is a non-None dict, otherwise an empty dict."""
            return value if isinstance(value, dict) else {}

        return _parse_cellcom_data(
            ban=ban,
            subscriber=subscriber,
            invoice_list_raw=_safe_dict(invoice_list_raw),
            invoices_raw=_safe_dict(invoices_raw),
            history_raw=_safe_dict(history_raw),
            products_raw=_safe_dict(products_raw),
        )


# ── Response parsers ───────────────────────────────────────────────────────────

def _extract_invoice_id(invoice_list_raw: dict, ban: str) -> str:
    """Return the most recent invoice ID for *ban* from an InvoiceData response.

    InvoiceData Body.invoices is a list of {banPsId, invoices[], billCycle, ...}.
    The inner invoices[] items have an 'id' field (UUID) needed for Ibill calls.
    """
    outer = invoice_list_raw.get("invoices", [])
    # Prefer the entry whose banPsId matches the Energy BAN
    for entry in outer:
        if str(entry.get("banPsId", "")) == str(ban):
            inner = entry.get("invoices", [])
            if inner:
                return str(inner[0].get("id", ""))
    # Fallback: first entry with any invoice
    for entry in outer:
        inner = entry.get("invoices", [])
        if inner:
            return str(inner[0].get("id", ""))
    return ""


def _parse_cellcom_data(
    ban: str,
    subscriber: str,
    invoice_list_raw: dict,
    invoices_raw: dict,
    history_raw: dict,
    products_raw: dict,
) -> CellcomData:
    """Parse raw API responses into a CellcomData dataclass."""
    return CellcomData(
        ban=ban,
        subscriber_number=subscriber,
        current_invoice=_parse_current_invoice(ban, invoices_raw),
        billing_period=_parse_billing_period(invoices_raw, invoice_list_raw),
        meter=_parse_meter_info(ban, subscriber, products_raw),
        tariff_plan=_parse_tariff_plan(products_raw),
        customer=None,
        history=_parse_history(history_raw),
    )


def _parse_current_invoice(ban: str, raw: dict) -> Invoice | None:
    """Extract the most recent energy invoice."""
    invoices = raw.get("dataInvoices", [])
    energy_invoices = [i for i in invoices if i.get("isEnergy") and i.get("ban") == ban]
    if not energy_invoices:
        energy_invoices = [i for i in invoices if i.get("isEnergy")]
    if not energy_invoices:
        return None

    inv = energy_invoices[0]
    price_data = inv.get("invoivePrice", {})
    cycle = str(inv.get("cycle_date", ""))
    period_str = inv.get("fullCycleDate", "")
    parts = [p.strip() for p in period_str.split("-")] if "-" in period_str else []

    return Invoice(
        guid_id=inv.get("guidId", ""),
        ban=inv.get("ban", ban),
        cycle_date=inv.get("cycle_date", 0),
        full_cycle_date=period_str,
        period_start=_parse_date_ddmmyy(parts[1]) if len(parts) == 2 else "",
        period_end=_parse_date_ddmmyy(parts[0]) if len(parts) == 2 else "",
        amount=InvoiceAmount(
            price=float(price_data.get("price", 0) or 0),
            amount=int(price_data.get("amount", 0) or 0),
            amount_agorot=int(price_data.get("amountAgorot", 0) or 0),
            is_credit=bool(price_data.get("isCreditExists")),
        ),
        is_energy=True,
        services=inv.get("listServices", ["ENERGY"]),
        bill_url=f"https://cellcom.co.il/selfcare/InvoicePageNew?id={inv.get('guidId', '')}",
    )


def _parse_billing_period(
    invoices_raw: dict, invoice_list_raw: dict | None = None
) -> BillingPeriod | None:
    """Parse the current billing period summary.

    Primary source: GetAllInvoicesAuth response (invoices_raw) → customerPerBan.
    Fallback: InvoiceData response (invoice_list_raw) → billCycle + first invoice.
    """
    per_ban = invoices_raw.get("customerPerBan", {})
    if not per_ban:
        return None

    def safe_date(val: str) -> str:
        """Convert dd/mm/yyyy to ISO yyyy-mm-dd."""
        try:
            parts = val.strip().split("/")
            if len(parts) == 3:
                dd, mm, yyyy = parts
                return f"{yyyy}-{mm}-{dd}"
        except Exception:
            pass
        return val

    return BillingPeriod(
        total_sum=float(per_ban.get("totalSum", 0) or 0),
        period_start=safe_date(per_ban.get("periodStartDate", "")),
        period_end=safe_date(per_ban.get("periodEndDate", "")),
        bill_due_date=safe_date(per_ban.get("billDueDate", "")),
        invoice_number=per_ban.get("invoiceNo", ""),
        payment_type=per_ban.get("paymentType", ""),
        payment_type_desc=per_ban.get("paymentTypeDesc", ""),
        credit_card_type=per_ban.get("creditCardType", ""),
        credit_card_type_desc=per_ban.get("creditCardTypeDesc", ""),
        bill_method=(per_ban.get("billMethod") or "").strip(),
        bill_method_desc=per_ban.get("billMethodDesc", ""),
        email_bill_dest=per_ban.get("emailBillDest", ""),
    )


def _parse_history(raw: dict) -> list[MonthlyHistory]:
    """Parse the monthly consumption history list."""
    items = raw.get("history", [])
    result: list[MonthlyHistory] = []

    for item in items:
        kwh_details = item.get("kwhDetails", {})
        amount_data = item.get("amountData", {})
        cycle_date = item.get("cycleDate", 0)

        try:
            kwh = float(kwh_details.get("kwh", 0) or 0)
        except (ValueError, TypeError):
            kwh = 0.0

        try:
            amount = float(amount_data.get("price", 0) or 0)
        except (ValueError, TypeError):
            amount = None

        year = item.get("periodYear", "")
        cycle_month = item.get("cycleMonthName", "")
        cycle_date_iso = _parse_cycle_date(cycle_date)
        month_iso = cycle_date_iso[:7] if len(cycle_date_iso) >= 7 else ""

        result.append(
            MonthlyHistory(
                month=month_iso,
                cycle_date=cycle_date,
                bill_periods=item.get("billPeriods") or "",
                cycle_month_name=cycle_month,
                period_year=year,
                kwh=kwh,
                amount=amount,
                is_view_pdf=bool(item.get("isViewPdf")),
            )
        )

    return sorted(result, key=lambda h: h.cycle_date)


def _parse_meter_info(ban: str, subscriber: str, raw: dict) -> MeterInfo | None:
    """Parse meter and contract details from GetAllProductsAuth."""
    products = raw.get("allDetailsCliProduct", [])
    energy = next((p for p in products if p.get("detailsType") == "ENERGY"), None)
    if not energy:
        return None

    items = energy.get("allDalDetailsCli", [])
    if not items:
        return None

    item = items[0]
    return MeterInfo(
        meter_number=item.get("userPhone", item.get("titleDescription", "")),
        contract_number=item.get("subTitleDescription", ""),
        customer_address=item.get("address", ""),
        subscriber_number=subscriber,
        ban=ban,
        asset_external_id=item.get("assetExternalId", ""),
        product_id=item.get("productId", ""),
        product_status=item.get("productStatus", ""),
        product_status_desc=item.get("productStatusDesc", ""),
        product_type=item.get("productType", ""),
        is_business=bool(item.get("isBusinness") or item.get("isBusiness")),
        is_energy_bundle=bool(item.get("isEnergyBundle")),
        account_type=item.get("accountType", ""),
    )


def _parse_tariff_plan(raw: dict) -> TariffPlan | None:
    """Parse tariff plan and discount details from GetAllProductsAuth."""
    products = raw.get("allDetailsCliProduct", [])
    energy = next((p for p in products if p.get("detailsType") == "ENERGY"), None)
    if not energy:
        return None

    items = energy.get("allDalDetailsCli", [])
    if not items:
        return None

    item = items[0]

    # Extract plan details text (nested list of lists)
    plan_texts: list[str] = []
    for row in item.get("listPlanDtlText", []):
        if isinstance(row, list):
            plan_texts.extend(str(t) for t in row)
        else:
            plan_texts.append(str(row))
    plan_text = " ".join(plan_texts)

    # Extract comments
    comments: list[str] = []
    for row in item.get("listCommentText", []):
        if isinstance(row, list):
            comments.extend(str(t) for t in row)
        else:
            comments.append(str(row))

    # Try to parse discount details from plan text
    discount_percent = 0
    discount_hours_start = ""
    discount_hours_end = ""
    discount_days: list[str] = []

    import re
    if pct_match := re.search(r"(\d+)\s*אחוז", plan_text):
        discount_percent = int(pct_match.group(1))
    if hours_match := re.search(r"(\d{2}:\d{2})\s*עד\s*(\d{2}:\d{2})", plan_text):
        discount_hours_start = hours_match.group(1)
        discount_hours_end = hours_match.group(2)
    if "א' עד ה'" in plan_text or "ראשון עד חמישי" in plan_text:
        discount_days = ["Sun", "Mon", "Tue", "Wed", "Thu"]

    plan_details = item.get("listPlanDtlText", [[""]])
    plan_start = ""
    if plan_text:
        if date_match := re.search(r"(\d{2}\.\d{2}\.\d{4})", plan_text):
            raw_date = date_match.group(1)
            parts = raw_date.split(".")
            if len(parts) == 3:
                plan_start = f"{parts[2]}-{parts[1]}-{parts[0]}"

    # Plan name and code from subscriber data (not available here, use placeholder)
    plan_name = item.get("pricePlanDesc", "")
    plan_code = item.get("pricePlanCode", "")

    return TariffPlan(
        plan_code=plan_code,
        plan_description=plan_name,
        plan_start_date=plan_start,
        plan_details_text=plan_text,
        discount_percent=discount_percent,
        discount_days=discount_days,
        discount_hours_start=discount_hours_start,
        discount_hours_end=discount_hours_end,
        future_plan_code="",
        future_plan_desc="",
        comments=comments,
    )
