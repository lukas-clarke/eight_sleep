"""Snore mitigation by the Base, from the trends response, as per-side sensors.

With a Base, each day of the trends response (`/users/{id}/trends`,
model-version v2) carries `mitigationEvents`, `snoringReductionPercent` and
`elevationDuration` (seconds). In real responses the reduction is
`(theoreticalSnorePercent - snorePercent) / theoreticalSnorePercent`; the day
below keeps that relation, and its values differ from each other so a sensor
reading the wrong field fails.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.sensor import (
    EIGHT_BASE_USER_SENSORS,
    async_setup_entry,
)

DAY = {
    "day": "2026-10-24",
    "sleepDuration": 27960,
    "snorePercent": 6,
    "theoreticalSnorePercent": 10,
    "mitigationEvents": 2,
    "stoppedSnoringEvents": 1,
    "reducedSnoringEvents": 1,
    "snoringReductionPercent": 40,
    "elevationDuration": 2700,
}

EXPECTED = {
    "snore_mitigation_events": (2, None, None),
    "snoring_reduction_percent": (40, "%", None),
    "elevation_duration": (2700, "s", SensorDeviceClass.DURATION),
}


async def _setup_sensors(trends: list[dict], has_base: bool) -> dict[str, object]:
    device = AsyncMock(spec=EightSleep)
    device.timezone = "America/New_York"
    device.device_data = {}
    device.device_id = "test-device-id"
    user = EightUser(device, "user-1", "left")
    user.trends = trends

    eight = MagicMock()
    eight.device_id = "test-device-id"
    eight.has_base = has_base
    eight.users = {"user-1": user}
    config_entry_data = MagicMock()
    config_entry_data.api = eight

    entry = MagicMock(entry_id="test_entry")
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: config_entry_data}}

    added: list = []
    with patch(
        "custom_components.eight_sleep.sensor.async_get_current_platform",
        return_value=MagicMock(),
    ):
        await async_setup_entry(hass, entry, added.extend)

    return {
        entity._sensor: entity
        for entity in added
        if getattr(entity, "_user_obj", None) is user
    }


def test_expected_covers_every_base_sensor():
    assert set(EXPECTED) == set(EIGHT_BASE_USER_SENSORS)


@pytest.mark.asyncio
async def test_base_sensors_read_the_latest_day():
    older = {"day": "2026-10-23", "mitigationEvents": 9, "elevationDuration": 99}
    sensors = await _setup_sensors([older, DAY], has_base=True)

    for key, (value, unit, device_class) in EXPECTED.items():
        sensor = sensors[key]
        assert sensor.native_value == value, key
        assert sensor.native_unit_of_measurement == unit, key
        assert sensor.device_class == device_class, key
        assert sensor.extra_state_attributes is None, key


@pytest.mark.asyncio
async def test_no_base_sensors_without_a_base():
    sensors = await _setup_sensors([DAY], has_base=False)

    assert not set(EIGHT_BASE_USER_SENSORS) & set(sensors)
    assert "time_slept" in sensors  # the side's other sensors are still there


@pytest.mark.asyncio
async def test_base_sensors_are_none_without_the_data():
    """A day without the fields (or no trends yet) reads as None, not 0."""
    for trends in ([], [{"day": "2026-10-24", "sleepDuration": 27960}]):
        sensors = await _setup_sensors(trends, has_base=True)
        for key in EXPECTED:
            assert sensors[key].native_value is None, (key, trends)
