import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eight_sleep.pyEight.constants import APP_API_URL, CLIENT_API_URL
from custom_components.eight_sleep.pyEight.eight import EightSleep
from custom_components.eight_sleep.pyEight.exceptions import RequestError
from custom_components.eight_sleep.pyEight.user import EightUser

LOGGER = "custom_components.eight_sleep.pyEight.eight"
ALARMS_URL = APP_API_URL + "v2/users/user/alarms"


@pytest.fixture
def api():
    response = SimpleNamespace(
        status=403, json=AsyncMock(return_value={"message": "Subscription required"})
    )
    session = MagicMock(request=AsyncMock(return_value=response))
    with patch("custom_components.eight_sleep.pyEight.eight.atexit.register"):
        eight = EightSleep("user", "password", "UTC", client_session=session)
    eight._token = SimpleNamespace(bearer_token="token", expiration=time.time() + 3600)
    return eight, response


@pytest.mark.asyncio
async def test_alarm_subscription_logs_warning_once_then_debug(api, caplog):
    eight, response = api
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for _ in range(3):
            with pytest.raises(RequestError) as raised:
                await eight.api_request("get", ALARMS_URL)
            assert raised.value.status == 403
            assert raised.value.error_details == await response.json()
    assert [record.levelno for record in caplog.records if record.name == LOGGER] == [
        logging.WARNING,
        logging.DEBUG,
        logging.DEBUG,
    ]
    assert eight._api_session.request.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,url,status,details",
    [
        ("GET", ALARMS_URL, 403, {"message": "Access denied"}),
        ("GET", ALARMS_URL, 403, "Subscription required"),
        ("GET", ALARMS_URL, 500, {"message": "Subscription required"}),
        ("POST", ALARMS_URL, 403, {"message": "Subscription required"}),
        (
            "GET",
            APP_API_URL + "v2/users/user/trends",
            403,
            {"message": "Subscription required"},
        ),
        (
            "GET",
            CLIENT_API_URL + "/v2/users/user/alarms",
            403,
            {"message": "Subscription required"},
        ),
    ],
)
async def test_other_failures_remain_errors(api, caplog, method, url, status, details):
    eight, response = api
    response.status = status
    response.json.return_value = details
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        with pytest.raises(RequestError) as raised:
            await eight.api_request(method, url)
    assert raised.value.status == status
    assert raised.value.error_details == details
    assert [record.levelno for record in caplog.records if record.name == LOGGER] == [
        logging.ERROR
    ]


@pytest.mark.asyncio
async def test_each_users_alarm_endpoint_warns_once(api, caplog):
    eight, _ = api
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for url in (ALARMS_URL, APP_API_URL + "v2/users/other/alarms", ALARMS_URL):
            with pytest.raises(RequestError):
                await eight.api_request("GET", url)
    assert [record.levelno for record in caplog.records if record.name == LOGGER] == [
        logging.WARNING,
        logging.WARNING,
        logging.DEBUG,
    ]


@pytest.mark.asyncio
async def test_alarm_poll_still_degrades_gracefully(api, caplog):
    eight, response = api
    user = EightUser(eight, "user", "left")
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await user.update_routines_data()
        await user.update_routines_data()
    assert user.alarms == []
    assert user.next_alarm is None
    assert user.next_alarm_id is None
    assert [record.levelno for record in caplog.records if record.name == LOGGER] == [
        logging.WARNING,
        logging.DEBUG,
    ]
    response.status = 200
    response.json.return_value = {"alarms": []}
    assert await eight.api_request("GET", ALARMS_URL) == {"alarms": []}
