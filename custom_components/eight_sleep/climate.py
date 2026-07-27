"""Support for Eight Sleep climate control."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
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
from homeassistant.helpers.restore_state import RestoreEntity


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


class EightSleepThermostat(EightSleepBaseEntity, ClimateEntity, RestoreEntity):
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
        # Serialize on/off/set-level API calls so a concurrent "off" + "set
        # temperature" pair cannot reorder at the Eight Sleep server.
        self._command_lock = asyncio.Lock()
        self._pending_hvac_mode: HVACMode | None = None
        self._pending_hvac_mode_request_id = 0
        self._pending_hvac_mode_request_complete = False
        self._hvac_mode_task: asyncio.Task[Any] | None = None
        self._hvac_mode_task_mode: HVACMode | None = None
        # Set temperature unit and ranges based on Home Assistant config
        self._attr_temperature_unit = hass.config.units.temperature_unit
        if self._attr_temperature_unit == UnitOfTemperature.CELSIUS:
            self._attr_min_temp = MIN_TEMP_C
            self._attr_max_temp = MAX_TEMP_C
        else:
            self._attr_min_temp = MIN_TEMP_F
            self._attr_max_temp = MAX_TEMP_F

        # device data seems to be more up-to-date than user data
        # Only initialize target temperature from API if the device is currently ON.
        if user.bed_state_type != "off":
            heating_level_key = f"{user.corrected_side_for_key}TargetHeatingLevel"
            heating_level = self._eight.device_data.get(heating_level_key)
            if heating_level is not None:
                try:
                    # Ensure heating_level is treated as a number
                    numeric_heating_level = float(heating_level)
                    unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
                    self._attr_target_temperature = heating_level_to_temp(numeric_heating_level, unit)
                except ValueError:
                    _LOGGER.warning(f"Could not convert heating level '{heating_level}' to a number for key {heating_level_key}")

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant and restore previous temperature."""
        await super().async_added_to_hass()
        # Restore last known target temperature if available
        last_state = await self.async_get_last_state()
        if last_state:
            temp = last_state.attributes.get(ATTR_TEMPERATURE)
            if temp is not None:
                try:
                    self._attr_target_temperature = float(temp)
                    _LOGGER.debug("Restored target temperature %s from previous state", self._attr_target_temperature)
                except (ValueError, TypeError):
                    _LOGGER.warning("Failed to restore target temperature from state: %s", temp)

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
    def _api_hvac_mode(self) -> HVACMode:
        """Return the operation mode reported by the API."""
        if self._user_obj and self._user_obj.bed_state_type != "off":
            return HVACMode.HEAT_COOL
        return HVACMode.OFF

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        if (pending_hvac_mode := self._pending_hvac_mode) is not None:
            return pending_hvac_mode
        return self._api_hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation."""
        if not self._user_obj:
            return None

        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        if self._user_obj.now_heating:
            return HVACAction.HEATING
        if self._user_obj.now_cooling:
            return HVACAction.COOLING

        return HVACAction.IDLE

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        # If the device is OFF, show the last known user/autopilot target
        # instead of the API's reported "0" (27C).
        # When OFF, prefer the stored target temperature; if none, fall back to Autopilot schedule
        if self.hvac_mode == HVACMode.OFF:
            if self._attr_target_temperature is not None:
                _LOGGER.debug(f"Target Temp (OFF): Returning stored value {self._attr_target_temperature}")
                return self._attr_target_temperature
            # Try Autopilot temperature via user helper
            if self._user_obj:
                autopilot_temp = self._user_obj.get_autopilot_target_temp(
                    unit=convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
                )
                if autopilot_temp is not None:
                    _LOGGER.debug(f"Target Temp (OFF): Returning Autopilot value {autopilot_temp}")
                    return autopilot_temp
            # Fallback to stored (may be None)
            _LOGGER.debug("Target Temp (OFF): No stored or Autopilot value, returning None")
            return None

        # Otherwise, trust the API (which handles Autopilot changes)
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

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if (
            self._pending_hvac_mode is not None
            and self._pending_hvac_mode_request_complete
            and self._pending_hvac_mode == self._api_hvac_mode
        ):
            self._record_pending_hvac_mode(None)

        # When ON, sync the API's target temperature to our local storage
        # so we persist Autopilot changes if the user turns the device off.
        # Skip while a power command is pending: stale API values must not clobber a
        # setpoint the user just requested.
        if self._pending_hvac_mode is None and self._api_hvac_mode != HVACMode.OFF:
            heating_level_key = f"{self._user_obj.corrected_side_for_key}TargetHeatingLevel"
            raw_target_temp = self._eight.device_data.get(heating_level_key)
            if raw_target_temp is not None:
                try:
                    numeric_raw_target_temp = float(raw_target_temp)
                    unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
                    new_target = heating_level_to_temp(numeric_raw_target_temp, unit)
                    if self._attr_target_temperature != new_target:
                        _LOGGER.debug(f"Syncing Autopilot/External change: {self._attr_target_temperature} -> {new_target}")
                        self._attr_target_temperature = new_target
                except ValueError:
                    pass
        super()._handle_coordinator_update()

    def _record_pending_hvac_mode(self, hvac_mode: HVACMode | None) -> int:
        """Remember the last requested power state until the API confirms it."""
        # `turn_on_side()`/`turn_off_side()` do not update `bed_state_type` locally, so the
        # requested state must remain authoritative until a coordinator update confirms it.
        self._pending_hvac_mode = hvac_mode
        self._pending_hvac_mode_request_id += 1
        self._pending_hvac_mode_request_complete = False
        return self._pending_hvac_mode_request_id

    def _should_defer_temperature(self) -> bool:
        """Return True when a setpoint should be stored without powering the side on."""
        # Apple HomeKit turns a thermostat off by sending an "off" mode together with a target
        # temperature. When the side is off (or was just commanded off), remember the setpoint
        # for the next power-on instead of sending a time-based temperature override.
        if self._pending_hvac_mode is not None:
            return self._pending_hvac_mode == HVACMode.OFF
        return self._user_obj is not None and self._user_obj.bed_state_type == "off"

    async def _async_apply_heating_level(self, temperature: float) -> None:
        """Push a target temperature to the API without changing power state."""
        self._attr_target_temperature = temperature

        unit = convert_hass_temp_unit_to_pyeight_temp_unit(self.temperature_unit)
        level = temp_to_heating_level(temperature, unit)

        # Set temperature level with default duration
        await self._user_obj.set_heating_level(level, DEFAULT_DURATION, power_on=False)
        await self._eight.update_device_data()
        # Refresh state
        await self.coordinator.async_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (heat_cool or off)."""
        if not self._user_obj:
            return

        # HomeKit may send the same mode through both `set_hvac_mode` and
        # `set_temperature`. Let both service calls wait for one API command.
        if (
            self._hvac_mode_task is not None
            and self._hvac_mode_task_mode == hvac_mode
        ):
            await asyncio.shield(self._hvac_mode_task)
            return
        if self._pending_hvac_mode == hvac_mode:
            return

        # Record the intent synchronously so a concurrent `async_set_temperature`
        # sees it before deciding whether to send a temperature override.
        request_id = self._record_pending_hvac_mode(hvac_mode)
        task = self.hass.async_create_task(
            self._async_set_hvac_mode(hvac_mode, request_id)
        )
        self._hvac_mode_task = task
        self._hvac_mode_task_mode = hvac_mode
        try:
            await task
        finally:
            if self._hvac_mode_task is task:
                self._hvac_mode_task = None
                self._hvac_mode_task_mode = None

    async def _async_set_hvac_mode(
        self, hvac_mode: HVACMode, request_id: int
    ) -> None:
        """Send a serialized HVAC mode command."""
        power_command_succeeded = False
        try:
            async with self._command_lock:
                if hvac_mode == HVACMode.OFF:
                    await self._user_obj.turn_off_side()
                else:
                    await self._user_obj.turn_on_side()
                power_command_succeeded = True
                if request_id == self._pending_hvac_mode_request_id:
                    self._pending_hvac_mode_request_complete = True

                if hvac_mode != HVACMode.OFF:
                    # Restore the target temperature if we have one
                    if self._attr_target_temperature is not None:
                        _LOGGER.debug("Turn On: Restoring target temperature to %s", self._attr_target_temperature)
                        await self._async_apply_heating_level(self._attr_target_temperature)

            # Refresh state
            await self.coordinator.async_request_refresh()
        finally:
            if (
                not power_command_succeeded
                and request_id == self._pending_hvac_mode_request_id
            ):
                self._record_pending_hvac_mode(None)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if not self._user_obj:
            return

        requested_hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None and (
            temperature < self.min_temp or temperature > self.max_temp
        ):
            _LOGGER.warning(
                "Temperature %s out of range (min: %s, max: %s)",
                temperature,
                self.min_temp,
                self.max_temp,
            )
            temperature = None

        if temperature is not None:
            self._attr_target_temperature = temperature

        if requested_hvac_mode is not None:
            await self.async_set_hvac_mode(requested_hvac_mode)
            self.async_write_ha_state()
            if requested_hvac_mode == HVACMode.OFF:
                return

        if temperature is None:
            return

        async with self._command_lock:
            if self._should_defer_temperature():
                _LOGGER.debug("Set Temperature (OFF): storing %s without powering on", temperature)
                self.async_write_ha_state()
                return
            await self._async_apply_heating_level(temperature)
