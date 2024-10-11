"""Support for Eight Sleep binary sensors."""
from __future__ import annotations

import logging

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

SNORE_MITIGATION_DESCRIPTION = BinarySensorEntityDescription(
    key="snore_mitigation",
    name="Snore Mitigaton",
    translation_key="snore_mitigation",
    icon="mdi:account-alert",
    device_class=BinarySensorDeviceClass.RUNNING,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the eight sleep binary sensor."""
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api
    heat_coordinator = config_entry_data.heat_coordinator

    entities: list[BinarySensorEntity] = []

    for user in eight.users.values():
        entities.append(EightHeatSensor(entry, heat_coordinator, eight, user.user_id))

        if eight.has_base:
            entities.append(EightBinaryEntity(SNORE_MITIGATION_DESCRIPTION, lambda: user.in_snore_mitigation))

    async_add_entities(entities)


class EightHeatSensor(EightSleepBaseEntity, BinarySensorEntity):
    """Representation of a Eight Sleep heat-based sensor."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user_id: str | None
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry, coordinator, eight, user_id, "bed_presence")
        assert self._user_obj
        _LOGGER.debug(
            f"Presence Sensor, Side: {self._user_obj.side}, User: {user_id}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        assert self._user_obj
        return bool(self._user_obj.bed_presence)


class EightBinaryEntity(BinarySensorEntity):
    def __init__(
        self,
        entity_description: BinarySensorEntityDescription,
        value_getter: callable
    ) -> None:
        self.entity_description = entity_description
        self._value_getter = value_getter

    @property
    def is_on(self) -> bool | None:
        return self._value_getter()
