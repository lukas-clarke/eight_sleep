"""
pyeight.household
~~~~~~~~~~~~~~~~~~~~
Provides household data for Eight Sleep
Copyright (c) 2022-2025 <https://github.com/lukas-clarke/pyEight>
Licensed under the MIT license.
"""

from typing import TYPE_CHECKING, Any, Optional

from .constants import APP_API_URL, CLIENT_API_URL

if TYPE_CHECKING:
    from .eight import EightSleep

class EightHousehold:
    def __init__(self, client: "EightSleep", user_id: Optional[str] = None):
        self.user_id: str | None = user_id
        self.client = client
        self.devices: dict[str, str] = {}

    async def get_user_id(self) -> str:
        url = f"{CLIENT_API_URL}/users/me"
        user_data = await self.client.api_request("get", url)
        return user_data["user"]["userId"]

    async def get_devices(self) -> dict[str, str]:
        user_id = await self.get_user_id() if self.user_id is None else self.user_id

        url = APP_API_URL + f"v1/household/users/{user_id}/summary"
        data = await self.client.api_request("GET", url)

        self.devices = {}
        for house_set in data["households"][0]["sets"]:
            device = house_set["devices"][0]
            self.devices[device["deviceId"]] = device["deviceName"]

        return self.devices
        
