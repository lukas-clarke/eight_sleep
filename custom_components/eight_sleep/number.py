from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.eight_sleep import EightSleepConfigEntryData
from custom_components.eight_sleep.const import DOMAIN

FEET_DESCRIPTION = NumberEntityDescription(
    key="feet_angle",
    native_unit_of_measurement="°",
    native_max_value=20,
    native_min_value=0,
    native_step=1,
    translation_key="feet_angle",
    name="Feet Angle",
)

HEAD_DESCRIPTION = NumberEntityDescription(
    key="head_angle",
    native_unit_of_measurement="°",
    native_max_value=45,
    native_min_value=0,
    native_step=1,
    translation_key="head_angle",
    name="Head Angle",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api

    entities: list[NumberEntity] = []

    if eight.has_base:
        for user in eight.users.values():
            def set_leg_angle(value):
                entry.async_create_task(user.set_base_angle(leg_angle=value, torso_angle=user.torso_angle))

            def set_torso_angle(value):
                entry.async_create_task(user.set_base_angle(leg_angle=user.leg_angle, torso_angle=value))

            # Note: The API refers to these as "leg" and "torso" angles, but the app shows them as "feet" and "head"
            # angles. This is the point where we change the terminology to match the app.
            entities.extend([
                EightNumberEntity(FEET_DESCRIPTION, lambda: user.leg_angle, set_leg_angle),
                EightNumberEntity(HEAD_DESCRIPTION, lambda: user.torso_angle, set_torso_angle)])

    async_add_entities(entities)


class EightNumberEntity(NumberEntity):

    def __init__(
        self,
        entity_description: NumberEntityDescription,
        value_getter: callable,
        set_value_callback: callable
    ):
        self.entity_description = entity_description
        self._value_getter = value_getter
        self._set_value_callback = set_value_callback

    @property
    def native_value(self) -> float | None:
        return self._value_getter()

    async def async_set_native_value(self, value: float) -> None:
        self._set_value_callback(value)
        self.schedule_update_ha_state()
