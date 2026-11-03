"""Sleep latency and sleep debt from the trends response become per-side sensors.

The trends call the integration already makes (`/users/{id}/trends`,
model-version v2) carries, per day, the seconds behind two routine scores
(`sleepRoutineScore.latencyAsleepSeconds.current`,
`sleepRoutineScore.latencyOutSeconds.current`) and the night's shortfall
against the sleep baseline (`sleepQualityScore.sleepDebt`). The day below
follows the shape of a real response; the values differ from each other so a
sensor reading the wrong field fails.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.sensor import async_setup_entry

DAY = {
    "day": "2026-08-21",
    "score": 69,
    "sleepDuration": 18180,
    "sleepQualityScore": {
        "total": 83,
        "sleepDebt": {
            "firstSleepDate": "2026-07-25",
            "dailySleepDebtSeconds": 6865.263157894737,
            "baselineSleepDurationSeconds": 25045.263157894737,
            "isCalibrating": False,
        },
    },
    "sleepRoutineScore": {
        "total": 70,
        "latencyAsleepSeconds": {"current": 2070, "average": 4326, "score": 0},
        "latencyOutSeconds": {"current": 1650, "average": 13.5, "score": 0},
    },
}

EXPECTED = {
    "sleep_latency": 2070,
    "out_of_bed_latency": 1650,
    "daily_sleep_debt": 6865,
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
async def test_sensors_read_the_latest_day():
    older = {
        "day": "2026-08-20",
        "sleepRoutineScore": {"latencyAsleepSeconds": {"current": 99}},
    }
    sensors = await _setup_sensors([older, DAY])

    for key, value in EXPECTED.items():
        sensor = sensors[key]
        assert sensor.native_value == value, key
        assert sensor.native_unit_of_measurement == "s", key
        assert sensor.device_class == SensorDeviceClass.DURATION, key
        # No "current"/"last" in the key, so no unrelated session attributes.
        assert sensor.extra_state_attributes is None, key


@pytest.mark.asyncio
async def test_sensors_are_none_without_the_data():
    """A day without the fields (or no trends yet) reads as None, not 0."""
    for trends in (
        [],
        [{"day": "2026-08-21", "score": 69}],
        [{"day": "2026-08-21", "sleepQualityScore": {"sleepDebt": {"isCalibrating": False}}}],
    ):
        sensors = await _setup_sensors(trends)
        for key in EXPECTED:
            assert sensors[key].native_value is None, (key, trends)


@pytest.mark.asyncio
async def test_sleep_debt_is_negative_after_a_night_above_baseline():
    """Real responses report a longer-than-baseline night as negative debt."""
    day = {
        "day": "2026-08-21",
        "sleepDuration": 31470,
        "sleepQualityScore": {
            "sleepDebt": {
                "dailySleepDebtSeconds": -6182.4,
                "baselineSleepDurationSeconds": 25287.6,
                "isCalibrating": False,
            },
        },
    }
    sensors = await _setup_sensors([day])

    assert sensors["daily_sleep_debt"].native_value == -6182


@pytest.mark.asyncio
async def test_sleep_debt_is_none_while_calibrating():
    day = {
        "day": "2026-08-21",
        "sleepQualityScore": {
            "sleepDebt": {"dailySleepDebtSeconds": 0, "isCalibrating": True},
        },
    }
    sensors = await _setup_sensors([day])

    assert sensors["daily_sleep_debt"].native_value is None
