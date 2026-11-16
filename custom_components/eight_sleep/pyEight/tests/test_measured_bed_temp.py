"""Measured bed temperature comes from the session timeseries (#163).

A Pod 6 sends the bed temperature it measures only as tempBedC in
sessions[].timeseries, about once an hour. current_bed_temp is the heating
level converted to degrees, so it must stay as it is and the measured value
gets its own property.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.eight_sleep.const import NAME_MAP
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser
from custom_components.eight_sleep.sensor import EIGHT_USER_SENSORS, EightUserSensor
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

# The shape a Pod 6 trend has: hourly bed and room readings, heart rate every
# five minutes, an empty heating series and no tempBedC in sleepQualityScore.
# The values are made up.
POD6_TREND = {
    "day": "2026-10-28",
    "presenceStart": "2026-10-27T12:05:00.000Z",
    "sleepQualityScore": {"heartRate": {"score": 80}},
    "sessions": [{
        "timeseries": {
            "tempBedC": [
                ["2026-10-27T12:00:00.000Z", 27.1],
                ["2026-10-27T13:00:00.000Z", 28.4],
                ["2026-10-27T14:00:00.000Z", 29.0],
            ],
            "tempRoomC": [
                ["2026-10-27T12:00:00.000Z", 21.2],
                ["2026-10-27T13:00:00.000Z", 21.0],
                ["2026-10-27T14:00:00.000Z", 20.8],
            ],
            "heartRate": [
                ["2026-10-27T12:05:00.000Z", 58],
                ["2026-10-27T12:10:00.000Z", 57],
            ],
            "heating": [],
        },
    }],
}


class TestMeasuredBedTemp(unittest.TestCase):
    def setUp(self):
        device = AsyncMock(spec=EightSleep)
        device.timezone = "Australia/Brisbane"
        device.device_data = {}
        device.device_id = "device_1"
        self.user = EightUser(device, "user_1", "left")

    def test_reads_the_last_measured_reading(self):
        self.user.trends = [POD6_TREND]

        self.assertEqual(self.user.current_measured_bed_temp, 29.0)

    def test_heating_level_bed_temp_is_unchanged(self):
        """The old sensor still reports the heating level, not tempBedC."""
        self.user.trends = [POD6_TREND]
        self.user.current_side_temp = 33

        self.assertEqual(self.user.current_bed_temp, 33)
        self.assertEqual(self.user.current_measured_bed_temp, 29.0)

    def test_reads_the_latest_session_of_the_latest_trend(self):
        earlier = {"sessions": [{"timeseries": {"tempBedC": [["t", 25.0]]}}]}
        two_sessions = {"sessions": [
            {"timeseries": {"tempBedC": [["t", 26.0]]}},
            {"timeseries": {"tempBedC": [["t", 30.5]]}},
        ]}
        self.user.trends = [earlier, two_sessions]

        self.assertEqual(self.user.current_measured_bed_temp, 30.5)

    def test_rejects_the_string_none(self):
        self.user.trends = [{"sessions": [{"timeseries": {"tempBedC": [["t", "None"]]}}]}]

        self.assertIsNone(self.user.current_measured_bed_temp)

    def test_none_without_readings(self):
        for trends in (
            [],
            [{"sessions": [{}]}],
            [{"sessions": [{"timeseries": {"tempBedC": []}}]}],
            [{"sessions": [{"timeseries": {"tempRoomC": [["t", 21.0]]}}]}],
        ):
            self.user.trends = trends
            self.assertIsNone(self.user.current_measured_bed_temp)


class TestMeasuredBedTempSensor(unittest.TestCase):
    def test_is_a_user_sensor_in_celsius(self):
        self.assertIn("current_measured_bed_temp", EIGHT_USER_SENSORS)
        entity = NAME_MAP["current_measured_bed_temp"]
        self.assertEqual(str(entity), "Measured Bed Temperature")
        self.assertEqual(entity.measurement, "°C")
        self.assertEqual(entity.device_class, SensorDeviceClass.TEMPERATURE)
        self.assertEqual(entity.state_class, SensorStateClass.MEASUREMENT)

    def test_old_bed_temperature_sensor_is_kept(self):
        self.assertIn("bed_temperature", EIGHT_USER_SENSORS)

    def test_entity_reports_the_measured_reading(self):
        device = AsyncMock(spec=EightSleep)
        device.timezone = "Australia/Brisbane"
        device.device_data = {}
        device.device_id = "device_1"
        user = EightUser(device, "user_1", "left")
        user.trends = [POD6_TREND]
        user.current_side_temp = 33

        measured = EightUserSensor(MagicMock(), MagicMock(), device, user, "current_measured_bed_temp")
        heating = EightUserSensor(MagicMock(), MagicMock(), device, user, "bed_temperature")

        self.assertEqual(measured.name, "Measured Bed Temperature")
        self.assertEqual(measured.native_unit_of_measurement, "°C")
        self.assertEqual(measured.device_class, SensorDeviceClass.TEMPERATURE)
        self.assertEqual(measured.native_value, 29.0)
        self.assertEqual(heating.native_value, 33)
        self.assertNotEqual(measured.unique_id, heating.unique_id)
        self.assertIsInstance(measured.extra_state_attributes, dict)
