"""Switch entities for AEG integration.

Creates switch entities for appliance power, sleep mode, UI lock,
clean air mode, energy saving, and other toggle properties.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COMMAND_OFF, COMMAND_ON, DOMAIN
from .coordinator import AegDataUpdateCoordinator
from .entity import AegBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AEG switch entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AegDataUpdateCoordinator = data["coordinator"]

    entities: list[SwitchEntity] = []

    for app_id, appliance in coordinator.data.get("appliances", {}).items():
        reported = appliance.get("properties", {}).get("reported", {})

        # Power switch (via executeCommand)
        entities.append(
            AegPowerSwitch(coordinator, app_id)
        )

        # Sleep mode (AC)
        if "sleepMode" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "sleepMode",
                    "Sleep Mode",
                    icon="mdi:sleep",
                )
            )

        # UI Lock
        if "uiLocked" in reported:
            entities.append(
                AegBoolToggleSwitch(
                    coordinator,
                    app_id,
                    "uiLocked",
                    "UI Lock",
                    icon="mdi:lock-outline",
                )
            )

        # Clean air mode (AC)
        if "cleanAirMode" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "cleanAirMode",
                    "Clean Air Mode",
                    icon="mdi:air-filter",
                )
            )

        # Energy saving mode (AC)
        if "energySavingMode" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "energySavingMode",
                    "Energy Saving",
                    icon="mdi:leaf",
                )
            )

        # Flap oscillate / vertical swing (AC)
        if "flapOscillate" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "flapOscillate",
                    "Swing",
                    icon="mdi:arrow-oscillating",
                )
            )
        elif "verticalSwing" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "verticalSwing",
                    "Vertical Swing",
                    icon="mdi:arrow-oscillating",
                )
            )

        # iClean (AC SEA)
        if "iClean" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "iClean",
                    "Self Clean",
                    icon="mdi:broom",
                )
            )

        # xFan (AC SEA)
        if "xFan" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "xFan",
                    "X-Fan",
                    icon="mdi:fan",
                )
            )

        # Comfort air (AC LATAM)
        if "comfortAir" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "comfortAir",
                    "Comfort Air",
                    icon="mdi:weather-windy",
                )
            )

        # Auto sense mode (AC LATAM)
        if "autoSenseMode" in reported:
            entities.append(
                AegToggleSwitch(
                    coordinator,
                    app_id,
                    "autoSenseMode",
                    "Auto Sense",
                    icon="mdi:eye",
                )
            )

    async_add_entities(entities)


class AegPowerSwitch(AegBaseEntity, SwitchEntity):
    """Switch for appliance power on/off via executeCommand."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:power"

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
    ) -> None:
        """Initialize power switch."""
        super().__init__(coordinator, appliance_id, "power", "Power")

    @property
    def is_on(self) -> bool | None:
        """Return True if appliance is not OFF."""
        state = self.get_property("applianceState")
        if state is None:
            return None
        return str(state).upper() != "OFF"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the appliance."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {"executeCommand": COMMAND_ON},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the appliance."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {"executeCommand": COMMAND_OFF},
        )
        await self.coordinator.async_request_refresh()


class AegToggleSwitch(AegBaseEntity, SwitchEntity):
    """Switch for ON/OFF string toggle properties."""

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        icon: str = "mdi:toggle-switch",
    ) -> None:
        """Initialize toggle switch."""
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        """Return True if property is ON."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        return str(value).upper() == "ON"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the feature."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._entity_key: "ON"},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the feature."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._entity_key: "OFF"},
        )
        await self.coordinator.async_request_refresh()


class AegBoolToggleSwitch(AegBaseEntity, SwitchEntity):
    """Switch for boolean toggle properties (true/false)."""

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        icon: str = "mdi:toggle-switch",
    ) -> None:
        """Initialize boolean toggle switch."""
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        """Return True if property is true."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set property to true."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._entity_key: True},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set property to false."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._entity_key: False},
        )
        await self.coordinator.async_request_refresh()
