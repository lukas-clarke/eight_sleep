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
        )
        for user in eight.users.values()
    ]

    async_add_entities(entities)


class EightSleepThermostat(EightSleepBaseEntity, ClimateEntity):
    """Representation of an Eight Sleep Thermostat device."""

    _attr_has_entity_name = True
    _attr_name = "Climate"
    _attr_hvac_modes = [HVACMode.HEAT_COOL, HVACMode.OFF]
    _attr_min_temp = MIN_TEMP_F
    _attr_max_temp = MAX_TEMP_F
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
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(entry, coordinator, eight, user, sensor)
        self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        # device data seems to be more up-to-date than user data
        heating_level = self._eight.device_data.get(f"{user.side}TargetHeatingLevel")
        if heating_level is not None:
            unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
            self._attr_target_temperature = heating_level_to_temp(heating_level, unit)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        # device data seems to be more up-to-date than user data
        heating_level = self._eight.device_data.get(
            f"{self._user_obj.side}HeatingLevel"
        )
        if heating_level is not None:
            unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
            return heating_level_to_temp(heating_level, unit)
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
        raw_target_temp = self._eight.device_data.get(
            f"{self._user_obj.side}TargetHeatingLevel"
        )
        if raw_target_temp is not None:
            unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
            return heating_level_to_temp(raw_target_temp, unit)
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
