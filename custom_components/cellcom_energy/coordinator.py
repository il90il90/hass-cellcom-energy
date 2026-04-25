"""DataUpdateCoordinator for Cellcom Energy."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CellcomEnergyClient
from .const import (
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    TOKEN_REFRESH_THRESHOLD_SECONDS,
)
from .exceptions import (
    CellcomAuthError,
    CellcomConnectionError,
    CellcomTokenExpiredError,
)
from .models import CellcomData, Tokens

_LOGGER = logging.getLogger(__name__)


class CellcomEnergyCoordinator(DataUpdateCoordinator[CellcomData]):
    """Fetch Cellcom Energy data on a schedule and manage token refresh."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Set up the coordinator."""
        scan_interval = entry.options.get(
            "scan_interval", DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )
        self._entry = entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._tokens: Tokens | None = None
        self._api_calls_today: int = 0

    # ── Public properties ──────────────────────────────────────────────────────

    @property
    def ban(self) -> str:
        """Return the billing account number."""
        return self._entry.data.get("ban", "")

    @property
    def subscriber(self) -> str:
        """Return the subscriber number."""
        return self._entry.data.get("subscriber", "")

    @property
    def tokens(self) -> Tokens | None:
        """Return the current token pair."""
        return self._tokens

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _make_client(self) -> CellcomEnergyClient:
        """Create an API client using the persisted device/session/client IDs."""
        return CellcomEnergyClient(
            async_get_clientsession(self.hass),
            device_id=self._entry.data.get("device_id"),
            session_id=self._entry.data.get("session_id"),
            client_id=self._entry.data.get("client_id") or None,
        )

    async def _async_load_tokens(self) -> Tokens | None:
        """Load tokens from HA Storage."""
        data = await self._store.async_load()
        if not data:
            return None
        return Tokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            access_expires_at=data["access_expires_at"],
            refresh_expires_at=data["refresh_expires_at"],
            device_id=data.get("device_id", ""),
            session_id=data.get("session_id", ""),
        )

    async def _async_save_tokens(self, tokens: Tokens) -> None:
        """Persist tokens to HA Storage."""
        await self._store.async_save(
            {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "access_expires_at": tokens.access_expires_at,
                "refresh_expires_at": tokens.refresh_expires_at,
                "device_id": tokens.device_id,
                "session_id": tokens.session_id,
            }
        )

    def _is_access_token_expiring(self, tokens: Tokens) -> bool:
        """Return True if the access token expires within the refresh threshold.

        Returns False if access_expires_at is 0 (unknown expiry — trust the token).
        """
        if tokens.access_expires_at == 0:
            return False
        remaining = tokens.access_expires_at - int(time.time())
        return remaining < TOKEN_REFRESH_THRESHOLD_SECONDS

    def _is_refresh_token_valid(self, tokens: Tokens) -> bool:
        """Return True if the refresh token has not yet expired.

        Returns True if refresh_expires_at is 0 (unknown — assume still valid).
        """
        if tokens.refresh_expires_at == 0:
            return True
        return tokens.refresh_expires_at > int(time.time())

    # ── Core update logic ──────────────────────────────────────────────────────

    async def _async_update_data(self) -> CellcomData:
        """Fetch fresh data. Called by DataUpdateCoordinator on each interval."""
        # Load tokens from storage on first run
        if self._tokens is None:
            self._tokens = await self._async_load_tokens()

        if self._tokens is None:
            raise ConfigEntryAuthFailed("No tokens found, re-authentication required")

        # Fail fast if the access token is already fully expired.
        # This avoids a pointless API call that would return 401 anyway.
        now = int(time.time())
        if self._tokens.access_expires_at != 0 and self._tokens.access_expires_at < now:
            _LOGGER.warning(
                "Access token expired %ss ago — triggering re-authentication",
                now - self._tokens.access_expires_at,
            )
            self._tokens = None
            raise ConfigEntryAuthFailed(
                "Access token has expired, please re-authenticate via the integration page"
            )

        # Proactively refresh the access token if it's about to expire
        if self._is_access_token_expiring(self._tokens):
            _LOGGER.debug("Access token expiring soon, refreshing")
            await self._async_refresh_access_token()

        # Fetch all data
        client = self._make_client()
        try:
            data = await client.async_fetch_all(
                self._tokens.access_token, self.ban, self.subscriber
            )
            self._api_calls_today += 5
            return data

        except CellcomAuthError as err:
            _LOGGER.warning("Auth error during data fetch: %s", err)
            raise ConfigEntryAuthFailed(
                f"Authentication failed, re-authentication required: {err}"
            ) from err

        except CellcomConnectionError as err:
            raise UpdateFailed(f"Cannot connect to Cellcom API: {err}") from err

        except Exception as err:
            raise UpdateFailed(f"Unexpected error fetching Cellcom data: {err}") from err

    async def _async_refresh_access_token(self) -> None:
        """Attempt to refresh the access token using the refresh token.

        If the refresh token is also expired, raise ConfigEntryAuthFailed
        to trigger the reauth flow.
        """
        if self._tokens is None:
            raise ConfigEntryAuthFailed("No tokens available for refresh")

        if not self._is_refresh_token_valid(self._tokens):
            _LOGGER.warning("Refresh token has expired, full re-authentication needed")
            self._tokens = None
            raise ConfigEntryAuthFailed("Refresh token expired, please re-authenticate")

        # TODO: implement /api/otp/RefreshToken endpoint once discovered.
        # For now, the refresh token is stored but the endpoint is unknown.
        # We log a warning and continue with the existing access token until it
        # fully expires, at which point ConfigEntryAuthFailed will be raised.
        remaining = self._tokens.access_expires_at - int(time.time())
        _LOGGER.warning(
            "Token refresh endpoint not yet implemented. "
            "Access token expires in %ss. Will prompt reauth when expired.",
            remaining,
        )

    @property
    def api_calls_today(self) -> int:
        """Return the number of API calls made today (approximate)."""
        return self._api_calls_today
