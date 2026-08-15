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

    async def get_devices(self, specialization: str | None = "pod") -> dict[str, str]:
        """Return {deviceId: label} for the household's devices.

        A set can hold more than one device (e.g. a Pod 5 hub plus its
        pillow, each with its own deviceId and specialization). The previous
        implementation took ``sets[0][devices][0]`` only, which could
        return the pillow instead of the pod and made any additional pod
        unselectable in the config flow.

        ``specialization`` filters the result ("pod" by default, matching the
        config-flow use case). Devices without a specialization key (older
        accounts) are treated as pods. Pass ``None`` to get everything.
        """
        user_id = await self.get_user_id() if self.user_id is None else self.user_id

        url = APP_API_URL + f"v1/household/users/{user_id}/summary"
        data = await self.client.api_request("GET", url)

        self.devices = {}
        for household in data.get("households") or []:
            for house_set in household.get("sets") or []:
                for device in house_set.get("devices") or []:
                    device_spec = device.get("specialization") or "pod"
                    if specialization is not None and device_spec != specialization:
                        continue
                    label = device.get("deviceName") or house_set.get("setName") or device["deviceId"]
                    if specialization is None and device.get("specialization"):
                        label = f"{label} ({device['specialization']})"
                    if label in self.devices.values():
                        label = f"{label} ({device['deviceId'][:6]})"
                    self.devices[device["deviceId"]] = label

        return self.devices
        
