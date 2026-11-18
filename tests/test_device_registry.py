from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.eight_sleep import async_setup_entry
from custom_components.eight_sleep.const import DOMAIN


async def register_devices(registry):
    entry = SimpleNamespace(
        entry_id="entry", title="Pod", data={"username": "user", "password": "password"}
    )
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    eight = MagicMock()
    eight.start = AsyncMock(return_value=True)
    eight.device_id = "pod"
    eight.device_data = {"modelString": "Pod"}
    eight.has_speaker = False
    eight.users = {
        side: SimpleNamespace(user_id=side, side=side, user_profile={"firstName": side})
        for side in ("left", "right")
    }
    eight.base_user.base_data = {"hardwareInfo": {"sku": "Base"}}
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    registry.async_get_or_create.return_value = SimpleNamespace(id="registered-hub")

    with (
        patch("custom_components.eight_sleep.EightSleep", return_value=eight),
        patch("custom_components.eight_sleep.async_get_clientsession"),
        patch("custom_components.eight_sleep.get_async_client"),
        patch(
            "custom_components.eight_sleep.DataUpdateCoordinator",
            return_value=coordinator,
        ),
        patch("custom_components.eight_sleep.dr.async_get", return_value=registry),
    ):
        assert await async_setup_entry(hass, entry)

    registrations = registry.async_get_or_create.call_args_list
    assert len(registrations) == 4
    assert registrations[0].kwargs["identifiers"] == {(DOMAIN, "pod")}
    assert "via_device" not in registrations[0].kwargs
    assert "via_device_id" not in registrations[0].kwargs
    for registration, identifier in zip(
        registrations[1:], ("pod.left", "pod.right", "pod.base")
    ):
        assert registration.kwargs["identifiers"] == {(DOMAIN, identifier)}
    return registrations[1:]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "version,link",
    [
        ((2026, 8), {"via_device_id": "registered-hub"}),
        ((2027, 1), {"via_device_id": "registered-hub"}),
        ((2026, 7), {"via_device": (DOMAIN, "pod")}),
        ((2025, 1), {"via_device": (DOMAIN, "pod")}),
    ],
)
async def test_sides_and_base_link_to_the_hub(version, link):
    with (
        patch("custom_components.eight_sleep.MAJOR_VERSION", version[0]),
        patch("custom_components.eight_sleep.MINOR_VERSION", version[1]),
    ):
        children = await register_devices(MagicMock())

    for registration in children:
        assert {
            key: registration.kwargs[key]
            for key in ("via_device", "via_device_id")
            if key in registration.kwargs
        } == link


@pytest.mark.asyncio
async def test_hub_link_matches_installed_device_registry():
    await register_devices(create_autospec(dr.DeviceRegistry, instance=True))
