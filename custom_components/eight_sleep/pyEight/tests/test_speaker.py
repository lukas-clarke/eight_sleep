"""Tests for Eight Sleep speaker functionality."""
import unittest
from unittest.mock import AsyncMock, patch

from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.pyEight.constants import APP_API_URL
from custom_components.eight_sleep.pyEight.exceptions import RequestError


class TestEightUserSpeaker(unittest.IsolatedAsyncioTestCase):
    """Tests for speaker methods in EightUser class."""

    def setUp(self):
        self.mock_eight_device = AsyncMock(spec=EightSleep)
        self.mock_eight_device.timezone = "America/New_York"
        self.mock_eight_device.device_data = {}
        self.mock_eight_device.device_id = "fake_device_id"

        self.user_id = "test_user_123"
        self.user_side = "left"
        self.user = EightUser(self.mock_eight_device, self.user_id, self.user_side)

    async def test_update_player_state_successful(self):
        """Test successful player state update."""
        self.mock_eight_device.api_request = AsyncMock(return_value={
            "state": "Playing",
            "volume": 50,
            "currentTrack": {"id": "white-noise", "name": "White noise"},
            "hardwareInfo": {"sku": "Minami"}
        })

        await self.user.update_player_state()

        expected_url = APP_API_URL + f"v1/users/{self.user_id}/audio/player"
        self.mock_eight_device.api_request.assert_called_once_with("get", expected_url)
        self.assertEqual(self.user.player_state["state"], "Playing")
        self.assertEqual(self.user.player_state["volume"], 50)

    async def test_update_player_state_request_error(self):
        """Test player state update handles RequestError gracefully."""
        self.mock_eight_device.api_request = AsyncMock(side_effect=RequestError("API Error"))

        await self.user.update_player_state()

        self.assertIsNone(self.user.player_state)

    async def test_fetch_audio_tracks_successful(self):
        """Test successful audio tracks fetch."""
        self.mock_eight_device.api_request = AsyncMock(return_value={
            "tracks": [
                {"id": "white-noise", "name": "White noise", "categoryId": "soundscapes"},
                {"id": "brown-noise", "name": "Brown noise", "categoryId": "soundscapes"},
            ]
        })

        await self.user.fetch_audio_tracks()

        expected_url = APP_API_URL + f"v1/users/{self.user_id}/audio/tracks"
        self.mock_eight_device.api_request.assert_called_once_with("get", expected_url)
        self.assertEqual(len(self.user.audio_tracks), 2)
        self.assertEqual(self.user.audio_tracks[0]["id"], "white-noise")

    async def test_fetch_audio_tracks_request_error(self):
        """Test audio tracks fetch handles RequestError gracefully."""
        self.mock_eight_device.api_request = AsyncMock(side_effect=RequestError("API Error"))

        await self.user.fetch_audio_tracks()

        self.assertEqual(self.user.audio_tracks, [])

    async def test_set_player_state_playing(self):
        """Test setting player state to Playing."""
        self.mock_eight_device.api_request = AsyncMock(return_value={})

        await self.user.set_player_state("Playing")

        expected_url = APP_API_URL + f"v1/users/{self.user_id}/audio/player/state"
        self.mock_eight_device.api_request.assert_called_once_with(
            "put", expected_url, data={"state": "Playing"}
        )

    async def test_set_player_state_paused(self):
        """Test setting player state to Paused."""
        self.mock_eight_device.api_request = AsyncMock(return_value={})

        await self.user.set_player_state("Paused")

        expected_url = APP_API_URL + f"v1/users/{self.user_id}/audio/player/state"
        self.mock_eight_device.api_request.assert_called_once_with(
            "put", expected_url, data={"state": "Paused"}
        )

    async def test_set_player_volume(self):
        """Test setting player volume."""
        self.mock_eight_device.api_request = AsyncMock(return_value={})

        await self.user.set_player_volume(75)

        expected_url = APP_API_URL + f"v1/users/{self.user_id}/audio/player/volume"
        self.mock_eight_device.api_request.assert_called_once_with(
            "put", expected_url, data={"volume": 75}
        )

    async def test_set_player_track_default_stop_criteria(self):
        """Test setting player track with default stop criteria."""
        self.mock_eight_device.api_request = AsyncMock(return_value={})

        await self.user.set_player_track("brown-noise")

        expected_url = APP_API_URL + f"v1/users/{self.user_id}/audio/player/currentTrack"
        self.mock_eight_device.api_request.assert_called_once_with(
            "put", expected_url, data={"id": "brown-noise", "stopCriteria": "ManualStop"}
        )

    async def test_set_player_track_custom_stop_criteria(self):
        """Test setting player track with custom stop criteria."""
        self.mock_eight_device.api_request = AsyncMock(return_value={})

        await self.user.set_player_track("nsdr-10", stop_criteria="Duration")

        expected_url = APP_API_URL + f"v1/users/{self.user_id}/audio/player/currentTrack"
        self.mock_eight_device.api_request.assert_called_once_with(
            "put", expected_url, data={"id": "nsdr-10", "stopCriteria": "Duration"}
        )

    async def test_player_state_property_returns_none_initially(self):
        """Test player_state property returns None before update."""
        self.assertIsNone(self.user.player_state)

    async def test_audio_tracks_property_returns_empty_list_initially(self):
        """Test audio_tracks property returns empty list before fetch."""
        self.assertEqual(self.user.audio_tracks, [])


