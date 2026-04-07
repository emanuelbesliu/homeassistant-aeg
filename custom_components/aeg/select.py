"""Select entities for AEG integration.

Creates select entities for appliance mode selection (AC, WM),
fan speed, display light, and other enumerated properties.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AegDataUpdateCoordinator
from .entity import AegBaseEntity

_LOGGER = logging.getLogger(__name__)

# Known options for each select property.
# The API uses uppercase values; we display title-cased labels.
AC_MODES = ["AUTO", "COOL", "HEAT", "DRY", "FANONLY", "SMART"]
AC_FAN_SPEEDS = ["AUTO", "LOW", "MEDIUM", "MIDDLE", "HIGH", "TURBO", "QUIET"]
AC_DISPLAY_LIGHT = ["ON", "OFF", "DIM"]
WM_WASH_TEMPS = ["COLD", "20", "30", "40", "50", "60", "90"]

# Maps property keys to (name, options, icon)
SELECT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "mode": {
        "name": "Mode",
        "options": AC_MODES,
        "icon": "mdi:thermostat",
    },
    "fanSpeedSetting": {
        "name": "Fan Speed",
        "options": AC_FAN_SPEEDS,
        "icon": "mdi:fan",
    },
    "displayLight": {
        "name": "Display Light",
        "options": AC_DISPLAY_LIGHT,
        "icon": "mdi:lightbulb-outline",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AEG select entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AegDataUpdateCoordinator = data["coordinator"]

    entities: list[SelectEntity] = []

    for app_id, appliance in coordinator.data.get("appliances", {}).items():
        reported = appliance.get("properties", {}).get("reported", {})

        for prop_key, definition in SELECT_DEFINITIONS.items():
            if prop_key in reported:
                entities.append(
                    AegSelectEntity(
                        coordinator,
                        app_id,
                        prop_key,
                        definition["name"],
                        definition["options"],
                        definition["icon"],
                    )
                )

        # Louver / flap position (AC DAM: 5 positions)
        if "louverPosition" in reported:
            entities.append(
                AegSelectEntity(
                    coordinator,
                    app_id,
                    "louverPosition",
                    "Louver Position",
                    ["1", "2", "3", "4", "5"],
                    "mdi:arrow-up-down",
                )
            )

        # Program selection (all appliance types via userSelections.programUID)
        user_selections = reported.get("userSelections", {})
        if isinstance(user_selections, dict) and "programUID" in user_selections:
            entities.append(
                AegDynamicSelectEntity(
                    coordinator,
                    app_id,
                    "programUID",
                    "Program",
                    "mdi:washing-machine",
                )
            )

    async_add_entities(entities)


class AegSelectEntity(AegBaseEntity, SelectEntity):
    """Select entity for enumerated property values."""

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        options: list[str],
        icon: str = "mdi:format-list-bulleted",
    ) -> None:
        """Initialize select entity.

        Args:
            coordinator: Data coordinator.
            appliance_id: Appliance ID.
            entity_key: Property key on the appliance.
            name: Human-readable name.
            options: List of valid option values.
            icon: MDI icon.
        """
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._attr_options = [o.replace("_", " ").title() for o in options]
        self._raw_options = options
        self._attr_icon = icon

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        # Convert raw API value to display format
        raw = str(value).upper()
        if raw in self._raw_options:
            idx = self._raw_options.index(raw)
            return self._attr_options[idx]
        # Fallback: return as-is in title case
        return str(value).replace("_", " ").title()

    async def async_select_option(self, option: str) -> None:
        """Select an option by sending the command.

        Args:
            option: The display-formatted option selected by the user.
        """
        # Convert display option back to raw API value
        if option in self._attr_options:
            idx = self._attr_options.index(option)
            raw_value = self._raw_options[idx]
        else:
            # Fallback: uppercase the option
            raw_value = option.upper().replace(" ", "_")

        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._entity_key: raw_value},
        )
        await self.coordinator.async_request_refresh()


class AegDynamicSelectEntity(AegBaseEntity, SelectEntity):
    """Select entity where options are discovered from the appliance data.

    Used for properties like oven programs where the list varies
    per appliance model.
    """

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        icon: str = "mdi:format-list-bulleted",
    ) -> None:
        """Initialize dynamic select entity."""
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._attr_icon = icon
        self._discovered_options: list[str] = []

    @property
    def options(self) -> list[str]:
        """Return dynamically discovered options.

        If we haven't discovered options yet, return an empty list
        which will be populated once we see capability data.
        """
        if self._discovered_options:
            return self._discovered_options

        # Try to get options from the appliance capabilities metadata
        data = self.appliance_data
        if data:
            caps = data.get("capabilities", {})
            prop_caps = caps.get(self._entity_key, {})
            values = prop_caps.get("values", [])
            if values:
                self._discovered_options = [
                    str(v).replace("_", " ").title() for v in values
                ]
                return self._discovered_options

        # Fallback: just the current value
        value = self.get_nested_property("userSelections", self._entity_key)
        if value:
            return [str(value).replace("_", " ").title()]
        return []

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        value = self.get_nested_property("userSelections", self._entity_key)
        if value is None:
            return None
        return str(value).replace("_", " ").title()

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        raw_value = option.upper().replace(" ", "_")
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._entity_key: raw_value},
        )
        await self.coordinator.async_request_refresh()
