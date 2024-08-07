from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

"""Eight Sleep constants."""
DOMAIN = "eight_sleep"

HEAT_ENTITY = "heat"
USER_ENTITY = "user"


class NameMapEntity:
    def __init__(
        self, name, measurement=None, state_class=None, device_class=None
    ) -> None:
        self.name = name
        self.measurement = measurement
        self.state_class = state_class
        self.device_class = device_class

    def __str__(self) -> str:
        return self.name


NAME_MAP = {
    "current_sleep_quality_score": NameMapEntity("Sleep Quality Score", "%"),
    "current_sleep_fitness_score": NameMapEntity("Sleep Fitness Score", "Score"),
    "current_sleep_routine_score": NameMapEntity("Sleep Routine Score", "%"),
    "current_heart_rate": NameMapEntity("Heart Rate", "bpm"),
    "current_hrv": NameMapEntity("HRV", "ms"),
    "current_breath_rate": NameMapEntity("Breath Rate", "/min"),
    "time_slept": NameMapEntity(
        "Time Slept", "s", SensorDeviceClass.DURATION, SensorDeviceClass.DURATION
    ),
    "presence_start": NameMapEntity(
        "Previous Presence Start",
    ),
    "presence_end": NameMapEntity(
        "Previous Presence End",
    ),
}

SERVICE_HEAT_SET = "heat_set"
SERVICE_HEAT_INCREMENT = "heat_increment"
SERVICE_SIDE_OFF = "side_off"
SERVICE_SIDE_ON = "side_on"
SERVICE_ALARM_SNOOZE = "alarm_snooze"
SERVICE_ALARM_STOP = "alarm_stop"
SERVICE_ALARM_DISMISS = "alarm_dismiss"
SERVICE_AWAY_MODE_START = "away_mode_start"
SERVICE_AWAY_MODE_STOP = "away_mode_stop"

ATTR_TARGET = "target"
ATTR_DURATION = "duration"
ATTR_SERVICE_SLEEP_STAGE = "sleep_stage"
