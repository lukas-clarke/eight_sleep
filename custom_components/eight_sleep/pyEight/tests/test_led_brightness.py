"""Hub LED brightness read/write (issue #133)."""
import unittest
from unittest.mock import AsyncMock, patch

from custom_components.eight_sleep.pyEight.eight import EightSleep


class TestLedBrightness(unittest.IsolatedAsyncioTestCase):
    """Verified against a live Pod 5: the device resource accepts the PUT."""

    def setUp(self):
        self.eight = EightSleep("u@example.com", "pw", "America/New_York")
        self.eight.device_id = "device_1"

    def test_none_before_any_device_payload(self):
        self.assertIsNone(self.eight.led_brightness)

    def test_reads_the_value_from_the_device_payload(self):
        self.eight._device_json_list = [{"ledBrightnessLevel": 40}]

        self.assertEqual(self.eight.led_brightness, 40)

    def test_none_when_the_hub_does_not_report_it(self):
        """A pod without the field must not grow a dead entity."""
        self.eight._device_json_list = [{"online": True}]

        self.assertIsNone(self.eight.led_brightness)

    def test_string_value_is_coerced(self):
        self.eight._device_json_list = [{"ledBrightnessLevel": "75"}]

        self.assertEqual(self.eight.led_brightness, 75)

    async def test_set_puts_to_the_device_resource(self):
        self.eight._device_json_list = [{"ledBrightnessLevel": 100}]
        self.eight.api_request = AsyncMock()

        await self.eight.set_led_brightness(40)

        method, url = self.eight.api_request.await_args[0][:2]
        self.assertEqual(method, "PUT")
        self.assertTrue(url.endswith("/devices/device_1"))
        self.assertEqual(
            self.eight.api_request.await_args.kwargs["data"],
            {"ledBrightnessLevel": 40},
        )

    async def test_set_updates_the_cached_value(self):
        """Otherwise the entity snaps back until the next refresh."""
        self.eight._device_json_list = [{"ledBrightnessLevel": 100}]
        self.eight.api_request = AsyncMock()

        await self.eight.set_led_brightness(40)

        self.assertEqual(self.eight.led_brightness, 40)

    async def test_set_clamps_out_of_range(self):
        self.eight._device_json_list = [{"ledBrightnessLevel": 50}]
        self.eight.api_request = AsyncMock()

        await self.eight.set_led_brightness(500)
        await self.eight.set_led_brightness(-500)

        enviados = [c.kwargs["data"] for c in self.eight.api_request.await_args_list]
        self.assertEqual(enviados[0], {"ledBrightnessLevel": 100})
        self.assertEqual(enviados[1], {"ledBrightnessLevel": 0})

    async def test_set_without_cached_payload_does_not_raise(self):
        """Setting before the first refresh must still send the request."""
        self.eight.api_request = AsyncMock()

        await self.eight.set_led_brightness(30)

        self.eight.api_request.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()


class TestLedBrightnessEntityWiring(unittest.IsolatedAsyncioTestCase):
    """The number entity must not write back to the hub on startup."""

    def test_entity_key_matches_the_displayed_name(self):
        """EightSleepBaseEntity derives _attr_name from the key and that wins
        over entity_description.name, so a mismatch would ship a wrong label."""
        from custom_components.eight_sleep.number import LED_BRIGHTNESS_DESCRIPTION as d

        self.assertEqual(d.key.replace("_", " ").title(), d.name)

    async def test_restore_disabled_does_not_write_on_startup(self):
        """Restoring would overwrite a change made in the app while HA was down."""
        from custom_components.eight_sleep.number import EightNumberEntity

        escrito = []
        ent = EightNumberEntity.__new__(EightNumberEntity)
        ent._restore_previous = False
        ent._set_value_callback = escrito.append

        with patch.object(
            EightNumberEntity, "async_get_last_state", AsyncMock(return_value=None)
        ) as leer, patch(
            "custom_components.eight_sleep.EightSleepBaseEntity.async_added_to_hass",
            AsyncMock(),
        ):
            await EightNumberEntity.async_added_to_hass(ent)

        self.assertEqual(escrito, [])
        leer.assert_not_awaited()

    async def test_restore_enabled_still_writes(self):
        """The snooze entity relies on this; it must keep working."""
        from unittest.mock import MagicMock

        from custom_components.eight_sleep.number import EightNumberEntity

        escrito = []
        ent = EightNumberEntity.__new__(EightNumberEntity)
        ent._restore_previous = True
        ent._set_value_callback = escrito.append
        estado = MagicMock()
        estado.state = "12"

        with patch.object(
            EightNumberEntity, "async_get_last_state", AsyncMock(return_value=estado)
        ), patch(
            "custom_components.eight_sleep.EightSleepBaseEntity.async_added_to_hass",
            AsyncMock(),
        ):
            await EightNumberEntity.async_added_to_hass(ent)

        self.assertEqual(escrito, [12.0])
