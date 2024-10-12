from typing import Callable
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.eight_sleep import EightSleepBaseEntity, EightSleepConfigEntryData
from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser

PRESETS = ["sleeping", "relaxing", "reading"]

BASE_PRESET_DESCRIPTION = SelectEntityDescription(
    key="base_preset",
    name="Base Preset",
    icon="mdi:train-car-flatbed",
    options=PRESETS,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api
    coordinator = config_entry_data.base_coordinator

    entities: list[SelectEntity] = []

    user = eight.base_user
    if user:
        def set_preset(value):
            entry.async_create_task(hass, user.set_base_preset(value))

        entities.append(EightSelectEntity(
            entry,
            coordinator,
            eight,
            user,
            BASE_PRESET_DESCRIPTION,
            lambda: user.base_preset,
            set_preset))

    async_add_entities(entities)


class EightSelectEntity(EightSleepBaseEntity, SelectEntity):

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser,
        entity_description: SelectEntityDescription,
        value_getter: Callable[[], str | None],
        set_value_callback: Callable[[str], None]
    ) -> None:
        super().__init__(entry, coordinator, eight, user, entity_description.key, base_entity=True)
        self.entity_description = entity_description
        self._attr_options = PRESETS
        self._attr_name = "Bed Preset"
        self._value_getter = value_getter
        self._set_value_callback = set_value_callback

    @property
    def current_option(self) -> str | None:
        return self._value_getter()

    async def async_select_option(self, option: str) -> None:
        self._set_value_callback(option)
        await self.coordinator.async_request_refresh()
