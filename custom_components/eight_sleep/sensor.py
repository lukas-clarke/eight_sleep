"""Support for Eight Sleep sensors."""

from __future__ import annotations

import logging
from typing import Any

from custom_components.eight_sleep.pyEight.user import EightUser

from .pyEight.eight import EightSleep
import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    CONF_BINARY_SENSORS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import EightSleepBaseEntity, EightSleepConfigEntryData
from .const import (
    ATTR_DURATION,
    ATTR_TARGET,
    ATTR_SERVICE_SLEEP_STAGE,
    DOMAIN,
    SERVICE_HEAT_SET,
    SERVICE_HEAT_INCREMENT,
    SERVICE_SIDE_OFF,
    SERVICE_SIDE_ON,
    SERVICE_ALARM_SNOOZE,
    SERVICE_ALARM_STOP,
    SERVICE_ALARM_DISMISS,
    SERVICE_AWAY_MODE_START,
    SERVICE_AWAY_MODE_STOP,
    NAME_MAP,
)

ATTR_ROOM_TEMP = "Room Temperature"
ATTR_AVG_ROOM_TEMP = "Average Room Temperature"
ATTR_BED_TEMP = "Bed Temperature"
ATTR_AVG_BED_TEMP = "Average Bed Temperature"
ATTR_RESP_RATE = "Respiratory Rate"
ATTR_AVG_RESP_RATE = "Average Respiratory Rate"
ATTR_HEART_RATE = "Heart Rate"
ATTR_AVG_HEART_RATE = "Average Heart Rate"
ATTR_SLEEP_DUR = "Time Slept"
ATTR_LIGHT_PERC = f"Light Sleep {PERCENTAGE}"
ATTR_DEEP_PERC = f"Deep Sleep {PERCENTAGE}"
ATTR_REM_PERC = f"REM Sleep {PERCENTAGE}"
ATTR_TNT = "Tosses & Turns"
ATTR_SLEEP_STAGE = "Sleep Stage"
ATTR_TARGET_HEAT = "Target Heating Level"
ATTR_TARGET_BED_TEMP = "Target Bed Temperature"
ATTR_ACTIVE_HEAT = "Heating Active"
ATTR_DURATION_HEAT = "Heating Time Remaining"
ATTR_PROCESSING = "Processing"
ATTR_SESSION_START = "Session Start"
ATTR_FIT_DATE = "Fitness Date"
ATTR_FIT_DURATION_SCORE = "Fitness Duration Score"
ATTR_FIT_ASLEEP_SCORE = "Fitness Asleep Score"
ATTR_FIT_OUT_SCORE = "Fitness Out-of-Bed Score"
ATTR_FIT_WAKEUP_SCORE = "Fitness Wakeup Score"
ATTR_ALARM_ID = "Alarm ID"

_LOGGER = logging.getLogger(__name__)

EIGHT_USER_SENSORS = [
    "current_sleep_fitness_score",
    "current_sleep_quality_score",
    "current_sleep_routine_score",
    "time_slept",
    "current_heart_rate",
    "current_hrv",
    "current_breath_rate",
    "bed_temperature",
    "target_heating_temp",
    "sleep_stage",
    "next_alarm",
    "bed_state_type",
    "presence_start",
    "presence_end",
    "side",
]

EIGHT_HEAT_SENSORS = ["bed_state"]
EIGHT_ROOM_SENSORS = [
    "room_temperature",
    "need_priming",
    "is_priming",
    "has_water",
    "last_prime",
]

VALID_TARGET_HEAT = vol.All(vol.Coerce(int), vol.Clamp(min=-100, max=100))
VALID_DURATION = vol.All(vol.Coerce(int), vol.Clamp(min=0, max=28800))

SERVICE_EIGHT_SCHEMA = {
    ATTR_TARGET: VALID_TARGET_HEAT,
    ATTR_DURATION: VALID_DURATION,
    ATTR_SERVICE_SLEEP_STAGE: vol.All(vol.Coerce(str)),
}

SERVICE_HEAT_INCREMENT_SCHEMA = {
    ATTR_TARGET: VALID_TARGET_HEAT,
}

