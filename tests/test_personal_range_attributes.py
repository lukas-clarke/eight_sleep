"""Heart rate, HRV and breath rate sensors carry the user's personal range.

The trends response the integration already fetches scores each of these
metrics against a range Eight Sleep learns from the user's own nights
(`sleepQualityScore.<metric>.lowerRange/upperRange/inclusive7DayAverage`).
The values below differ per metric so an attribute read from the wrong
metric fails.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.sensor import async_setup_entry

DAY = {
    "day": "2026-08-21",
    "sleepQualityScore": {
        "heartRate": {"current": 61, "lowerRange": 49.5, "upperRange": 63.25, "inclusive7DayAverage": 52.75},
        "hrv": {"current": 44.5, "lowerRange": 37.25, "upperRange": 48.75, "inclusive7DayAverage": 41.5},
        "respiratoryRate": {"current": 12.25, "lowerRange": 10.5, "upperRange": 17.75, "inclusive7DayAverage": 11.75},
    },
}

EXPECTED = {
    "current_heart_rate": (61, 49.5, 63.25, 52.75),
    "current_hrv": (44.5, 37.25, 48.75, 41.5),
    "current_breath_rate": (12.25, 10.5, 17.75, 11.75),
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
async def test_sensors_carry_the_personal_range():
    sensors = await _setup_sensors([DAY])

    for key, (night, low, high, avg) in EXPECTED.items():
        attrs = sensors[key].extra_state_attributes
        assert attrs["Scored Night Value"] == night, key
        assert attrs["Personal Range Low"] == low, key
        assert attrs["Personal Range High"] == high, key
        assert attrs["7-Day Average"] == avg, key


@pytest.mark.asyncio
async def test_other_current_sensors_do_not_get_a_range():
    sensors = await _setup_sensors([DAY])

    attrs = sensors["current_sleep_quality_score"].extra_state_attributes
    assert "Personal Range Low" not in attrs


@pytest.mark.asyncio
async def test_range_is_absent_without_the_metric():
    sensors = await _setup_sensors([{"day": "2026-08-21", "score": 69}])

    for key in EXPECTED:
        assert "Personal Range Low" not in sensors[key].extra_state_attributes, key
