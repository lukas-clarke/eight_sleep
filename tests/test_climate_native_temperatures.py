from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import UnitOfTemperature

from custom_components.eight_sleep import EightSleepBaseEntity
from custom_components.eight_sleep.climate import (
    DEFAULT_DURATION,
    EightSleepPillowThermostat,
    EightSleepThermostat,
)
from custom_components.eight_sleep.pyEight.util import (
    heating_level_to_temp,
    temp_to_heating_level,
)


def make_thermostat(entity_type, unit, level):
    hass = MagicMock()
    hass.config.units.temperature_unit = unit
    coordinator = MagicMock(hass=hass)
    coordinator.async_refresh = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    eight = MagicMock(device_id="pod")
    eight.device_data = {"leftHeatingLevel": level, "leftTargetHeatingLevel": level}
    eight.update_device_data = AsyncMock()
    user = MagicMock(
        user_id="user",
        corrected_side_for_key="left",
        bed_state_type="on",
        pillow_level=level,
    )
    user.set_heating_level = AsyncMock()
    user.set_pillow_level = AsyncMock()
    return entity_type(MagicMock(), coordinator, eight, user, "climate", hass)


@pytest.mark.parametrize(
    "entity_type,properties",
    [
        (EightSleepThermostat, ("current_temperature", "target_temperature")),
        (EightSleepPillowThermostat, ("temperature_unit", "target_temperature")),
    ],
)
def test_temperature_properties_use_native_api(entity_type, properties):
    for name in properties:
        assert f"native_{name}" in entity_type.__dict__
        assert name not in entity_type.__dict__


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_type", [EightSleepThermostat, EightSleepPillowThermostat]
)
@pytest.mark.parametrize(
    "unit,api_unit,minimum,maximum",
    [
        (UnitOfTemperature.CELSIUS, "C", 13, 43),
        (UnitOfTemperature.FAHRENHEIT, "F", 55, 110),
    ],
)
@pytest.mark.parametrize("level", [-100, -40, 0, 40, 100])
async def test_native_temperatures_preserve_readings_and_commands(
    entity_type, unit, api_unit, minimum, maximum, level
):
    entity = make_thermostat(entity_type, unit, level)
    expected = heating_level_to_temp(level, api_unit)
    assert entity.native_temperature_unit == unit
    assert entity.target_temperature_step == 1
    assert entity.native_target_temperature == expected
    assert (entity.min_temp, entity.max_temp) == (minimum, maximum)

    if entity_type is EightSleepThermostat:
        assert entity.native_current_temperature == expected
        entity._user_obj.bed_state_type = "off"
        entity._eight.device_data["leftTargetHeatingLevel"] = 0
        assert entity.native_target_temperature == expected
        entity._user_obj.bed_state_type = "on"
    else:
        assert entity.native_current_temperature is None

    target = 30 if api_unit == "C" else 86
    await entity.async_set_temperature(temperature=target)
    expected_level = temp_to_heating_level(target, api_unit)
    if entity_type is EightSleepThermostat:
        entity._user_obj.set_heating_level.assert_awaited_once_with(
            expected_level, DEFAULT_DURATION, power_on=False
        )
        assert entity._attr_native_target_temperature == target
    else:
        entity._user_obj.set_pillow_level.assert_awaited_once_with(expected_level)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unit,api_unit",
    [(UnitOfTemperature.CELSIUS, "C"), (UnitOfTemperature.FAHRENHEIT, "F")],
)
async def test_restore_and_coordinator_sync_keep_native_target(unit, api_unit):
    entity = make_thermostat(EightSleepThermostat, unit, 0)
    restored = 30 if api_unit == "C" else 86
    with (
        patch.object(EightSleepBaseEntity, "async_added_to_hass", new=AsyncMock()),
        patch.object(
            entity,
            "async_get_last_state",
            new=AsyncMock(
                return_value=SimpleNamespace(attributes={"temperature": restored})
            ),
        ),
    ):
        await entity.async_added_to_hass()
    entity._user_obj.bed_state_type = "off"
    assert entity.native_target_temperature == restored

    entity._user_obj.bed_state_type = "on"
    entity._eight.device_data["leftTargetHeatingLevel"] = 40
    with patch.object(EightSleepBaseEntity, "_handle_coordinator_update"):
        entity._handle_coordinator_update()
    entity._user_obj.bed_state_type = "off"
    assert entity.native_target_temperature == heating_level_to_temp(40, api_unit)
