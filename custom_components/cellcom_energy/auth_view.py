"""HTTP view that serves the reCAPTCHA login page for the config flow.

HA registers this endpoint at /api/cellcom_energy/auth.
The user's browser opens the page, executes real reCAPTCHA, submits the phone
number, and this view calls LoginStep1 server-side and then resumes the
config-flow with the GUID it received.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

import aiohttp
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CellcomEnergyClient
from .exceptions import CellcomConnectionError, CellcomAuthError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

RECAPTCHA_SITE_KEY = "6Lfdn98UAAAAAP0Hryf898rV70y6TuwWgJEV7ytW"


class CellcomAuthView(HomeAssistantView):
    """Serve a real-browser reCAPTCHA page and drive LoginStep1."""

    url = "/api/cellcom_energy/auth"
    name = "api:cellcom_energy:auth"
    requires_auth = False  # Must be accessible without HA login token.

    def __init__(self, hass: HomeAssistant) -> None:
        """Store a reference to hass for later use."""
        self.hass = hass

    async def get(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Return the login HTML page with embedded reCAPTCHA."""
        flow_id = request.query.get("flow_id", "")
        html = _build_login_page(flow_id)
        return aiohttp.web.Response(
            text=html,
            content_type="text/html",
            charset="utf-8",
        )

    async def post(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        """Receive phone + reCAPTCHA token, call LoginStep1, resume flow."""
        try:
            data = await request.post()
        except Exception:
            return _error_response("Could not parse form data.")

        flow_id = data.get("flow_id", "")
        phone = str(data.get("phone", "")).strip().replace("-", "").replace(" ", "")
        recaptcha_token = str(data.get("g-recaptcha-response", "")).strip()

        if not phone or not recaptcha_token:
            return _error_response("Phone number and reCAPTCHA are required.")

        _LOGGER.debug("Auth view: LoginStep1 for phone=%s flow_id=%s", phone, flow_id)

        try:
            client = CellcomEnergyClient(
                async_get_clientsession(self.hass),
                recaptcha_token=recaptcha_token,
            )
            guid = await client.async_login_step1(phone)
        except CellcomConnectionError as err:
            _LOGGER.warning("Auth view: connection error: %s", err)
            return _error_response(f"Cannot reach Cellcom servers: {err}")
        except CellcomAuthError as err:
            _LOGGER.warning("Auth view: auth error: %s", err)
            return _error_response(f"Login failed: {err}")
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Auth view: unexpected error")
            return _error_response(f"Unexpected error: {err}")

        # Resume the config flow with phone + guid.
        # This triggers async_step_user_confirm (via async_external_step_done).
        try:
            result = await self.hass.config_entries.flow.async_configure(
                flow_id,
                user_input={"phone": phone, "guid": guid},
            )
            _LOGGER.debug("Flow %s resumed, result type: %s", flow_id, result.get("type"))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Auth view: failed to resume flow %s", flow_id)
            return _error_response("Internal error resuming the setup flow.")

        # Return a self-closing page — HA UI picks up the flow automatically.
        return aiohttp.web.Response(
            text=_build_success_page(),
            content_type="text/html",
            charset="utf-8",
        )


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _build_login_page(flow_id: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cellcom Energy — Login</title>
  <script src="https://www.google.com/recaptcha/api.js" async defer></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #1c1c2e; color: #e0e0e0;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; margin: 0;
    }}
    .card {{
      background: #2a2a40; border-radius: 16px; padding: 2.5rem;
      width: 100%; max-width: 420px; box-shadow: 0 8px 32px rgba(0,0,0,.4);
    }}
    h1 {{ font-size: 1.4rem; margin: 0 0 1.5rem; color: #fff; }}
    label {{ display: block; margin-bottom: .4rem; font-size: .9rem; color: #aaa; }}
    input {{
      width: 100%; padding: .75rem 1rem; border: 1px solid #444;
      border-radius: 8px; background: #1c1c2e; color: #fff;
      font-size: 1rem; margin-bottom: 1.5rem;
    }}
    input:focus {{ outline: none; border-color: #5c8ee6; }}
    button {{
      width: 100%; padding: .85rem; background: #5c8ee6;
      color: #fff; border: none; border-radius: 8px;
      font-size: 1rem; cursor: pointer; font-weight: 600;
    }}
    button:hover {{ background: #4a7bcf; }}
    .hint {{ margin-top: 1rem; font-size: .8rem; color: #888; text-align: center; }}
    .error {{ color: #f87171; font-size: .85rem; margin-top: 1rem; }}
  </style>
</head>
<body>
<div class="card">
  <h1>&#x26A1; Cellcom Energy</h1>
  <form method="POST" action="/api/cellcom_energy/auth">
    <input type="hidden" name="flow_id" value="{flow_id}">
    <label for="phone">Phone number</label>
    <input
      id="phone" name="phone" type="tel"
      placeholder="050-1234567" required autofocus
      pattern="0[0-9]{{9}}"
    >
    <div
      class="g-recaptcha"
      data-sitekey="{RECAPTCHA_SITE_KEY}"
      data-size="invisible"
      data-callback="onRecaptchaSuccess"
    ></div>
    <button type="button" onclick="submitForm()">Send verification code</button>
    <p class="hint">You will receive an SMS with a one-time code.</p>
  </form>
</div>
<script>
function submitForm() {{
  var phone = document.getElementById("phone").value.trim().replace(/-/g, "");
  if (!phone.match(/^0\\d{{9}}$/)) {{
    alert("Please enter a valid Israeli mobile number (e.g. 0501234567)");
    return;
  }}
  grecaptcha.execute("{RECAPTCHA_SITE_KEY}", {{action: "OtpVerifyPhonePage"}})
    .then(function(token) {{
      var form = document.querySelector("form");
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "g-recaptcha-response";
      input.value = token;
      form.appendChild(input);
      form.submit();
    }});
}}
</script>
</body>
</html>"""


def _build_success_page() -> str:
    return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Cellcom Energy</title>
  <style>
    body {
      font-family: sans-serif; background: #1c1c2e; color: #e0e0e0;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; margin: 0; text-align: center;
    }
    .card { background: #2a2a40; border-radius: 16px; padding: 2.5rem; max-width: 380px; }
    h1 { color: #4ade80; font-size: 2rem; }
    p { color: #aaa; }
  </style>
</head>
<body>
<div class="card">
  <h1>&#10003;</h1>
  <p>SMS sent! Return to Home Assistant and enter the verification code.</p>
  <p style="font-size:.8rem;color:#666;margin-top:1.5rem">You can close this window.</p>
</div>
</body>
</html>"""


def _error_response(message: str) -> aiohttp.web.Response:
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Error</title>
<style>body{{font-family:sans-serif;background:#1c1c2e;color:#e0e0e0;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center}}
.card{{background:#2a2a40;border-radius:16px;padding:2.5rem;max-width:380px}}
h1{{color:#f87171}}a{{color:#5c8ee6}}</style></head>
<body><div class="card">
<h1>Error</h1><p>{message}</p>
<p><a href="javascript:history.back()">Go back</a></p>
</div></body></html>"""
    return aiohttp.web.Response(
        text=html,
        content_type="text/html",
        charset="utf-8",
        status=HTTPStatus.BAD_REQUEST,
    )
