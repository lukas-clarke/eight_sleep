import asyncio
import unittest
from unittest.mock import AsyncMock, patch, call # Add 'call' for checking multiple calls
from datetime import datetime, timedelta, timezone # Import datetime for away_mode test

# Assuming similar import structure as test_auth.py
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.pyEight.constants import APP_API_URL # For URL construction

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


class TestEightUserBase(unittest.IsolatedAsyncioTestCase):
    """Tests for bed base control when base data is missing or partial (#144)."""

    def setUp(self):
        self.mock_eight_device = AsyncMock(spec=EightSleep)
        self.mock_eight_device.timezone = "America/New_York"
        self.mock_eight_device.device_data = {}
        self.mock_eight_device.device_id = "fake_device_id"
        self.mock_eight_device.has_base = True
        self.user = EightUser(self.mock_eight_device, "test_user_123", "left")
        self.user._base_data = {}

    async def test_set_base_angle_without_base_data_still_sends_request(self):
        """An empty _base_data must not stop the command from reaching the API.

        `update_base_data` swallows a failed GET /base (the API answers 404
        BaseOffline when the frame is unplugged), leaving _base_data empty. The
        optimistic local write then raised KeyError *before* the POST, so the
        user's request was silently dropped.
        """
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.set_base_angle(leg_angle=10, torso_angle=20)

        self.mock_eight_device.api_request.assert_awaited_once()
        args, kwargs = self.mock_eight_device.api_request.await_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(kwargs["data"]["legAngle"], 10)
        self.assertEqual(kwargs["data"]["torsoAngle"], 20)

    async def test_set_base_angle_with_partial_base_data(self):
        """Only one of the two angle keys present must not raise either."""
        self.user._base_data = {"left": {"leg": {"currentAngle": 0}}}
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.set_base_angle(leg_angle=5, torso_angle=15)

        self.mock_eight_device.api_request.assert_awaited_once()

    async def test_set_base_angle_updates_local_state_when_present(self):
        """The optimistic local update must still happen when the keys exist."""
        self.user._base_data = {
            "left": {"leg": {"currentAngle": 0}, "torso": {"currentAngle": 0}}
        }
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.set_base_angle(leg_angle=7, torso_angle=12)

        self.assertEqual(self.user.leg_angle, 7)
        self.assertEqual(self.user.torso_angle, 12)

    async def test_set_base_preset_without_base_data_still_sends_request(self):
        """set_base_preset must survive empty base data the same way."""
        self.mock_eight_device.api_request = AsyncMock()

        await self.user.set_base_preset("sleep")

        self.mock_eight_device.api_request.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
