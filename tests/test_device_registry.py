"""Verify device links without deprecated registry arguments."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eight_sleep import async_setup_entry
from custom_components.eight_sleep.const import DOMAIN


@pytest.mark.parametrize("has_base", [False, True])
async def test_device_links(hass, caplog, has_base):
    """Sides and the optional base link to the hub without usage warnings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bed",
        data={"username": "test@example.com", "password": "test"},
    )
    entry.add_to_hass(hass)
    users = {
        side: SimpleNamespace(
            user_id=side, side=side, user_profile={"firstName": side}
        )
        for side in ("left", "right")
    }
    eight = SimpleNamespace(
        device_id="hub",
        device_data={"modelString": "Pod"},
        users=users,
        base_user=SimpleNamespace(base_data={"hardwareInfo": {}}) if has_base else None,
        has_speaker=False,
        start=AsyncMock(return_value=True),
        update_device_data=AsyncMock(),
        update_user_data=AsyncMock(),
        update_base_data=AsyncMock(),
    )
    with (
        patch("custom_components.eight_sleep.EightSleep", return_value=eight),
        patch("custom_components.eight_sleep.async_get_clientsession"),
        patch("custom_components.eight_sleep.get_async_client"),
        patch("custom_components.eight_sleep.DataUpdateCoordinator") as coordinator,
        patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()),
    ):
        coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry)

    registry = dr.async_get(hass)
    devices = {
        identifier: device
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
        for identifier in device.identifiers
    }
    hub = devices.get((DOMAIN, "hub"))
    assert hub is not None
    for suffix in ("left", "right", "base"):
        device = devices.get((DOMAIN, f"hub.{suffix}"))
        if suffix == "base" and not has_base:
            assert device is None
        else:
            assert device is not None
            assert device.via_device_id == hub.id

    # Older HA releases do not warn; link assertions above still cover them.
    assert "via_device" not in caplog.text
