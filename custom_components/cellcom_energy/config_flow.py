"""Config flow for Cellcom Energy integration."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CellcomEnergyClient, _generate_device_id, _generate_session_id
from .const import (
    CONF_ID_NUMBER,
    CONF_PHONE,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .exceptions import (
    CellcomConnectionError,
    CellcomIDError,
    CellcomOTPError,
)
from .models import Tokens

_LOGGER = logging.getLogger(__name__)

# reCAPTCHA site key for cellcom.co.il (public, embedded in their JS bundle)
_RECAPTCHA_SITE_KEY = "6Lfdn98UAAAAAP0Hryf898rV70y6TuwWgJEV7ytW"
_RECAPTCHA_ACTION = "OtpVerifyPhonePage"
_CLIENT_ID = "984193a2-8d29-11ea-bc55-0242ac130004"

STEP_PHONE_SCHEMA = vol.Schema({vol.Required(CONF_PHONE): str})
STEP_GUID_SCHEMA = vol.Schema({vol.Required("guid"): str})
STEP_OTP_SCHEMA = vol.Schema({vol.Required("otp_code"): str})
STEP_ID_SCHEMA = vol.Schema({vol.Required(CONF_ID_NUMBER): str})


def _make_console_snippet(phone: str) -> str:
    """Build the JavaScript one-liner to paste in the browser console on cellcom.co.il.

    When executed on cellcom.co.il the snippet:
      1. Calls grecaptcha.execute() — works because the page already has the
         reCAPTCHA script loaded for the correct domain.
      2. POSTs to LoginStep1 with the valid token.
      3. Shows the returned GUID in a prompt() so the user can copy it.
    """
    dev = _generate_device_id()
    sess = _generate_session_id()
    tid = uuid.uuid4().hex.upper()

    # Single-line JS (no line breaks — must be pasteable as one line in console)
    return (
        "(async()=>{"
        f"const ph='{phone}';"
        "try{"
        "const t=await new Promise((res,rej)=>{"
        "if(typeof grecaptcha==='undefined'){{rej(new Error('reCAPTCHA not loaded. Make sure you are on cellcom.co.il.'));return;}}"
        f"grecaptcha.ready(()=>grecaptcha.execute('{_RECAPTCHA_SITE_KEY}',{{action:'{_RECAPTCHA_ACTION}'}}).then(res).catch(rej));"
        "});"
        "const r=await fetch('https://digital-api.cellcom.co.il/api/otp/LoginStep1',{method:'PUT',"
        f"headers:{{'Content-Type':'application/json','ClientID':'{_CLIENT_ID}',"
        f"'DeviceId':'{dev}','SessionID':'{sess}',"
        "'Origin':'https://cellcom.co.il','Referer':'https://cellcom.co.il/',"
        f"'x-cell-recaptcha-token':t,'x-cell-tracking-id':'{tid}'}},"
        "body:JSON.stringify({Subscriber:ph,IsExtended:false,ProcessType:'',OtpOrigin:'main OTP'})});"
        "const d=await r.json();"
        "if(d.Header.ReturnCode!==0){alert('Error: '+d.Header.ReturnCodeMessage);return;}"
        "const g=d.Body.message||d.Body.Guid;"
        "prompt('Copy this GUID and paste it in Home Assistant:',g);"
        "}catch(e){alert('Error: '+e.message);}"
        "})()"
    )


class CellcomEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Cellcom Energy config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow with empty state."""
        self._phone: str = ""
        self._guid: str = ""
        self._preliminary_jwt: str = ""
        self._device_id: str = _generate_device_id()
        self._session_id: str = _generate_session_id()

    # ── Step 1: Phone number ──────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Ask for the phone number."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input[CONF_PHONE].strip().replace("-", "").replace(" ", "")
            if not phone.startswith("0") or not phone.isdigit() or len(phone) != 10:
                errors[CONF_PHONE] = "invalid_phone"
            else:
                self._phone = phone
                return await self.async_step_browser_login()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_PHONE_SCHEMA,
            errors=errors,
            description_placeholders={},
        )

    # ── Step 2: Browser login instructions ───────────────────────────────────

    async def async_step_browser_login(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show instructions + console snippet → ask user to paste the GUID.

        The snippet must run in the browser console on cellcom.co.il so that
        reCAPTCHA executes on the correct domain.  After running the snippet the
        user sees a prompt() dialog with the GUID; they paste it here.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            guid = user_input["guid"].strip()
            if len(guid) < 8:
                errors["guid"] = "invalid_guid"
            else:
                self._guid = guid
                _LOGGER.debug("GUID accepted: %s…", guid[:8])
                return await self.async_step_otp()

        snippet = _make_console_snippet(self._phone)

        return self.async_show_form(
            step_id="browser_login",
            data_schema=STEP_GUID_SCHEMA,
            errors=errors,
            description_placeholders={
                "phone": self._phone,
                "snippet": snippet,
            },
        )

    # ── Step 3: OTP code ──────────────────────────────────────────────────────

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Verify the OTP code sent via SMS."""
        errors: dict[str, str] = {}

        if user_input is not None:
            otp_code = user_input["otp_code"].strip()
            client = CellcomEnergyClient(
                async_get_clientsession(self.hass),
                device_id=self._device_id,
                session_id=self._session_id,
            )
            try:
                self._preliminary_jwt = await client.async_login_step2(
                    self._guid, otp_code, self._phone
                )
                return await self.async_step_id_number()
            except CellcomOTPError:
                errors["base"] = "invalid_otp"
            except CellcomConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error in LoginStep2")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="otp",
            data_schema=STEP_OTP_SCHEMA,
            errors=errors,
            description_placeholders={"phone": self._phone},
        )

    # ── Step 4: ID number ─────────────────────────────────────────────────────

    async def async_step_id_number(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Complete authentication with the ID number."""
        errors: dict[str, str] = {}

        if user_input is not None:
            id_number = user_input[CONF_ID_NUMBER].strip()
            client = CellcomEnergyClient(
                async_get_clientsession(self.hass),
                device_id=self._device_id,
                session_id=self._session_id,
            )
            try:
                tokens = await client.async_login_step3(
                    self._preliminary_jwt, id_number, self._phone
                )
                init_data = await client.async_get_customer_init(tokens.access_token)
                ban, subscriber = _extract_energy_subscriber(init_data)

                if not ban:
                    errors["base"] = "no_energy_account"
                    return self.async_show_form(
                        step_id="id_number",
                        data_schema=STEP_ID_SCHEMA,
                        errors=errors,
                    )

                await self.async_set_unique_id(f"cellcom_energy_{ban}")
                self._abort_if_unique_id_configured()
                await _store_tokens(self.hass, tokens)

                return self.async_create_entry(
                    title=f"Cellcom Energy ({ban})",
                    data={
                        CONF_PHONE: self._phone,
                        CONF_ID_NUMBER: id_number,
                        "ban": ban,
                        "subscriber": subscriber,
                        "device_id": self._device_id,
                        "session_id": self._session_id,
                    },
                )
            except CellcomIDError:
                errors["base"] = "invalid_id"
            except CellcomConnectionError:
                errors["base"] = "cannot_connect"
            except config_entries.data_entry_flow.AbortFlow:
                return self.async_abort(reason="already_configured")
            except Exception:
                _LOGGER.exception("Unexpected error in LoginStep3")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="id_number",
            data_schema=STEP_ID_SCHEMA,
            errors=errors,
        )

    # ── Reauth flow ───────────────────────────────────────────────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.FlowResult:
        """Handle re-authentication when tokens have expired."""
        self._phone = entry_data.get(CONF_PHONE, "")
        self._device_id = entry_data.get("device_id", _generate_device_id())
        self._session_id = _generate_session_id()
        return await self.async_step_browser_login()

    def _get_reauth_entry(self) -> config_entries.ConfigEntry:
        return self.hass.config_entries.async_get_entry(self.context["entry_id"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_energy_subscriber(init_data: dict) -> tuple[str, str]:
    """Extract BAN and subscriber number for the Energy product."""
    subscribers_by_product = init_data.get("subscribersByProduct", {})
    energy_list = subscribers_by_product.get("Energy", [])

    if not energy_list:
        _LOGGER.warning("No Energy subscriber found in CustomerInit response")
        return "", ""

    active = [s for s in energy_list if s.get("productStatus") == "A"]
    subscriber = (active or energy_list)[0]
    ban = subscriber.get("ban", "")
    subscriber_no = subscriber.get("productSubscriberNo", "")
    _LOGGER.debug("Found Energy subscriber: BAN=%s, sub=%s", ban, subscriber_no)
    return ban, subscriber_no


async def _store_tokens(hass: HomeAssistant, tokens: Tokens) -> None:
    """Persist tokens to HA's encrypted Storage."""
    from homeassistant.helpers.storage import Store

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    await store.async_save(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "access_expires_at": tokens.access_expires_at,
            "refresh_expires_at": tokens.refresh_expires_at,
            "device_id": tokens.device_id,
            "session_id": tokens.session_id,
        }
    )
    _LOGGER.debug("Tokens persisted to storage")
