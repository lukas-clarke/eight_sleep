from typing import Callable
from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.eight_sleep import EightSleepBaseEntity, EightSleepConfigEntryData
from custom_components.eight_sleep.const import DOMAIN
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser

FEET_DESCRIPTION = NumberEntityDescription(
    key="feet_angle",
    native_unit_of_measurement="°",
    native_max_value=20,
    native_min_value=0,
    native_step=1,
    name="Feet Angle",
)

HEAD_DESCRIPTION = NumberEntityDescription(
    key="head_angle",
    native_unit_of_measurement="°",
    native_max_value=45,
    native_min_value=0,
    native_step=1,
    name="Head Angle",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api
    coordinator = config_entry_data.base_coordinator

    entities: list[NumberEntity] = []

    if eight.has_base:
        for user in eight.users.values():
            def set_leg_angle(value):
                entry.async_create_task(hass, user.set_base_angle(leg_angle=value, torso_angle=user.torso_angle))

            def set_torso_angle(value):
                entry.async_create_task(hass, user.set_base_angle(leg_angle=user.leg_angle, torso_angle=value))

            # Note: The API refers to these as "leg" and "torso" angles, but the app shows them as "feet" and "head"
            # angles. This is the point where we change the terminology to match the app.
            entities.extend([
                EightNumberEntity(
                    entry,
                    coordinator,
                    eight,
                    user,
                    FEET_DESCRIPTION,
                    lambda: user.leg_angle,
                    set_leg_angle),
                EightNumberEntity(
                    entry,
                    coordinator,
                    eight,
                    user,
                    HEAD_DESCRIPTION,
                    lambda: user.torso_angle,
                    set_torso_angle)])

    async_add_entities(entities)


class EightNumberEntity(EightSleepBaseEntity, NumberEntity):

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser | None,
        entity_description: NumberEntityDescription,
        value_getter: Callable[[], float | None],
        set_value_callback: Callable[[float], None]
    ):
        super().__init__(entry, coordinator, eight, user, entity_description.key)
        self.entity_description = entity_description
        self._value_getter = value_getter
        self._set_value_callback = set_value_callback

    @property
    def native_value(self) -> float | None:
        return self._value_getter()

    async def async_set_native_value(self, value: float) -> None:
        self._set_value_callback(value)
        self.schedule_update_ha_state()
