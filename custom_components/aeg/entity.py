"""Base entity class for AEG integration.

Provides common functionality for all AEG entities:
- Device info from appliance data
- Property access helpers
- Unique ID generation
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CATEGORY_NAMES, DOMAIN
from .coordinator import AegDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class AegBaseEntity(CoordinatorEntity[AegDataUpdateCoordinator]):
    """Base class for AEG entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        entity_key: str,
        name: str,
    ) -> None:
        """Initialize the entity.

        Args:
            coordinator: Data update coordinator.
            appliance_id: Unique appliance ID.
            entity_key: Key identifying this specific entity (e.g. "applianceState").
            name: Human-readable entity name.
        """
        super().__init__(coordinator)
        self._appliance_id = appliance_id
        self._entity_key = entity_key

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{appliance_id}_{entity_key}"
        self._attr_name = name

    @property
    def appliance_data(self) -> dict[str, Any] | None:
        """Get the appliance data from coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("appliances", {}).get(
            self._appliance_id
        )

    @property
    def reported_properties(self) -> dict[str, Any]:
        """Get the reported properties for this appliance."""
        data = self.appliance_data
        if not data:
            return {}
        return data.get("properties", {}).get("reported", {})

    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a reported property value.

        Args:
            key: Property key (e.g. "applianceState").
            default: Default value if property not found.

        Returns:
            Property value or default.
        """
        return self.reported_properties.get(key, default)

    def get_nested_property(self, *keys: str, default: Any = None) -> Any:
        """Get a nested reported property value.

        Args:
            keys: Sequence of keys to traverse (e.g. "networkInterface", "linkQualityIndicator").
            default: Default value if property not found.

        Returns:
            Property value or default.
        """
        value = self.reported_properties
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.data:
            return False
        data = self.appliance_data
        if not data:
            return False
        # Check connectivity
        conn = self.get_property("connectivityState")
        if conn and conn.lower() == "disconnected":
            return False
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this appliance."""
        data = self.appliance_data or {}
        info = data.get("applianceData", {})
        model_name = info.get("modelName", "")
        appliance_type = info.get("applianceName", "")
        brand = info.get("brand", "AEG")

        # Try to get a human-readable type
        category = data.get("applianceType", "")
        type_name = CATEGORY_NAMES.get(category, appliance_type)

        return DeviceInfo(
            identifiers={(DOMAIN, self._appliance_id)},
            name=info.get("applianceName")
            or type_name
            or f"{brand} Appliance",
            manufacturer=brand,
            model=model_name or type_name,
            serial_number=info.get("serialNumber"),
            sw_version=self.get_nested_property(
                "networkInterface", "swVersion"
            ),
        )
