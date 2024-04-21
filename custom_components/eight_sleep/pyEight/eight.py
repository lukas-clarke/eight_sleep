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
from datetime import datetime
import pytz
import logging
from typing import Any
import time

import httpx
from aiohttp.client import ClientError, ClientSession, ClientTimeout

from .constants import *
from .exceptions import NotAuthenticatedError, RequestError
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
        client_id: str = None,
        client_secret: str = None,
        client_session: ClientSession | None = None,
        check_auth: bool = False,
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

        self.users: dict[str, EightUser] = {}

        self._user_id: str | None = None
        self._token: str | None = None
        self._token_expiration: datetime | None = None
        self._device_ids: list[str] = []
        self._is_pod: bool = False

        # Setup 10 element list
        self._device_json_list: list[dict] = []

        self._api_session = client_session
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
    def token(self) -> str | None:
        """Return session token."""
        return self._token

    @property
    def user_id(self) -> str | None:
        """Return user ID of the logged in user."""
        return self._user_id

    @property
    def device_id(self) -> str | None:
        """Return devices id."""
        return self._device_ids[0]

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
        """Return if device is a POD."""
        return self._is_pod

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

    def convert_string_to_datetime(self, datetime_str):
        datetime_str = str(datetime_str).strip()
        # Convert string to datetime object.
        try:
            # Try to parse the first format
            datetime_object = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            try:
                # Try to parse the second format
                datetime_object = datetime.strptime(
                    datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ"
                )
            except ValueError:
                # Handle if neither format is matched
                raise ValueError(f"Unsupported date string format for {datetime_str}")

        # Set the timezone to UTC
        utc_timezone = pytz.UTC
        datetime_object_utc = datetime_object.replace(tzinfo=utc_timezone)
        # Set the timezone to a specific timezone
        timezone = pytz.timezone(self.timezone)
        return datetime_object_utc.astimezone(timezone)

    async def _get_auth(self) -> Token:
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "password",
            "username": self._email,
            "password": self._password,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
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
                raise RequestError(
                    f"Auth request failed with status code: {response.status_code}"
                )

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
        for obj in self.users.values():
            await obj.update_user()

    async def start(self) -> bool:
        """Start api initialization."""
        _LOGGER.debug("Initializing pyEight.")
        if not self._api_session:
            self._api_session = ClientSession()
            self._internal_session = True

        await self.token
        await self.fetch_device_list()
        await self.assign_users()
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

    async def fetch_device_list(self) -> None:
        """Fetch list of devices."""
        url = f"{CLIENT_API_URL}/users/me"

        dlist = await self.api_request("get", url)
        self._device_ids = dlist["user"]["devices"]

        if "cooling" in dlist["user"]["features"]:
            self._is_pod = True

        _LOGGER.debug("Devices: %s, POD: %s", self._device_ids, self._is_pod)

    async def assign_users(self) -> None:
        """Update device properties."""
        device_id = self._device_ids[0]
        url = f"{CLIENT_API_URL}/devices/{device_id}?filter=ownerId,leftUserId,rightUserId"

        data = await self.api_request("get", url)
        for side in ("left", "right"):
            user_id = data["result"].get(f"{side}UserId")
            if user_id is not None and user_id not in self.users:
                user = self.users[user_id] = EightUser(self, user_id, side)
                await user.update_user_profile()

    @property
    def room_temperature(self) -> float | None:
        """Return room temperature for both sides of bed."""
        # Check which side is active, if both are return the average
        tmp = None
        tmp2 = None
        for user in self.users.values():
            if user.current_values["processing"]:
                if tmp is None:
                    tmp = user.current_values["room_temp"]
                else:
                    tmp = (tmp + user.current_values["room_temp"]) / 2
            else:
                if tmp2 is None:
                    tmp2 = user.current_values["room_temp"]
                else:
                    tmp2 = (tmp2 + user.current_values["room_temp"]) / 2

        if tmp is not None:
            return tmp

        # If tmp2 is None we will just return None
        return tmp2

    def handle_device_json(self, data: dict[str, Any]) -> None:
        """Manage the device json list."""
        self._device_json_list = [data, *self._device_json_list][:10]

    async def update_device_data(self) -> None:
        """Update device data json."""
        url = f"{CLIENT_API_URL}/devices/{self.device_id}"

        device_resp = await self.api_request("get", url)
        # Want to keep last 10 readings so purge the last after we add
        self.handle_device_json(device_resp["result"])
        for obj in self.users.values():
            obj.dynamic_presence()

    async def api_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        input_headers=None,
        return_json=True,
    ) -> Any:
        """Make api request."""
        if input_headers is not None:
            headers = input_headers
        else:
            headers = DEFAULT_API_HEADERS

        token = await self.token
        headers.update({"authorization": f"Bearer {token.bearer_token}"})
        try:
            assert self._api_session
            resp = await self._api_session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=data,
                timeout=CLIENT_TIMEOUT,
                raise_for_status=True,
            )
            if resp.status == 401:
                # refresh token and try again if request in unauthorized
                await self.refresh_token()
                return await self.api_request(method, url, params, data, input_headers)
            if return_json:
                return await resp.json()
            else:
                return None

        except (ClientError, asyncio.TimeoutError, ConnectionRefusedError) as err:
            _LOGGER.error(f"Error {method}ing Eight data. {err}s")
            raise RequestError from err
