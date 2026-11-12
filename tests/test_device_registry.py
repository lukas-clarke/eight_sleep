from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eight_sleep import async_setup_entry
from custom_components.eight_sleep.const import DOMAIN


@pytest.mark.asyncio
async def test_sides_and_base_link_to_the_registered_hub():
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
    registry = MagicMock()
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
    assert "via_device_id" not in registrations[0].kwargs
    for registration, identifier in zip(
        registrations[1:], ("pod.left", "pod.right", "pod.base")
    ):
        assert registration.kwargs["identifiers"] == {(DOMAIN, identifier)}
        assert registration.kwargs["via_device_id"] == "registered-hub"
        assert "via_device" not in registration.kwargs
