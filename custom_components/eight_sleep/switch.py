from __future__ import annotations
import logging
from typing import Any

from custom_components.eight_sleep.pyEight.user import EightUser

from .pyEight.eight import EightSleep

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import EightSleepBaseEntity, EightSleepConfigEntryData
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _format_weekdays(repeat: dict) -> str | list[str]:
    """Convert the new repeat.weekDays dict to a display-friendly format."""
    if not repeat.get("enabled", False):
        return "Once"
    weekdays = repeat.get("weekDays", {})
    day_names = [day.capitalize() for day, active in weekdays.items() if active]
    if len(day_names) == 7:
        return "Every day"
    if not day_names:
        return "Once"
    return day_names


def _make_alarm_key(alarm_id: str) -> str:
    """Build a stable entity key from an alarm's UUID."""
    return f"alarm_{alarm_id}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api
    coordinator = config_entry_data.user_coordinator

    # Track entities per user keyed by alarm_id for dynamic add/remove
    tracked: dict[str, dict[str, EightSwitchEntity]] = {}

    all_entities = []

    for user in eight.users.values():
        user_entities: dict[str, EightSwitchEntity] = {}
        for index, alarm in enumerate(user.alarms, start=1):
            entity = _create_alarm_entity(entry, coordinator, eight, user, alarm, index)
            user_entities[alarm["id"]] = entity
        tracked[user.user_id] = user_entities

        # Add pillow switch if user has a pillow
        if user.has_pillow:
            pillow_switch = EightPillowSwitchEntity(entry, coordinator, eight, user)
            all_entities.append(pillow_switch)

    # Add all initial entities
    all_entities.extend([e for user_map in tracked.values() for e in user_map.values()])
    async_add_entities(all_entities)

    # Register a listener to dynamically add/remove entities on coordinator refresh
    @callback
    def _async_sync_alarm_entities() -> None:
        ent_reg = er.async_get(hass)

        for user in eight.users.values():
            user_entities = tracked.setdefault(user.user_id, {})
            current_ids = {alarm["id"] for alarm in user.alarms}
            tracked_ids = set(user_entities.keys())

            # Add entities for new alarms
            new_ids = current_ids - tracked_ids
            if new_ids:
                next_index = len(user_entities) + 1
                new_entities = []
                for alarm in user.alarms:
                    if alarm["id"] in new_ids:
                        entity = _create_alarm_entity(
                            entry, coordinator, eight, user, alarm, next_index
                        )
                        next_index += 1
                        user_entities[alarm["id"]] = entity
                        new_entities.append(entity)
                async_add_entities(new_entities)
                _LOGGER.debug("Added %d new alarm entities for user %s", len(new_entities), user.user_id)

            # Remove entities for deleted alarms
            removed_ids = tracked_ids - current_ids
            for alarm_id in removed_ids:
                entity = user_entities.pop(alarm_id)
                entity_id = ent_reg.async_get_entity_id(
                    "switch", DOMAIN, entity.unique_id
                )
                if entity_id:
                    ent_reg.async_remove(entity_id)
                    _LOGGER.debug("Removed alarm entity %s for user %s", entity_id, user.user_id)

    coordinator.async_add_listener(_async_sync_alarm_entities)


def _create_alarm_entity(
    entry: ConfigEntry,
    coordinator: DataUpdateCoordinator,
    eight: EightSleep,
    user: EightUser,
    alarm: dict[str, Any],
    index: int,
) -> EightSwitchEntity:
    """Create a switch entity for a single alarm."""
    alarm_id = alarm["id"]
    description = SwitchEntityDescription(
        key=_make_alarm_key(alarm_id),
        name=f"Alarm {index}",
        icon="mdi:alarm",
    )
    return EightSwitchEntity(entry, coordinator, eight, user, description, alarm_id)


class EightSwitchEntity(EightSleepBaseEntity, SwitchEntity):
    """Representation of an Eight Sleep switch entity."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser,
        entity_description: SwitchEntityDescription,
        alarm_id: str,
    ) -> None:
        super().__init__(entry, coordinator, eight, user, entity_description.key)
        self.entity_description = entity_description
        self._alarm_id = alarm_id
        # Set clean positional name for entity_id generation at registration
        self._attr_name = entity_description.name
        self._attr_extra_state_attributes = {}
        self._update_attributes()

    def _update_attributes(self) -> None:
        if self._user_obj:
            self._attr_is_on = self._user_obj.get_alarm_enabled(self._alarm_id)

            for alarm in self._user_obj.alarms:
                if alarm["id"] == self._alarm_id:
                    self._attr_extra_state_attributes["time"] = alarm.get("time")
                    self._attr_extra_state_attributes["days"] = _format_weekdays(
                        alarm.get("repeat", {})
                    )
                    self._attr_extra_state_attributes["thermal"] = alarm.get("thermal", {})
                    self._attr_extra_state_attributes["vibration"] = alarm.get("vibration", {})
                    self._attr_extra_state_attributes["snoozing"] = alarm.get("snoozing", False)
                    self._attr_extra_state_attributes["snoozed_until"] = alarm.get("snoozedUntil")
                    return

        self._attr_extra_state_attributes.pop("time", None)
        self._attr_extra_state_attributes.pop("days", None)
        self._attr_extra_state_attributes.pop("thermal", None)
        self._attr_extra_state_attributes.pop("vibration", None)
        self._attr_extra_state_attributes.pop("snoozing", None)
        self._attr_extra_state_attributes.pop("snoozed_until", None)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._user_obj:
            await self._user_obj.set_alarm_enabled(None, self._alarm_id, True)
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._user_obj:
            await self._user_obj.set_alarm_enabled(None, self._alarm_id, False)
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        # Update display name dynamically (entity_id is already locked at registration)
        if self._user_obj:
            for alarm in self._user_obj.alarms:
                if alarm["id"] == self._alarm_id:
                    alarm_time = alarm.get("time", "")
                    if alarm_time:
                        self._attr_name = f"Alarm {alarm_time[:5]}"
                    break
        super()._handle_coordinator_update()


class EightPillowSwitchEntity(EightSleepBaseEntity, SwitchEntity):
    """Representation of an Eight Sleep pillow switch entity."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        eight: EightSleep,
        user: EightUser,
    ) -> None:
        super().__init__(entry, coordinator, eight, user, "pillow_switch")
        self._attr_name = "Pillow"
        self._attr_icon = "mdi:pillow"
        self._attr_extra_state_attributes = {}
        self._update_attributes()

    def _update_attributes(self) -> None:
        if self._user_obj and self._user_obj.has_pillow:
            state = self._user_obj.pillow_state
            self._attr_is_on = state is not None and state != "off"
            self._attr_extra_state_attributes["state"] = state
            self._attr_extra_state_attributes["current_temp"] = self._user_obj.pillow_current_temp
            self._attr_extra_state_attributes["target_temp"] = self._user_obj.pillow_target_temp
            self._attr_extra_state_attributes["current_level"] = self._user_obj.pillow_current_level
        else:
            self._attr_is_on = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._user_obj and self._user_obj.has_pillow:
            await self._user_obj.turn_on_pillow()
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._user_obj and self._user_obj.has_pillow:
            await self._user_obj.turn_off_pillow()
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        super()._handle_coordinator_update()
