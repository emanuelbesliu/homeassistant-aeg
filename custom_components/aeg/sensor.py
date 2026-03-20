"""Sensor entities for AEG integration.

Creates sensor entities for appliance state, cycle progress, temperatures,
network quality, and other read-only properties.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AegDataUpdateCoordinator
from .entity import AegBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AEG sensor entities.

    Args:
        hass: Home Assistant instance.
        entry: Config entry.
        async_add_entities: Callback to add entities.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AegDataUpdateCoordinator = data["coordinator"]

    entities: list[SensorEntity] = []

    for app_id, appliance in coordinator.data.get("appliances", {}).items():
        reported = appliance.get("properties", {}).get("reported", {})

        # Appliance state sensor (always created)
        entities.append(
            AegStateSensor(coordinator, app_id, "applianceState", "State")
        )

        # Time to end (washing machines, dryers, dishwashers, ovens)
        if "timeToEnd" in reported:
            entities.append(
                AegTimeSensor(
                    coordinator, app_id, "timeToEnd", "Time to End"
                )
            )

        # Start time
        if "startTime" in reported:
            entities.append(
                AegTimeSensor(
                    coordinator, app_id, "startTime", "Start Time"
                )
            )

        # Cycle sub-phase (washing machines, dryers)
        if "cycleSubPhase" in reported:
            entities.append(
                AegStateSensor(
                    coordinator, app_id, "cycleSubPhase", "Cycle Phase"
                )
            )

        # Program UID
        if "programUID" in reported:
            entities.append(
                AegStateSensor(
                    coordinator, app_id, "programUID", "Program"
                )
            )

        # Temperature sensors
        if "temperature" in reported:
            entities.append(
                AegTemperatureSensor(
                    coordinator, app_id, "temperature", "Temperature"
                )
            )

        if "targetTemperatureC" in reported:
            entities.append(
                AegTemperatureSensor(
                    coordinator, app_id, "targetTemperatureC", "Target Temperature"
                )
            )

        if "ambientTemperatureC" in reported:
            entities.append(
                AegTemperatureSensor(
                    coordinator, app_id, "ambientTemperatureC", "Ambient Temperature"
                )
            )

        # Oven-specific: food probe temperature
        if "foodProbeTemperatureC" in reported:
            entities.append(
                AegTemperatureSensor(
                    coordinator,
                    app_id,
                    "foodProbeTemperatureC",
                    "Food Probe Temperature",
                )
            )

        if "targetFoodProbeTemperatureC" in reported:
            entities.append(
                AegTemperatureSensor(
                    coordinator,
                    app_id,
                    "targetFoodProbeTemperatureC",
                    "Target Food Probe Temperature",
                )
            )

        # Spin speed (washing machines)
        if "analogSpinSpeed" in reported:
            entities.append(
                AegGenericSensor(
                    coordinator,
                    app_id,
                    "analogSpinSpeed",
                    "Spin Speed",
                    icon="mdi:rotate-right",
                    unit="RPM",
                )
            )

        # Analog temperature (WM water temp)
        if "analogTemperature" in reported:
            entities.append(
                AegTemperatureSensor(
                    coordinator,
                    app_id,
                    "analogTemperature",
                    "Wash Temperature",
                )
            )

        # Network interface
        ni = reported.get("networkInterface", {})
        if isinstance(ni, dict):
            if "linkQualityIndicator" in ni:
                entities.append(
                    AegNestedStateSensor(
                        coordinator,
                        app_id,
                        "wifi_quality",
                        "WiFi Quality",
                        "networkInterface",
                        "linkQualityIndicator",
                        icon="mdi:wifi",
                    )
                )
            if "swVersion" in ni:
                entities.append(
                    AegNestedStateSensor(
                        coordinator,
                        app_id,
                        "sw_version",
                        "Firmware Version",
                        "networkInterface",
                        "swVersion",
                        icon="mdi:chip",
                    )
                )

        # AC-specific sensors
        if "currentEnergyUsePercent" in reported:
            entities.append(
                AegPercentSensor(
                    coordinator,
                    app_id,
                    "currentEnergyUsePercent",
                    "Energy Use",
                    icon="mdi:lightning-bolt",
                )
            )

        if "totalRuntime" in reported:
            entities.append(
                AegTimeSensor(
                    coordinator,
                    app_id,
                    "totalRuntime",
                    "Total Runtime",
                )
            )

        # Filter state (AC)
        if "filterState" in reported:
            entities.append(
                AegStateSensor(
                    coordinator, app_id, "filterState", "Filter State"
                )
            )

        # Mode sensor (read-only mirror for all appliance types)
        if "mode" in reported:
            entities.append(
                AegStateSensor(
                    coordinator, app_id, "mode", "Mode"
                )
            )

        # Remote control state
        if "remoteControl" in reported:
            entities.append(
                AegStateSensor(
                    coordinator, app_id, "remoteControl", "Remote Control"
                )
            )

    async_add_entities(entities)


class AegStateSensor(AegBaseEntity, SensorEntity):
    """Sensor for string state properties (applianceState, mode, etc.)."""

    _attr_icon = "mdi:information-outline"

    @property
    def native_value(self) -> str | None:
        """Return the state value."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        return str(value).replace("_", " ").title()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes with raw value."""
        value = self.get_property(self._entity_key)
        if value is not None:
            return {"raw_value": value}
        return {}


class AegTimeSensor(AegBaseEntity, SensorEntity):
    """Sensor for time values (seconds)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-outline"

    @property
    def native_value(self) -> int | None:
        """Return the time value in seconds."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return human-readable time."""
        value = self.native_value
        if value is not None and value > 0:
            hours = value // 3600
            minutes = (value % 3600) // 60
            return {"formatted": f"{hours}h {minutes}m"}
        return {}


class AegTemperatureSensor(AegBaseEntity, SensorEntity):
    """Sensor for temperature values."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the temperature value."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


class AegPercentSensor(AegBaseEntity, SensorEntity):
    """Sensor for percentage values."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        icon: str = "mdi:percent",
    ) -> None:
        """Initialize with optional icon."""
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._attr_icon = icon

    @property
    def native_value(self) -> float | None:
        """Return the percentage value."""
        value = self.get_property(self._entity_key)
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


class AegGenericSensor(AegBaseEntity, SensorEntity):
    """Generic sensor with configurable unit and icon."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        icon: str = "mdi:information-outline",
        unit: str | None = None,
    ) -> None:
        """Initialize with custom unit and icon."""
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._attr_icon = icon
        if unit:
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.get_property(self._entity_key)


class AegNestedStateSensor(AegBaseEntity, SensorEntity):
    """Sensor for nested property values (e.g. networkInterface.swVersion)."""

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        parent_key: str,
        child_key: str,
        icon: str = "mdi:information-outline",
    ) -> None:
        """Initialize with parent and child keys."""
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._parent_key = parent_key
        self._child_key = child_key
        self._attr_icon = icon

    @property
    def native_value(self) -> str | None:
        """Return the nested value."""
        value = self.get_nested_property(self._parent_key, self._child_key)
        if value is None:
            return None
        return str(value)
