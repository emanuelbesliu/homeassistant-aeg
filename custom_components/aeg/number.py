"""Number entities for AEG integration.

Creates number entities for target temperature, start/stop scheduling
times, fan speed, and flap position controls.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AegDataUpdateCoordinator
from .entity import AegBaseEntity

_LOGGER = logging.getLogger(__name__)

# Number entity definitions: property_key -> (name, min, max, step, unit, device_class, icon)
NUMBER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "targetTemperatureC": {
        "name": "Target Temperature",
        "min": 16,
        "max": 32,
        "step": 1,
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": NumberDeviceClass.TEMPERATURE,
        "icon": None,
    },
    "targetFoodProbeTemperatureC": {
        "name": "Target Food Probe Temperature",
        "min": 30,
        "max": 96,
        "step": 1,
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": NumberDeviceClass.TEMPERATURE,
        "icon": "mdi:thermometer-probe",
    },
    "startTime": {
        "name": "Start Time",
        "min": 0,
        "max": 86400,
        "step": 900,
        "unit": UnitOfTime.SECONDS,
        "device_class": NumberDeviceClass.DURATION,
        "icon": "mdi:clock-start",
    },
    "stopTime": {
        "name": "Stop Time",
        "min": 0,
        "max": 86400,
        "step": 900,
        "unit": UnitOfTime.SECONDS,
        "device_class": NumberDeviceClass.DURATION,
        "icon": "mdi:clock-end",
    },
    "analogSpinSpeed": {
        "name": "Spin Speed",
        "min": 0,
        "max": 1600,
        "step": 100,
        "unit": "RPM",
        "device_class": None,
        "icon": "mdi:rotate-right",
    },
    "flapPosition": {
        "name": "Flap Position",
        "min": 1,
        "max": 7,
        "step": 1,
        "unit": None,
        "device_class": None,
        "icon": "mdi:arrow-up-down",
    },
}

# Oven temperature definitions (different range per context)
OVEN_TEMP_DEFINITION = {
    "name": "Oven Temperature",
    "min": 30,
    "max": 230,
    "step": 5,
    "unit": UnitOfTemperature.CELSIUS,
    "device_class": NumberDeviceClass.TEMPERATURE,
    "icon": "mdi:thermometer",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AEG number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AegDataUpdateCoordinator = data["coordinator"]

    entities: list[NumberEntity] = []

    for app_id, appliance in coordinator.data.get("appliances", {}).items():
        reported = appliance.get("properties", {}).get("reported", {})
        app_type = appliance.get("applianceType", "")

        for prop_key, definition in NUMBER_DEFINITIONS.items():
            if prop_key in reported:
                # Skip targetTemperatureC for AC — handled by climate entity
                if prop_key == "targetTemperatureC" and app_type in (
                    "AC",
                    "AC_SPLIT",
                    "WRAC",
                ):
                    continue

                entities.append(
                    AegNumberEntity(
                        coordinator,
                        app_id,
                        prop_key,
                        definition["name"],
                        definition["min"],
                        definition["max"],
                        definition["step"],
                        definition.get("unit"),
                        definition.get("device_class"),
                        definition.get("icon"),
                    )
                )

        # Oven-specific target temperature (wider range: 30-230)
        if app_type in ("OV", "DOUBLE_OV") and "targetTemperatureC" in reported:
            d = OVEN_TEMP_DEFINITION
            entities.append(
                AegNumberEntity(
                    coordinator,
                    app_id,
                    "targetTemperatureC",
                    d["name"],
                    d["min"],
                    d["max"],
                    d["step"],
                    d.get("unit"),
                    d.get("device_class"),
                    d.get("icon"),
                )
            )

    async_add_entities(entities)


class AegNumberEntity(AegBaseEntity, NumberEntity):
    """Number entity for numeric property controls."""

    _attr_mode = NumberMode.AUTO

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        min_value: float,
        max_value: float,
        step: float,
        unit: str | None = None,
        device_class: NumberDeviceClass | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize number entity.

        Args:
            coordinator: Data coordinator.
            appliance_id: Appliance ID.
            entity_key: Property key on the appliance.
            name: Human-readable name.
            min_value: Minimum allowed value.
            max_value: Maximum allowed value.
            step: Step increment.
            unit: Unit of measurement.
            device_class: HA device class.
            icon: MDI icon.
        """
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        if unit:
            self._attr_native_unit_of_measurement = unit
        if device_class:
            self._attr_device_class = device_class
        if icon:
            self._attr_icon = icon

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value by sending a command.

        Args:
            value: The new numeric value.
        """
        # Send as int if the step is an integer
        send_value: int | float = (
            int(value)
            if self._attr_native_step >= 1
            and value == int(value)
            else value
        )

        await self.coordinator.api.execute_command(
            self._appliance_id,
            {self._entity_key: send_value},
        )
        await self.coordinator.async_request_refresh()
