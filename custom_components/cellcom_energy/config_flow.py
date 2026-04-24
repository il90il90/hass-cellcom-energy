"""Config flow for Cellcom Energy integration."""

from __future__ import annotations

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
# Checks direct keys first (accessToken, auth_token), then scans all storage
# entries for any JWT-containing JSON object.
_EXTRACT_SNIPPET = (
    "(function(){"
    # Try well-known direct keys first
    "var at=localStorage.getItem('accessToken')||localStorage.getItem('auth_token')||'';"
    "var rt=localStorage.getItem('refreshToken')||localStorage.getItem('refresh_token')||'';"
    # If not found as direct string, scan all storage for JSON objects
    "if(!at.includes('eyJ')){"
    "[localStorage,sessionStorage].forEach(function(s){"
    "for(var i=0;i<s.length;i++){"
    "var raw=s.getItem(s.key(i))||'';"
    "if(!raw.includes('eyJ'))continue;"
    "try{var o=JSON.parse(raw);"
    "if(o&&o.accessToken){at=o.accessToken;rt=o.refreshToken||rt;}"
    "}catch(e){}"
    "}"
    "});}"
    "if(at&&at.includes('eyJ')){"
    "prompt('Copy ALL and paste in Home Assistant:',JSON.stringify({accessToken:at,refreshToken:rt}));}"
    "else alert('Tokens not found.\\nKeys: '+Object.keys(localStorage).join(', '));"
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
                access_token, refresh_token = parsed
                if not access_token.startswith("eyJ"):
                    errors["tokens_json"] = "invalid_tokens_json"
                else:
                    self._access_token = access_token
                    self._refresh_token = refresh_token
                    return await self._async_validate_and_create()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={
                "snippet": _INTERCEPT_SNIPPET,
                "extract_snippet": _EXTRACT_SNIPPET,
            },
        )

    # ── Validate tokens and create entry ─────────────────────────────────────

    async def _async_validate_and_create(self) -> config_entries.FlowResult:
        """Call CustomerInit to validate the token and extract account details."""
        client = CellcomEnergyClient(
            async_get_clientsession(self.hass),
            device_id=self._device_id,
            session_id=self._session_id,
        )
        try:
            init_data = await client.async_get_customer_init(self._access_token)
        except CellcomConnectionError:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_TOKEN_SCHEMA,
                errors={"base": "cannot_connect"},
                description_placeholders={"snippet": _INTERCEPT_SNIPPET},
            )
        except Exception:
            _LOGGER.exception("CustomerInit failed during token validation")
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_TOKEN_SCHEMA,
                errors={"base": "invalid_tokens_json"},
                description_placeholders={"snippet": _INTERCEPT_SNIPPET},
            )

        ban, subscriber, phone = _extract_energy_info(init_data)
        if not ban:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_TOKEN_SCHEMA,
                errors={"base": "no_energy_account"},
                description_placeholders={"snippet": _INTERCEPT_SNIPPET},
            )

        await self.async_set_unique_id(f"cellcom_energy_{ban}")
        self._abort_if_unique_id_configured()

        # Persist tokens to HA Storage
        tokens = Tokens(
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            access_expires_at=0,   # Will be refreshed on first coordinator run
            refresh_expires_at=0,
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

def _parse_tokens_json(raw: str) -> tuple[str, str] | None:
    """Parse {"accessToken": "...", "refreshToken": "..."} from user input."""
    try:
        data = json.loads(raw)
        at = data.get("accessToken") or data.get("access_token") or ""
        rt = data.get("refreshToken") or data.get("refresh_token") or ""
        if at and rt:
            return at, rt
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


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
