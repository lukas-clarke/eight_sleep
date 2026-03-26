"""Eight Sleep button entities for alarm actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import EightSleepBaseEntity, EightSleepConfigEntryData
from .const import DOMAIN
from .pyEight.eight import EightSleep
from .pyEight.user import EightUser


BUTTON_DESCRIPTIONS = [
    ButtonEntityDescription(
        key="alarm_dismiss",
        name="Dismiss Alarm",
        icon="mdi:alarm-check",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api

    entities: list[ButtonEntity] = []

    for user in eight.users.values():
        for description in BUTTON_DESCRIPTIONS:
            entities.append(
                EightAlarmButton(
                    entry,
                    config_entry_data.user_coordinator,
                    eight,
                    user,
                    description,
                )
            )

    async_add_entities(entities)


class EightAlarmButton(EightSleepBaseEntity, ButtonEntity):
    """Button to dismiss the currently active alarm."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser,
        entity_description: ButtonEntityDescription,
    ) -> None:
        super().__init__(entry, coordinator, eight, user, entity_description.key)
        self.entity_description = entity_description

    async def async_press(self) -> None:
        if self._user_obj is None:
            return

        await self._user_obj.alarm_dismiss()
        await self.coordinator.async_request_refresh()
