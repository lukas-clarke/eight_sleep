"""Support for Eight Sleep binary sensors."""
from __future__ import annotations
from typing import Callable

from custom_components.eight_sleep.pyEight.user import EightUser

from .pyEight.eight import EightSleep

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import EightSleepBaseEntity, EightSleepConfigEntryData
from .const import DOMAIN

BED_PRESENCE_DESCRIPTION = BinarySensorEntityDescription(
    key="bed_presence",
    name="Bed Presence",
    device_class=BinarySensorDeviceClass.OCCUPANCY,
)

SNORE_MITIGATION_DESCRIPTION = BinarySensorEntityDescription(
    key="snore_mitigation",
    name="Snore Mitigaton",
    icon="mdi:account-alert",
)

# Device-level (hub) status booleans, sourced from the device doc.
IS_PRIMING_DESCRIPTION = BinarySensorEntityDescription(
    key="is_priming",
    name="Is Priming",
    device_class=BinarySensorDeviceClass.RUNNING,
)

NEED_PRIMING_DESCRIPTION = BinarySensorEntityDescription(
    key="need_priming",
    name="Need Priming",
    device_class=BinarySensorDeviceClass.PROBLEM,
    icon="mdi:water-alert",
)

HAS_WATER_DESCRIPTION = BinarySensorEntityDescription(
    key="has_water",
    name="Has Water",
    icon="mdi:water",
)

FIRMWARE_UPDATING_DESCRIPTION = BinarySensorEntityDescription(
    key="firmware_updating",
    name="Firmware Updating",
    device_class=BinarySensorDeviceClass.UPDATE,
)

ONLINE_DESCRIPTION = BinarySensorEntityDescription(
    key="online",
    name="Online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the eight sleep binary sensor."""
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api

    entities: list[BinarySensorEntity] = []

    for user in eight.users.values():
        entities.append(EightBinaryEntity(
            entry,
            config_entry_data.user_coordinator,
            eight,
            user,
            BED_PRESENCE_DESCRIPTION,
            lambda user=user: user.bed_presence))

    base_user = eight.base_user
    if base_user:
        entities.append(EightBinaryEntity(
            entry,
            config_entry_data.base_coordinator,
            eight,
            None,
            SNORE_MITIGATION_DESCRIPTION,
            lambda: base_user.in_snore_mitigation,
            base_entity=True))

    # Device-level (hub) status bools — driven by the device coordinator so HA
    # sees on/off transitions (priming / water / firmware-updating / online).
    device_coordinator = config_entry_data.device_coordinator
    for description, getter in (
        (IS_PRIMING_DESCRIPTION, lambda: eight.is_priming),
        (NEED_PRIMING_DESCRIPTION, lambda: eight.need_priming),
        (HAS_WATER_DESCRIPTION, lambda: eight.has_water),
        (FIRMWARE_UPDATING_DESCRIPTION, lambda: eight.firmware_updating),
        (ONLINE_DESCRIPTION, lambda: eight.online),
    ):
        entities.append(EightBinaryEntity(
            entry, device_coordinator, eight, None, description, getter))

    async_add_entities(entities)


class EightBinaryEntity(EightSleepBaseEntity, BinarySensorEntity):
    """Representation of an Eight Sleep binary entity."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser | None,
        entity_description: BinarySensorEntityDescription,
        value_getter: Callable[[], bool | None],
        base_entity: bool = False
    ) -> None:
        super().__init__(entry, coordinator, eight, user, entity_description.key, base_entity)
        self.entity_description = entity_description
        self._value_getter = value_getter

    @property
    def is_on(self) -> bool | None:
        return self._value_getter()
