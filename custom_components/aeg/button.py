"""Button entities for AEG integration.

Creates button entities for appliance commands like START, PAUSE,
RESUME, STOP/RESET, and filter reset alerts.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    COMMAND_PAUSE,
    COMMAND_RESUME,
    COMMAND_START,
    COMMAND_STOPRESET,
    DOMAIN,
)
from .coordinator import AegDataUpdateCoordinator
from .entity import AegBaseEntity

_LOGGER = logging.getLogger(__name__)

# Commands that are available per appliance state
COMMANDS = [
    {
        "key": "start",
        "name": "Start",
        "command": COMMAND_START,
        "icon": "mdi:play",
    },
    {
        "key": "pause",
        "name": "Pause",
        "command": COMMAND_PAUSE,
        "icon": "mdi:pause",
    },
    {
        "key": "resume",
        "name": "Resume",
        "command": COMMAND_RESUME,
        "icon": "mdi:play-pause",
    },
    {
        "key": "stop_reset",
        "name": "Stop / Reset",
        "command": COMMAND_STOPRESET,
        "icon": "mdi:stop",
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AEG button entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AegDataUpdateCoordinator = data["coordinator"]

    entities: list[ButtonEntity] = []

    for app_id, appliance in coordinator.data.get("appliances", {}).items():
        reported = appliance.get("properties", {}).get("reported", {})

        # Only create command buttons if the appliance supports executeCommand
        if "applianceState" in reported:
            for cmd in COMMANDS:
                entities.append(
                    AegCommandButton(
                        coordinator,
                        app_id,
                        cmd["key"],
                        cmd["name"],
                        cmd["command"],
                        cmd["icon"],
                    )
                )

        # Filter reset button (AC — when filterState reports CLEAN/CHANGE/BUY)
        if "filterState" in reported:
            entities.append(
                AegFilterResetButton(coordinator, app_id)
            )

        # Auto-clean button (AC SEA)
        if "autoClean" in reported:
            entities.append(
                AegPropertyCommandButton(
                    coordinator,
                    app_id,
                    "auto_clean",
                    "Auto Clean",
                    "autoClean",
                    "ON",
                    icon="mdi:broom",
                )
            )

    async_add_entities(entities)


class AegCommandButton(AegBaseEntity, ButtonEntity):
    """Button for appliance executeCommand actions."""

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        command: str,
        icon: str,
    ) -> None:
        """Initialize command button.

        Args:
            coordinator: Data coordinator.
            appliance_id: Appliance ID.
            entity_key: Unique key (e.g. "start").
            name: Human-readable name.
            command: OCP executeCommand value (e.g. "START").
            icon: MDI icon.
        """
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._command = command
        self._attr_icon = icon

    async def async_press(self) -> None:
        """Press the button - execute the command."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {"executeCommand": self._command},
        )
        await self.coordinator.async_request_refresh()


class AegFilterResetButton(AegBaseEntity, ButtonEntity):
    """Button to reset the AC filter alert."""

    _attr_icon = "mdi:air-filter"

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
    ) -> None:
        """Initialize filter reset button."""
        super().__init__(
            coordinator, appliance_id, "filter_reset", "Reset Filter Alert"
        )

    async def async_press(self) -> None:
        """Press the button - reset the filter state to GOOD."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {"filterState": "GOOD"},
        )
        await self.coordinator.async_request_refresh()


class AegPropertyCommandButton(AegBaseEntity, ButtonEntity):
    """Button that sets a property to a specific value (one-shot action)."""

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        property_key: str,
        property_value: Any,
        icon: str = "mdi:button-pointer",
    ) -> None:
        """Initialize property command button.

        Args:
            coordinator: Data coordinator.
            appliance_id: Appliance ID.
            entity_key: Unique key for this entity.
            name: Human-readable name.
            property_key: The property to set.
            property_value: The value to set the property to.
            icon: MDI icon.
        """
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._property_key = property_key
        self._property_value = property_value
        self._attr_icon = icon

    async def async_press(self) -> None:
        """Press the button - set the property value."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._property_key: self._property_value},
        )
        await self.coordinator.async_request_refresh()
