"""Per-side sleep timing sensors and the hourly bedtime recommendation."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.constants import APP_API_URL
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.exceptions import RequestError
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.sensor import async_setup_entry

ZONE = ZoneInfo("America/Denver")
DAY = {
    "day": "2026-09-18",
    "performanceWindows": {
        "isAvailable": True,
        "performanceWindowStats": {"bedtimeBaseline": "22:31:12"},
        "exerciseWindow": {
            "exerciseWindowStart": "06:17:23",
            "exerciseWindowMidpoint": "07:18:24",
            "exerciseWindowEnd": "08:19:25",
        },
        "cognitiveWindow": {
            "cognitiveWindowStart": "09:21:31",
            "cognitiveWindowMidpoint": "10:22:32",
            "cognitiveWindowEnd": "11:23:33",
        },
        "chronotype": {"chronoClass": "early", "isCalibrating": False},
        "socialJetlag": {"socialJetlagSeconds": 4321},
    },
}
TIMES = {
    "exercise_window_start": (6, 17, 23),
    "exercise_window_end": (8, 19, 25),
    "cognitive_window_start": (9, 21, 31),
    "cognitive_window_end": (11, 23, 33),
}
RECOMMENDATION = {
    "recommendedBedtime": "22:41:19",
    "standardDeviation": "00:27:13",
    "daysAnalyzed": 73,
    "topPerformingDays": 18,
}
MODULE = "custom_components.eight_sleep.pyEight.user"


async def setup_sensors(trends):
    device = AsyncMock(spec=EightSleep)
    device.timezone = ZONE.key
    device.device_data = {}
    device.device_id = "timing-device"
    user = EightUser(device, "timing-user", "left")
    user.trends = trends
    eight = MagicMock(device_id=device.device_id, users={user.user_id: user})
    data = MagicMock(api=eight)
    entry = MagicMock(entry_id="timing-entry")
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: data}}
    added = []
    with patch("custom_components.eight_sleep.sensor.async_get_current_platform"):
        await async_setup_entry(hass, entry, added.extend)
    return user, {e._sensor: e for e in added if getattr(e, "_user_obj", None) is user}


@pytest.mark.asyncio
async def test_latest_day_and_sensor_metadata():
    user, sensors = await setup_sensors([{"day": "2026-09-17"}, DAY])
    for key, clock in TIMES.items():
        sensor = sensors[key]
        assert sensor.native_value == datetime(2026, 9, 18, *clock, tzinfo=ZONE)
        assert sensor.native_value.tzinfo == ZONE
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.state_class is None
    assert sensors["chronotype"].native_value == "early"
    assert sensors["chronotype"].state_class is None
    assert sensors["social_jetlag"].native_value == 4321
    assert sensors["social_jetlag"].native_unit_of_measurement == "s"
    assert sensors["social_jetlag"].device_class == SensorDeviceClass.DURATION
    user.device.api_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_calibrating_chronotype():
    day = deepcopy(DAY)
    day["performanceWindows"]["chronotype"]["isCalibrating"] = True
    _, sensors = await setup_sensors([day])
    assert sensors["chronotype"].native_value is None


@pytest.mark.asyncio
async def test_unavailable_and_missing_data():
    unavailable = deepcopy(DAY)
    unavailable["performanceWindows"]["isAvailable"] = False
    for trends in ([], [{}], [unavailable], [{"performanceWindows": {"isAvailable": True}}]):
        _, sensors = await setup_sensors(trends)
        for key in (*TIMES, "chronotype", "social_jetlag", "recommended_bedtime"):
            assert sensors[key].native_value is None


@pytest.mark.asyncio
async def test_bad_window_time_or_day():
    for field, value in (("day", "invalid"), ("day", "None")):
        day = deepcopy(DAY)
        day[field] = value
        _, sensors = await setup_sensors([day])
        for key in TIMES:
            assert sensors[key].native_value is None
    day = deepcopy(DAY)
    day["performanceWindows"]["exerciseWindow"]["exerciseWindowStart"] = "None"
    _, sensors = await setup_sensors([day])
    assert sensors["exercise_window_start"].native_value is None


@pytest.mark.asyncio
@pytest.mark.parametrize("hour, expected_day", [(21, 18), (23, 19)])
async def test_bedtime_next_occurrence(hour, expected_day):
    user, sensors = await setup_sensors([])
    user.device.api_request.return_value = RECOMMENDATION
    await user.update_bedtime_recommendation()
    with patch(MODULE + ".datetime", wraps=datetime) as clock:
        clock.now.return_value = datetime(2026, 9, 18, hour, tzinfo=ZONE)
        value = sensors["recommended_bedtime"].native_value
    assert value == datetime(2026, 9, expected_day, 22, 41, 19, tzinfo=ZONE)
    assert value.tzinfo == ZONE
    assert sensors["recommended_bedtime"].device_class == SensorDeviceClass.TIMESTAMP
    assert sensors["recommended_bedtime"].extra_state_attributes == {
        "standard_deviation": "00:27:13", "days_analyzed": 73,
    }
    user.device.api_request.assert_awaited_once_with(
        "get", APP_API_URL + "v1/users/timing-user/bedtime/recommendation"
    )


@pytest.mark.asyncio
async def test_update_user_throttles_recommendation():
    user, _ = await setup_sensors([])
    user.device.api_request.return_value = RECOMMENDATION
    for method in ("get_user_side", "update_trend_data", "update_routines_data",
                   "get_bed_state_type", "_update_temperature_data", "update_pillow_data"):
        setattr(user, method, AsyncMock(return_value="left" if method == "get_user_side" else None))
    now = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    with patch(MODULE + ".datetime", wraps=datetime) as clock:
        clock.now.return_value = now
        await user.update_user()
        clock.now.return_value = now + timedelta(minutes=59, seconds=59)
        await user.update_user()
        assert user.device.api_request.await_count == 1
        clock.now.return_value = now + timedelta(hours=1)
        await user.update_user()
        assert user.device.api_request.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [RequestError("offline"), None, [], {},
                                      {**RECOMMENDATION, "recommendedBedtime": "bad"}])
async def test_failed_refresh_retains_previous_value(response):
    user, sensors = await setup_sensors([])
    user.device.api_request.return_value = RECOMMENDATION
    await user.update_bedtime_recommendation()
    with patch(MODULE + ".datetime", wraps=datetime) as clock:
        # A fixed clock, so the two reads cannot straddle the bedtime.
        clock.now.return_value = datetime(2026, 9, 18, 12, tzinfo=ZONE)
        previous = sensors["recommended_bedtime"].native_value
    user._last_bedtime_recommendation_update -= timedelta(hours=1)
    if isinstance(response, RequestError):
        user.device.api_request.side_effect = response
    else:
        user.device.api_request.return_value = response
    await user.update_bedtime_recommendation()
    with patch(MODULE + ".datetime", wraps=datetime) as clock:
        clock.now.return_value = datetime(2026, 9, 18, 12, tzinfo=ZONE)
        assert sensors["recommended_bedtime"].native_value == previous
    assert sensors["recommended_bedtime"].extra_state_attributes["days_analyzed"] == 73
    await user.update_bedtime_recommendation()
    assert user.device.api_request.await_count == 2
