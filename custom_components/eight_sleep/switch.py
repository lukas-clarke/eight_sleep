from __future__ import annotations
from typing import Any, Awaitable, Callable

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
        alarm_index = 1
        for routine in user.routines:
            for alarm in routine["alarms"]:
                description = SwitchEntityDescription(
                    key=f"alarm_{alarm_index}",
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
        
        description = SwitchEntityDescription(
            key=f"next_alarm",
            name=f"Next Alarm",
            icon="mdi:alarm",
        )

        entities.append(EightSwitchEntity(
            entry,
            config_entry_data.user_coordinator,
            eight,
            user,
            description))

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

    def _update_attributes(self) -> None:
        if self._user_obj:
            self._attr_is_on = self._user_obj.get_alarm_enabled(self._alarm_id)

            alarm_id = self._alarm_id or self._user_obj.next_alarm_id
            if alarm_id:
                for routine in self._user_obj.routines:
                    if "override" in routine:
                        for alarm in routine["override"]["alarms"]:
                            if alarm["alarmId"] == alarm_id:
                                self._attr_extra_state_attributes["time"] = alarm["time"]
                                self._attr_extra_state_attributes["days"] = "Tonight"
                                self._attr_extra_state_attributes["thermal"] = alarm["settings"]["thermal"]
                                self._attr_extra_state_attributes["vibration"] = alarm["settings"]["vibration"]
                                return

                    for alarm in routine["alarms"]:
                        if alarm["alarmId"] == alarm_id:
                            self._attr_extra_state_attributes["time"] = alarm["timeWithOffset"]["time"]
                            self._attr_extra_state_attributes["days"] = routine["days"]
                            self._attr_extra_state_attributes["thermal"] = alarm["settings"]["thermal"]
                            self._attr_extra_state_attributes["vibration"] = alarm["settings"]["vibration"]
                            return

        self._attr_extra_state_attributes.pop("time", None)
        self._attr_extra_state_attributes.pop("days", None)
        self._attr_extra_state_attributes.pop("thermal", None)
        self._attr_extra_state_attributes.pop("vibration", None)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._user_obj:
            await self._user_obj.set_alarm_enabled(self._routine_id, self._alarm_id, True)
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._user_obj:
            await self._user_obj.set_alarm_enabled(self._routine_id, self._alarm_id, False)
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        super()._handle_coordinator_update()
