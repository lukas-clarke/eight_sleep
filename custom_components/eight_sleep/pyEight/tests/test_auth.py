import asyncio
import time
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

# Attempt to import from the custom_components structure
# This might need adjustment based on how tests are run and PYTHONPATH
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.exceptions import RequestError

class TestAuth(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.email = "test@example.com"
        self.password = "password"
        self.timezone = "America/New_York"

    @patch('custom_components.eight_sleep.pyEight.eight.httpx.AsyncClient')
    async def test_get_auth_successful(self, MockAsyncClient):
        # Configure the mock httpx client instance and its post method
        mock_httpx_instance = MockAsyncClient.return_value # This is the client

        # This is the mock for the response object that `client.post` will return
        mock_response_object = MagicMock()
        mock_response_object.status_code = 200
        mock_response_object.json.return_value = { # .json() is a sync method for httpx
            "access_token": "fake_access_token",
            "expires_in": 3600, # 1 hour
            "userId": "fake_user_id_auth"
        }

        # Configure the client's post method (which is async) to return the mock_response_object
        mock_httpx_instance.post = AsyncMock(return_value=mock_response_object)

        eight = EightSleep(self.email, self.password, self.timezone)

        # Directly test _get_auth which is now feasible as it's an async method
        # We need to ensure the httpx_client is the mocked one if not passed in constructor
        # The constructor for EightSleep will create its own if not provided.
        # So, we can also patch 'httpx.AsyncClient' globally for this test.

        token_info = await eight._get_auth()

        self.assertEqual(token_info.bearer_token, "fake_access_token")
        self.assertEqual(token_info.main_id, "fake_user_id_auth") # Corrected to main_id
        self.assertAlmostEqual(token_info.expiration, time.time() + 3600, delta=5) # Check expiration time

        # Verify httpx.AsyncClient().post was called correctly
        mock_httpx_instance.post.assert_called_once()
        args, kwargs = mock_httpx_instance.post.call_args
        self.assertEqual(kwargs['json']['username'], self.email)

    @patch('custom_components.eight_sleep.pyEight.eight.httpx.AsyncClient')
    async def test_get_auth_failure(self, MockAsyncClient):
        mock_httpx_instance = MockAsyncClient.return_value # This is the client

        # This is the mock for the response object
        mock_response_object = MagicMock()
        mock_response_object.status_code = 400
        mock_response_object.json.return_value = {"error": "bad_request"} # .json() is sync
        mock_response_object.text = "Bad Request Details" # .text is a property or sync method

        # Configure the client's post method (which is async) to return the mock_response_object
        mock_httpx_instance.post = AsyncMock(return_value=mock_response_object)

        eight = EightSleep(self.email, self.password, self.timezone)

        with self.assertRaises(RequestError) as cm:
            await eight._get_auth()

        self.assertIn("Auth request failed with status code: 400", str(cm.exception))
        self.assertIn("{'error': 'bad_request'}", str(cm.exception))

    # Test for EightSleep.start() which includes auth and subsequent calls
    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession') # Mocks aiohttp session
    @patch('custom_components.eight_sleep.pyEight.eight.httpx.AsyncClient') # Mocks httpx client for auth
    async def test_start_successful(self, MockHttpxClient, MockAiohttpSession):
        # --- Mock httpx for _get_auth ---
        mock_httpx_instance = MockHttpxClient.return_value # This is the client

        mock_auth_response_object = MagicMock()
        mock_auth_response_object.status_code = 200
        mock_auth_response_object.json.return_value = { # .json() is sync
            "access_token": "fake_access_token",
            "expires_in": 3600,
            "userId": "fake_user_id_main"
        }
        mock_httpx_instance.post = AsyncMock(return_value=mock_auth_response_object) # client.post is async

        # --- Mock aiohttp.ClientSession for subsequent API calls ---
        mock_aiohttp_session_instance = MockAiohttpSession.return_value
        mock_aiohttp_session_instance.close = AsyncMock() # Ensure close is an AsyncMock

        # Mock for fetch_device_list (/users/me)
        mock_users_me_response = AsyncMock()
        mock_users_me_response.status = 200
        mock_users_me_response.json = AsyncMock(return_value={
            "user": {"devices": ["fake_device_id_123"], "features": ["cooling"]}
        })

        # Mock for assign_users (/devices/{id})
        mock_devices_id_response = AsyncMock()
        mock_devices_id_response.status = 200
        mock_devices_id_response.json = AsyncMock(return_value={
            "result": {"leftUserId": "user_left_abc", "rightUserId": "user_right_def"}
        })

        # Mock for assign_users (/users/{id} for left user)
        mock_user_left_response = AsyncMock()
        mock_user_left_response.status = 200
        mock_user_left_response.json = AsyncMock(return_value={
            "user": {"userId": "user_left_abc", "firstName": "Left", "currentDevice": {"side": "left"}}
        })

        # Mock for assign_users (/users/{id} for right user)
        mock_user_right_response = AsyncMock()
        mock_user_right_response.status = 200
        mock_user_right_response.json = AsyncMock(return_value={
            "user": {"userId": "user_right_def", "firstName": "Right", "currentDevice": {"side": "right"}}
        })

        # Configure session.request to return different mocks based on URL
        async def mock_aiohttp_request(method, url, **kwargs):
            if "users/me" in url:
                return mock_users_me_response
            elif f"devices/fake_device_id_123" in url: # Check for specific device ID
                return mock_devices_id_response
            elif "users/user_left_abc" in url:
                return mock_user_left_response
            elif "users/user_right_def" in url:
                return mock_user_right_response
            # Fallback for unexpected calls
            fallback_mock = AsyncMock()
            fallback_mock.status = 404
            fallback_mock.json = AsyncMock(return_value={"error": "not found"})
            return fallback_mock

        mock_aiohttp_session_instance.request = MagicMock(side_effect=mock_aiohttp_request)

        eight = EightSleep(self.email, self.password, self.timezone)
        # The actual ClientSession and httpx.AsyncClient will be created inside eight.start()
        # if not provided, so the patches will apply to those.

        success = await eight.start()

        self.assertTrue(success)
        self.assertIsNotNone(eight._token)
        self.assertEqual(eight._token.bearer_token, "fake_access_token")
        # Check token's main_id directly
        self.assertEqual(eight._token.main_id, "fake_user_id_main")
        self.assertEqual"fake_device_id_123", eight.device_id)
        self.assertTrue(eight._is_pod)
        self.assertIn("user_left_abc", eight.users)
        self.assertIn("user_right_def", eight.users)
        self.assertEqual(eight.users["user_left_abc"].side, "left")

if __name__ == '__main__':
    unittest.main()
