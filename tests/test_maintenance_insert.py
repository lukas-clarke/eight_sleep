"""The maintenance insert due date becomes a bed-level date sensor.

GET /v1/user/{userId}/device_maintenance/maintenance_insert?v=2 lists one entry
per device the account has owned. Only the entry for this device counts, and
only its replacement dates are kept: the records also carry shipping and
invoice details. Dates differ per entry so reading the wrong one fails.
"""

from datetime import date, timedelta
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.constants import APP_API_URL
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.exceptions import RequestError
from custom_components.eight_sleep.pyEight.structs import Token
from custom_components.eight_sleep.sensor import async_setup_entry

ENTRIES = [
    {
        "deviceId": "dev-old",
        "previousInsertReplacement": {"replacementDate": "2026-03-14", "invoiceNumber": "X"},
        "nextInsertReplacement": {"replacementDate": "2026-09-14"},
    },
    {
        "deviceId": "dev-pod",
        "previousInsertReplacement": {"replacementDate": "2026-04-09", "shippingAddress": "***"},
        "nextInsertReplacement": {"replacementDate": "2026-10-09"},
    },
    {"deviceId": "dev-none"},
]


def _eight(response) -> EightSleep:
    eight = EightSleep("a@example.com", "pw", "America/Denver")
    eight.device_id = "dev-pod"
    eight._token = Token("bearer", time.time() + 3600, "user-9")
    eight.api_request = AsyncMock(
        side_effect=response if isinstance(response, Exception) else None,
        return_value=None if isinstance(response, Exception) else response,
    )
    return eight


@pytest.mark.asyncio
async def test_reads_this_devices_dates():
    eight = _eight(ENTRIES)

    await eight.update_maintenance_insert()

    assert eight.next_insert_replacement == date(2026, 10, 9)
    assert eight.last_insert_replacement == date(2026, 4, 9)
    eight.api_request.assert_awaited_once_with(
        "get",
        f"{APP_API_URL}v1/user/user-9/device_maintenance/maintenance_insert",
        params={"v": "2"},
    )


@pytest.mark.asyncio
async def test_fetches_at_most_daily():
    eight = _eight(ENTRIES)

    await eight.update_maintenance_insert()
    await eight.update_maintenance_insert()
    assert eight.api_request.await_count == 1

    eight._last_insert_update -= timedelta(days=1, seconds=1)
    await eight.update_maintenance_insert()
    assert eight.api_request.await_count == 2


@pytest.mark.asyncio
async def test_device_without_a_schedule_reads_none():
    eight = _eight(ENTRIES)
    eight.device_id = "dev-none"

    await eight.update_maintenance_insert()

    assert eight.next_insert_replacement is None
    assert eight.last_insert_replacement is None


@pytest.mark.asyncio
async def test_request_error_keeps_values_and_waits_a_day():
    eight = _eight(ENTRIES)
    await eight.update_maintenance_insert()
    eight._last_insert_update -= timedelta(days=2)

    eight.api_request = AsyncMock(side_effect=RequestError("boom", status=404))
    await eight.update_maintenance_insert()
    await eight.update_maintenance_insert()

    assert eight.next_insert_replacement == date(2026, 10, 9)
    assert eight.api_request.await_count == 1


@pytest.mark.asyncio
async def test_sensor_is_a_date_with_the_last_replacement():
    eight = MagicMock()
    eight.device_id = "dev-pod"
    eight.users = {}
    eight.next_insert_replacement = date(2026, 10, 9)
    eight.last_insert_replacement = date(2026, 4, 9)
    config_entry_data = MagicMock()
    config_entry_data.api = eight
    entry = MagicMock(entry_id="test_entry")
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: config_entry_data}}

    added: list = []
    with patch(
        "custom_components.eight_sleep.sensor.async_get_current_platform",
        return_value=MagicMock(),
    ):
        await async_setup_entry(hass, entry, added.extend)

    sensor = next(e for e in added if e._sensor == "next_insert_replacement")
    assert sensor.device_class == SensorDeviceClass.DATE
    assert sensor.native_value == date(2026, 10, 9)
    assert sensor.extra_state_attributes == {"Last Replacement": date(2026, 4, 9)}


@pytest.mark.asyncio
async def test_user_update_refreshes_the_dates():
    """The sensor listens to the user coordinator, so that update fetches."""
    eight = _eight(ENTRIES)

    await eight.update_user_data()

    assert eight.next_insert_replacement == date(2026, 10, 9)
