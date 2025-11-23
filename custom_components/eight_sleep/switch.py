from __future__ import annotations
from typing import Any

from custom_components.eight_sleep.pyEight.user import EightUser

from .pyEight.eight import EightSleep

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import EightSleepBaseEntity, EightSleepConfigEntryData
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api

    entities: list[SwitchEntity] = []

    for user in eight.users.values():
        # 1. Routine Alarms
        alarm_index = 1
        for routine in user.routines:
            for alarm in routine["alarms"]:
                # Key is unique (side_alarm_1)
                description = SwitchEntityDescription(
                    key=f"alarm_{alarm_index}",
                    # Name is simplified (e.g., "Alarm 1")
                    name=f"Alarm {alarm_index}",
                    icon="mdi:alarm",
                )

                entities.append(EightSwitchEntity(
                    entry,
                    config_entry_data.user_coordinator,
                    eight,
                    user,
                    description,
                    alarm["alarmId"],
                    routine["id"]))

                alarm_index += 1

        # 2. One-Off Alarms
        one_off_alarm_index = 1
        for alarm in user.one_off_alarms:
            # Key is unique (side_one_off_alarm_1)
            description = SwitchEntityDescription(
                key=f"one_off_alarm_{one_off_alarm_index}",
                # Name is simplified (e.g., "One-Off Alarm 1")
                name=f"One-Off Alarm {one_off_alarm_index}",
                icon="mdi:alarm",
            )

            entities.append(EightSwitchEntity(
                entry,
                config_entry_data.user_coordinator,
                eight,
                user,
                description,
                alarm["alarmId"],
                None)) # Pass None for routine_id

            one_off_alarm_index += 1
            
    async_add_entities(entities)

class EightSwitchEntity(EightSleepBaseEntity, SwitchEntity):
    """Representation of an Eight Sleep switch entity."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser,
        entity_description: SwitchEntityDescription,
        alarm_id: str | None = None,
        routine_id: str | None = None,
    ) -> None:
        super().__init__(entry, coordinator, eight, user, entity_description.key)
        self.entity_description = entity_description
        self._alarm_id = alarm_id
        self._routine_id = routine_id
        self._attr_extra_state_attributes = {}
        self._update_attributes()

    @callback
    def _update_attributes(self) -> None:
        """Update the entity attributes."""
        if not self._user_obj or not (alarm_id := self._alarm_id):
            self._attr_is_on = False
            self._attr_extra_state_attributes = {} # Clear attributes on fail
            return

        self._attr_extra_state_attributes = {}
        
        # 1. Check for One-Off Alarms
        if self._routine_id is None:
            for alarm in self._user_obj.one_off_alarms:
                if alarm["alarmId"] == alarm_id:
                    self._attr_is_on = alarm["enabled"] # Status check
                    self._attr_extra_state_attributes["time"] = alarm.get("time")

                    if settings := alarm.get("settings"):
                        self._attr_extra_state_attributes["thermal"] = settings.get("thermal")
                        self._attr_extra_state_attributes["vibration"] = settings.get("vibration")

                    # CRITICAL FIX: Return immediately to prevent hitting the fallback logic
                    return 
        
        # 2. Check for Routine Alarms (Original Logic)
        else:
            for routine in self._user_obj.routines:
                if routine["id"] == self._routine_id:
                    # Logic for routine overrides
                    if "override" in routine:
                        for alarm in routine["override"]["alarms"]:
                            if alarm["alarmId"] == alarm_id:
                                self._attr_is_on = alarm["enabled"]
                                self._attr_extra_state_attributes["time"] = alarm["timeWithOffset"]["time"]
                                self._attr_extra_state_attributes["days"] = routine["days"]
                                self._attr_extra_state_attributes["thermal"] = alarm["settings"]["thermal"]
                                self._attr_extra_state_attributes["vibration"] = alarm["settings"]["vibration"]
                                return

                    # Logic for regular routine alarms
                    for alarm in routine["alarms"]:
                        if alarm["alarmId"] == alarm_id:
                            # Routine alarms are enabled if not disabled individually
                            self._attr_is_on = not alarm["disabledIndividually"]
                            self._attr_extra_state_attributes["time"] = alarm["timeWithOffset"]["time"]
                            self._attr_extra_state_attributes["days"] = routine["days"]
                            self._attr_extra_state_attributes["thermal"] = alarm["settings"]["thermal"]
                            self._attr_extra_state_attributes["vibration"] = alarm["settings"]["vibration"]
                            return

        # If not found in either list, clear the state/attributes
        self._attr_is_on = False
        self._attr_extra_state_attributes = {}

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._user_obj:
            # self._routine_id will be None for one-off alarms
            await self._user_obj.set_alarm_enabled(self._routine_id, self._alarm_id, True)
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._user_obj:
            # self._routine_id will be None for one-off alarms
            await self._user_obj.set_alarm_enabled(self._routine_id, self._alarm_id, False)
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        super()._handle_coordinator_update()
