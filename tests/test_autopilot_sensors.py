"""Per-user Autopilot status and latest-session temperature adjustments."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorStateClass

from custom_components.eight_sleep.binary_sensor import async_setup_entry as setup_binary
from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.constants import APP_API_URL
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.exceptions import RequestError
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.sensor import async_setup_entry as setup_sensor

DETAILS = {
    "isAutopilotActive": True,
    "hasActiveSubscription": False,
    "userMode": {"autopilotMode": "automatic", "autopilotToggledOn": False},
    "calibrationStatus": {"isCalibrated": False, "isFirstSessionAfterCalibration": True},
}
DAY = {
    "presenceStart": "2026-09-14T23:17:29.456-05:00",
    "presenceEnd": "2026-09-15T09:43:51.789-05:00",
}
EARLY = {
    "eventTime": "2026-09-15T05:21:32Z", "actionType": "autopilot-update",
    "previousLevel": -23, "currentLevel": 17,
    "currentPhase": "smart:initial", "previousPhase": "smart:bedtime",
}
LATE = {
    "eventTime": "2026-09-15T12:34:56Z", "actionType": "autopilot-update",
    "previousLevel": 31, "currentLevel": -9,
    "currentPhase": "smart:final", "previousPhase": "smart:initial",
}
EVENTS = [LATE, {"actionType": "dial-update", "previousLevel": 42},
          {"actionType": "settings-update"}, EARLY, {"actionType": "smart"}]


@pytest.fixture
def user():
    device = AsyncMock(spec=EightSleep)
    device.device_id = "invented-pod"
    device.device_data = {}
    user = EightUser(device, "invented-sleeper", "right")
    user.trends = [DAY.copy()]
    # Keep the normal update orchestration, isolating the pre-existing endpoints.
    user.get_user_side = AsyncMock(return_value="right")
    user.update_trend_data = AsyncMock()
    user.update_routines_data = AsyncMock()
    user.get_bed_state_type = AsyncMock(return_value="off")
    user._update_temperature_data = AsyncMock()
    user.update_pillow_data = AsyncMock()

    async def response(method, url, **kwargs):
        if url.endswith("/autopilotDetails"):
            return DETAILS.copy()
        if url.endswith("/temp-events"):
            return {"events": EVENTS, "phases": [{"phaseName": "ignored"}]}
        raise AssertionError(url)

    device.api_request.side_effect = response
    return user


async def entities(user):
    eight = MagicMock()
    eight.device_id = "invented-pod"
    eight.users = {user.user_id: user}
    eight.base_user = None
    data = MagicMock()
    data.api = eight
    entry = MagicMock(entry_id="invented-entry")
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: data}}
    added = []
    with patch("custom_components.eight_sleep.sensor.async_get_current_platform", return_value=MagicMock()):
        await setup_sensor(hass, entry, added.extend)
    await setup_binary(hass, entry, added.extend)
    return {entity._sensor: entity for entity in added}


@pytest.mark.asyncio
async def test_entities_and_session_window(user):
    await user.update_user()
    sensors = await entities(user)
    active = sensors["autopilot_active"]
    assert active.is_on is True
    assert active.extra_state_attributes == {"autopilot_mode": "automatic", "calibrated": False}
    adjustments = sensors["autopilot_adjustments"]
    assert adjustments.native_value == 2
    assert adjustments.native_unit_of_measurement is None
    assert adjustments.state_class == SensorStateClass.MEASUREMENT
    assert adjustments.extra_state_attributes == {
        "manual_adjustments": 1,
        "adjustments": [
            {"time": EARLY["eventTime"], "from_level": -23, "to_level": 17, "phase": "smart:initial"},
            {"time": LATE["eventTime"], "from_level": 31, "to_level": -9, "phase": "smart:final"},
        ],
    }
    user.device.api_request.assert_any_await(
        "get", APP_API_URL + "v1/users/invented-sleeper/temp-events",
        params={"from": "2026-09-15T04:17:29.000Z", "to": "2026-09-15T14:43:51.000Z"},
    )
    user.device.api_request.assert_any_await(
        "get", APP_API_URL + "v1/users/invented-sleeper/autopilotDetails",
    )


@pytest.mark.asyncio
async def test_hourly_throttling_and_independent_timers(user):
    await user.update_user()
    await user.update_user()
    assert user.device.api_request.await_count == 2
    user._last_autopilot_details_update -= timedelta(hours=2)
    await user.update_user()
    assert user.device.api_request.await_count == 3
    user._last_autopilot_events_update -= timedelta(hours=2)
    await user.update_user()
    assert user.device.api_request.await_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    RequestError("invented outage"), None, [],
    {"events": [None], "userMode": []}, {"events": "invalid", "userMode": []},
])
async def test_failures_preserve_previous_values(user, failure):
    await user.update_user()
    before = (user.autopilot_active, user.autopilot_attributes,
              user.autopilot_adjustments, user.autopilot_adjustment_attributes)
    user._last_autopilot_details_update -= timedelta(hours=2)
    user._last_autopilot_events_update -= timedelta(hours=2)
    if isinstance(failure, RequestError):
        user.device.api_request.side_effect = failure
    else:
        user.device.api_request.side_effect = None
        user.device.api_request.return_value = failure
    await user.update_user()
    assert (user.autopilot_active, user.autopilot_attributes,
            user.autopilot_adjustments, user.autopilot_adjustment_attributes) == before
    await user.update_user()
    assert user.device.api_request.await_count == 4


@pytest.mark.asyncio
async def test_missing_fields_and_missing_session(user):
    user.trends = [{"presenceStart": "None"}]
    user.device.api_request.side_effect = None
    user.device.api_request.return_value = {}
    await user.update_user()
    sensors = await entities(user)
    assert sensors["autopilot_active"].is_on is None
    assert sensors["autopilot_active"].extra_state_attributes == {"autopilot_mode": None, "calibrated": None}
    assert sensors["autopilot_adjustments"].native_value is None
    assert user.device.api_request.await_count == 1
    assert user._last_autopilot_events_update is None


@pytest.mark.asyncio
async def test_missing_end_uses_utc_now(user):
    user.trends = [{"presenceStart": DAY["presenceStart"], "presenceEnd": "None"}]
    now = datetime(2026, 9, 15, 16, 27, 38, 987654, tzinfo=timezone.utc)
    with patch("custom_components.eight_sleep.pyEight.user.datetime") as clock:
        clock.now.return_value = now
        clock.fromisoformat.side_effect = datetime.fromisoformat
        await user.update_autopilot_events()
    assert user.device.api_request.await_args.kwargs["params"] == {
        "from": "2026-09-15T04:17:29.000Z", "to": "2026-09-15T16:27:38.000Z",
    }


@pytest.mark.asyncio
async def test_adjustment_list_is_capped_but_count_is_not(user):
    events = [dict(EARLY, eventTime=f"2026-09-15T06:{minute:02d}:00Z") for minute in range(55)]
    user.device.api_request.side_effect = None
    user.device.api_request.return_value = {"events": list(reversed(events))}
    await user.update_autopilot_events()
    assert user.autopilot_adjustments == 55
    adjustments = user.autopilot_adjustment_attributes["adjustments"]
    assert len(adjustments) == 50
    assert [item["time"] for item in adjustments] == [event["eventTime"] for event in events[:50]]


@pytest.mark.asyncio
async def test_new_session_refetches_events_within_the_hour():
    """A new night must not keep showing the previous night's count."""
    user = EightUser(AsyncMock(spec=EightSleep), "user-new-night", "left")
    user.trends = [{"day": "2026-09-18", "presenceStart": "2026-09-18T04:00:00.000Z"}]
    user.device.api_request = AsyncMock(return_value={"events": []})

    await user.update_autopilot_events()
    await user.update_autopilot_events()
    assert user.device.api_request.await_count == 1

    # presenceStart moves during a session; that alone must not refetch.
    user.trends = [{"day": "2026-09-18", "presenceStart": "2026-09-18T04:07:00.000Z"}]
    await user.update_autopilot_events()
    assert user.device.api_request.await_count == 1

    user.trends = [{"day": "2026-09-19", "presenceStart": "2026-09-19T04:30:00.000Z"}]
    await user.update_autopilot_events()
    assert user.device.api_request.await_count == 2


@pytest.mark.asyncio
async def test_failed_fetch_on_a_new_night_does_not_show_the_last_one():
    user = EightUser(AsyncMock(spec=EightSleep), "user-failed-night", "left")
    user.trends = [{"day": "2026-09-18", "presenceStart": "2026-09-18T04:00:00.000Z"}]
    user.device.api_request = AsyncMock(return_value={"events": [
        {"eventTime": "2026-09-18T05:00:00Z", "actionType": "autopilot-update",
         "previousLevel": 3, "currentLevel": 7, "currentPhase": "smart:bedtime"},
    ]})
    await user.update_autopilot_events()
    assert user.autopilot_adjustments == 1

    user.trends = [{"day": "2026-09-19", "presenceStart": "2026-09-19T04:30:00.000Z"}]
    user.device.api_request = AsyncMock(side_effect=RequestError("offline"))
    await user.update_autopilot_events()
    assert user.autopilot_adjustments is None