VALID_SNOOZE_DURATION = vol.All(vol.Coerce(int), vol.Clamp(min=1, max=1440))
SERVICE_ALARM_SNOOZE_SCHEMA = {
    ATTR_DURATION: VALID_SNOOZE_DURATION,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the eight sleep sensors."""
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api
    device_coordinator = config_entry_data.device_coordinator
    user_coordinator = config_entry_data.user_coordinator

    all_sensors: list[SensorEntity] = []

    for user in eight.users.values():
        all_sensors.extend(
            EightUserSensor(entry, user_coordinator, eight, user, sensor)
            for sensor in EIGHT_USER_SENSORS
        )
        all_sensors.extend(
            EightHeatSensor(entry, device_coordinator, eight, user, sensor)
            for sensor in EIGHT_HEAT_SENSORS
        )

    all_sensors.extend(
        EightRoomSensor(entry, user_coordinator, eight, sensor)
        for sensor in EIGHT_ROOM_SENSORS
    )

    async_add_entities(all_sensors)

    platform = async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_HEAT_SET,
        SERVICE_EIGHT_SCHEMA,
        "async_heat_set",
    )
    platform.async_register_entity_service(
        SERVICE_HEAT_INCREMENT,
        SERVICE_HEAT_INCREMENT_SCHEMA,
        "async_heat_increment",
    )
    platform.async_register_entity_service(
        SERVICE_SIDE_OFF,
        {},
        "async_side_off",
    )
    platform.async_register_entity_service(
        SERVICE_SIDE_ON,
        {},
        "async_side_on",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_SNOOZE,
        SERVICE_ALARM_SNOOZE_SCHEMA,
        "async_alarm_snooze",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_STOP,
        {},
        "async_alarm_stop",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_DISMISS,
        {},
        "async_alarm_dismiss",
    )
    platform.async_register_entity_service(
        SERVICE_AWAY_MODE_START,
        {},
        "async_start_away_mode",
    )
    # The API currently doesn't have a stop for the away mode
    platform.async_register_entity_service(
        SERVICE_AWAY_MODE_STOP,
        {},
        "async_stop_away_mode",
    )
    platform.async_register_entity_service(
        "prime_pod",
        {},
        "async_prime_pod",
    )
    platform.async_register_entity_service(
        "set_bed_side",
        {
            "bed_side_state": vol.All(vol.Coerce(str)),
        },
        "async_set_bed_side",
    )


class EightHeatSensor(EightSleepBaseEntity, SensorEntity):
    """Representation of an eight sleep heat-based sensor."""

    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser | None,
        sensor: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry, coordinator, eight, user, sensor)

        _LOGGER.debug(
            "Heat Sensor: %s, Side: %s, User: %s",
            self._sensor,
            self._user_obj.side,
            self._user_obj.user_id,
        )

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        assert self._user_obj
        return self._user_obj.heating_level

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device state attributes."""
        assert self._user_obj
        return {
            ATTR_TARGET_HEAT: self._user_obj.target_heating_level,
            ATTR_ACTIVE_HEAT: self._user_obj.now_heating,
            ATTR_DURATION_HEAT: self._user_obj.heating_remaining,
        }


def _get_breakdown_percent(
    attr: dict[str, Any], key: str, denominator: int | float
) -> int | float:
    """Get a breakdown percent."""
    try:
        return round((attr["breakdown"][key] / denominator) * 100, 2)
    except (ZeroDivisionError, KeyError):
        return 0


def _get_rounded_value(attr: dict[str, Any], key: str) -> int | float | None:
    """Get rounded value for given key."""
    if (val := attr.get(key)) is None:
        return None
    return round(val, 2)


class EightUserSensor(EightSleepBaseEntity, SensorEntity):
    """Representation of an eight sleep user-based sensor."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser | None,
        sensor: str,
        base_entity: bool = False
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry, coordinator, eight, user, sensor, base_entity)
        assert self._user_obj

        if self._sensor == "bed_temperature":
            self._attr_icon = "mdi:thermometer"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif self._sensor in (NAME_MAP):
            self._attr_native_unit_of_measurement = NAME_MAP[self._sensor].measurement
            self._attr_device_class = NAME_MAP[self._sensor].device_class
            self._attr_state_class = NAME_MAP[self._sensor].state_class
        elif (
            self._sensor == "sleep_stage"
            or self._sensor == "bed_state_type"
            or self._sensor == "side"
        ):
            # These have string values, leave the class None
            pass
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT

        _LOGGER.debug(
            "User Sensor: %s, Side: %s, User: %s",
            self._sensor,
            self._user_obj.side,
            self._user_obj.user_id,
        )

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        if not self._user_obj:
            return None

        if self._sensor in NAME_MAP:
            return getattr(self._user_obj, self._sensor)
        if "bed_state_type" in self._sensor:
            return self._user_obj.bed_state_type
        if "last" in self._sensor:
            return self._user_obj.last_sleep_score
        if self._sensor == "side":
            return self._user_obj.side
        if self._sensor == "bed_temperature":
            return self._user_obj.current_bed_temp
        if self._sensor == "sleep_stage":
            return self._user_obj.current_sleep_stage

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return device state attributes."""
        attr = None
        if "current" in self._sensor and self._user_obj:
            if "fitness" in self._sensor:
                attr = self._user_obj.current_fitness_values
            else:
                attr = self._user_obj.current_values
        elif "last" in self._sensor and self._user_obj:
            attr = self._user_obj.last_values
        elif "next_alarm" in self._sensor and self._user_obj:
            state_attr = {
                ATTR_ALARM_ID: self._user_obj.next_alarm_id,
            }
            return state_attr

        if attr is None:
            # Skip attributes if sensor type doesn't support
            return None

        if "fitness" in self._sensor:
            state_attr = {
                ATTR_FIT_DATE: attr["date"],
                ATTR_FIT_DURATION_SCORE: attr["duration"],
                ATTR_FIT_ASLEEP_SCORE: attr["asleep"],
                ATTR_FIT_OUT_SCORE: attr["out"],
                ATTR_FIT_WAKEUP_SCORE: attr["wakeup"],
            }
            return state_attr

        state_attr = {ATTR_SESSION_START: attr["date"]}
        state_attr[ATTR_TNT] = attr["tnt"]
        state_attr[ATTR_PROCESSING] = attr["processing"]

        if attr.get("breakdown") is not None:
            sleep_time = sum(attr["breakdown"].values()) - attr["breakdown"]["awake"]
            state_attr[ATTR_SLEEP_DUR] = sleep_time
            state_attr[ATTR_LIGHT_PERC] = _get_breakdown_percent(
                attr, "light", sleep_time
            )
            state_attr[ATTR_DEEP_PERC] = _get_breakdown_percent(
                attr, "deep", sleep_time
            )
            state_attr[ATTR_REM_PERC] = _get_breakdown_percent(attr, "rem", sleep_time)

        room_temp = _get_rounded_value(attr, "room_temp")
        bed_temp = _get_rounded_value(attr, "bed_temp")

        if "current" in self._sensor:
            state_attr[ATTR_RESP_RATE] = _get_rounded_value(attr, "resp_rate")
            state_attr[ATTR_HEART_RATE] = _get_rounded_value(attr, "heart_rate")
            state_attr[ATTR_SLEEP_STAGE] = attr["stage"]
            state_attr[ATTR_ROOM_TEMP] = room_temp
            state_attr[ATTR_BED_TEMP] = bed_temp
        elif "last" in self._sensor:
            state_attr[ATTR_AVG_RESP_RATE] = _get_rounded_value(attr, "resp_rate")
            state_attr[ATTR_AVG_HEART_RATE] = _get_rounded_value(attr, "heart_rate")
            state_attr[ATTR_AVG_ROOM_TEMP] = room_temp
            state_attr[ATTR_AVG_BED_TEMP] = bed_temp

        return state_attr


class EightRoomSensor(EightSleepBaseEntity, SensorEntity):
    """Representation of an eight sleep room sensor."""

    def __init__(
        self,
        entry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        sensor: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry, coordinator, eight, None, sensor)
        if self._sensor == "room_temperature":
            self._attr_icon = "mdi:thermometer"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif self._sensor == "last_prime":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        else:
            self._attr_state_class = CONF_BINARY_SENSORS
            self._attr_device_class = CONF_BINARY_SENSORS

    @property
    def native_value(self) -> int | float | None:
        """Return the state of the sensor."""
        # return self._eight.room_temperature
        return getattr(self._eight, self._sensor)
