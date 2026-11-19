"""Turning a side on must leave Autopilot in charge (#179).

On turn-on the thermostat re-sent its stored target temperature. That value is
whatever the API last reported while the side was on, for example the level an
alarm warmed the bed to that morning. Since the setpoint no longer expires
(#160), turning the bed on from Home Assistant or Google held that level all
night instead of following Autopilot, unlike turning it on from the app.

Only a temperature the user set while the side was off (HomeKit sends "off"
together with a setpoint) is still applied on the next turn-on.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.eight_sleep.climate import (
    MAX_TEMP_C,
    MIN_TEMP_C,
    EightSleepThermostat,
)

ALARM_WARMED_TEMP = 33.0  # what the API reported this morning, after the alarm


def _thermostat(bed_state: str = "off") -> EightSleepThermostat:
    entity = EightSleepThermostat.__new__(EightSleepThermostat)
    entity._command_lock = asyncio.Lock()
    entity._pending_hvac_mode = None
    entity._pending_hvac_mode_request_id = 0
    entity._pending_hvac_mode_request_complete = False
    entity._hvac_mode_task = None
    entity._hvac_mode_task_mode = None
    entity._off_setpoint = None
    entity._attr_temperature_unit = "°C"
    entity._attr_min_temp = MIN_TEMP_C
    entity._attr_max_temp = MAX_TEMP_C
    entity._attr_target_temperature = ALARM_WARMED_TEMP

    user = MagicMock()
    user.bed_state_type = bed_state
    user.corrected_side_for_key = "left"
    user.turn_on_side = AsyncMock()
    user.turn_off_side = AsyncMock()
    user.set_heating_level = AsyncMock()
    entity._user_obj = user

    entity._eight = MagicMock()
    entity._eight.update_device_data = AsyncMock()
    entity._eight.device_data = {}
    entity.coordinator = MagicMock()
    entity.coordinator.async_refresh = AsyncMock()
    entity.coordinator.async_request_refresh = AsyncMock()
    entity.hass = MagicMock()
    entity.hass.async_create_task = asyncio.ensure_future
    entity.async_write_ha_state = MagicMock()
    return entity


@pytest.mark.asyncio
async def test_turning_on_does_not_resend_the_last_reported_level():
    entity = _thermostat("off")

    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)

    entity._user_obj.turn_on_side.assert_awaited_once()
    entity._user_obj.set_heating_level.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_temperature_set_while_off_is_applied_on_turn_on():
    entity = _thermostat("off")

    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 20.0})
    entity._user_obj.set_heating_level.assert_not_awaited()  # stored, not sent

    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)

    entity._user_obj.set_heating_level.assert_awaited_once()
    assert entity._attr_target_temperature == 20.0


@pytest.mark.asyncio
async def test_the_stored_setpoint_is_used_only_once():
    entity = _thermostat("off")
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 20.0})
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    await entity.async_set_hvac_mode(HVACMode.OFF)
    entity._user_obj.set_heating_level.reset_mock()

    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)

    entity._user_obj.set_heating_level.assert_not_awaited()


@pytest.mark.asyncio
async def test_turning_on_with_a_temperature_still_applies_it():
    entity = _thermostat("off")

    await entity.async_set_temperature(
        **{ATTR_TEMPERATURE: 20.0, "hvac_mode": HVACMode.HEAT_COOL}
    )

    entity._user_obj.turn_on_side.assert_awaited_once()
    entity._user_obj.set_heating_level.assert_awaited()
    assert entity._attr_target_temperature == 20.0


def test_turning_on_outside_home_assistant_drops_the_stored_setpoint():
    entity = _thermostat("off")
    entity._off_setpoint = 20.0
    entity._user_obj.bed_state_type = "smart:bedtime"  # turned on from the app

    EightSleepThermostat._handle_coordinator_update(entity)

    assert entity._off_setpoint is None


@pytest.mark.asyncio
async def test_homekit_off_echo_is_not_kept_for_the_next_turn_on():
    # HomeKit turns a tile off with two concurrent calls: "off" and the
    # temperature it was displaying. That echo must not pin the next turn-on.
    entity = _thermostat("smart:bedtime")

    await asyncio.gather(
        entity.async_set_hvac_mode(HVACMode.OFF),
        entity.async_set_temperature(**{ATTR_TEMPERATURE: ALARM_WARMED_TEMP}),
    )
    entity._user_obj.bed_state_type = "off"
    EightSleepThermostat._handle_coordinator_update(entity)
    entity._user_obj.set_heating_level.reset_mock()

    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)

    entity._user_obj.set_heating_level.assert_not_awaited()
