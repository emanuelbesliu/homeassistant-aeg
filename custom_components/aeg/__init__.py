"""AEG (Electrolux OCP) integration for Home Assistant.

Connects to AEG/Electrolux appliances via the OCP API (the same API
used by the official AEG iOS app) with real-time WebSocket updates.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import OcpApi, OcpAuthError, OcpConnectionError
from .const import CONF_BRAND, CONF_COUNTRY_CODE, DOMAIN
from .coordinator import AegDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.CLIMATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AEG from a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry being set up.

    Returns:
        True if setup succeeded.

    Raises:
        ConfigEntryAuthFailed: If credentials are invalid.
        ConfigEntryNotReady: If connection fails.
    """
    api = OcpApi(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        country_code=entry.data[CONF_COUNTRY_CODE],
        brand=entry.data.get(CONF_BRAND, "AEG"),
    )

    try:
        await api.async_init()

        # Restore persisted tokens if available
        tokens = entry.data.get("tokens")
        if tokens and tokens.get("access_token"):
            api.set_tokens(
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_expiry=tokens["token_expiry"],
            )

        # Verify auth (will refresh/re-auth as needed)
        await api.ensure_authenticated()

    except OcpAuthError as err:
        await api.async_close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except (OcpConnectionError, Exception) as err:
        await api.async_close()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = AegDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry being unloaded.

    Returns:
        True if unload succeeded.
    """
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator: AegDataUpdateCoordinator = data["coordinator"]
        api: OcpApi = data["api"]

        await coordinator.async_shutdown()
        await api.async_close()

    return unload_ok
