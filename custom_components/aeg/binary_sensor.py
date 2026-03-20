"""Binary sensor entities for AEG integration.

Creates binary sensors for door state, remote control, water tank,
food probe insertion, and connectivity.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up AEG binary sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AegDataUpdateCoordinator = data["coordinator"]

    entities: list[BinarySensorEntity] = []

    for app_id, appliance in coordinator.data.get("appliances", {}).items():
        reported = appliance.get("properties", {}).get("reported", {})

        # Door state
        if "doorState" in reported:
            entities.append(
                AegDoorSensor(coordinator, app_id)
            )

        # Door lock
        if "doorLock" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "doorLock",
                    "Door Lock",
                    on_values=["ON", "LOCKING"],
                    device_class=BinarySensorDeviceClass.LOCK,
                    icon="mdi:lock",
                )
            )

        # Remote control enabled
        if "remoteControl" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "remoteControl_binary",
                    "Remote Control Enabled",
                    property_key="remoteControl",
                    on_values=["ENABLED", "NOT_SAFETY_RELEVANT_ENABLED"],
                    icon="mdi:remote",
                )
            )

        # Connectivity
        if "connectivityState" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "connectivity",
                    "Connected",
                    property_key="connectivityState",
                    on_values=["connected", "CONNECTED"],
                    device_class=BinarySensorDeviceClass.CONNECTIVITY,
                )
            )

        # Water tank empty (oven)
        if "waterTankEmpty" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "waterTankEmpty",
                    "Water Tank Empty",
                    on_values=["EMPTY", "empty", True, "true"],
                    device_class=BinarySensorDeviceClass.PROBLEM,
                    icon="mdi:water-off",
                )
            )

        # Water tray insertion (oven)
        if "waterTrayInsertionState" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "waterTrayInserted",
                    "Water Tray Inserted",
                    property_key="waterTrayInsertionState",
                    on_values=["INSERTED", "inserted"],
                    icon="mdi:tray-full",
                )
            )

        # Food probe insertion (oven)
        if "foodProbeInsertionState" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "foodProbeInserted",
                    "Food Probe Inserted",
                    property_key="foodProbeInsertionState",
                    on_values=["INSERTED", "inserted"],
                    icon="mdi:thermometer-probe",
                )
            )

        # Evaporator defrost (AC)
        if "evaporatorDefrostState" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "defrosting",
                    "Defrosting",
                    property_key="evaporatorDefrostState",
                    on_values=["DEFROSTING"],
                    icon="mdi:snowflake-melt",
                )
            )

        # Scheduler active (AC)
        if "schedulerSession" in reported:
            entities.append(
                AegBooleanSensor(
                    coordinator,
                    app_id,
                    "schedulerActive",
                    "Scheduler Active",
                    property_key="schedulerSession",
                    on_values=[True, "true", "True"],
                    icon="mdi:calendar-clock",
                )
            )

    async_add_entities(entities)


class AegDoorSensor(AegBaseEntity, BinarySensorEntity):
    """Binary sensor for appliance door state."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_icon = "mdi:door"

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
    ) -> None:
        """Initialize door sensor."""
        super().__init__(coordinator, appliance_id, "doorState", "Door")

    @property
    def is_on(self) -> bool | None:
        """Return True if door is open."""
        value = self.get_property("doorState")
        if value is None:
            return None
        return str(value).upper() == "OPEN"


class AegBooleanSensor(AegBaseEntity, BinarySensorEntity):
    """Generic boolean sensor with configurable on values."""

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
        on_values: list[Any] | None = None,
        property_key: str | None = None,
        device_class: BinarySensorDeviceClass | None = None,
        icon: str = "mdi:checkbox-marked-circle-outline",
    ) -> None:
        """Initialize boolean sensor.

        Args:
            coordinator: Data coordinator.
            appliance_id: Appliance ID.
            entity_key: Unique key for this entity.
            name: Human-readable name.
            on_values: Values that mean "on" / True.
            property_key: Property key (defaults to entity_key).
            device_class: HA device class.
            icon: MDI icon.
        """
        super().__init__(coordinator, appliance_id, entity_key, name)
        self._on_values = on_values or [True, "ON", "on"]
        self._property_key = property_key or entity_key
        if device_class:
            self._attr_device_class = device_class
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        """Return True if property value is in on_values."""
        value = self.get_property(self._property_key)
        if value is None:
            return None
        return value in self._on_values
