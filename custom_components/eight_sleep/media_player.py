"""Support for Eight Sleep speaker."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EightSleepBaseEntity, EightSleepConfigEntryData
from .const import DOMAIN
from .pyEight.eight import EightSleep
from .pyEight.exceptions import RequestError

_LOGGER = logging.getLogger(__name__)

# Categories to filter from source list (alarm sounds are confusing as ambient sounds)
FILTERED_CATEGORIES = ["alarms"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eight Sleep media player."""
    config_entry_data: EightSleepConfigEntryData = hass.data[DOMAIN][entry.entry_id]
    eight = config_entry_data.api

    # Only create entity if speaker exists and coordinator was created
    if eight.has_speaker and config_entry_data.speaker_coordinator:
        async_add_entities([
            EightSleepMediaPlayer(
                entry,
                config_entry_data.speaker_coordinator,
                eight,
            )
        ])


class EightSleepMediaPlayer(EightSleepBaseEntity, MediaPlayerEntity):
    """Representation of an Eight Sleep speaker."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )
    _attr_media_content_type = MediaType.MUSIC

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        eight: EightSleep,
    ) -> None:
        """Initialize the media player."""
        # Speaker is part of the base, so use base_entity=True to attach to base device
        super().__init__(
            entry,
            coordinator,
            eight,
            user=eight.speaker_user,
            sensor="speaker",
            base_entity=True,
        )
        self._attr_name = "Speaker"

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        if not self._eight.speaker_user or not self._eight.speaker_user.player_state:
            return MediaPlayerState.UNAVAILABLE

        state = self._eight.speaker_user.player_state.get("state", "").lower()
        if state == "playing":
            return MediaPlayerState.PLAYING
        elif state == "paused":
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        """Return volume level (0.0 to 1.0)."""
        if not self._eight.speaker_user or not self._eight.speaker_user.player_state:
            return None
        volume = self._eight.speaker_user.player_state.get("volume", 0)
        return volume / 100.0

    @property
    def media_title(self) -> str | None:
        """Return current track name."""
        if not self._eight.speaker_user or not self._eight.speaker_user.player_state:
            return None
        track = self._eight.speaker_user.player_state.get("currentTrack", {})
        return track.get("name")

    @property
    def media_content_id(self) -> str | None:
        """Return current track ID."""
        if not self._eight.speaker_user or not self._eight.speaker_user.player_state:
            return None
        track = self._eight.speaker_user.player_state.get("currentTrack", {})
        return track.get("id")

    @property
    def source(self) -> str | None:
        """Return current source (track name)."""
        return self.media_title

    @property
    def source_list(self) -> list[str]:
        """Return list of available sources (track names), excluding alarm sounds."""
        if not self._eight.speaker_user:
            return []
        return [
            track.get("name", track.get("id"))
            for track in self._eight.speaker_user.audio_tracks
            if track.get("categoryId") not in FILTERED_CATEGORIES
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {}
        if self._eight.speaker_user and self._eight.speaker_user.player_state:
            track = self._eight.speaker_user.player_state.get("currentTrack", {})
            attrs["track_id"] = track.get("id")
            attrs["track_position"] = track.get("currentPosition")
            attrs["track_duration"] = track.get("trackDuration")

            hardware = self._eight.speaker_user.player_state.get("hardwareInfo", {})
            if hardware:
                attrs["speaker_sku"] = hardware.get("sku")
                attrs["speaker_hw_version"] = hardware.get("hardwareVersion")
                attrs["speaker_sw_version"] = hardware.get("softwareVersion")

        # Include full track list for reference (including filtered tracks)
        if self._eight.speaker_user:
            attrs["available_tracks"] = [
                {"id": t.get("id"), "name": t.get("name"), "category": t.get("categoryId")}
                for t in self._eight.speaker_user.audio_tracks
            ]
        return attrs

    async def async_media_play(self) -> None:
        """Play media."""
        if not self._eight.speaker_user:
            return
        try:
            await self._eight.speaker_user.set_player_state("Playing")
            await self.coordinator.async_request_refresh()
        except RequestError as e:
            _LOGGER.error(f"Failed to play: {e}")

    async def async_media_pause(self) -> None:
        """Pause media."""
        if not self._eight.speaker_user:
            return
        try:
            await self._eight.speaker_user.set_player_state("Paused")
            await self.coordinator.async_request_refresh()
        except RequestError as e:
            _LOGGER.error(f"Failed to pause: {e}")

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0.0 to 1.0)."""
        if not self._eight.speaker_user:
            return
        try:
            await self._eight.speaker_user.set_player_volume(int(volume * 100))
            await self.coordinator.async_request_refresh()
        except RequestError as e:
            _LOGGER.error(f"Failed to set volume: {e}")

    async def async_select_source(self, source: str) -> None:
        """Select source (track by name)."""
        if not self._eight.speaker_user:
            return

        # Find track ID from name
        for track in self._eight.speaker_user.audio_tracks:
            if track.get("name") == source:
                try:
                    await self._eight.speaker_user.set_player_track(track.get("id"))
                    await self.coordinator.async_request_refresh()
                except RequestError as e:
                    _LOGGER.error(f"Failed to select track: {e}")
                return

        _LOGGER.warning(f"Track not found: {source}")
