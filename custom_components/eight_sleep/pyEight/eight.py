"""
pyeight.eight
~~~~~~~~~~~~~~~~~~~~
Provides api for Eight Sleep
Copyright (c) 2022-2023 <https://github.com/lukas-clarke/pyEight>
Licensed under the MIT license.

"""

from __future__ import annotations

import asyncio
import atexit
from datetime import datetime, timezone
from dateutil import parser
import logging
from typing import Any
import time
from zoneinfo import ZoneInfo

import httpx
from aiohttp.client import ClientError, ClientSession, ClientTimeout

from .constants import (
    DEFAULT_TIMEOUT,
    KNOWN_CLIENT_ID,
    KNOWN_CLIENT_SECRET,
    AUTH_URL,
    DEFAULT_AUTH_HEADERS,
    CLIENT_API_URL,
    APP_API_URL,
    DEFAULT_API_HEADERS,
    TOKEN_TIME_BUFFER_SECONDS,
    RAW_TO_CELSIUS_MAP,
    RAW_TO_FAHRENHEIT_MAP,
)
from .exceptions import RequestError
from .user import EightUser
from .structs import Token

_LOGGER = logging.getLogger(__name__)

CLIENT_TIMEOUT = ClientTimeout(total=DEFAULT_TIMEOUT)