class TestEightSleepSpeaker(unittest.IsolatedAsyncioTestCase):
    """Tests for speaker detection in EightSleep class."""

    def setUp(self):
        self.email = "test@example.com"
        self.password = "password"
        self.timezone = "America/New_York"

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_has_speaker_false_by_default(self, mock_get_auth, MockAiohttpSession):
        """Test has_speaker is False by default."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)
        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session

        self.assertFalse(eight.has_speaker)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_fetch_device_list_sets_has_speaker_from_audio_feature(self, mock_get_auth, MockAiohttpSession):
        """Test fetch_device_list sets has_speaker when audio feature present."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)

        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "user": {"devices": ["dev123"], "features": ["cooling", "elevation", "audio"]}
        })
        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session

        await eight.fetch_device_list()

        self.assertTrue(eight.has_speaker)
        self.assertTrue(eight._is_pod)
        self.assertTrue(eight._has_base)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_speaker_user_returns_first_user_when_speaker_exists(self, mock_get_auth, MockAiohttpSession):
        """Test speaker_user returns first user when speaker is available."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)
        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session
        eight._has_speaker = True

        # Add a mock user
        mock_user = AsyncMock(spec=EightUser)
        mock_user.user_id = "user123"
        eight.users = {"user123": mock_user}

        self.assertEqual(eight.speaker_user, mock_user)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_speaker_user_returns_none_when_no_speaker(self, mock_get_auth, MockAiohttpSession):
        """Test speaker_user returns None when speaker not available."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)
        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session
        eight._has_speaker = False

        self.assertIsNone(eight.speaker_user)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_probe_speaker_availability_success(self, mock_get_auth, MockAiohttpSession):
        """Test probe returns True when hardwareInfo present in response."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)

        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "state": "Paused",
            "hardwareInfo": {"sku": "Minami", "hardwareVersion": "2"}
        })
        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session

        # Add a mock user for probe
        mock_user = AsyncMock(spec=EightUser)
        mock_user.user_id = "user123"
        eight.users = {"user123": mock_user}

        result = await eight._probe_speaker_availability()

        self.assertTrue(result)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_probe_speaker_availability_no_hardware_info(self, mock_get_auth, MockAiohttpSession):
        """Test probe returns False when no hardwareInfo in response."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)

        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"state": "Paused"})  # No hardwareInfo
        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session

        mock_user = AsyncMock(spec=EightUser)
        mock_user.user_id = "user123"
        eight.users = {"user123": mock_user}

        result = await eight._probe_speaker_availability()

        self.assertFalse(result)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_probe_speaker_availability_request_error(self, mock_get_auth, MockAiohttpSession):
        """Test probe returns False on RequestError (expected for devices without speaker)."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)

        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session

        # Mock api_request to raise RequestError
        eight.api_request = AsyncMock(side_effect=RequestError("404 Not Found"))

        mock_user = AsyncMock(spec=EightUser)
        mock_user.user_id = "user123"
        eight.users = {"user123": mock_user}

        result = await eight._probe_speaker_availability()

        self.assertFalse(result)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_probe_speaker_availability_no_users(self, mock_get_auth, MockAiohttpSession):
        """Test probe returns False when no users available."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)
        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session
        eight.users = {}  # No users

        result = await eight._probe_speaker_availability()

        self.assertFalse(result)

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_update_speaker_data_calls_user_method(self, mock_get_auth, MockAiohttpSession):
        """Test update_speaker_data delegates to speaker_user."""
        mock_get_auth.return_value = AsyncMock(bearer_token="token", expiration=9999999999)
        mock_aiohttp_session = MockAiohttpSession.return_value
        mock_aiohttp_session.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session
        eight._has_speaker = True

        mock_user = AsyncMock(spec=EightUser)
        mock_user.update_player_state = AsyncMock()
        eight.users = {"user123": mock_user}

        await eight.update_speaker_data()

        mock_user.update_player_state.assert_called_once()


if __name__ == '__main__':
    unittest.main()
