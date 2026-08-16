"""Values the device owns must not be pushed back on startup."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.eight_sleep.number import (
    FEET_DESCRIPTION,
    HEAD_DESCRIPTION,
    SNOOZE_MINUTES_DESCRIPTION,
    EightNumberEntity,
)


def _entity(restore_previous):
    ent = EightNumberEntity.__new__(EightNumberEntity)
    ent._restore_previous = restore_previous
    ent._set_value_callback = MagicMock()
    return ent


async def _added(ent, last_state):
    with patch.object(
        EightNumberEntity, "async_get_last_state", AsyncMock(return_value=last_state)
    ) as leer, patch(
        "custom_components.eight_sleep.EightSleepBaseEntity.async_added_to_hass",
        AsyncMock(),
    ):
        await EightNumberEntity.async_added_to_hass(ent)
    return leer


class TestNumberRestore(unittest.IsolatedAsyncioTestCase):
    """Restoring a base angle re-sends a real command that moves the bed."""

    async def test_no_restore_does_not_call_the_setter(self):
        ent = _entity(restore_previous=False)
        estado = MagicMock()
        estado.state = "12"

        await _added(ent, estado)

        ent._set_value_callback.assert_not_called()

    async def test_no_restore_does_not_even_read_the_last_state(self):
        ent = _entity(restore_previous=False)

        leer = await _added(ent, None)

        leer.assert_not_awaited()

    async def test_restore_still_works_where_it_is_wanted(self):
        """Snooze minutes has no server-side counterpart; it must keep restoring."""
        ent = _entity(restore_previous=True)
        estado = MagicMock()
        estado.state = "12"

        await _added(ent, estado)

        ent._set_value_callback.assert_called_once_with(12.0)

    async def test_restore_ignores_unusable_states(self):
        for valor in ("unknown", "unavailable", "not-a-number"):
            with self.subTest(valor=valor):
                ent = _entity(restore_previous=True)
                estado = MagicMock()
                estado.state = valor

                await _added(ent, estado)

                ent._set_value_callback.assert_not_called()

    def test_default_keeps_the_previous_behaviour(self):
        """Anything not opting out must still restore, so nothing else changes."""
        import inspect

        firma = inspect.signature(EightNumberEntity.__init__)
        self.assertIs(firma.parameters["restore_previous"].default, True)


if __name__ == '__main__':
    unittest.main()
