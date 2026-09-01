"""Verify every entity service declared in services.yaml is actually
registered by sensor.async_setup_entry() (#101).

services.yaml is what Home Assistant's UI and docs read to offer a
service as callable; it does not by itself wire the service to a
handler. `set_routine_alarm` was declared there, and its
`async_set_routine_alarm` handler method exists on the entity, but
nothing ever called `platform.async_register_entity_service()` for it --
so calling it from an automation raised "Unable to find service", which
is exactly what the Spook integration flags as an unknown action.

`set_routine_bedtime` was declared alongside it but is deliberately left
unregistered (and removed from services.yaml): its handler,
`EightUser.set_routine_bedtime()`, is a no-op that only logs a warning --
Eight Sleep's API no longer supports bedtime routines. Registering it
would silence the unknown-service error while making automations that
call it appear to succeed without doing anything.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.sensor import async_setup_entry

SERVICES_YAML = (
    Path(__file__).parent.parent / "custom_components" / "eight_sleep" / "services.yaml"
)


def _declared_service_names() -> set[str]:
    with SERVICES_YAML.open() as f:
        return set(yaml.safe_load(f).keys())


@pytest.mark.asyncio
async def test_every_declared_service_is_registered():
    """Every service name in services.yaml must reach
    platform.async_register_entity_service() during setup."""
    entry = MagicMock(entry_id="test_entry")
    config_entry_data = MagicMock(users={})
    config_entry_data.api.users = {}
    config_entry_data.api.device_id = "test-device-id"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: config_entry_data}}

    platform = MagicMock()
    registered_service_names: set[str] = set()
    platform.async_register_entity_service.side_effect = (
        lambda name, *_args, **_kwargs: registered_service_names.add(name)
    )

    with patch(
        "custom_components.eight_sleep.sensor.async_get_current_platform",
        return_value=platform,
    ):
        await async_setup_entry(hass, entry, MagicMock())

    declared = _declared_service_names()
    missing = declared - registered_service_names
    assert not missing, (
        f"Declared in services.yaml but never registered: {sorted(missing)}"
    )


def test_set_routine_bedtime_is_not_declared():
    """set_routine_bedtime must stay out of services.yaml until its handler
    does something other than log a warning -- see #152 review discussion."""
    assert "set_routine_bedtime" not in _declared_service_names()


@pytest.mark.asyncio
async def test_set_routine_bedtime_is_not_registered():
    """set_routine_bedtime must not be wired to a service even if someone
    re-adds it to services.yaml without also fixing the handler."""
    entry = MagicMock(entry_id="test_entry")
    config_entry_data = MagicMock(users={})
    config_entry_data.api.users = {}
    config_entry_data.api.device_id = "test-device-id"

    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: config_entry_data}}

    platform = MagicMock()
    registered_service_names: set[str] = set()
    platform.async_register_entity_service.side_effect = (
        lambda name, *_args, **_kwargs: registered_service_names.add(name)
    )

    with patch(
        "custom_components.eight_sleep.sensor.async_get_current_platform",
        return_value=platform,
    ):
        await async_setup_entry(hass, entry, MagicMock())

    assert "set_routine_bedtime" not in registered_service_names
