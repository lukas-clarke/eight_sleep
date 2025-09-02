"""Support for Eight Sleep climate control."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import EightSleepBaseEntity, EightSleepConfigEntryData
from .const import DOMAIN
from .pyEight.eight import EightSleep
from .pyEight.user import EightUser
from .pyEight.util import heating_level_to_temp, temp_to_heating_level
from .util import convert_hass_temp_unit_to_pyeight_temp_unit

_LOGGER = logging.getLogger(__name__)

# Temperature mapping - the API uses -100 to 100 scale
# We map to standard Fahrenheit temperatures for better UX
MIN_TEMP_F = 55
MIN_TEMP_C = 13
MAX_TEMP_F = 110
MAX_TEMP_C = 43
TEMP_STEP = 1

# Duration for heating/cooling in seconds (2 hours)
DEFAULT_DURATION = 7200


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Eight Sleep climate platform."""
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api

    entities = [
        EightSleepThermostat(
            entry,
            config_entry_data.user_coordinator,
            eight,
            user,
            "climate",
            hass,
        )
        for user in eight.users.values()
    ]

    async_add_entities(entities)


class EightSleepThermostat(EightSleepBaseEntity, ClimateEntity):
    """Representation of an Eight Sleep Thermostat device."""

    _attr_has_entity_name = True
    _attr_name = "Climate"
    _attr_hvac_modes = [HVACMode.HEAT_COOL, HVACMode.OFF]
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TARGET_TEMPERATURE
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser,
        sensor: str,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(entry, coordinator, eight, user, sensor)
        # Set temperature unit and ranges based on Home Assistant config
        self._attr_temperature_unit = hass.config.units.temperature_unit
        if self._attr_temperature_unit == UnitOfTemperature.CELSIUS:
            self._attr_min_temp = MIN_TEMP_C
            self._attr_max_temp = MAX_TEMP_C
        else:
            self._attr_min_temp = MIN_TEMP_F
            self._attr_max_temp = MAX_TEMP_F

        # device data seems to be more up-to-date than user data
        heating_level_key = f"{user.corrected_side_for_key}TargetHeatingLevel"
        heating_level = self._eight.device_data.get(heating_level_key)
        if heating_level is not None:
            try:
                # Ensure heating_level is treated as a number, pyEight.util.heating_level_to_temp can handle numeric types.
                numeric_heating_level = float(heating_level) # Or int() if API guarantees integers
                unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
                self._attr_target_temperature = heating_level_to_temp(numeric_heating_level, unit)
            except ValueError:
                _LOGGER.warning(f"Could not convert heating level '{heating_level}' to a number for key {heating_level_key}")

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        # device data seems to be more up-to-date than user data
        heating_level_key = f"{self._user_obj.corrected_side_for_key}HeatingLevel"
        heating_level = self._eight.device_data.get(heating_level_key)
        if heating_level is not None:
            try:
                numeric_heating_level = float(heating_level)
                unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
                return heating_level_to_temp(numeric_heating_level, unit)
            except ValueError:
                _LOGGER.warning(f"Could not convert heating level '{heating_level}' to a number for key {heating_level_key}")
                return None
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        if self._user_obj and self._user_obj.bed_state_type != "off":
            return HVACMode.HEAT_COOL
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation."""
        if not self._user_obj:
            return None

        if self._user_obj.bed_state_type == "off":
            return HVACAction.OFF

        if self._user_obj.now_heating:
            return HVACAction.HEATING
        if self._user_obj.now_cooling:
            return HVACAction.COOLING

        return HVACAction.IDLE

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        # Convert from Celsius to Fahrenheit
        heating_level_key = f"{self._user_obj.corrected_side_for_key}TargetHeatingLevel"
        raw_target_temp = self._eight.device_data.get(heating_level_key)
        if raw_target_temp is not None:
            try:
                numeric_raw_target_temp = float(raw_target_temp)
                unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
                return heating_level_to_temp(numeric_raw_target_temp, unit)
            except ValueError:
                _LOGGER.warning(f"Could not convert target heating level '{raw_target_temp}' to a number for key {heating_level_key}")
                # Fall through to return self._attr_target_temperature
        return self._attr_target_temperature

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (heat_cool or off)."""
        if not self._user_obj:
            return

        if hvac_mode == HVACMode.OFF:
            await self._user_obj.turn_off_side()
        else:
            await self._user_obj.turn_on_side()

        # Refresh state
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if not self._user_obj:
            return

        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if temperature < self.min_temp or temperature > self.max_temp:
            _LOGGER.warning(
                "Temperature %s out of range (min: %s, max: %s)",
                temperature,
                self.min_temp,
                self.max_temp,
            )
            return

        # Save target temperature
        self._attr_target_temperature = temperature

        unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
        level = temp_to_heating_level(temperature, unit)

        # Set temperature level with default duration
        await self._user_obj.set_heating_level(level, DEFAULT_DURATION)
        await self._eight.update_device_data()
        # Refresh state
        await self.coordinator.async_refresh()
