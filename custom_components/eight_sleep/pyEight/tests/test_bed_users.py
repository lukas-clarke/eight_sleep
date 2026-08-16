"""A pod must be asked about itself, not about whoever administers it.

`assign_users` also creates users listed in `awaySides`. On a pod someone
else administers that includes the administrator, whose own bed is a
different device. Since the speaker endpoint is scoped to the user rather
than the device, asking them returns *their* speaker, and the administered
pod inherits hardware it does not have.

Captured from a live account: the pod's own user answers
`404 {"errorType": "BaseNotPaired"}` while the administrator answers `200`
for a speaker whose MAC belongs to another bedroom.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.user import EightUser

OWNER = "owner_on_another_pod"
SLEEPER = "sleeper_on_this_pod"


def _device(users, *, left=SLEEPER, right=SLEEPER) -> EightSleep:
    """An EightSleep whose sides belong to `left`/`right`."""
    eight = EightSleep.__new__(EightSleep)
    eight._device_json_list = [{"leftUserId": left, "rightUserId": right}]
    eight.users = {uid: MagicMock(spec=EightUser, user_id=uid) for uid in users}
    for uid, user in eight.users.items():
        user.user_id = uid
    eight._has_speaker = True
    return eight


class TestBedUsers(unittest.TestCase):
    def test_an_away_user_is_not_a_bed_user(self):
        """The administrator arrives through awaySides, not through a side."""
        eight = _device([OWNER, SLEEPER])

        assert [u.user_id for u in eight.bed_users] == [SLEEPER]

    def test_both_sides_are_kept(self):
        eight = _device([OWNER, SLEEPER, "other"], left=SLEEPER, right="other")

        assert {u.user_id for u in eight.bed_users} == {SLEEPER, "other"}

    def test_speaker_user_ignores_the_away_user(self):
        """Ordering decided this before -- the away user could come first."""
        eight = _device([OWNER, SLEEPER])

        assert eight.speaker_user.user_id == SLEEPER

    def test_speaker_user_falls_back_when_no_side_is_assigned(self):
        """Losing the speaker outright would be worse than the old guess."""
        eight = _device([OWNER], left=None, right=None)

        assert eight.speaker_user.user_id == OWNER

    def test_speaker_user_is_none_without_a_speaker(self):
        eight = _device([SLEEPER])
        eight._has_speaker = False

        assert eight.speaker_user is None


class TestSpeakerProbe(unittest.IsolatedAsyncioTestCase):
    async def test_probe_asks_the_pod_s_own_user(self):
        """Asking the administrator is what invented the phantom speaker."""
        eight = _device([OWNER, SLEEPER])
        eight._token = MagicMock(expiration=2**31, bearer_token="t")
        eight._api_session = MagicMock()
        response = MagicMock(status=404)
        eight._api_session.request = AsyncMock(return_value=response)

        assert await eight._probe_speaker_availability() is False

        url = eight._api_session.request.await_args.args[1]
        assert SLEEPER in url
        assert OWNER not in url

    async def test_probe_is_false_when_no_one_occupies_a_side(self):
        """No side means nothing to ask -- do not fall back to a stranger."""
        eight = _device([OWNER], left=None, right=None)
        eight._api_session = MagicMock()
        eight._api_session.request = AsyncMock()

        assert await eight._probe_speaker_availability() is False
        eight._api_session.request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
