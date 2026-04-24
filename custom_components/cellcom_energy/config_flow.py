"""Config flow for Cellcom Energy integration."""

from __future__ import annotations

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
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .exceptions import (
    CellcomAuthError,
    CellcomConnectionError,
    CellcomIDError,
    CellcomOTPError,
)
from .models import Tokens

_LOGGER = logging.getLogger(__name__)

# Extra keys stored temporarily during the flow (not persisted to config entry)
_FLOW_GUID = "guid"
_FLOW_PHONE = "phone"
_FLOW_PRELIMINARY_JWT = "preliminary_jwt"
_FLOW_DEVICE_ID = "device_id"
_FLOW_SESSION_ID = "session_id"

STEP_PHONE_SCHEMA = vol.Schema(
    {vol.Required(CONF_PHONE): str}
)

STEP_OTP_SCHEMA = vol.Schema(
    {vol.Required("otp_code"): str}
)

STEP_ID_SCHEMA = vol.Schema(
    {vol.Required(CONF_ID_NUMBER): str}
)


class CellcomEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Cellcom Energy config flow (3-step OTP login)."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow with empty state."""
        self._phone: str = ""
        self._guid: str = ""
        self._preliminary_jwt: str = ""
        self._device_id: str = _generate_device_id()
        self._session_id: str = _generate_session_id()
        self._ban: str = ""
        self._subscriber: str = ""

    # ── Step 1: Phone number ──────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show the phone number form and send the OTP SMS."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input[CONF_PHONE].strip().replace("-", "").replace(" ", "")
            self._phone = phone

            client = CellcomEnergyClient(
                async_get_clientsession(self.hass),
                device_id=self._device_id,
                session_id=self._session_id,
            )

            try:
                self._guid = await client.async_login_step1(phone)
                return await self.async_step_otp()
            except CellcomConnectionError:
                errors["base"] = "cannot_connect"
            except CellcomAuthError:
                errors["base"] = "invalid_phone"
            except Exception:
                _LOGGER.exception("Unexpected error in LoginStep1")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_PHONE_SCHEMA,
            errors=errors,
            description_placeholders={},
        )

    # ── Step 2: OTP code ──────────────────────────────────────────────────────

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show the OTP form and verify the SMS code."""
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

    # ── Step 3: ID number ─────────────────────────────────────────────────────

    async def async_step_id_number(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show the ID number form and complete authentication."""
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

                # Fetch customer init to find the Energy BAN and subscriber number
                init_data = await client.async_get_customer_init(tokens.access_token)
                ban, subscriber = _extract_energy_subscriber(init_data)

                if not ban:
                    errors["base"] = "unknown"
                    return self.async_show_form(
                        step_id="id_number",
                        data_schema=STEP_ID_SCHEMA,
                        errors=errors,
                    )

                # Prevent duplicate entries for the same Energy account
                await self.async_set_unique_id(f"cellcom_energy_{ban}")
                self._abort_if_unique_id_configured()

                # Persist tokens to HA Storage
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
        """Handle re-authentication when the token has expired."""
        self._phone = entry_data.get(CONF_PHONE, "")
        self._device_id = entry_data.get("device_id", _generate_device_id())
        self._session_id = _generate_session_id()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Send a new OTP for re-authentication."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = CellcomEnergyClient(
                async_get_clientsession(self.hass),
                device_id=self._device_id,
                session_id=self._session_id,
            )
            try:
                self._guid = await client.async_login_step1(self._phone)
                return await self.async_step_reauth_otp()
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"phone": self._phone},
        )

    async def async_step_reauth_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Verify OTP during reauth."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = CellcomEnergyClient(
                async_get_clientsession(self.hass),
                device_id=self._device_id,
                session_id=self._session_id,
            )
            try:
                self._preliminary_jwt = await client.async_login_step2(
                    self._guid, user_input["otp_code"].strip(), self._phone
                )
                return await self.async_step_reauth_id()
            except CellcomOTPError:
                errors["base"] = "invalid_otp"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_otp",
            data_schema=STEP_OTP_SCHEMA,
            errors=errors,
            description_placeholders={"phone": self._phone},
        )

    async def async_step_reauth_id(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Verify ID number during reauth and update stored tokens."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entry = self._get_reauth_entry()
            client = CellcomEnergyClient(
                async_get_clientsession(self.hass),
                device_id=self._device_id,
                session_id=self._session_id,
            )
            try:
                tokens = await client.async_login_step3(
                    self._preliminary_jwt,
                    user_input[CONF_ID_NUMBER].strip(),
                    self._phone,
                )
                await _store_tokens(self.hass, tokens)
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, "session_id": self._session_id},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except CellcomIDError:
                errors["base"] = "invalid_id"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_id",
            data_schema=STEP_ID_SCHEMA,
            errors=errors,
        )

    def _get_reauth_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry being re-authenticated."""
        return self.hass.config_entries.async_get_entry(self.context["entry_id"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_energy_subscriber(init_data: dict) -> tuple[str, str]:
    """Extract the BAN and subscriber number for the Energy product."""
    subscribers_by_product = init_data.get("subscribersByProduct", {})
    energy_list = subscribers_by_product.get("Energy", [])

    if not energy_list:
        _LOGGER.warning("No Energy subscriber found in CustomerInit response")
        return "", ""

    # Prefer active subscribers
    active = [s for s in energy_list if s.get("productStatus") == "A"]
    subscriber = (active or energy_list)[0]

    ban = subscriber.get("ban", "")
    subscriber_no = subscriber.get("productSubscriberNo", "")
    _LOGGER.debug("Found Energy subscriber: BAN=%s, Subscriber=%s", ban, subscriber_no)
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
