"""
pyeight.constants
~~~~~~~~~~~~~~~~~~~~
Constants list
Copyright (c) 2022-2023 <https://github.com/lukas-clarke/pyEight>
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

POSSIBLE_SLEEP_STAGES = ["bedTimeLevel", "initialSleepLevel", "finalSleepLevel"]

RAW_TO_CELSIUS_MAP = {
    -100: 13,
    -97: 14,
    -94: 15,
    -91: 16,
    -83: 17,
    -75: 18,
    -67: 19,
    -58: 20,
    -50: 21,
    -42: 22,
    -33: 23,
    -25: 24,
    -17: 25,
    -8: 26,
    0: 27,
    6: 28,
    11: 29,
    17: 30,
    22: 31,
    28: 32,
    33: 33,
    39: 34,
    44: 35,
    50: 36,
    56: 37,
    61: 38,
    67: 39,
    72: 40,
    78: 41,
    83: 42,
    89: 43,
    100: 44,
}

RAW_TO_FAHRENHEIT_MAP = {
    -100: 55,
    -99: 56,
    -97: 57,
    -95: 58,
    -94: 59,
    -92: 60,
    -90: 61,
    -86: 62,
    -81: 63,
    -77: 64,
    -72: 65,
    -68: 66,
    -63: 67,
    -58: 68,
    -54: 69,
    -49: 70,
    -44: 71,
    -40: 72,
    -35: 73,
    -31: 74,
    -26: 75,
    -21: 76,
    -17: 77,
    -12: 78,
    -7: 79,
    -3: 80,
    1: 81,
    4: 82,
    7: 83,
    10: 84,
    14: 85,
    17: 86,
    20: 87,
    23: 88,
    26: 89,
    29: 90,
    32: 91,
    35: 92,
    38: 93,
    41: 94,
    44: 95,
    48: 96,
    51: 97,
    54: 98,
    57: 99,
    60: 100,
    63: 101,
    66: 102,
    69: 103,
    72: 104,
    75: 105,
    78: 106,
    81: 107,
    85: 108,
    88: 109,
    92: 110,
    100: 111,
}
