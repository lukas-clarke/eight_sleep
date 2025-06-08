import asyncio
import time # Add time import
import unittest
from unittest.mock import AsyncMock, patch, MagicMock, call # Add call

from custom_components.eight_sleep.pyEight.structs import Token # Import Token for spec
from custom_components.eight_sleep.pyEight.eight import EightSleep, EightUser
from custom_components.eight_sleep.pyEight.exceptions import RequestError
from custom_components.eight_sleep.pyEight.constants import CLIENT_API_URL, DEFAULT_API_HEADERS # For verifying calls

class TestEightSleep(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.email = "test@example.com"
        self.password = "password"
        self.timezone = "America/New_York"
        # We will often patch 'EightSleep._get_auth' or 'httpx.AsyncClient' for these tests
        # and 'aiohttp.ClientSession' for api_request.

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth') # Patch _get_auth directly
    async def test_fetch_device_list_successful(self, mock_get_auth, MockAiohttpSession):
        # _get_auth is called by self.token property if token is None or expired.
        # Mock it to avoid actual HTTP call during token property access.
        mock_get_auth.return_value = AsyncMock(bearer_token="fake_token", user_id="fake_user", expiration=9999999999)

        mock_aiohttp_session_instance = MockAiohttpSession.return_value
        # This is the mock for the response object from aiohttp
        mock_response_object = AsyncMock()
        mock_response_object.status = 200
        # aiohttp's response.json() is an async method
        mock_response_object.json = AsyncMock(return_value={
            "user": {"devices": ["dev123"], "features": ["cooling", "elevation"]}
        })
        # Configure the session's request method (which is async) to return the mock_response_object
        mock_aiohttp_session_instance.request = AsyncMock(return_value=mock_response_object)
        mock_aiohttp_session_instance.close = AsyncMock() # For at_exit

        eight = EightSleep(self.email, self.password, self.timezone)
        # eight._api_session needs to be the mocked one
        eight._api_session = mock_aiohttp_session_instance
        await eight.fetch_device_list()

        self.assertEqual(eight._device_ids, ["dev123"])
        self.assertTrue(eight._is_pod)
        self.assertTrue(eight._has_base)
        mock_aiohttp_session_instance.request.assert_called_once_with(
            "get", f"{CLIENT_API_URL}/users/me", headers=unittest.mock.ANY, params=None, json=None, timeout=unittest.mock.ANY
        )

    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_assign_users_successful(self, mock_get_auth, MockAiohttpSession):
        mock_get_auth.return_value = AsyncMock(bearer_token="fake_token", user_id="fake_user", expiration=9999999999)

        mock_aiohttp_session_instance = MockAiohttpSession.return_value

        # Prepare responses for the sequence of calls in assign_users
        # Response for device info
        mock_device_info_resp_obj = AsyncMock()
        mock_device_info_resp_obj.status = 200
        mock_device_info_resp_obj.json = AsyncMock(return_value={
            "result": {"leftUserId": "userL", "rightUserId": "userR"}
        })

        # Response for user L
        mock_userL_resp_obj = AsyncMock()
        mock_userL_resp_obj.status = 200
        mock_userL_resp_obj.json = AsyncMock(return_value={
            "user": {"userId": "userL", "firstName": "Left", "currentDevice": {"side": "left"}}
        })

        # Response for user R
        mock_userR_resp_obj = AsyncMock()
        mock_userR_resp_obj.status = 200
        mock_userR_resp_obj.json = AsyncMock(return_value={
            "user": {"userId": "userR", "firstName": "Right", "currentDevice": {"side": "right"}}
        })

        # Use a side_effect to return different responses
        async def mock_request_side_effect(method, url, **kwargs):
            if f"/devices/dev123" in url:
                return mock_device_info_resp_obj
            elif "/users/userL" in url:
                return mock_userL_resp_obj
            elif "/users/userR" in url:
                return mock_userR_resp_obj
            fallback_resp = AsyncMock()
            fallback_resp.status = 404
            fallback_resp.json = AsyncMock(return_value={"error":"not found"})
            return fallback_resp

        mock_aiohttp_session_instance.request = AsyncMock(side_effect=mock_request_side_effect)
        mock_aiohttp_session_instance.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session_instance
        eight._device_ids = ["dev123"] # Pre-set device ID for the test

        await eight.assign_users()

        self.assertIn("userL", eight.users)
        self.assertIn("userR", eight.users)
        self.assertIsInstance(eight.users["userL"], EightUser)
        self.assertEqual(eight.users["userL"].side, "left")
        self.assertEqual(eight.users["userR"].side, "right")
        # Check call count, could be 1 (for device info) + N_users
        self.assertTrue(mock_aiohttp_session_instance.request.call_count >= 3)


    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')
    @patch('custom_components.eight_sleep.pyEight.eight.EightSleep._get_auth')
    async def test_update_device_data_successful(self, mock_get_auth, MockAiohttpSession):
        mock_get_auth.return_value = AsyncMock(bearer_token="fake_token", user_id="fake_user", expiration=9999999999)

        mock_aiohttp_session_instance = MockAiohttpSession.return_value
        mock_response_data = {"result": {"needsPriming": False, "leftHeatingLevel": 10}}
        mock_response_object = AsyncMock(status=200)
        mock_response_object.json = AsyncMock(return_value=mock_response_data) # json is async
        mock_aiohttp_session_instance.request = AsyncMock(return_value=mock_response_object)
        mock_aiohttp_session_instance.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session_instance
        eight._device_ids = ["dev123"] # Pre-set device ID

        await eight.update_device_data()

        self.assertEqual(len(eight._device_json_list), 1)
        self.assertEqual(eight.device_data, mock_response_data["result"])
        mock_aiohttp_session_instance.request.assert_called_once_with(
            "get", f"{CLIENT_API_URL}/devices/dev123", headers=unittest.mock.ANY, params=None, json=None, timeout=unittest.mock.ANY
        )

    @patch('custom_components.eight_sleep.pyEight.eight.httpx.AsyncClient') # For refresh_token
    @patch('custom_components.eight_sleep.pyEight.eight.ClientSession')   # For api_request
    async def test_api_request_401_retry_successful(self, MockAiohttpSession, MockHttpxClient):
        # --- Mock initial token & auth setup ---
        # This initial token is "stale" for API call, but not expired for self.token property
        initial_token_val = MagicMock(
            spec=Token,
            bearer_token="stale_token",
            main_id="fake_user",  # Corrected attribute name
            expiration=time.time() + 1000 # Valid for token property, but API will reject
        )

        # Mock httpx client for refresh_token call (which calls _get_auth)
        mock_httpx_instance = MockHttpxClient.return_value # This is the client instance

        # This is the mock for the response object that client.post (in _get_auth) will return
        mock_auth_response_object = MagicMock() # httpx.Response is not async itself
        mock_auth_response_object.status_code = 200
        mock_auth_response_object.json.return_value = { # .json() is sync for httpx
            "access_token": "fresh_token",
            "expires_in": 3600,
            "userId": "fake_user" # This becomes token.user_id_str
        }
        # Configure the client's post method (which is async) to return the mock_auth_response_object
        mock_httpx_instance.post = AsyncMock(return_value=mock_auth_response_object)

        # --- Mock aiohttp session ---
        mock_aiohttp_session_instance = MockAiohttpSession.return_value

        # First call to api_request gets 401 response object
        mock_401_response_obj = AsyncMock()
        mock_401_response_obj.status = 401
        mock_401_response_obj.json = AsyncMock(return_value={"error": "unauthorized"})
        mock_401_response_obj.text = AsyncMock(return_value="Unauthorized token") # text is async for aiohttp

        # Second call (retry) gets 200 response object
        mock_200_response_obj = AsyncMock()
        mock_200_response_obj.status = 200
        mock_200_response_obj.json = AsyncMock(return_value={"data": "success"})

        # Configure the session's request method (which is async) with a side_effect
        mock_aiohttp_session_instance.request = AsyncMock(side_effect=[
            mock_401_response_obj, # First call
            mock_200_response_obj  # Retry call
        ])
        mock_aiohttp_session_instance.close = AsyncMock()

        eight = EightSleep(self.email, self.password, self.timezone)
        eight._api_session = mock_aiohttp_session_instance
        # Manually set the token. The self.token property should not auto-refresh this.
        eight._token = initial_token_val

        test_url = f"{CLIENT_API_URL}/test/endpoint"
        response_data = await eight.api_request("get", test_url)

        self.assertEqual(response_data, {"data": "success"})
        self.assertEqual(mock_aiohttp_session_instance.request.call_count, 2)

        # Check that refresh_token (httpx call) was made
        mock_httpx_instance.post.assert_called_once()

        # Check that the token was updated
        self.assertEqual(eight._token.bearer_token, "fresh_token")

        # Verify headers of the calls to aiohttp
        calls = mock_aiohttp_session_instance.request.call_args_list
        self.assertIn("Bearer stale_token", calls[0].kwargs['headers']['authorization'])
        self.assertIn("Bearer fresh_token", calls[1].kwargs['headers']['authorization'])

if __name__ == '__main__':
    unittest.main()
