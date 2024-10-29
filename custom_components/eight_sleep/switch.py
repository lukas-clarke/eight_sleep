from __future__ import annotations
from typing import Any, Awaitable, Callable

from custom_components.eight_sleep.pyEight.user import EightUser

from .pyEight.eight import EightSleep

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

                attributes = {
                    "time": alarm["timeWithOffset"]["time"],
                    "days": routine["days"],
                    "thermal": alarm["settings"]["thermal"],
                    "vibration": alarm["settings"]["vibration"],
                }

                alarm_id = alarm["alarmId"]

                entities.append(EightSwitchEntity(
                    entry,
                    config_entry_data.user_coordinator,
                    eight,
                    user,
                    description,
                    lambda user=user, alarm_id=alarm_id: user.get_alarm(alarm_id)["enabled"],
                    lambda value, user=user, routine_id=routine["id"], alarm_id=alarm_id:
                        user.set_alarm_enabled(routine_id, alarm_id, value),
                    attributes))

                alarm_index += 1

    async_add_entities(entities)


class EightSwitchEntity(EightSleepBaseEntity, SwitchEntity):
    """Representation of an Eight Sleep switch entity."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser | None,
        entity_description: SwitchEntityDescription,
        value_getter: Callable[[], bool | None],
        switch_callback: Callable[[bool], Awaitable[None]],
        attributes: dict[str, Any]
    ) -> None:
        super().__init__(entry, coordinator, eight, user, entity_description.key)
        self.entity_description = entity_description
        self._value_getter = value_getter
        self._switch_callback = switch_callback
        self._attr_extra_state_attributes = attributes

    @property
    def is_on(self) -> bool | None:
        return self._value_getter()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._switch_callback(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._switch_callback(False)
        await self.coordinator.async_request_refresh()
