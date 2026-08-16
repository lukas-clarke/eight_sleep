"""Tests for the Eight Sleep media player entity."""
import unittest
from unittest.mock import MagicMock, patch

from homeassistant.components.media_player import MediaPlayerState

from custom_components.eight_sleep.media_player import EightSleepMediaPlayer
from custom_components.eight_sleep.pyEight.eight import EightSleep


def _build_player(player_state):
    """Build the entity with a speaker user whose player_state is given."""
    eight = MagicMock(spec=EightSleep)
    eight.device_id = "fake_device_id"
    if player_state is None:
        eight.speaker_user = None
    else:
        speaker_user = MagicMock()
        speaker_user.player_state = player_state
        speaker_user.user_id = "user_1"
        eight.speaker_user = speaker_user

    coordinator = MagicMock()
    coordinator.last_update_success = True
    entry = MagicMock()
    entry.entry_id = "entry_1"

    with patch.object(EightSleepMediaPlayer, "__init__", lambda self, *a, **k: None):
        player = EightSleepMediaPlayer(entry, coordinator, eight)
    player._eight = eight
    player.coordinator = coordinator
    return player


class TestEightSleepMediaPlayerState(unittest.TestCase):
    """The speaker must not raise when the hub has no speaker paired (#144)."""

    def test_media_player_state_has_no_unavailable_member(self):
        """Guards the premise: MediaPlayerState.UNAVAILABLE does not exist."""
        self.assertFalse(hasattr(MediaPlayerState, "UNAVAILABLE"))

    def test_state_without_speaker_user_does_not_raise(self):
        """GET /audio/player answers 404 BaseNotPaired on hubs with no speaker."""
        player = _build_player(None)

        self.assertIsNone(player.state)

    def test_state_without_player_state_does_not_raise(self):
        """A speaker user that has never reported state must not raise either."""
        player = _build_player({})

        self.assertIsNone(player.state)

    def test_entity_reports_unavailable_instead(self):
        """Unavailability belongs on `available`, not on the state enum."""
        self.assertFalse(_build_player(None).available)
        self.assertFalse(_build_player({}).available)

    def test_known_states_still_map(self):
        """The real states must keep working."""
        self.assertEqual(_build_player({"state": "playing"}).state, MediaPlayerState.PLAYING)
        self.assertEqual(_build_player({"state": "paused"}).state, MediaPlayerState.PAUSED)
        self.assertEqual(_build_player({"state": "stopped"}).state, MediaPlayerState.IDLE)
        self.assertTrue(_build_player({"state": "playing"}).available)


if __name__ == '__main__':
    unittest.main()
