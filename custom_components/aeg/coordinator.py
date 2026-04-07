"""Data update coordinator for AEG integration.

Manages polling (fallback) and WebSocket (primary) data updates,
token persistence, and appliance state aggregation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import OcpApi, OcpAuthError, OcpConnectionError
from .const import (
    CONF_BRAND,
    CONF_COUNTRY_CODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    WS_RECONNECT_DELAY,
)
from .websocket import OcpWebSocket

_LOGGER = logging.getLogger(__name__)

RETRY_BASE_MINUTES = 2
RETRY_MAX_MINUTES = 30


class AegDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for AEG appliance data.

    Uses WebSocket for real-time updates with polling as fallback.
    Manages token refresh and persistence.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: OcpApi,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            entry: Config entry.
            api: Authenticated OCP API client.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.config_entry = entry
        self._api = api
        self._ws: OcpWebSocket | None = None
        self._ws_reconnect_task: asyncio.Task | None = None
        self._retry_count = 0
        self._cached_data: dict[str, Any] | None = None
        self._appliance_ids: list[str] = []

    @property
    def api(self) -> OcpApi:
        """Return the API client."""
        return self._api

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from OCP API.

        Returns:
            Dict with "appliances" key containing list of appliance data,
            and "user" key with user info.

        Raises:
            ConfigEntryAuthFailed: If credentials are invalid.
            UpdateFailed: If update fails transiently.
        """
        try:
            # Ensure we have a valid token
            await self._api.ensure_authenticated()

            # Persist tokens after any auth/refresh
            self._persist_tokens()

            # Fetch all appliances
            appliances = await self._api.get_appliances()

            # Build result
            data: dict[str, Any] = {
                "appliances": {},
            }

            for appliance in appliances:
                app_id = appliance.get("applianceId", "")
                if app_id:
                    # Extract applianceType from nested location into top level
                    # API returns it at properties.reported.applianceInfo.applianceType
                    if "applianceType" not in appliance:
                        reported = (
                            appliance
                            .get("properties", {})
                            .get("reported", {})
                        )
                        app_info = reported.get("applianceInfo", {})
                        app_type = app_info.get("applianceType", "")
                        if app_type:
                            appliance["applianceType"] = app_type

                    data["appliances"][app_id] = appliance

            # Track appliance IDs for WebSocket
            new_ids = list(data["appliances"].keys())
            if new_ids != self._appliance_ids:
                self._appliance_ids = new_ids
                # Reconnect WS with updated appliance list
                if self._ws and self._ws.connected:
                    self._ws.update_appliances(self._appliance_ids)

            # Success: cache and reset retry
            self._cached_data = data
            self._reset_retry()

            # Start WebSocket if not connected
            if not self._ws or not self._ws.connected:
                self.hass.async_create_task(self._start_websocket())

            return data

        except OcpAuthError as err:
            _LOGGER.error("Authentication failed: %s", err)
            # Persist cleared state
            self._api.set_tokens("", "", 0)
            self._persist_tokens()
            raise ConfigEntryAuthFailed(
                "Authentication failed. Please reconfigure."
            ) from err

        except OcpConnectionError as err:
            return self._handle_transient_error(err)

        except Exception as err:
            return self._handle_transient_error(err)

    def _handle_transient_error(self, err: Exception) -> dict[str, Any]:
        """Handle a transient error with retry backoff.

        Args:
            err: The exception that occurred.

        Returns:
            Cached data if available.

        Raises:
            UpdateFailed: If no cached data is available.
        """
        self._retry_count += 1
        next_interval = self._next_retry_interval()
        self.update_interval = next_interval

        _LOGGER.warning(
            "Update failed (attempt %d), next retry in %s: %s",
            self._retry_count,
            next_interval,
            err,
        )

        if self._cached_data:
            return self._cached_data

        raise UpdateFailed(f"Update failed with no cached data: {err}")

    def _next_retry_interval(self) -> timedelta:
        """Calculate next retry interval with exponential backoff."""
        minutes = min(
            RETRY_BASE_MINUTES * (2 ** (self._retry_count - 1)),
            RETRY_MAX_MINUTES,
        )
        return timedelta(minutes=minutes)

    def _reset_retry(self) -> None:
        """Reset retry count and restore normal update interval."""
        self._retry_count = 0
        self.update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    def _persist_tokens(self) -> None:
        """Save current tokens to config entry data for persistence."""
        tokens = self._api.get_tokens()
        new_data = {**self.config_entry.data, "tokens": tokens}
        self.hass.config_entries.async_update_entry(
            self.config_entry, data=new_data
        )

    # ---- WebSocket Management ----

    async def _start_websocket(self) -> None:
        """Start the WebSocket connection for real-time updates."""
        if not self._appliance_ids:
            return

        if not self._api.is_authenticated:
            return

        try:
            tokens = self._api.get_tokens()
            brand_config = self._get_brand_config()

            self._ws = OcpWebSocket(
                session=self._api._session,
                access_token=tokens["access_token"],
                api_key=brand_config["api_key"],
                appliance_ids=self._appliance_ids,
                on_message=self._handle_ws_message,
                on_disconnect=self._handle_ws_disconnect,
            )
            await self._ws.connect()
            _LOGGER.info(
                "WebSocket connected for %d appliances",
                len(self._appliance_ids),
            )

        except Exception:
            _LOGGER.warning(
                "Failed to start WebSocket, will rely on polling",
                exc_info=True,
            )

    def _handle_ws_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming WebSocket message.

        Merges the update into cached data and triggers entity updates.

        Args:
            data: Message payload from WebSocket.
        """
        if not self._cached_data:
            return

        # WebSocket messages contain appliance state updates
        # Format: {"applianceId": "...", "properties": {...}}
        # or list of such objects
        updates = data if isinstance(data, list) else [data]

        for update in updates:
            app_id = update.get("applianceId")
            if not app_id or app_id not in self._cached_data["appliances"]:
                continue

            # Merge properties into cached appliance data
            properties = update.get("properties", {})
            if properties:
                appliance = self._cached_data["appliances"][app_id]
                # Properties from WS are nested under "properties.reported"
                reported = appliance.get("properties", {}).get("reported", {})
                reported.update(properties.get("reported", properties))
                appliance.setdefault("properties", {})["reported"] = reported

                _LOGGER.debug(
                    "WebSocket update for %s: %d properties",
                    app_id,
                    len(properties),
                )

        # Notify listeners of the update
        self.async_set_updated_data(self._cached_data)

    def _handle_ws_disconnect(self) -> None:
        """Handle WebSocket disconnection - schedule reconnect."""
        _LOGGER.warning("WebSocket disconnected, scheduling reconnect")
        if self._ws_reconnect_task and not self._ws_reconnect_task.done():
            return
        self._ws_reconnect_task = self.hass.async_create_task(
            self._ws_reconnect()
        )

    async def _ws_reconnect(self) -> None:
        """Attempt to reconnect WebSocket with delay."""
        await asyncio.sleep(WS_RECONNECT_DELAY)
        if self._api.is_authenticated:
            # Update token in case it was refreshed
            if self._ws:
                tokens = self._api.get_tokens()
                self._ws.update_token(tokens["access_token"])
            await self._start_websocket()

    def _get_brand_config(self) -> dict[str, str]:
        """Get brand configuration from entry data."""
        from .const import BRANDS

        brand = self.config_entry.data.get(CONF_BRAND, "AEG")
        return BRANDS.get(brand, BRANDS["AEG"])

    async def async_shutdown(self) -> None:
        """Shut down coordinator - disconnect WebSocket."""
        if self._ws_reconnect_task and not self._ws_reconnect_task.done():
            self._ws_reconnect_task.cancel()
            try:
                await self._ws_reconnect_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.disconnect()
            self._ws = None

        await super().async_shutdown()
