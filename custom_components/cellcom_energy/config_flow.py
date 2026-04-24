"""Config flow for Cellcom Energy integration."""

from __future__ import annotations

import base64
import json
import logging
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
from .exceptions import CellcomConnectionError
from .models import Tokens

_LOGGER = logging.getLogger(__name__)

# Cellcom login page URL — the REAL page where reCAPTCHA is loaded correctly.
CELLCOM_LOGIN_URL = "https://cellcom.co.il/Authentication/otp-login-page/"

# ── Snippet A: paste BEFORE logging in ───────────────────────────────────────
# Intercepts BOTH fetch AND XMLHttpRequest (axios uses XHR in browsers).
# When LoginStep3 response arrives the tokens are shown in a prompt().
_INTERCEPT_SNIPPET = (
    "(function(){"
    # Patch fetch
    "var _f=window.fetch;"
    "window.fetch=async function(){var r=await _f.apply(this,arguments);"
    "if((arguments[0]||'').includes('LoginStep3')){"
    "r.clone().json().then(function(d){"
    "var ex=(d.Body||{}).extra||{};"
    "if(ex.accessToken)prompt('Copy ALL and paste in Home Assistant:',"
    "JSON.stringify({accessToken:ex.accessToken,refreshToken:ex.refreshToken}));"
    "});}"
    "return r;};"
    # Patch XMLHttpRequest (axios default transport in browsers)
    "var _op=XMLHttpRequest.prototype.open,_sn=XMLHttpRequest.prototype.send;"
    "XMLHttpRequest.prototype.open=function(m,u){"
    "this._cUrl=u||'';return _op.apply(this,arguments);};"
    "XMLHttpRequest.prototype.send=function(){"
    "if(this._cUrl.includes('LoginStep3')){"
    "this.addEventListener('load',function(){"
    "try{var d=JSON.parse(this.responseText);"
    "var ex=(d.Body||{}).extra||{};"
    "if(ex.accessToken)prompt('Copy ALL and paste in Home Assistant:',"
    "JSON.stringify({accessToken:ex.accessToken,refreshToken:ex.refreshToken}));}"
    "catch(e){}});}"
    "return _sn.apply(this,arguments);};"
    "console.log('%c[Cellcom Energy] Interceptor active (XHR+fetch) — now log in normally.',"
    "'color:#5c8ee6;font-weight:bold;font-size:14px');"
    "})()"
)

# ── Snippet B: paste when ALREADY logged in ───────────────────────────────────
# Tries multiple strategies to locate the JWT in localStorage:
#   1. Direct keys: accessToken, auth_token (plain or unescape-decoded JSON)
#   2. refresh_token as fallback (accepted by the integration)
#   3. Full scan of all storage entries
_EXTRACT_SNIPPET = (
    "(function(){"
    # Helper: extract JWT from a raw localStorage value (plain, JSON, or unescape-encoded)
    "function extractJwt(raw){"
    "if(!raw)return '';"
    "if(raw.startsWith('eyJ'))return raw;"          # plain JWT
    "try{var o=JSON.parse(raw);"                    # JSON object
    "return o.access_token||o.accessToken||o.token||'';}"
    "catch(e){}"
    "try{var d=unescape(raw);"                      # unescape-encoded
    "if(d.startsWith('eyJ'))return d;"
    "var o2=JSON.parse(d);return o2.access_token||o2.accessToken||o2.token||'';}"
    "catch(e2){}"
    "return '';}"
    # Try well-known keys
    "var at=extractJwt(localStorage.getItem('accessToken'))"
    "||extractJwt(localStorage.getItem('auth_token'))"
    "||extractJwt(localStorage.getItem('refresh_token'));"   # refresh token as fallback
    # Full scan if still not found
    "if(!at){"
    "[localStorage,sessionStorage].forEach(function(s){"
    "for(var i=0;i<s.length;i++){var j=extractJwt(s.getItem(s.key(i)));if(j&&!at)at=j;}"
    "});}"
    "if(!at){alert('Token not found. Keys: '+Object.keys(localStorage).join(', '));return;}"
    # Copy to clipboard
    "if(navigator.clipboard&&navigator.clipboard.writeText){"
    "navigator.clipboard.writeText(at).then(function(){"
    "alert('[Cellcom Energy] Token copied! Paste in HA.');});}"
    "else if(typeof copy==='function'){copy(at);alert('[Cellcom Energy] Token copied! Paste in HA.');}"
    "else{prompt('Copy and paste in Home Assistant:',at);}"
    "})()"
)

STEP_TOKEN_SCHEMA = vol.Schema({vol.Required("tokens_json"): str})
STEP_ID_SCHEMA = vol.Schema({vol.Required(CONF_ID_NUMBER): str})


class CellcomEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Cellcom Energy config flow.

    Login flow (one-time setup):
      Step 1 (user)  : Show interceptor snippet + instructions.
                       User pastes snippet in browser console, logs in on
                       cellcom.co.il, then pastes the resulting JSON here.
      Step 2 (tokens): Validate the pasted JSON, call CustomerInit, create entry.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._device_id: str = _generate_device_id()
        self._session_id: str = _generate_session_id()
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._client_id: str = ""

    # ── Step 1: Instructions + token paste ────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show the interceptor snippet and accept the pasted tokens JSON."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw = user_input.get("tokens_json", "").strip()
            parsed = _parse_tokens_json(raw)
            if parsed is None:
                errors["tokens_json"] = "invalid_tokens_json"
            else:
                self._access_token, self._refresh_token, self._client_id = parsed
                return await self._async_validate_and_create()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
        )

    # ── Validate tokens and create entry ─────────────────────────────────────

    async def _async_validate_and_create(self) -> config_entries.FlowResult:
        """Call CustomerInit to validate the token and extract account details."""
        client = CellcomEnergyClient(
            async_get_clientsession(self.hass),
            device_id=self._device_id,
            session_id=self._session_id,
            client_id=self._client_id or None,
        )
        try:
            init_data = await client.async_get_customer_init(self._access_token)
        except CellcomConnectionError:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_TOKEN_SCHEMA,
                errors={"base": "cannot_connect"},
            )
        except Exception:
            _LOGGER.exception("CustomerInit failed during token validation")
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_TOKEN_SCHEMA,
                errors={"base": "invalid_tokens_json"},
            )

        ban, subscriber, phone = _extract_energy_info(init_data)
        if not ban:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_TOKEN_SCHEMA,
                errors={"base": "no_energy_account"},
            )

        await self.async_set_unique_id(f"cellcom_energy_{ban}")
        self._abort_if_unique_id_configured()

        # Extract real expiry from the JWT so the coordinator does not
        # immediately think the token is expired and trigger a refresh.
        access_exp = _extract_jwt_expiry(self._access_token)
        refresh_exp = _extract_jwt_expiry(self._refresh_token) if self._refresh_token else 0

        # Persist tokens to HA Storage
        tokens = Tokens(
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            access_expires_at=access_exp,
            refresh_expires_at=refresh_exp,
            device_id=self._device_id,
            session_id=self._session_id,
        )
        await _store_tokens(self.hass, tokens)

        return self.async_create_entry(
            title=f"Cellcom Energy ({ban})",
            data={
                CONF_PHONE: phone,
                "ban": ban,
                "subscriber": subscriber,
                "device_id": self._device_id,
                "session_id": self._session_id,
                "client_id": self._client_id,
            },
        )

    # ── Reauth flow ───────────────────────────────────────────────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.FlowResult:
        """Handle re-authentication (same flow — paste fresh tokens)."""
        self._device_id = entry_data.get("device_id", _generate_device_id())
        self._session_id = _generate_session_id()
        return await self.async_step_user()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_tokens_json(raw: str) -> tuple[str, str, str] | None:
    """Parse tokens from user input.

    Accepts:
      - {"accessToken": "eyJ...", "refreshToken": "eyJ..."}  — full JSON
      - Plain JWT string starting with "eyJ"                 — used as access token
      - unescape()-encoded JSON containing access_token key  — decoded automatically

    Returns (access_token, refresh_token, client_id).
    client_id is extracted from the JWT payload claim CLIENT_ID.
    refresh_token and client_id may be empty strings.
    """
    raw = raw.strip().strip('"')

    # Plain JWT pasted directly
    if raw.startswith("eyJ") and "." in raw:
        return raw, "", _extract_client_id_from_jwt(raw)

    # JSON object
    try:
        data = json.loads(raw)
        at = data.get("accessToken") or data.get("access_token") or ""
        rt = data.get("refreshToken") or data.get("refresh_token") or ""
        if at.startswith("eyJ"):
            return at, rt, _extract_client_id_from_jwt(at)
    except (json.JSONDecodeError, AttributeError):
        pass

    # unescape()-encoded value (Cellcom stores auth_token this way)
    try:
        decoded = raw.encode("utf-8").decode("unicode_escape")
        data2 = json.loads(decoded)
        at2 = data2.get("access_token") or data2.get("accessToken") or ""
        rt2 = data2.get("refresh_token") or data2.get("refreshToken") or ""
        if at2.startswith("eyJ"):
            return at2, rt2, _extract_client_id_from_jwt(at2)
    except Exception:
        pass

    return None


def _extract_client_id_from_jwt(token: str) -> str:
    """Decode the JWT payload and return the CLIENT_ID claim (no signature check)."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return ""
        payload_b64 = parts[1] + "=="
        payload = json.loads(base64.b64decode(payload_b64))
        return payload.get("CLIENT_ID") or payload.get("client_id") or ""
    except Exception:
        return ""


def _extract_jwt_expiry(token: str) -> int:
    """Return the 'exp' claim from a JWT as a Unix timestamp (0 if missing/invalid)."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return 0
        payload_b64 = parts[1] + "=="
        payload = json.loads(base64.b64decode(payload_b64))
        return int(payload.get("exp", 0))
    except Exception:
        return 0


def _extract_energy_info(init_data: dict) -> tuple[str, str, str]:
    """Return (ban, subscriber_no, phone) for the Energy product."""
    subscribers_by_product = init_data.get("subscribersByProduct", {})
    energy_list = subscribers_by_product.get("Energy", [])

    if not energy_list:
        _LOGGER.warning("No Energy subscriber found in CustomerInit response")
        return "", "", ""

    active = [s for s in energy_list if s.get("productStatus") == "A"]
    subscriber = (active or energy_list)[0]

    ban = subscriber.get("ban", "")
    subscriber_no = subscriber.get("productSubscriberNo", "")
    phone = subscriber.get("contactNumber", "") or subscriber.get("msisdn", "")
    _LOGGER.debug("Energy subscriber: BAN=%s sub=%s phone=%s", ban, subscriber_no, phone)
    return ban, subscriber_no, phone


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
