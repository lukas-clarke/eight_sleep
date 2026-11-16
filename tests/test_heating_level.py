"""A temperature set through the thermostat must not expire after two hours.

The thermostat passed a fixed 7200 s duration to `set_heating_level`, which
then sent a `timeBased` override after the level. A temperature set from Home
Assistant, HomeKit or a dashboard lasted two hours and went back to the
schedule. The `heat_set` service can still ask for a duration.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eight_sleep.climate import EightSleepThermostat


@pytest.mark.asyncio
async def test_the_thermostat_sets_a_level_without_a_time_limit():
    entity = MagicMock()
    entity.temperature_unit = "°C"
    entity._user_obj.set_heating_level = AsyncMock()
    entity._eight.update_device_data = AsyncMock()
    entity.coordinator.async_refresh = AsyncMock()

    await EightSleepThermostat._async_apply_heating_level(entity, 30)

    entity._user_obj.set_heating_level.assert_awaited_once()
    args = entity._user_obj.set_heating_level.await_args
    assert len(args.args) == 1
    assert args.kwargs == {"power_on": False}
