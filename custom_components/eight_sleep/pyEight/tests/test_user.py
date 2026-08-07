import asyncio
import unittest
from unittest.mock import AsyncMock, patch, call # Add 'call' for checking multiple calls
from datetime import datetime, timedelta, timezone # Import datetime for away_mode test

# Assuming similar import structure as test_auth.py
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.pyEight.constants import APP_API_URL
from custom_components.eight_sleep.pyEight.exceptions import RequestError # For URL construction

class TestEightUser(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Mock EightSleep device instance.
        # Tests for EightUser will typically mock calls to self.device.api_request
        self.mock_eight_device = AsyncMock(spec=EightSleep)
        self.mock_eight_device.timezone = "America/New_York" # Needed for convert_string_to_datetime

        # Mock device_data on the EightSleep instance if properties rely on it directly
        self.mock_eight_device.device_data = {}
        self.mock_eight_device.device_id = "fake_device_id_for_user_tests"


        self.user_id = "test_user_123"
        self.user_side = "left"
        self.user = EightUser(self.mock_eight_device, self.user_id, self.user_side)

    async def test_set_heating_level(self):
        # Reset mock for each test
        self.mock_eight_device.api_request = AsyncMock()
        # Mock the get_current_heating_level call made before turning on side if needed
        # For set_heating_level, it calls turn_on_side() first.
        # turn_on_side() also calls api_request.

        # To simplify, we can assume turn_on_side works or mock its specific api_request call.
        # Let's mock the sequence of calls expected from set_heating_level:
        # 1. PUT to .../temperature for turn_on_side {"currentState": {"type": "smart"}}
        # 2. PUT to .../temperature for set_heating_level {"currentLevel": 50}
        # 3. PUT to .../temperature for set_heating_level {"timeBased": {"level": 50, "durationSeconds": 7200}}

        self.mock_eight_device.api_request.return_value = {} # Successful API call returns something

        await self.user.set_heating_level(level=50, duration=7200)

        expected_url = f"{APP_API_URL}v1/users/{self.user_id}/temperature"

        # Check the calls made to api_request
        self.assertEqual(self.mock_eight_device.api_request.call_count, 3)

        calls = self.mock_eight_device.api_request.call_args_list

        # Call 1: turn_on_side
        self.assertEqual(calls[0], call('PUT', expected_url, data={'currentState': {'type': 'smart'}}))

        # Call 2: set_heating_level (currentLevel)
        self.assertEqual(calls[1], call('PUT', expected_url, data={'currentLevel': 50}))

        # Call 3: set_heating_level (timeBased)
        self.assertEqual(calls[2], call('PUT', expected_url, data={'timeBased': {'level': 50, 'durationSeconds': 7200}}))

    async def test_set_heating_level_without_powering_on(self):
        self.mock_eight_device.api_request = AsyncMock(return_value={})

        await self.user.set_heating_level(level=50, duration=7200, power_on=False)

        expected_url = f"{APP_API_URL}v1/users/{self.user_id}/temperature"
        self.assertEqual(self.mock_eight_device.api_request.call_count, 2)

        calls = self.mock_eight_device.api_request.call_args_list
        self.assertEqual(calls[0], call('PUT', expected_url, data={'currentLevel': 50}))
        self.assertEqual(calls[1], call('PUT', expected_url, data={'timeBased': {'level': 50, 'durationSeconds': 7200}}))

    @patch('custom_components.eight_sleep.pyEight.user.datetime') # Mock datetime within user.py
    async def test_set_away_mode_start(self, mock_datetime):
        self.mock_eight_device.api_request = AsyncMock(return_value={})

        # Mock datetime.utcnow() to return a fixed time for predictable payload
        fixed_utcnow = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.utcnow.return_value = fixed_utcnow

        # The method calculates 'now' as 24 hours ago
        expected_api_timestamp = (fixed_utcnow - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        await self.user.set_away_mode("start")

        expected_url = f"{APP_API_URL}v1/users/{self.user_id}/away-mode"
        expected_payload = {"awayPeriod": {"start": expected_api_timestamp}}

        self.mock_eight_device.api_request.assert_called_once_with(
            'PUT', expected_url, data=expected_payload
        )

    async def test_current_hrv_property_with_data(self):
        # Mock the user's trends data
        self.user.trends = [
            { # Trend 0 (current)
                "sessions": [{
                    "timeseries": { "heartRate": [["ts", 60]] }, # Minimal timeseries
                }],
                "sleepQualityScore": {
                    "hrv": {"current": 55.0}
                }
            }
        ]
        self.assertEqual(self.user.current_hrv, 55.0)

    async def test_current_hrv_property_no_data(self):
        self.user.trends = [] # No trend data
        self.assertIsNone(self.user.current_hrv)

    async def test_current_hrv_property_missing_keys(self):
        self.user.trends = [
            {
                "sessions": [{}],
                "sleepQualityScore": {} # Missing hrv or current
            }
        ]
        self.assertIsNone(self.user.current_hrv)

    async def test_current_hrv_property_string_none(self):
        # Test the fix for string "None"
        self.user.trends = [
            {
                "sessions": [{}],
                "sleepQualityScore": {
                    "hrv": {"current": "None"}
                }
            }
        ]
        self.assertIsNone(self.user.current_hrv)

    async def test_corrected_side_for_key(self):
        self.assertEqual(self.user.corrected_side_for_key, "left")

        self.user.side = "right"
        self.assertEqual(self.user.corrected_side_for_key, "right")

        self.user.side = "solo"
        self.assertEqual(self.user.corrected_side_for_key, "left")

        with patch('custom_components.eight_sleep.pyEight.user._LOGGER') as mock_logger:
            self.user.side = None
            self.assertEqual(self.user.corrected_side_for_key, "left")
            mock_logger.warning.assert_called_once()


def _pillow_resp():
    """Fresh copy per test: these dicts get mutated in place."""
    return {
        "devices": [
            {
                "device": {"deviceId": "pillow_1", "side": "left", "specialization": "pillow"},
                "currentLevel": 10,
                "currentDeviceLevel": -28,
                "overrideLevels": {},
                "currentState": {"type": "smart:bedtime"},
                "smart": {"bedTimeLevel": 17, "initialSleepLevel": -35, "finalSleepLevel": -19},
            }
        ],
        "temperatureSettings": [{"name": "pillow", "bedTimeLevel": 17}],
    }


class TestEightUserPillow(unittest.IsolatedAsyncioTestCase):
    """Pillow support via /temperature/{pod|pillow|all} (#138)."""

    def setUp(self):
        self.mock_eight_device = AsyncMock(spec=EightSleep)
        self.mock_eight_device.timezone = "America/New_York"
        self.mock_eight_device.device_data = {}
        self.mock_eight_device.device_id = "fake_device_id"
        self.user = EightUser(self.mock_eight_device, "test_user_123", "left")

    async def test_no_pillow_before_any_fetch(self):
        self.assertFalse(self.user.has_pillow)
        self.assertIsNone(self.user.pillow_level)
        self.assertFalse(self.user.pillow_is_on)

    async def test_update_pillow_data_populates_state(self):
        self.mock_eight_device.api_request = AsyncMock(return_value=_pillow_resp())

        await self.user.update_pillow_data()

        self.assertTrue(self.user.has_pillow)
        self.assertEqual(self.user.pillow_level, 10)
        self.assertEqual(self.user.pillow_state, "smart:bedtime")
        self.assertTrue(self.user.pillow_is_on)
        url = self.mock_eight_device.api_request.await_args[0][1]
        self.assertTrue(url.endswith("/temperature/pillow"))

    async def test_bed_without_pillow_reports_none(self):
        """An empty devices list must leave has_pillow False, not raise."""
        self.mock_eight_device.api_request = AsyncMock(return_value={"devices": []})

        await self.user.update_pillow_data()

        self.assertFalse(self.user.has_pillow)
        self.assertIsNone(self.user.pillow_level)

    async def test_pillow_fetch_failure_does_not_propagate(self):
        """A failed pillow lookup must not abort the whole user update."""
        self.mock_eight_device.api_request = AsyncMock(side_effect=RequestError("boom"))

        await self.user.update_pillow_data()

        self.assertFalse(self.user.has_pillow)

    async def test_pillow_off_reports_not_on(self):
        resp = {"devices": [{"device": {}, "currentLevel": 0, "currentState": {"type": "off"}}]}
        self.mock_eight_device.api_request = AsyncMock(return_value=resp)

        await self.user.update_pillow_data()

        self.assertTrue(self.user.has_pillow)
        self.assertFalse(self.user.pillow_is_on)

    async def test_set_level_powers_on_first_when_off(self):
        """Writing a level to an off pillow is a silent no-op at the API."""
        self.mock_eight_device.api_request = AsyncMock(return_value=_pillow_resp())
        await self.user.update_pillow_data()
        self.user._pillow_data["devices"][0]["currentState"] = {"type": "off"}
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.set_pillow_level(20)

        cuerpos = [c.kwargs.get("data") for c in self.mock_eight_device.api_request.await_args_list]
        self.assertEqual(cuerpos[0], {"currentState": {"type": "smart"}})
        self.assertEqual(cuerpos[1], {"currentLevel": 20})

    async def test_set_level_skips_power_on_when_already_on(self):
        self.mock_eight_device.api_request = AsyncMock(return_value=_pillow_resp())
        await self.user.update_pillow_data()
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.set_pillow_level(20)

        self.assertEqual(self.mock_eight_device.api_request.await_count, 1)

    async def test_set_level_clamps_to_api_range(self):
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.set_pillow_level(500, power_on=False)
        await self.user.set_pillow_level(-500, power_on=False)

        cuerpos = [c.kwargs.get("data") for c in self.mock_eight_device.api_request.await_args_list]
        self.assertEqual(cuerpos[0], {"currentLevel": 100})
        self.assertEqual(cuerpos[1], {"currentLevel": -100})

    async def test_turn_on_and_off_use_the_pillow_route(self):
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.turn_on_pillow()
        await self.user.turn_off_pillow()

        for call_args in self.mock_eight_device.api_request.await_args_list:
            self.assertTrue(call_args[0][1].endswith("/temperature/pillow"))


if __name__ == '__main__':
    unittest.main()
