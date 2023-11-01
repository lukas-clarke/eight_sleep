"""
pyeight.constants
~~~~~~~~~~~~~~~~~~~~
Constants list
Copyright (c) 2017-2022 John Mihalic <https://github.com/mezz64>
Licensed under the MIT license.
"""

MAJOR_VERSION = 1
MINOR_VERSION = 0
SUB_MINOR_VERSION = 0
__version__ = f"{MAJOR_VERSION}.{MINOR_VERSION}.{SUB_MINOR_VERSION}"

DEFAULT_TIMEOUT = 240
DATE_TIME_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DATE_FORMAT = "%Y-%m-%d"

DEFAULT_HEADERS = {
    "content-type": "application/json",
    "connection": "keep-alive",
    "user-agent": "okhttp/4.9.3",
    "accept-encoding": "gzip",
    "accept": "application/json",
    ":authority": "client-api.8slp.net",
    ":scheme": "https",
}
CLIENT_API_URL = "https://client-api.8slp.net/v1"
APP_API_URL = "https://app-api.8slp.net/"
AUTH_URL = "https://auth-api.8slp.net/v1/tokens"

TOKEN_TIME_BUFFER_SECONDS = 120


DEFAULT_API_HEADERS = {
    "content-type": "application/json",
    "connection": "keep-alive",
    "user-agent": "Android App",
    "accept-encoding": "gzip",
    "accept": "application/json",
    "host": "app-api.8slp.net",
    "authorization": f"Bearer ADD",
}

DEFAULT_AUTH_HEADERS = {
    "content-type": "application/json",
    "user-agent": "Android App",
    "accept-encoding": "gzip",
    "accept": "application/json",
}
DEFAULT_TIMEOUT = 2400


TEMPERATURE_JSON = """{"currentLevel":{level}}"""
CURRENT_STATE_JSON = """
        {
          "currentState": {
            "type": "smart"
          }
        }"""