class EightSleep:
    """Eight sleep API object."""

    def __init__(
        self,
        email: str,
        password: str,
        timezone: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        client_session: ClientSession | None = None,
        httpx_client: httpx.AsyncClient | None = None,
        check_auth: bool = False,
        device_id: str | None = None,
    ) -> None:
        """Initialize eight sleep class."""
        self._email = email
        self._password = password
        # If client_id isn't set, use the default value
        if not client_id:
            client_id = KNOWN_CLIENT_ID
        self._client_id = client_id
        # if client_secret isn't set manually, use the known one
        # that works for now
        if not client_secret:
            client_secret = KNOWN_CLIENT_SECRET
        self._client_secret = client_secret

        self.timezone = timezone
        self.device_id: str | None = device_id

        self.users: dict[str, EightUser] = {}

        self._user_id: str | None = None
        self._token: Token | None = None
        self._token_expiration: datetime | None = None
        self._is_pod: bool = False
        self._has_base: bool = False
        self._has_speaker: bool = False

        # Setup 10 element list
        self._device_json_list: list[dict] = []

        self._api_session = client_session
        self._httpx_client = httpx_client
        self._internal_session: bool = False

        if check_auth:
            self._get_auth()

        # Stop on exit
        atexit.register(self.at_exit)

    def at_exit(self) -> None:
        """Run at exit."""
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(self.stop(), loop).result()
        except RuntimeError:
            asyncio.run(self.stop())

    @property
    def user_id(self) -> str | None:
        """Return user ID of the logged in user."""
        return self._user_id

    @property
    def device_data(self) -> dict:
        """Return current raw device_data json."""
        return self._device_json_list[0]

    @property
    def device_data_history(self) -> list[dict]:
        """Return full raw device_data json list."""
        return self._device_json_list

    @property
    def need_priming(self) -> bool:
        return self.device_data["needsPriming"]

    @property
    def is_priming(self) -> bool:
        return self.device_data["priming"]

    @property
    def has_water(self) -> bool:
        return self.device_data["hasWater"]

    @property
    def last_prime(self):
        return self.convert_string_to_datetime(self.device_data["lastPrime"])

    @property
    def is_pod(self) -> bool:
        """Return if device is a Pod."""
        return self._is_pod

    @property
    def has_base(self) -> bool:
        """Return if device has a base."""
        return self._has_base

    @property
    def has_speaker(self) -> bool:
        """Return if device has speaker capability."""
        return self._has_speaker

    @property
    def speaker_user(self) -> EightUser | None:
        """Return the user object for speaker API calls."""
        if self.has_speaker:
            return next(iter(self.users.values()))
        return None

    def convert_raw_bed_temp_to_degrees(self, raw_value, degree_unit):
        """degree_unit can be 'c' or 'f'
        I couldn't find a constant algrebraic equation for converting
        the raw value to degrees so I had to iterate over the whole range
        and save a conversion map for the values."""
        if degree_unit.lower() == "c" or degree_unit.lower() == "celsius":
            unit_map = RAW_TO_CELSIUS_MAP
        else:
            unit_map = RAW_TO_FAHRENHEIT_MAP

        last_raw_unit = -100
        # Mapping the raw unit to an actual degree value
        # Doing iterative search instead of binary for readability, and because constant size
        for raw_unit, degree_unit in unit_map.items():
            if raw_value == raw_unit:
                return float(degree_unit)
            if raw_unit > raw_value:
                last_degree_unit = unit_map[last_raw_unit]
                ratio = (raw_value - last_raw_unit) / (raw_unit - last_raw_unit)
                delta_degrees = degree_unit - last_degree_unit
                return last_degree_unit + (ratio * delta_degrees)
            last_raw_unit = raw_unit
        raise Exception(f"Raw value {raw_value} unable to be mapped.")

    def convert_string_to_datetime(self, datetime_str) -> datetime:
        try:
            # Parse the datetime string
            dt = parser.isoparse(str(datetime_str).strip())

            # If the datetime is naive (no timezone info), assume it's UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            # Convert to the desired timezone
            return dt.astimezone(ZoneInfo(self.timezone))
        except ValueError:
            raise ValueError(f"Unsupported date string format: {datetime_str}")

    async def _get_auth(self) -> Token:
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "password",
            "username": self._email,
            "password": self._password,
        }

        if not self._httpx_client:
            self._httpx_client = httpx.AsyncClient()

        response = await self._httpx_client.post(
            AUTH_URL,
            headers=DEFAULT_AUTH_HEADERS,
            json=data,
            timeout=DEFAULT_TIMEOUT,
        )
        if response.status_code == 200:
            access_token_str = response.json()["access_token"]
            expiration_seconds_int = (
                float(response.json()["expires_in"]) + time.time()
            )
            main_id = response.json()["userId"]
            return Token(access_token_str, expiration_seconds_int, main_id)
        else:
            error_message = f"Auth request failed with status code: {response.status_code}"
            try:
                error_details = response.json()
                error_message += f" - Details: {error_details}"
            except ValueError: # Not a JSON response
                error_message += f" - Response: {response.text}"
            raise RequestError(error_message)

    @property
    async def token(self) -> Token:
        """Return session token."""
        if not self._token:
            await self.refresh_token()

        if time.time() + TOKEN_TIME_BUFFER_SECONDS > self._token.expiration:
            await self.refresh_token()

        return self._token

    async def refresh_token(self):
        self._token = await self._get_auth()

    def fetch_user_id(self, side: str) -> str | None:
        """Return the user_id for the specified bed side."""
        return next(
            (user_id for user_id, user in self.users.items() if user.side == side),
            None,
        )

    async def update_user_data(self) -> None:
        """Update data for users."""
        for user in self.users.values():
            await user.update_user()

    async def update_base_data(self) -> None:
        """Update data for the bed base.
        While it's possible to retrieve the data for each user, the contents are identical."""
        user = self.base_user
        if user:
            await user.update_base_data()

    @property
    def base_user(self) -> EightUser | None:
        """Return the user object for the base."""
        if not self.has_base:
            return
        
        for user in self.users.values():
            if user.side != "away":
                return user

        _LOGGER.info("No base user found, it's likely all base users are 'away'.")

    async def _probe_speaker_availability(self) -> bool:
        """Probe for speaker by attempting to get player state.

        The Pod 5 bed platform (with speaker) can be purchased separately
        and used with a Pod 4 hub, so we can't rely on model detection.
        """
        if not self.users:
            return False

        user = next(iter(self.users.values()))
        url = f"{APP_API_URL}v1/users/{user.user_id}/audio/player"

        try:
            response = await self.api_request("get", url)
            # If we get a response with hardwareInfo, speaker is available
            if response and response.get("hardwareInfo"):
                _LOGGER.debug(f"Speaker detected via probe: {response.get('hardwareInfo', {}).get('sku')}")
                return True
            return False
        except RequestError as e:
            _LOGGER.debug(f"Speaker probe failed (expected if no speaker): {e}")
            return False

    async def update_speaker_data(self) -> None:
        """Update data for the speaker."""
        user = self.speaker_user
        if user:
            await user.update_player_state()

    async def start(self) -> bool:
        """Start api initialization."""
        _LOGGER.debug("Initializing pyEight.")
        if not self._api_session:
            self._api_session = ClientSession()
            self._internal_session = True

        await self.token
        
        if self.device_id is None:
            await self.fetch_device_id()

        await self.update_device_data()
        await self.assign_users()

        # If speaker not detected via feature flag, try probe-based detection
        # This handles Pod 4 hub + Pod 5 bed platform combinations
        if not self._has_speaker:
            self._has_speaker = await self._probe_speaker_availability()

        # Fetch audio tracks if speaker available
        if self._has_speaker and self.speaker_user:
            await self.speaker_user.fetch_audio_tracks()

        return True

    async def stop(self) -> None:
        """Stop api session."""
        if self._internal_session and self._api_session:
            _LOGGER.debug("Closing eight sleep api session.")
            await self._api_session.close()
            self._api_session = None
        elif self._internal_session:
            _LOGGER.debug("No-op because session hasn't been created")
        else:
            _LOGGER.debug("No-op because session is being managed outside of pyEight")

    async def assign_users(self) -> None:
        """Update device properties."""
        url = f"{CLIENT_API_URL}/devices/{self.device_id}?filter=leftUserId,rightUserId,awaySides"

        data = await self.api_request("get", url)

        # The API includes an awaySides key if at least one of the users is away
        # We can get the ids for the away users from there
        ids = set([
            data["result"].get("leftUserId"),
            data["result"].get("rightUserId"),
            *data["result"].get("awaySides", {}).values()
        ])

        # Get each user's side from the API
        # Create users for each unique id, including 'away' users
        for user_id in filter(None, ids):
            url = f"{CLIENT_API_URL}/users/{user_id}"
            data = await self.api_request("get", url)
            side = data.get("user", {}).get("currentDevice", {}).get("side")

            if side is None:
                _LOGGER.warning(f"User with ID {user_id} has no 'side' information returned from API endpoint {url}. This user may not function correctly.")

            if user_id not in self.users:
                user = self.users[user_id] = EightUser(self, user_id, side)
                await user.update_user_profile()

    @property
    def room_temperature(self) -> float | None:
        """Return room temperature for both sides of bed."""
        # Check which side is active, if both are return the average
        tmp = None
        tmp2 = None
        for user in self.users.values():
            current_temp = user.current_room_temp
            if current_temp is None:
                continue  # Skip users with no temperature data
            
            if user.current_session_processing:
                if tmp is None:
                    tmp = current_temp
                else:
                    tmp = (tmp + current_temp) / 2
            else:
                if tmp2 is None:
                    tmp2 = current_temp
                else:
                    tmp2 = (tmp2 + current_temp) / 2

        if tmp is not None:
            return tmp

        # If tmp2 is None we will just return None
        return tmp2

    def handle_device_json(self, data: dict[str, Any]) -> None:
        """Manage the device json list."""
        self._device_json_list = [data, *self._device_json_list][:10]

        if "cooling" in data["features"]:
            self._is_pod = True

        if "elevation" in data["features"]:
            self._has_base = True

        if "audio" in data["features"]:
            self._has_speaker = True

        _LOGGER.debug(f"Device: {self.device_id}, Pod: {self._is_pod}, Base: {self._has_base}, Speaker: {self._has_speaker}")

    async def fetch_device_id(self) -> None:
        """Fetch device id for backwards compatibility."""
        url = f"{CLIENT_API_URL}/users/me"
        dlist = await self.api_request("get", url)

       self.device_id =  dlist["user"]["devices"][0]
        

    async def update_device_data(self) -> None:
        """Update device data json."""
        url = f"{CLIENT_API_URL}/devices/{self.device_id}"

        device_resp = await self.api_request("get", url)
        # Want to keep last 10 readings so purge the last after we add
        self.handle_device_json(device_resp["result"])

    async def api_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        input_headers: dict[str, Any] | None = None, # Explicitly type hint
        return_json: bool = True,
        _is_retry: bool = False
    ) -> Any:
        """Make api request with 401 retry."""

        current_headers: dict[str, Any] # Define type for current_headers
        if input_headers is not None:
            current_headers = input_headers
        else:
            current_headers = dict(DEFAULT_API_HEADERS) # Use a copy

        # Ensure token is fresh and add to headers for this attempt
        # self.token property handles its own refresh if expired before this call
        token_data = await self.token # Renamed to avoid conflict with Token type hint
        current_headers["authorization"] = f"Bearer {token_data.bearer_token}"

        try:
            assert self._api_session
            resp = await self._api_session.request(
                method,
                url,
                headers=current_headers,
                params=params,
                json=data,
                timeout=CLIENT_TIMEOUT,
                # No raise_for_status=True here for the first attempt
            )

            if resp.status == 401 and not _is_retry:
                _LOGGER.info(
                    f"Unauthorized (401) for {method.upper()} {url}. Refreshing token and retrying."
                )
                await self.refresh_token() # This should update self._token
                # For the retry, we make a new call to api_request.
                # It will pick up the new token when it calls self.token again.
                return await self.api_request(
                    method, url, params, data, input_headers, return_json, _is_retry=True
                )

            if resp.status >= 400:
                # Handle HTTP errors for non-401 or for 401 on retry
                error_message = f"API request {method.upper()} {url} failed with status {resp.status}"
                try:
                    error_details = await resp.json()
                    error_message += f" - Details: {error_details}"
                except Exception: # Catch broad errors like not being JSON
                    try:
                        error_text = await resp.text()
                        error_message += f" - Response: {error_text}"
                    except Exception as text_exc:
                        error_message += f" - Failed to get response text: {text_exc}"
                _LOGGER.error(error_message)
                raise RequestError(error_message)

            # Successful response
            if return_json:
                return await resp.json()
            return None

        except (ClientError, asyncio.TimeoutError, ConnectionRefusedError) as err:
            # Catch network errors or errors from aiohttp if they occur
            # Avoid re-wrapping if it's already a RequestError (e.g. from a failed retry that raised it)
            if isinstance(err, RequestError):
                raise

            error_message = f"Network/Connection error during {method.upper()} request to {url}: {err}"
            _LOGGER.error(error_message)
            raise RequestError(error_message) from err
        except Exception as e: # Catch any other unexpected error
            if isinstance(e, RequestError): # Should have been caught by the previous block if it was a ClientError
                raise
            _LOGGER.error(f"Unexpected error during API request to {url}: {e}", exc_info=True)
            raise RequestError(f"Unexpected error during API request to {url}: {e}") from e
