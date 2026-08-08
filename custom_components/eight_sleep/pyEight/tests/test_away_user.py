"""An away user has no session data; nothing may raise on it (#52)."""
import unittest
from unittest.mock import AsyncMock

from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser

# last_sleep_breakdown reads trends[-2], so a later session has to exist or the
# property returns None for lack of data and the test proves nothing.
SESION_POSTERIOR = {"score": 1, "sessions": [{}]}


class TestAwayUserNullData(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        device = AsyncMock(spec=EightSleep)
        device.timezone = "America/New_York"
        device.device_data = {}
        device.device_id = "device_1"
        self.user = EightUser(device, "user_1", "left")

    def _con_sesion(self, sesion):
        """Put `sesion` where last_sleep_breakdown will actually read it."""
        self.user.trends = [sesion, SESION_POSTERIOR]

    def test_sleep_breakdown_without_durations(self):
        """An away side reports a session with no durations at all."""
        self._con_sesion({"score": 0, "sessions": [{}]})

        self.assertIsNone(self.user.last_sleep_breakdown)

    def test_sleep_breakdown_with_only_presence(self):
        """Half the pair present is enough to break the subtraction."""
        self._con_sesion({"presenceDuration": 3600, "sessions": [{}]})

        resultado = self.user.last_sleep_breakdown

        self.assertNotIn("awake", resultado or {})

    def test_sleep_breakdown_with_the_string_none(self):
        """The API sends the literal string "None" for absent values."""
        self._con_sesion({
            "presenceDuration": "None",
            "sleepDuration": "None",
            "sessions": [{}],
        })

        self.assertIsNone(self.user.last_sleep_breakdown)

    def test_sleep_breakdown_still_computes_when_both_present(self):
        """The real path must keep working, or the guard is just hiding data."""
        self._con_sesion({
            "presenceDuration": 3600,
            "sleepDuration": 3000,
            "lightDuration": 2000,
            "sessions": [{}],
        })

        resultado = self.user.last_sleep_breakdown

        self.assertEqual(resultado["awake"], 600)
        self.assertEqual(resultado["light"], 2000)

    def test_current_trend_value_rejects_the_string_none(self):
        """A "None" in the timeseries must not reach a numeric sensor."""
        self.user.trends = [{"sessions": [{"timeseries": {"tempRoomC": [["t", "None"]]}}]}]

        self.assertIsNone(self.user.current_room_temp)

    def test_current_trend_value_still_returns_real_readings(self):
        self.user.trends = [{"sessions": [{"timeseries": {"tempRoomC": [["t", 21.5]]}}]}]

        self.assertEqual(self.user.current_room_temp, 21.5)

    def test_heart_rate_rejects_the_string_none(self):
        self.user.trends = [{"sessions": [{"timeseries": {"heartRate": [["t", "None"]]}}]}]

        self.assertIsNone(self.user.current_heart_rate)


if __name__ == '__main__':
    unittest.main()
