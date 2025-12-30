"""
pyeight.user
~~~~~~~~~~~~~~~~~~~~
Provides user data for Eight Sleep
Copyright (c) 2022-2023 <https://github.com/lukas-clarke/pyEight>
Licensed under the MIT license.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import statistics
from typing import TYPE_CHECKING, Any

from .exceptions import RequestError
from .constants import APP_API_URL, DATE_FORMAT, DATE_TIME_ISO_FORMAT, CLIENT_API_URL, POSSIBLE_SLEEP_STAGES
from .util import heating_level_to_temp

if TYPE_CHECKING:
    from .eight import EightSleep

_LOGGER = logging.getLogger(__name__)


class EightUser:  # pylint: disable=too-many-public-methods
    """Class for handling data of each eight user."""

    def __init__(self, device: "EightSleep", user_id: str, side: str):
        """Initialize user class."""
        self.device = device
        self.user_id = user_id
        self.side = side
        self._user_profile: dict[str, Any] = {}
        self._base_data: dict[str, Any] = {}
        self.trends: list[dict[str, Any]] = []
        self.routines: list[dict[str, Any]] = []
        self.smart_schedule: dict[str, Any] | None = None
        self.next_alarm = None
        self.next_alarm_id = None
        self.bed_state_type = None
        self.current_side_temp = None
        self.target_heating_temp = None

    def get_autopilot_target_temp(self, unit: str = "c") -> float | None:
        """Return the temperature that Autopilot (smart schedule) is currently targeting."""
        if not self.smart_schedule:
            return None
        # bedTimeLevel seems to be the primary target for the active sleep session
        level = self.smart_schedule.get("bedTimeLevel")
        if level is None:
            return None
        try:
            return heating_level_to_temp(float(level), unit)
        except (ValueError, TypeError):
            return None

    def _get_trend(self, trend_num: int, keys: str | tuple[str, ...]) -> Any:
        """Get trend value for specified key."""
        if len(self.trends) < trend_num + 1:
            return None
# ... (omitting unchanged lines for brevity if possible, keeping Context) ...
# Actually replace_file_content requires exact match. I'll target the __init__ and update_user separately if needed?
# No, I can do it in chunks or one big block if contiguous.
# __init__ and update_user are far apart. I should use multi_replace.

        """Get trend value for specified key."""
        if len(self.trends) < trend_num + 1:
            return None
        data_source = self.trends[-(trend_num + 1)] # Use a different variable name to avoid confusion
        if isinstance(keys, str):
            value = data_source.get(keys)
            return None if value == "None" else value

        # Traverse the keys
        current_data = data_source
        for key in keys[:-1]:
            if not isinstance(current_data, dict): # Ensure current_data is a dict before .get
                return None
            current_data = current_data.get(key)
            if current_data is None: # Stop if any intermediate key is missing
                return None
            # If an intermediate key's value is "None" string, treat as actual None for traversal
            if current_data == "None":
                return None

        if not isinstance(current_data, dict): # Final check before the last .get
            # If current_data itself became "None" string and was the target (e.g. keys has only one element after initial data_source)
            # This case should be handled by the loop's "if current_data == "None":" check if keys has more than one element.
            # If keys had only one element, this path isn't taken.
            # However, if the expected structure is dict but we got "None" string, it should be None.
            return None
        value = current_data.get(keys[-1])
        return None if value == "None" else value

    def _get_quality_score(self, trend_num: int, key: str) -> Any:
        """Get quality score for specified key."""
        return self._get_trend(trend_num, ("sleepQualityScore", key, "score"))

    def _get_routine_score(self, trend_num: int, key: str) -> Any:
        """Get routine score for specified key."""
        return self._get_trend(trend_num, ("sleepRoutineScore", key, "score"))

    def _get_sleep_score(self, trend_num: int) -> int | None:
        """Return sleep score for a given trend."""
        return self._get_trend(trend_num, "score")

    def _trend_timeseries(self) -> dict[str, Any] | None:
        """Return the timeseries for the latest trend."""
        if not self.trends:
            return None
        return self.trends[-1].get("sessions", [{}])[-1].get("timeseries", {})

    def _get_current_trend_property_value(self, key: str) -> int | float | None:
        """Get current property from trends."""
        if (
            not (timeseries_data := self._trend_timeseries())
            or timeseries_data.get(key) is None
        ):
            return None
        return timeseries_data[key][-1][1]

    def _session_date(self, trend_num: int) -> datetime | None:
        """Get session date for given trend."""
        if (
            len(self.trends) < trend_num + 1
            or (session_date := self.trends[-(trend_num + 1)].get("presenceStart")) is None
        ):
            return None
        return self.device.convert_string_to_datetime(session_date)

    def _sleep_breakdown(self, trend_num: int) -> dict[str, Any] | None:
        """Return durations of sleep stages for given session."""
        if len(self.trends) < (trend_num + 1):
            return None
        breakdown = {
            "light": self._get_trend(trend_num, "lightDuration"),
            "deep": self._get_trend(trend_num, "deepDuration"),
            "rem": self._get_trend(trend_num, "remDuration"),
            "awake": self._get_trend(trend_num, "presenceDuration") - self._get_trend(trend_num, "sleepDuration")
        }
        return {k: v for k, v in breakdown.items() if v is not None}

    def _session_processing(self, trend_num: int) -> bool | None:
        """Return processing state of given session."""
        if len(self.trends) < trend_num + 1:
            return None
        return self.trends[-(trend_num + 1)].get("processing", False)

    def _get_routine(self, id: str) -> dict[str, Any]:
        """Get routine data for the specified ID."""
        for routine in self.routines:
            if routine["id"] == id:
                return routine

        raise Exception(f"Routine with ID {id} not found")

    def get_alarm_enabled(self, id: str | None) -> bool:
        """Get alarm enabled for the specified ID.
        If no ID is specified, the next alarm will be used."""
        check_next_alarm = id is None
        if check_next_alarm:
            if self.next_alarm_id:
                id = self.next_alarm_id
            else:
                return False

        # There are two fields that represent the state of an alarm:
        #
        # "enabled" represents whether the alarm will be active next time.
        # We use this when displaying the next alarm as it can be toggled
        # on/off independently of your routine.
        #
        # "disabledIndividually" represents whether the user turned off the alarm
        # for all days of a routine. We use this when displaying regular alarms.
        for routine in self.routines:
            if "override" in routine:
                for alarm in routine["override"]["alarms"]:
                    if alarm["alarmId"] == id:
                        return alarm["enabled"] if check_next_alarm else not alarm["disabledIndividually"]

            for alarm in routine["alarms"]:
                if alarm["alarmId"] == id:
                    return alarm["enabled"] if check_next_alarm else not alarm["disabledIndividually"]

        raise Exception(f"Alarm with ID {id} not found")

    def _get_next_alarm_routine_id(self) -> str:
        for routine in self.routines:
            if "override" in routine:
                for alarm in routine["override"]["alarms"]:
                    if alarm["alarmId"] == self.next_alarm_id:
                        return routine["id"]

            for alarm in routine["alarms"]:
                if alarm["alarmId"] == self.next_alarm_id:
                    return routine["id"]

        raise Exception(f"Alarm with ID {self.next_alarm_id} not found")

    @property
    def user_profile(self) -> dict[str, Any] | None:
        """Return userdata."""
        return self._user_profile

    @property
    def base_data(self) -> dict[str, Any]:
        """Return the base data."""
        return self._base_data

    @property
    def base_data_for_side(self) -> dict[str, Any]:
        """Return the base data for the user's side.
        Currently the data is identical for both sides."""
        return self.base_data.get(self.corrected_side_for_key, {})

    @property
    def base_preset(self) -> str | None:
        """Return the base preset.
        Currently these are sleep, relaxing and reading."""
        return self.base_data_for_side.get("preset", {}).get("name")

    @property
    def leg_angle(self) -> int:
        """Return the base leg angle."""
        return self.base_data_for_side.get("leg", {}).get("currentAngle", 0)

    @property
    def torso_angle(self) -> int:
        """Return the base torso angle."""
        return self.base_data_for_side.get("torso", {}).get("currentAngle", 0)

    @property
    def in_snore_mitigation(self) -> bool:
        """Return the snore mitigation state."""
        return self.base_data_for_side.get("inSnoreMitigation", False)

    @property
    def bed_presence(self) -> bool:
        """Return true/false for bed presence based on recent heart rate data."""

        timeseries = self._trend_timeseries()
        if not timeseries or "heartRate" not in timeseries:
            return False

        heart_rate_entry = timeseries["heartRate"][-1]
        _LOGGER.debug(f"Last heart rate: {heart_rate_entry} for {self.user_id}")
        heart_rate_time = datetime.fromisoformat(heart_rate_entry[0].replace('Z', '+00:00'))

        time_difference = datetime.now(timezone.utc) - heart_rate_time

        # Consider the person present if the last heart rate reading was within the last 10 minutes
        # This assumes that trend are updated every 5 minutes
        return time_difference.total_seconds() < 600

    @property
    def target_heating_level(self) -> int | None:
        """Return target heating/cooling level."""
        return self.device.device_data.get(
            f"{self.corrected_side_for_key}TargetHeatingLevel"
        )

    @property
    def heating_level(self) -> int | None:
        """Return heating/cooling level."""
        key = f"{self.corrected_side_for_key}HeatingLevel"
        level = self.device.device_data.get(key)

        if level is not None:
            return level

        for data in self.device.device_data_history:
            level = data.get(key)
            if level is not None:
                return level

    @property
    def corrected_side_for_key(self) -> str:
        if self.side is None:
            _LOGGER.warning(f"User {self.user_id} has no side information; defaulting to 'left' for key access. This might lead to unexpected behavior.")
            return "left" # Defaulting to 'left' as a fallback
        if self.side.lower() == "solo":
            return "left"
        else:
            return self.side

    def past_heating_level(self, num) -> int:
        """Return a heating level from the past."""
        if num > 9 or len(self.device.device_data_history) < num + 1:
            return 0

        return self.device.device_data_history[num].get(
            f"{self.corrected_side_for_key}HeatingLevel", 0
        )

    def _now_heating_or_cooling(self, target_heating_level_check: bool) -> bool | None:
        """Return true/false if heating or cooling is currently happening."""
        key = f"{self.corrected_side_for_key}NowHeating"
        if (
            self.target_heating_level is None
            or (target := self.device.device_data.get(key)) is None
        ):
            return None
        return target and target_heating_level_check

    @property
    def now_heating(self) -> bool | None:
        """Return current heating state."""
        level = self.target_heating_level
        return self._now_heating_or_cooling(level is not None and level > 0)

    @property
    def now_cooling(self) -> bool | None:
        """Return current cooling state."""
        level = self.target_heating_level
        return self._now_heating_or_cooling(level is not None and level < 0)

    @property
    def heating_remaining(self) -> int | None:
        """Return seconds of heat/cool time remaining."""
        return self.device.device_data.get(
            f"{self.corrected_side_for_key}HeatingDuration"
        )

    @property
    def last_seen(self) -> str | None:
        """Return mattress last seen time.

        These values seem to be rarely updated correctly in the API.
        Don't expect accurate results from this property.
        """
        if not (
            last_seen := self.device.device_data.get(
                f"{self.corrected_side_for_key}PresenceEnd"
            )
        ):
            return None
        return datetime.fromtimestamp(int(last_seen)).strftime(DATE_TIME_ISO_FORMAT)

    @property
    def heating_values(self) -> dict[str, Any]:
        """Return a dict of all the current heating values."""
        return {
            "level": self.heating_level,
            "target": self.target_heating_level,
            "active": self.now_heating,
            "remaining": self.heating_remaining,
            "last_seen": self.last_seen,
        }

    @property
    def current_session_date(self) -> datetime | None:
        """Return date/time for start of last session data."""
        return self._session_date(0)

    @property
    def current_session_processing(self) -> bool | None:
        """Return processing state of current session."""
        return self._session_processing(0)

    @property
    def current_sleep_stage(self) -> str | None:
        """Return sleep stage for in-progress session."""
        if not self.trends:
            return None

        current_trend = self.trends[-1]
        sessions = current_trend.get('sessions', [])

        if not sessions:
            return None

        current_session = sessions[-1]
        stages = current_session.get('stages', [])

        if not stages:
            return None

        # API now always has an awake state last in the dict
        # so always pull the second to last stage while we are
        # in a processing state
        if self.current_session_processing:
            stage = stages[-2].get('stage') if len(stages) >= 2 else None
        else:
            stage = stages[-1].get('stage')

        return stage

    @property
    def current_sleep_score(self) -> int | None:
        """Return sleep score for in-progress session."""
        return self._get_sleep_score(0)

    @property
    def current_sleep_fitness_score(self) -> int | None:
        """Return sleep fitness score for latest session."""
        # return self._get_trend(0, ("sleepFitnessScore", "total"))
        return self._get_trend(0, "score")

    @property
    def current_sleep_quality_score(self) -> int | None:
        return self._get_trend(0, ("sleepQualityScore", "total"))

    @property
    def current_sleep_routine_score(self) -> int | None:
        return self._get_trend(0, ("sleepRoutineScore", "total"))

    @property
    def current_sleep_duration_score(self) -> int | None:
        """Return sleep duration score for latest session."""
        return self._get_quality_score(0, "sleepDurationSeconds")

    @property
    def current_latency_asleep_score(self) -> int | None:
        """Return latency asleep score for latest session."""
        return self._get_routine_score(0, "latencyAsleepSeconds")

    @property
    def time_slept(self) -> int | None:
        return self._get_trend(0, ("sleepDuration"))

    @property
    def presence_start(self):
        timestamp = self._get_trend(0, "presenceStart")
        if timestamp:
            return self.device.convert_string_to_datetime(timestamp)

    @property
    def presence_end(self):
        timestamp = self._get_trend(0, "presenceEnd")
        if timestamp:
            return self.device.convert_string_to_datetime(timestamp)

    @property
    def current_latency_out_score(self) -> int | None:
        """Return latency out score for latest session."""
        return self._get_routine_score(0, "latencyOutSeconds")

    @property
    def current_hrv(self) -> float | None:
        """Return wakeup consistency score for latest session."""
        return self._get_trend(0, ("sleepQualityScore", "hrv", "current"))

    @property
    def current_breath_rate(self) -> float | None:
        """Return wakeup consistency score for latest session."""
        return self._get_trend(0, ("sleepQualityScore", "respiratoryRate", "current"))

    @property
    def current_wakeup_consistency_score(self) -> int | None:
        """Return wakeup consistency score for latest session."""
        return self._get_routine_score(0, "wakeupConsistency")

    @property
    def current_fitness_session_date(self) -> str | None:
        """Return date/time for start of last session data."""
        return self._get_trend(0, "day")

    @property
    def current_sleep_breakdown(self) -> dict[str, Any] | None:
        """Return durations of sleep stages for in-progress session."""
        return self._sleep_breakdown(0)

    @property
    def current_bed_temp(self) -> int | float | None:
        """Return current bed temperature for in-progress session."""
        # return self._get_current_interval_property_value("tempBedC")
        return self.current_side_temp

    @property
    def current_room_temp(self) -> int | float | None:
        """Return current room temperature for in-progress session."""
        timeseries = self._trend_timeseries()
        if timeseries and "tempRoomC" in timeseries:
            return timeseries["tempRoomC"][-1][1]
        return None

    @property
    def current_tnt(self) -> int | None:
        """Return current toss & turns for in-progress session."""
        return self._get_trend(0, "tnt")

    @property
    def current_resp_rate(self) -> int | float | None:
        """Return current respiratory rate for in-progress session."""
        return self._get_trend(0, ("sleepQualityScore", "respiratoryRate", "current"))

    @property
    def current_heart_rate(self) -> int | float | None:
        """Return current heart rate for in-progress session."""
        timeseries = self._trend_timeseries()
        if timeseries and "heartRate" in timeseries:
            return timeseries["heartRate"][-1][1]
        return None

    @property
    def current_values(self) -> dict[str, Any]:
        """Return a dict of all the 'current' parameters."""
        return {
            "date": self.current_session_date,
            "score": self.current_sleep_score,
            "stage": self.current_sleep_stage,
            "breakdown": self.current_sleep_breakdown,
            "tnt": self.current_tnt,
            "bed_temp": self.current_bed_temp,
            "room_temp": self.current_room_temp,
            "resp_rate": self.current_resp_rate,
            "heart_rate": self.current_heart_rate,
            "processing": self.current_session_processing,
        }

    @property
    def current_fitness_values(self) -> dict[str, Any]:
        """Return a dict of all the 'current' fitness score parameters."""
        return {
            "date": self.current_fitness_session_date,
            "score": self.current_sleep_fitness_score,
            "duration": self.current_sleep_duration_score,
            "asleep": self.current_latency_asleep_score,
            "out": self.current_latency_out_score,
            "wakeup": self.current_wakeup_consistency_score,
        }

    @property
    def last_session_date(self) -> datetime | None:
        """Return date/time for start of last session data."""
        return self._session_date(1)

    @property
    def last_session_processing(self) -> bool | None:
        """Return processing state of current session."""
        return self._session_processing(1)

    @property
    def last_sleep_score(self) -> int | None:
        """Return sleep score from last complete sleep session."""
        return self._get_sleep_score(1)

    @property
    def last_sleep_fitness_score(self) -> int | None:
        """Return sleep fitness score for previous sleep session."""
        return self._get_trend(1, ("sleepFitnessScore", "total"))

    @property
    def last_sleep_duration_score(self) -> int | None:
        """Return sleep duration score for previous session."""
        return self._get_quality_score(1, "sleepDurationSeconds")

    @property
    def last_latency_asleep_score(self) -> int | None:
        """Return latency asleep score for previous session."""
        return self._get_routine_score(1, "latencyAsleepSeconds")

    @property
    def last_latency_out_score(self) -> int | None:
        """Return latency out score for previous session."""
        return self._get_routine_score(1, "latencyOutSeconds")

    @property
    def last_wakeup_consistency_score(self) -> int | None:
        """Return wakeup consistency score for previous session."""
        return self._get_routine_score(1, "wakeupConsistency")

    @property
    def last_fitness_session_date(self) -> str | None:
        """Return date/time for start of previous session data."""
        return self._get_trend(1, "day")

    @property
    def last_sleep_breakdown(self) -> dict[str, Any] | None:
        """Return durations of sleep stages for last complete session."""
        return self._sleep_breakdown(1)

    @property
    def last_bed_temp(self) -> int | float | None:
        """Return avg bed temperature for last session."""
        return self._get_trend(1, ("sleepQualityScore", "tempBedC", "average"))

    @property
    def last_room_temp(self) -> int | float | None:
        """Return avg room temperature for last session."""
        return self._get_trend(1, ("sleepQualityScore", "tempRoomC", "average"))

    @property
    def last_tnt(self) -> int | None:
        """Return toss & turns for last session."""
        return self._get_trend(1, "tnt")

    @property
    def last_resp_rate(self) -> int | float | None:
        """Return avg respiratory rate for last session."""
        return self._get_trend(1, ("sleepQualityScore", "respiratoryRate", "average"))

    @property
    def last_heart_rate(self) -> int | float | None:
        """Return avg heart rate for last session."""
        return self._get_trend(1, ("sleepQualityScore", "heartRate", "average"))

    @property
    def last_values(self) -> dict[str, Any]:
        """Return a dict of all the 'last' parameters."""
        return {
            "date": self.last_session_date,
            "score": self.last_sleep_score,
            "breakdown": self.last_sleep_breakdown,
            "tnt": self.last_tnt,
            "bed_temp": self.last_bed_temp,
            "room_temp": self.last_room_temp,
            "resp_rate": self.last_resp_rate,
            "heart_rate": self.last_heart_rate,
            "processing": self.last_session_processing,
        }

    @property
    def last_fitness_values(self) -> dict[str, Any]:
        """Return a dict of all the 'last' fitness score parameters."""
        return {
            "date": self.last_fitness_session_date,
            "score": self.last_sleep_fitness_score,
            "duration": self.last_sleep_duration_score,
            "asleep": self.last_latency_asleep_score,
            "out": self.last_latency_out_score,
            "wakeup": self.last_wakeup_consistency_score,
        }

    def trend_sleep_score(self, date: str) -> int | None:
        """Return trend sleep score for specified date."""
        return next(
            (day.get("score") for day in self.trends if day.get("day") == date),
            None,
        )

    def sleep_fitness_score(self, date: str) -> int | None:
        """Return sleep fitness score for specified date."""
        return next(
            (
                day.get("sleepFitnessScore", {}).get("total")
                for day in self.trends
                if day.get("day") == date
            ),
            None,
        )

    async def get_user_side(self) -> str:
        """Returns the side that the current user is set to"""
        url = CLIENT_API_URL + f"/users/{self.user_id}/current-device"
        data = await self.device.api_request("GET", url, return_json=True)
        return data["side"]

    def heating_stats(self) -> None:
        """Calculate some heating data stats."""
        local_5 = []
        local_10 = []

        for i in range(0, 10):
            if (level := self.past_heating_level(i)) is None:
                continue
            if level == 0:
                _LOGGER.debug("Cant calculate stats yet...")
                return
            if i < 5:
                local_5.append(level)
            local_10.append(level)

        _LOGGER.debug("%s Heating History: %s", self.side, local_10)

        try:
            # Average of 5min on the history dict.
            fiveminavg = statistics.mean(local_5)
            tenminavg = statistics.mean(local_10)
            _LOGGER.debug("%s Heating 5 min avg: %s", self.side, fiveminavg)
            _LOGGER.debug("%s Heating 10 min avg: %s", self.side, tenminavg)

            # Standard deviation
            fivestdev = statistics.stdev(local_5)
            tenstdev = statistics.stdev(local_10)
            _LOGGER.debug("%s Heating 5 min stdev: %s", self.side, fivestdev)
            _LOGGER.debug("%s Heating 10 min stdev: %s", self.side, tenstdev)

            # Variance
            fivevar = statistics.variance(local_5)
            tenvar = statistics.variance(local_10)
            _LOGGER.debug("%s Heating 5 min variance: %s", self.side, fivevar)
            _LOGGER.debug("%s Heating 10 min variance: %s", self.side, tenvar)
        except statistics.StatisticsError:
            _LOGGER.debug("Cant calculate stats yet...")

    async def update_user(self) -> None:
        """Update all user data."""
        self.side = await self.get_user_side()

        now = datetime.today()
        start = now - timedelta(days=1)
        end = now + timedelta(days=1)

        await self.update_trend_data(
            start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)
        )
        await self.update_routines_data()

        self.bed_state_type = await self.get_bed_state_type()

        # Update temperature data (current temp, smart schedule, etc.)
        await self._update_temperature_data()

        if self.target_heating_level is None:
            self.target_heating_temp = None
        else:
            self.target_heating_temp = heating_level_to_temp(
                self.target_heating_level, "c"
            )

    async def _update_temperature_data(self) -> None:
        """Fetch and update detailed temperature data including smart schedule."""
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        try:
            resp = await self.device.api_request("GET", url)
            if resp and isinstance(resp, dict):
                # Update current side temp (from sensor)
                level = resp.get("currentDeviceLevel")
                if level is not None:
                    self.current_side_temp = heating_level_to_temp(int(level), "c")
                else:
                    self.current_side_temp = None
                
                # Update smart schedule (Autopilot)
                self.smart_schedule = resp.get("smart")
                _LOGGER.debug(f"User {self.user_id} Smart Schedule: {self.smart_schedule}")

        except Exception as e:
             _LOGGER.warning(f"Error fetching temperature data for {self.user_id}: {e}")


    async def set_bed_side(self, side) -> None:
        side = str(side).lower()
        if side not in ["solo", "left", "right"]:
            raise Exception(f"Invalid side parameter passed in: {side}")
        url = CLIENT_API_URL + f"/users/{self.user_id}/current-device"
        data = {"id": str(self.device.device_id), "side": side}
        _LOGGER.debug(f"User {self.user_id}: Setting bed side to '{side}' with payload {data}")
        await self.device.api_request("PUT", url, data=data, return_json=False)
        _LOGGER.debug(f"User {self.user_id}: Successfully set bed side to '{side}'")

    async def get_bed_state_type(self) -> str:
        """Gets the bed state."""
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        data = await self.device.api_request("GET", url)
        return data["currentState"]["type"]

    async def set_heating_level(self, level: int, duration: int = 0) -> None:
        """Update heating data json."""
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        data_for_duration = {"timeBased": {"level": level, "durationSeconds": duration}}
        data_for_level = {"currentLevel": level}
        # Catch bad low inputs
        level = max(-100, level)
        # Catch bad high inputs
        level = min(100, level)

        await self.turn_on_side()  # Turn on side before setting temperature
        await self.device.api_request(
            "PUT", url, data=data_for_level
        )  # Set heating level before duration
        await self.device.api_request("PUT", url, data=data_for_duration)

    async def set_smart_heating_level(self, level: int, sleep_stage: str) -> None:
        """Will set the temperature level at a smart sleep stage"""
        if sleep_stage not in POSSIBLE_SLEEP_STAGES:
            raise Exception(
                f"Invalid sleep stage {sleep_stage}. Should be one of {POSSIBLE_SLEEP_STAGES}"
            )
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        data = await self.device.api_request("GET", url)
        sleep_stages_levels = data["smart"]
        # Catch bad low inputs
        level = max(-100, level)
        # Catch bad high inputs
        level = min(100, level)
        sleep_stages_levels[sleep_stage] = level
        data = {"smart": sleep_stages_levels}
        await self.device.api_request("PUT", url, data=data)

    async def increment_heating_level(self, offset: int) -> None:
        """Increment heating level with offset"""
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        current_level = await self.get_current_heating_level()
        new_level = current_level + offset
        # Catch bad low inputs
        new_level = max(-100, new_level)
        # Catch bad high inputs
        new_level = min(100, new_level)

        data_for_level = {"currentLevel": new_level}

        await self.device.api_request("PUT", url, data=data_for_level)

    async def get_current_heating_level(self) -> int:
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        resp = await self.device.api_request("GET", url)
        return int(resp["currentLevel"])

    async def get_current_device_level(self) -> int | None: # Return type can be None
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        try:
            resp = await self.device.api_request("GET", url)
            if resp and isinstance(resp, dict):
                level = resp.get("currentDeviceLevel")
                if level is not None:
                    return int(level)
            _LOGGER.debug(f"Could not determine current device level for user {self.user_id} from response: {resp}")
            return None # Return None if data is not as expected
        except ValueError as e: # Handles int() conversion error
            _LOGGER.warning(f"ValueError converting current device level for user {self.user_id}: {e} - Response: {resp}")
            return None
        # RequestError will be raised by api_request if the call itself fails

    async def prime_pod(self):
        url = APP_API_URL + f"v1/devices/{self.device.device_id}/priming/tasks"
        data_for_priming = {
            "notifications": {"users": [self.user_id], "meta": "rePriming"}
        }
        await self.device.api_request("POST", url, data=data_for_priming)

    async def turn_on_side(self):
        """Turns on the side of the user"""
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        data = {"currentState": {"type": "smart"}}
        await self.device.api_request("PUT", url, data=data)

    async def alarm_snooze(self, snooze_minutes: int):
        """Snoozes the user alarm for the specified minutes"""
        if not self.next_alarm_id:
            raise Exception(f"No next alarm ID set for {self.user_id}")
        url = APP_API_URL + f"v1/users/{self.user_id}/routines"
        data = {
            "alarm": {"alarmId": self.next_alarm_id, "snoozeForMinutes": snooze_minutes}
        }
        await self.device.api_request("PUT", url, data=data)

    async def alarm_stop(self):
        """Stops the next user alarm"""
        if not self.next_alarm_id:
            raise Exception(f"No next alarm ID set for {self.user_id}")
        url = APP_API_URL + f"v1/users/{self.user_id}/routines"
        data = {"alarm": {"alarmId": self.next_alarm_id, "stopped": True}}
        await self.device.api_request("PUT", url, data=data)

    async def alarm_dismiss(self):
        """Dismisses the next user alarm"""
        if not self.next_alarm_id:
            raise Exception(f"No next alarm ID set for {self.user_id}")
        url = APP_API_URL + f"v1/users/{self.user_id}/routines"
        data = {"alarm": {"alarmId": self.next_alarm_id, "dismissed": True}}
        await self.device.api_request("PUT", url, data=data)

    async def set_alarm_enabled(self, routine_id: str | None, alarm_id: str | None, enabled: bool) -> None:
        """Enables or disables the alarm.
        If no ID is specified, the next alarm will be used."""
        if routine_id and alarm_id:
            await self._set_alarm_enabled(routine_id, alarm_id, enabled)
            return
        if self.next_alarm_id is None:
            # We don't do anything for now if there is no next alarm
            return
        routine_id = self._get_next_alarm_routine_id()
        routine = self._get_routine(routine_id)
        # If there is already an override, toggle it
        if "override" in routine:
            await self._set_alarm_enabled(routine_id, self.next_alarm_id, enabled)
            return
        # Otherwise create a new override
        for alarm in routine["alarms"]:
            if alarm["alarmId"] == self.next_alarm_id:
                routine["override"] = {
                    "routineEnabled": True,
                    "alarms": [{
                        "enabled": enabled,
                        "disabledIndividually": not enabled,
                        "settings": alarm["settings"],
                        "dismissUntil": alarm.get("dismissUntil"),
                        "snoozeUntil": alarm.get("snoozeUntil"),
                        "time": alarm["timeWithOffset"]["time"],
                    }],
                }
                await self.device.api_request(
                    "PUT",
                    f"{APP_API_URL}v2/users/{self.user_id}/routines/{routine_id}",
                    data=routine
                )
                return

    async def _set_alarm_enabled(self, routine_id: str, alarm_id: str, enabled: bool) -> None:
        """Enables or disables the alarm with the specified ID."""
        url = APP_API_URL + f"v2/users/{self.user_id}/routines/{routine_id}"
        routine = self._get_routine(routine_id)

        if "override" in routine:
            for alarm in routine["override"]["alarms"]:
                if alarm["alarmId"] == alarm_id:
                    alarm["enabled"] = enabled
                    alarm["disabledIndividually"] = not enabled
                    await self.device.api_request("PUT", url, data=routine)
                    return

        for alarm in routine["alarms"]:
            if alarm["alarmId"] == alarm_id:
                alarm["enabled"] = enabled
                alarm["disabledIndividually"] = not enabled
                await self.device.api_request("PUT", url, data=routine)
                return

        raise ValueError(f"Alarm with ID {alarm_id} not found")

    async def turn_off_side(self):
        """Turns off the side of the user"""
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        data = {"currentState": {"type": "off"}}
        await self.device.api_request("PUT", url, data=data)

    async def set_away_mode(self, action: str):
        """Sets the away mode. The action can either be 'start' or 'stop'"""
        url = APP_API_URL + f"v1/users/{self.user_id}/away-mode"
        # Setting time to UTC of 24 hours ago to get API to trigger immediately
        now = str(
            (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
                :-3
            ]
            + "Z"
        )
        if action != "start" and action != "end":
            raise Exception(f"Invalid action: {action}")
        data = {"awayPeriod": {action: now}}
        _LOGGER.debug(f"User {self.user_id}: Setting away mode action '{action}' with payload {data}")
        await self.device.api_request("PUT", url, data=data)
        _LOGGER.debug(f"User {self.user_id}: Successfully set away mode action '{action}'")

    async def update_user_profile(self) -> None:
        """Update user profile data."""
        url = f"{CLIENT_API_URL}/users/{self.user_id}"
        profile_data = await self.device.api_request("get", url)
        if profile_data is None:
            _LOGGER.error("Unable to fetch user profile data for %s", self.user_id)
        else:
            self._user_profile = profile_data["user"]

    async def update_trend_data(self, start_date: str, end_date: str) -> None:
        """Update trends data json for specified time period. V2 of the api used"""
        url = f"{CLIENT_API_URL}/users/{self.user_id}/trends"
        params = {
            "tz": self.device.timezone,
            "from": start_date,
            "to": end_date,
            "include-main": "false",
            "include-all-sessions": "true",
            "model-version": "v2",
        }
        trend_data = await self.device.api_request("get", url, params=params)
        self.trends = trend_data.get("days", [])

    async def update_routines_data(self) -> None:
        url = APP_API_URL + f"v2/users/{self.user_id}/routines"
        resp = await self.device.api_request("GET", url)

        self.routines = resp["settings"]["routines"]

        try:
            nextTimestamp = resp["state"]["nextAlarm"]["nextTimestamp"]
        except KeyError:
            nextTimestamp = None

        if not nextTimestamp:
            self.next_alarm = None
            self.next_alarm_id = None
            # Check if there is an upcoming routine with an alarm (which is currently disabled)
            if "upcomingRoutineId" in resp["state"]:
                upcoming_routine = self._get_routine(resp["state"]["upcomingRoutineId"])
                if upcoming_routine.get("override"):
                    if upcoming_routine["override"].get("alarms"):
                        self.next_alarm_id = upcoming_routine["override"]["alarms"][0]["alarmId"]
                elif upcoming_routine.get("alarms"):
                    self.next_alarm_id = upcoming_routine["alarms"][0]["alarmId"]
        else:
            self.next_alarm = self.device.convert_string_to_datetime(nextTimestamp)
            self.next_alarm_id = resp["state"]["nextAlarm"]["alarmId"]

    async def set_routine_alarm(self, routine_id: str, alarm_id: str, alarm_time: str) -> None:
        """Set an alarm from a routine."""
        await self.update_routines_data()
        # Find the original routine
        original_routine: dict[str, Any] = {}
        for r in self.routines:
            try:
                if r["id"] == routine_id:
                    original_routine = r
            except KeyError:
                pass

        # Update the alarm
        try:
            for a in original_routine["alarms"]:
                if a["alarmId"] == alarm_id:
                    a["enabledSince"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    a["timeWithOffset"]["time"] = alarm_time
        except KeyError:
            pass

        # Push to cloud
        url = APP_API_URL + f"v2/users/{self.user_id}/routines/{routine_id}"
        await self.device.api_request("PUT", url, data=original_routine)

    async def set_routine_bedtime(self, routine_id: str, bedtime: str) -> None:
        """Set an alarm from a routine."""
        await self.update_routines_data()
        # Find the original routine
        original_routine: dict[str, Any] = {}
        for r in self.routines:
            try:
                if r["id"] == routine_id:
                    original_routine = r
            except KeyError:
                pass

        # Update bedtime
        try:
            original_routine["bedtime"]["time"] = bedtime
            original_routine["bedtime"]["dayOffset"] = "MinusOne" if "12:00:00" <= bedtime else "Zero"
        except KeyError:
            pass

        # Push to cloud
        url = APP_API_URL + f"v2/users/{self.user_id}/routines/{routine_id}"
        await self.device.api_request("PUT", url, data=original_routine)

    async def update_base_data(self):
        """Update the data about the bed base."""
        if self.device.has_base:
            try:
                url = f"{APP_API_URL}v1/users/{self.user_id}/base"
                self._base_data = await self.device.api_request("GET", url)
            except RequestError:
                _LOGGER.warning(
                    "Unable to fetch base data for user %s. This is normal if the user is not paired to a base.",
                    self.user_id,
                )

    async def set_base_angle(self, leg_angle: int, torso_angle: int) -> None:
        """Set the angles of the bed base."""
        if self.device.has_base:
            # Update the angles locally
            self.base_data_for_side["leg"]["currentAngle"] = leg_angle
            self.base_data_for_side["torso"]["currentAngle"] = torso_angle

            url = f"{APP_API_URL}v1/users/{self.user_id}/base/angle?ignoreDeviceErrors=false"
            payload = {
                "deviceId": self.device.device_id,
                "deviceOnline": True,
                "legAngle": leg_angle,
                "torsoAngle": torso_angle,
                "enableOfflineMode": False
            }
            await self.device.api_request("POST", url, data=payload, return_json=False)

    async def set_base_preset(self, preset: str) -> None:
        """Set the preset of the bed base."""
        if self.device.has_base:
            # Update the preset locally
            # Note: The preset goes missing from the local data when a custom angle is used
            # and it also goes missing after some time
            self.base_data_for_side.setdefault("preset", {})["name"] = preset

            url = f"{APP_API_URL}v1/users/{self.user_id}/base/angle?ignoreDeviceErrors=false"
            payload = {
                "deviceId": self.device.device_id,
                "deviceOnline": True,
                "preset": preset,
                "enableOfflineMode": False
            }
            await self.device.api_request("POST", url, data=payload, return_json=False)

    async def set_one_off_alarm(
        self,
        time: str,
        enabled: bool = True,
        vibration_enabled: bool = True,
        vibration_power_level: int = 50,
        vibration_pattern: str = "RISE",
        thermal_enabled: bool = True,
        thermal_level: int = 0,
    ) -> None:
        """Set a one-off alarm."""
        url = APP_API_URL + f"v2/users/{self.user_id}/routines?ignoreDeviceErrors=false"
        data = {
            "oneOffAlarms": [
                {
                    "time": time,
                    "enabled": enabled,
                    "settings": {
                        "vibration": {
                            "enabled": vibration_enabled,
                            "powerLevel": vibration_power_level,
                            "pattern": vibration_pattern,
                        },
                        "thermal": {
                            "enabled": thermal_enabled,
                            "level": thermal_level,
                        },
                    },
                }
            ]
        }
        await self.device.api_request("PUT", url, data=data)
