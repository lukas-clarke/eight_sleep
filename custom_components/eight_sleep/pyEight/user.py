"""
pyeight.user
~~~~~~~~~~~~~~~~~~~~
Provides user data for Eight Sleep
Copyright (c) 2022-2023 <https://github.com/lukas-clarke/pyEight>
Licensed under the MIT license.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import statistics
from typing import TYPE_CHECKING, Any, Optional, cast
from zoneinfo import ZoneInfo
import pytz

from .constants import *
from .constants import *

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
        self.trends: list[dict[str, Any]] = []
        self.intervals: list[dict[str, Any]] = []
        self.next_alarm = None
        self.bed_state_type = None

        # Variables to do dynamic presence
        self.presence: bool = False
        self.observed_low: int = 0

    def _get_trend(self, trend_num: int, keys: str | tuple[str, ...]) -> Any:
        """Get trend value for specified key."""
        if len(self.trends) < trend_num + 1:
            return None
        data = self.trends[-(trend_num + 1)]
        if isinstance(keys, str):
            return data.get(keys)
        if self.trends:
            for key in keys[:-1]:
                data = data.get(key, {})
        return data.get(keys[-1])

    def _get_fitness_score(self, trend_num: int, key: str) -> Any:
        """Get fitness score for specified key."""
        return self._get_trend(trend_num, ("sleepFitnessScore", key, "score"))

    def _get_sleep_score(self, interval_num: int) -> int | None:
        """Return sleep score for a given interval."""
        if len(self.intervals) < interval_num + 1:
            return None
        return self.intervals[interval_num].get("score")

    def _interval_timeseries(self, interval_num: int) -> dict[str, Any] | None:
        """Return timeseries interval if it exists."""
        if len(self.intervals) < interval_num + 1:
            return None
        return self.intervals[interval_num].get("timeseries", {})

    def _get_current_interval_property_value(self, key: str) -> int | float | None:
        """Get current property from intervals."""
        if (
            not (timeseries_data := self._interval_timeseries(0))
            or timeseries_data.get(key) is None
        ):
            return None
        return timeseries_data[key][-1][1]

    def _calculate_interval_data(
        self, interval_num: int, key: str, average_data: bool = True
    ) -> int | float | None:
        """Calculate interval data."""

        if (timeseries := self._interval_timeseries(interval_num)) is None or (
            data_list := timeseries.get(key)
        ) is None:
            return None
        total = 0
        for entry in data_list:
            total += entry[1]
        if not average_data:
            return total
        return total / len(data_list)

    def _session_date(self, interval_num: int) -> datetime | None:
        """Get session date for given interval."""
        if (
            len(self.intervals) < interval_num + 1
            or (session_date := self.intervals[interval_num].get("ts")) is None
        ):
            return None
        date = datetime.strptime(session_date, DATE_TIME_ISO_FORMAT)
        return date.replace(tzinfo=ZoneInfo("UTC"))

    def _sleep_breakdown(self, interval_num: int) -> dict[str, Any] | None:
        """Return durations of sleep stages for given session."""
        if len(self.intervals) < (interval_num + 1) or not (
            stages := self.intervals[interval_num].get("stages")
        ):
            return None
        breakdown = {}
        for stage in stages:
            if stage["stage"] in ("out"):
                continue
            if stage["stage"] not in breakdown:
                breakdown[stage["stage"]] = 0
            breakdown[stage["stage"]] += stage["duration"]

        return breakdown

    def _session_processing(self, interval_num: int) -> bool | None:
        """Return processing state of given session."""
        if len(self.intervals) < interval_num + 1:
            return None
        return self.intervals[interval_num].get("incomplete", False)

    @property
    def user_profile(self) -> dict[str, Any] | None:
        """Return userdata."""
        return self._user_profile

    @property
    def bed_presence(self) -> bool:
        """Return true/false for bed presence."""
        return self.presence

    @property
    def target_heating_level(self) -> int | None:
        """Return target heating/cooling level."""
        return self.device.device_data.get(f"{self.side}TargetHeatingLevel")

    @property
    def heating_level(self) -> int | None:
        """Return heating/cooling level."""
        level = self.device.device_data.get(f"{self.side}HeatingLevel")
        # Update observed low
        if level is not None and level < self.observed_low:
            self.observed_low = level
        return level

    def past_heating_level(self, num) -> int:
        """Return a heating level from the past."""
        if num > 9 or len(self.device.device_data_history) < num + 1:
            return 0

        return self.device.device_data_history[num].get(f"{self.side}HeatingLevel", 0)

    def _now_heating_or_cooling(self, target_heating_level_check: bool) -> bool | None:
        """Return true/false if heating or cooling is currently happening."""
        key = f"{self.side}NowHeating"
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
        return self.device.device_data.get(f"{self.side}HeatingDuration")

    @property
    def last_seen(self) -> str | None:
        """Return mattress last seen time.

        These values seem to be rarely updated correctly in the API.
        Don't expect accurate results from this property.
        """
        if not (last_seen := self.device.device_data.get(f"{self.side}PresenceEnd")):
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
        if (
            not self.intervals
            or not (stages := self.intervals[0].get("stages"))
            or len(stages) < 2
        ):
            return None
        # API now always has an awake state last in the dict
        # so always pull the second to last stage while we are
        # in a processing state
        if self.current_session_processing:
            stage = stages[-2].get("stage")
        else:
            stage = stages[-1].get("stage")

        # UNRELIABLE... Removing for now.
        # Check sleep stage against last_seen time to make
        # sure we don't get stuck in a non-awake state.
        # delta_elap = datetime.fromtimestamp(time.time()) \
        #    - datetime.strptime(self.last_seen, 'DATE_TIME_ISO_FORMAT')
        # _LOGGER.debug('User elap: %s', delta_elap.total_seconds())
        # if stage != 'awake' and delta_elap.total_seconds() > 1800:
        # Bed hasn't seen us for 30min so set awake.
        #    stage = 'awake'

        return stage

    @property
    def current_sleep_score(self) -> int | None:
        """Return sleep score for in-progress session."""
        return self._get_sleep_score(0)

    @property
    def current_sleep_fitness_score(self) -> int | None:
        """Return sleep fitness score for latest session."""
        return self._get_trend(0, ("sleepFitnessScore", "total"))

    @property
    def current_sleep_duration_score(self) -> int | None:
        """Return sleep duration score for latest session."""
        return self._get_fitness_score(0, "sleepDurationSeconds")

    @property
    def current_latency_asleep_score(self) -> int | None:
        """Return latency asleep score for latest session."""
        return self._get_fitness_score(0, "latencyAsleepSeconds")

    @property
    def current_latency_out_score(self) -> int | None:
        """Return latency out score for latest session."""
        return self._get_fitness_score(0, "latencyOutSeconds")

    @property
    def current_wakeup_consistency_score(self) -> int | None:
        """Return wakeup consistency score for latest session."""
        return self._get_fitness_score(0, "wakeupConsistency")

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
        return self._get_current_interval_property_value("tempBedC")

    @property
    def current_room_temp(self) -> int | float | None:
        """Return current room temperature for in-progress session."""
        return self._get_current_interval_property_value("tempRoomC")

    @property
    def current_tnt(self) -> int | None:
        """Return current toss & turns for in-progress session."""
        return cast(
            Optional[int], self._calculate_interval_data(0, "tnt", average_data=False)
        )

    @property
    def current_resp_rate(self) -> int | float | None:
        """Return current respiratory rate for in-progress session."""
        return self._get_current_interval_property_value("respiratoryRate")

    @property
    def current_heart_rate(self) -> int | float | None:
        """Return current heart rate for in-progress session."""
        return self._get_current_interval_property_value("heartRate")

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
        return self._get_fitness_score(1, "sleepDurationSeconds")

    @property
    def last_latency_asleep_score(self) -> int | None:
        """Return latency asleep score for previous session."""
        return self._get_fitness_score(1, "latencyAsleepSeconds")

    @property
    def last_latency_out_score(self) -> int | None:
        """Return latency out score for previous session."""
        return self._get_fitness_score(1, "latencyOutSeconds")

    @property
    def last_wakeup_consistency_score(self) -> int | None:
        """Return wakeup consistency score for previous session."""
        return self._get_fitness_score(1, "wakeupConsistency")

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
        return self._calculate_interval_data(1, "tempBedC")

    @property
    def last_room_temp(self) -> int | float | None:
        """Return avg room temperature for last session."""
        return self._calculate_interval_data(1, "tempRoomC")

    @property
    def last_tnt(self) -> int | None:
        """Return toss & turns for last session."""
        return cast(
            Optional[int], self._calculate_interval_data(1, "tnt", average_data=False)
        )

    @property
    def last_resp_rate(self) -> int | float | None:
        """Return avg respiratory rate for last session."""
        return self._calculate_interval_data(1, "respiratoryRate")

    @property
    def last_heart_rate(self) -> int | float | None:
        """Return avg heart rate for last session."""
        return self._calculate_interval_data(1, "heartRate")

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

        # Other possible options for exploration....
        # Pearson correlation coefficient
        # Spearman rank correlation
        # Kendalls Tau

    def dynamic_presence(self) -> None:
        """
        Determine presence based on bed heating level and end presence
        time reported by the api.

        Idea originated from Alex Lee Yuk Cheung SmartThings Code.
        """

        # self.heating_stats()

        # Method needs to be different for pod since it doesn't rest at 0
        #  - Working idea is to track the low and adjust the scale so that low is 0
        #  - Buffer changes while cooling/heating is active
        if self.target_heating_level is None or self.heating_level is None:
            return
        level_zero = self.observed_low * (-1)
        working_level = self.heating_level + level_zero
        if self.device.is_pod:
            if not self.presence:
                if working_level > 50:
                    if not self.now_cooling and not self.now_heating:
                        self.presence = True
                    elif self.target_heating_level > 0:
                        # Heating
                        if working_level - self.target_heating_level >= 8:
                            self.presence = True
                    elif self.target_heating_level < 0:
                        # Cooling
                        if self.heating_level + self.target_heating_level >= 8:
                            self.presence = True
                elif working_level > 25:
                    # Catch rising edge
                    if (
                        self.past_heating_level(0) - self.past_heating_level(1) >= 2
                        and self.past_heating_level(1) - self.past_heating_level(2) >= 2
                        and self.past_heating_level(2) - self.past_heating_level(3) >= 2
                    ):
                        # Values are increasing so we are likely in bed
                        if not self.now_heating:
                            self.presence = True
                        elif working_level - self.target_heating_level >= 8:
                            self.presence = True

            elif self.presence:
                if working_level <= 15:
                    # Failsafe, very slow
                    self.presence = False
                elif working_level < 35:  # Threshold is expiremental for now
                    if (
                        self.past_heating_level(0) - self.past_heating_level(1) < 0
                        and self.past_heating_level(1) - self.past_heating_level(2) < 0
                        and self.past_heating_level(2) - self.past_heating_level(3) < 0
                    ):
                        # Values are decreasing so we are likely out of bed
                        self.presence = False
        else:
            # Method for 0 resting state
            if not self.presence:
                if self.heating_level > 50:
                    # Can likely make this better
                    if not self.now_heating:
                        self.presence = True
                    elif self.heating_level - self.target_heating_level >= 8:
                        self.presence = True
                elif self.heating_level > 25:
                    # Catch rising edge
                    if (
                        self.past_heating_level(0) - self.past_heating_level(1) >= 2
                        and self.past_heating_level(1) - self.past_heating_level(2) >= 2
                        and self.past_heating_level(2) - self.past_heating_level(3) >= 2
                    ):
                        # Values are increasing so we are likely in bed
                        if not self.now_heating:
                            self.presence = True
                        elif self.heating_level - self.target_heating_level >= 8:
                            self.presence = True

            elif self.presence:
                if self.heating_level <= 15:
                    # Failsafe, very slow
                    self.presence = False
                elif self.heating_level < 50:
                    if (
                        self.past_heating_level(0) - self.past_heating_level(1) < 0
                        and self.past_heating_level(1) - self.past_heating_level(2) < 0
                        and self.past_heating_level(2) - self.past_heating_level(3) < 0
                    ):
                        # Values are decreasing so we are likely out of bed
                        self.presence = False

        # Last seen can lag real-time by up to 35min so this is
        # mostly a backup to using the heat values.
        # seen_delta = datetime.fromtimestamp(time.time()) \
        #     - datetime.strptime(self.last_seen, 'DATE_TIME_ISO_FORMAT')
        # _LOGGER.debug('%s Last seen time delta: %s', self.side,
        #               seen_delta.total_seconds())
        # if self.presence and seen_delta.total_seconds() > 2100:
        #     self.presence = False

        _LOGGER.debug("%s Presence Results: %s", self.side, self.presence)

    async def update_user(self) -> None:
        """Update all user data."""
        await self.update_intervals_data()

        now = datetime.today()
        start = now - timedelta(days=2)
        end = now + timedelta(days=2)

        await self.update_trend_data(
            start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)
        )
        await self.update_routines_data()

        self.bed_state_type = await self.get_bed_state_type()

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

    async def turn_on_side(self):
        """Turns on the side of the user"""
        url = APP_API_URL + f"v1/users/{self.user_id}/temperature"
        data = {"currentState": {"type": "smart"}}
        await self.device.api_request("PUT", url, data=data)

    async def turn_off_side(self):
        """Turns on the side of the user"""
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
        await self.device.api_request("PUT", url, data=data)

    async def update_user_profile(self) -> None:
        """Update user profile data."""
        url = f"{CLIENT_API_URL}/users/{self.user_id}"
        profile_data = await self.device.api_request("get", url)
        if profile_data is None:
            _LOGGER.error("Unable to fetch user profile data for %s", self.user_id)
        else:
            self._user_profile = profile_data["user"]

    async def update_trend_data(self, start_date: str, end_date: str) -> None:
        """Update trends data json for specified time period."""
        url = f"{CLIENT_API_URL}/users/{self.user_id}/trends"
        params = {
            "tz": self.device.timezone,
            "from": start_date,
            "to": end_date,
            # 'include-main': 'true'
        }
        trend_data = await self.device.api_request("get", url, params=params)
        self.trends = trend_data.get("days", [])

    async def update_intervals_data(self) -> None:
        """Update intervals data json for specified time period."""
        url = f"{CLIENT_API_URL}/users/{self.user_id}/intervals"

        intervals = await self.device.api_request("get", url)
        self.intervals = intervals.get("intervals", [])

    async def update_routines_data(self) -> None:
        url = APP_API_URL + f"v2/users/{self.user_id}/routines"
        resp = await self.device.api_request("GET", url)

        try:
            nextTimestamp = resp["state"]["nextAlarm"]["nextTimestamp"]
        except KeyError:
            nextTimestamp = None

        if not nextTimestamp:
            self.next_alarm = None
            return

        date_format = "%Y-%m-%dT%H:%M:%SZ"
        # Convert string to datetime object
        datetime_object = datetime.strptime(nextTimestamp, date_format)
        # Set the timezone to UTC
        utc_timezone = pytz.UTC
        datetime_object_utc = datetime_object.replace(tzinfo=utc_timezone)
        # Set the timezone to a specific timezone
        timezone = pytz.timezone(self.device.timezone)
        self.next_alarm = datetime_object_utc.astimezone(timezone)
