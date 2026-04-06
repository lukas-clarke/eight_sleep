from typing import Callable
from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
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
    icon="mdi:foot-print",
)

HEAD_DESCRIPTION = NumberEntityDescription(
    key="head_angle",
    native_unit_of_measurement="°",
    native_max_value=45,
    native_min_value=0,
    native_step=1,
    name="Head Angle",
    icon="mdi:head",
)

SNOOZE_MINUTES_DESCRIPTION = NumberEntityDescription(
    key="alarm_snooze_minutes",
    native_unit_of_measurement="min",
    native_max_value=30,
    native_min_value=5,
    native_step=1,
    name="Alarm Snooze Minutes",
    icon="mdi:alarm-snooze",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api
    coordinator = config_entry_data.base_coordinator

    entities: list[NumberEntity] = []

    # Add snooze minutes number entity for each user
    for user in eight.users.values():
        entities.append(
            EightNumberEntity(
                entry,
                config_entry_data.user_coordinator,
                eight,
                user,
                SNOOZE_MINUTES_DESCRIPTION,
                lambda u=user: u.snooze_minutes,
                lambda value, u=user: setattr(u, 'snooze_minutes', int(value)),
                base_entity=False,
            )
        )

    user = eight.base_user
    if user:
        def set_leg_angle(value):
            entry.async_create_task(hass, user.set_base_angle(leg_angle=value, torso_angle=user.torso_angle))

        def set_torso_angle(value):
            entry.async_create_task(hass, user.set_base_angle(leg_angle=user.leg_angle, torso_angle=value))

        # Note: The API refers to these as "leg" and "torso" angles, but the app shows them as "feet" and "head" angles.
        # This is the point where we change the terminology to match the app.
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


class EightNumberEntity(EightSleepBaseEntity, NumberEntity, RestoreEntity):

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser | None,
        entity_description: NumberEntityDescription,
        value_getter: Callable[[], float | None],
        set_value_callback: Callable[[float], None],
        base_entity: bool = True,
    ):
        super().__init__(entry, coordinator, eight, user, entity_description.key, base_entity=base_entity)
        self.entity_description = entity_description
        self._value_getter = value_getter
        self._set_value_callback = set_value_callback

    async def async_added_to_hass(self) -> None:
        """Restore previous value on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._set_value_callback(float(last_state.state))
            except (ValueError, TypeError):
                pass

    @property
    def native_value(self) -> float | None:
        return self._value_getter()

    async def async_set_native_value(self, value: float) -> None:
        self._set_value_callback(value)
        self.schedule_update_ha_state()
