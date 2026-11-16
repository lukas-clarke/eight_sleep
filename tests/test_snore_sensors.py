"""Snoring history from the trends response becomes per-side sensors (#150).

The trends call the integration already makes (`/users/{id}/trends`,
model-version v2) returns, per day, `snoreDuration`, `heavySnoreDuration`
(seconds) and `snorePercent`, `heavySnorePercent`. The day below follows the
shape of a real response; the values differ from each other so a sensor
reading the wrong field fails.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.sensor import async_setup_entry

DAY = {
    "day": "2026-10-30",
    "score": 82,
    "sleepDuration": 25920,
    "snoreDuration": 1620,
    "heavySnoreDuration": 240,
    "snorePercent": 9,
    "heavySnorePercent": 1,
    "sessions": [
        {
            "snoring": [
                {"intensity": "none", "duration": 6900},
                {"intensity": "light", "duration": 60},
            ],
        }
    ],
}

EXPECTED = {
    "snore_duration": (1620, "s", SensorDeviceClass.DURATION),
    "heavy_snore_duration": (240, "s", SensorDeviceClass.DURATION),
    "snore_percent": (9, "%", None),
    "heavy_snore_percent": (1, "%", None),
}


async def _setup_sensors(trends: list[dict]) -> dict[str, object]:
    device = AsyncMock(spec=EightSleep)
    device.timezone = "America/New_York"
    device.device_data = {}
    device.device_id = "test-device-id"
    user = EightUser(device, "user-1", "left")
    user.trends = trends

    eight = MagicMock()
    eight.device_id = "test-device-id"
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


@pytest.mark.asyncio
async def test_snore_sensors_read_the_latest_day():
    sensors = await _setup_sensors([{"day": "2026-10-29", "snoreDuration": 99}, DAY])

    for key, (value, unit, device_class) in EXPECTED.items():
        sensor = sensors[key]
        assert sensor.native_value == value, key
        assert sensor.native_unit_of_measurement == unit, key
        assert sensor.device_class == device_class, key


@pytest.mark.asyncio
async def test_snore_sensors_are_none_without_snoring_data():
    """A day without the fields (or no trends yet) reads as None, not 0."""
    for trends in ([], [{"day": "2026-10-30", "score": 82}]):
        sensors = await _setup_sensors(trends)
        for key in EXPECTED:
            assert sensors[key].native_value is None, (key, trends)
