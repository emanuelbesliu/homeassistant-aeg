"""Climate entity for AEG air conditioner integration.

Maps AEG/Electrolux AC appliances to the HA ClimateEntity interface
with HVAC modes, fan modes, swing modes, and temperature control.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COMMAND_OFF, COMMAND_ON, DOMAIN
from .coordinator import AegDataUpdateCoordinator
from .entity import AegBaseEntity

_LOGGER = logging.getLogger(__name__)

# AEG AC categories
AC_CATEGORIES = {"AC", "AC_SPLIT", "WRAC"}

# Map OCP mode values -> HA HVAC modes
OCP_TO_HVAC_MODE: dict[str, HVACMode] = {
    "AUTO": HVACMode.AUTO,
    "COOL": HVACMode.COOL,
    "HEAT": HVACMode.HEAT,
    "DRY": HVACMode.DRY,
    "FANONLY": HVACMode.FAN_ONLY,
    "FAN_ONLY": HVACMode.FAN_ONLY,
    "SMART": HVACMode.AUTO,
}

# Reverse map: HA mode -> OCP mode (prefer standard OCP values)
HVAC_TO_OCP_MODE: dict[HVACMode, str] = {
    HVACMode.AUTO: "AUTO",
    HVACMode.COOL: "COOL",
    HVACMode.HEAT: "HEAT",
    HVACMode.DRY: "DRY",
    HVACMode.FAN_ONLY: "FANONLY",
}

# Fan speed mapping
OCP_TO_FAN_MODE: dict[str, str] = {
    "AUTO": "Auto",
    "LOW": "Low",
    "MEDIUM": "Medium",
    "MIDDLE": "Medium",
    "HIGH": "High",
    "TURBO": "Turbo",
    "QUIET": "Quiet",
}

FAN_TO_OCP_MODE: dict[str, str] = {
    "Auto": "AUTO",
    "Low": "LOW",
    "Medium": "MEDIUM",
    "High": "HIGH",
    "Turbo": "TURBO",
    "Quiet": "QUIET",
}

# Swing modes
SWING_OFF = "Off"
SWING_VERTICAL = "Vertical"
SWING_ON = "On"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AEG climate entities for AC appliances."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AegDataUpdateCoordinator = data["coordinator"]

    entities: list[ClimateEntity] = []

    for app_id, appliance in coordinator.data.get("appliances", {}).items():
        app_type = appliance.get("applianceType", "")
        if app_type not in AC_CATEGORIES:
            continue

        entities.append(AegClimateEntity(coordinator, app_id, appliance))

    async_add_entities(entities)


class AegClimateEntity(AegBaseEntity, ClimateEntity):
    """Climate entity for AEG air conditioners."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = 16
    _attr_max_temp = 32
    _enable_turn_on_off_backwards_compat = False

    def __init__(
        self,
        coordinator: AegDataUpdateCoordinator,
        appliance_id: str,
        appliance: dict[str, Any],
    ) -> None:
        """Initialize the AC climate entity.

        Args:
            coordinator: Data coordinator.
            appliance_id: Appliance ID.
            appliance: Full appliance data dict.
        """
        super().__init__(coordinator, appliance_id, "climate", "Climate")

        reported = appliance.get("properties", {}).get("reported", {})

        # Determine supported features
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

        if "fanSpeedSetting" in reported:
            features |= ClimateEntityFeature.FAN_MODE

        if (
            "flapOscillate" in reported
            or "verticalSwing" in reported
        ):
            features |= ClimateEntityFeature.SWING_MODE

        self._attr_supported_features = features

        # Determine available HVAC modes
        self._attr_hvac_modes = [HVACMode.OFF]
        if "mode" in reported:
            # Discover available modes from the current value + known set
            for ocp_mode in OCP_TO_HVAC_MODE:
                ha_mode = OCP_TO_HVAC_MODE[ocp_mode]
                if ha_mode not in self._attr_hvac_modes:
                    self._attr_hvac_modes.append(ha_mode)

        # Determine available fan modes
        if "fanSpeedSetting" in reported:
            self._attr_fan_modes = list(FAN_TO_OCP_MODE.keys())
        else:
            self._attr_fan_modes = None

        # Determine available swing modes
        if "flapOscillate" in reported or "verticalSwing" in reported:
            self._attr_swing_modes = [SWING_OFF, SWING_VERTICAL, SWING_ON]
        else:
            self._attr_swing_modes = None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        state = self.get_property("applianceState")
        if state and str(state).upper() == "OFF":
            return HVACMode.OFF

        mode = self.get_property("mode")
        if mode:
            ha_mode = OCP_TO_HVAC_MODE.get(str(mode).upper())
            if ha_mode:
                return ha_mode
        return HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current ambient temperature."""
        value = self.get_property("ambientTemperatureC")
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        value = self.get_property("targetTemperatureC")
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        value = self.get_property("fanSpeedSetting")
        if value is None:
            return None
        return OCP_TO_FAN_MODE.get(str(value).upper(), str(value).title())

    @property
    def swing_mode(self) -> str | None:
        """Return the current swing mode."""
        # Check flapOscillate first (DAM model)
        oscillate = self.get_property("flapOscillate")
        if oscillate is not None:
            return (
                SWING_ON if str(oscillate).upper() == "ON" else SWING_OFF
            )

        # Check verticalSwing (SEA model)
        vswing = self.get_property("verticalSwing")
        if vswing is not None:
            return (
                SWING_VERTICAL
                if str(vswing).upper() == "ON"
                else SWING_OFF
            )

        return None

    @property
    def hvac_action(self) -> str | None:
        """Return the current HVAC action (heating, cooling, idle, off)."""
        state = self.get_property("applianceState")
        if not state or str(state).upper() == "OFF":
            return "off"
        if str(state).upper() == "RUNNING":
            mode = self.get_property("mode")
            if mode:
                upper_mode = str(mode).upper()
                if upper_mode == "COOL":
                    return "cooling"
                if upper_mode == "HEAT":
                    return "heating"
                if upper_mode == "DRY":
                    return "drying"
                if upper_mode in ("FANONLY", "FAN_ONLY"):
                    return "fan"
            return "idle"
        return "idle"

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode.

        Args:
            hvac_mode: The desired HA HVAC mode.
        """
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.api.execute_command(
                self._appliance_id,
                {"executeCommand": COMMAND_OFF},
            )
        else:
            # Turn on if off, then set mode
            state = self.get_property("applianceState")
            if state and str(state).upper() == "OFF":
                await self.coordinator.api.execute_command(
                    self._appliance_id,
                    {"executeCommand": COMMAND_ON},
                )

            ocp_mode = HVAC_TO_OCP_MODE.get(hvac_mode)
            if ocp_mode:
                await self.coordinator.api.execute_command(
                    self._appliance_id,
                    {"mode": ocp_mode},
                )

        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature.

        Args:
            kwargs: Must contain ATTR_TEMPERATURE.
        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        await self.coordinator.api.execute_command(
            self._appliance_id,
            {"targetTemperatureC": int(temperature)},
        )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode.

        Args:
            fan_mode: Fan mode display name (e.g. "Auto", "High").
        """
        ocp_fan = FAN_TO_OCP_MODE.get(fan_mode)
        if ocp_fan:
            await self.coordinator.api.execute_command(
                self._appliance_id,
                {"fanSpeedSetting": ocp_fan},
            )
            await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode.

        Args:
            swing_mode: Swing mode (Off, Vertical, On).
        """
        value = "ON" if swing_mode in (SWING_ON, SWING_VERTICAL) else "OFF"

        # Use the correct property key based on what the appliance supports
        if self.get_property("flapOscillate") is not None:
            prop_key = "flapOscillate"
        elif self.get_property("verticalSwing") is not None:
            prop_key = "verticalSwing"
        else:
            return

        await self.coordinator.api.execute_command(
            self._appliance_id,
            {prop_key: value},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn on the AC."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {"executeCommand": COMMAND_ON},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off the AC."""
        await self.coordinator.api.execute_command(
            self._appliance_id,
            {"executeCommand": COMMAND_OFF},
        )
        await self.coordinator.async_request_refresh()
