"""Config flow for Eight Sleep integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .pyEight.eight import EightSleep
from .pyEight.exceptions import RequestError
from .pyEight.household import EightHousehold
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_DEVICE_ID = "device_id"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_CLIENT_ID): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Optional(CONF_CLIENT_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eight Sleep."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._validated_user_input: dict[str, Any] | None = None
        self._device_options: dict[str, str] = {}
        self.client: EightSleep | None = None

    def _build_eight_client(self, config: dict[str, Any]) -> EightSleep:
        """Create an EightSleep client from user provided config."""
        client_id = config.get(CONF_CLIENT_ID)
        client_secret = config.get(CONF_CLIENT_SECRET)

        return EightSleep(
            config[CONF_USERNAME],
            config[CONF_PASSWORD],
            self.hass.config.time_zone,
            client_id,
            client_secret,
            client_session=async_get_clientsession(self.hass),
            httpx_client=get_async_client(self.hass),
        )

    async def _fetch_devices(self) -> dict[str, str]:
        """Fetch available devices for the authenticated user.

        Return a mapping of:
            { "<device_id>": "<human-friendly label>" }

        Example:
            {
                "pod_123": "Master Bedroom Pod",
                "pod_456": "Guest Bedroom Pod",
            }
        """
        household = EightHousehold(self.client)
        return await household.get_devices()

    async def _validate_credentials(self, config: dict[str, Any]) -> str | None:
        """Validate input data and return any error string (or None)."""
        self.client = self._build_eight_client(config)

        try:
            await self.client.refresh_token()
        except RequestError as err:
            if "401" in str(err):
                return "Credentials are invalid"
            return str(err)

        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (authenticate)."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

        if (err := await self._validate_credentials(user_input)) is not None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": err},
                description_placeholders={"error": err},
            )

        # Credentials are valid; store them temporarily for the next step.
        self._validated_user_input = user_input

        # Fetch devices to allow user to select which device this config entry represents.
        try:
            self._device_options = await self._fetch_devices()
        except Exception as err:  # noqa: BLE001 (surface as flow error)
            _LOGGER.exception("Error fetching Eight Sleep devices: %s", err)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "Unable to fetch devices"},
                description_placeholders={"error": "Unable to fetch devices"},
            )

        # If there are no devices returned, fail fast with a clear message.
        if not self._device_options:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "No devices found for this account"},
                description_placeholders={"error": "No devices found for this account"},
            )

        # If only one device exists, skip the selection step.
        if len(self._device_options) == 1:
            device_id = next(iter(self._device_options))
            return await self._create_entry_for_device(device_id)

        return await self.async_step_device()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the device selection step."""
        if self._validated_user_input is None:
            # If HA re-enters this step unexpectedly, bounce back to auth.
            return await self.async_step_user()

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            return await self._create_entry_for_device(device_id)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": dev_id, "label": label}
                                for dev_id, label in self._device_options.items()
                            ],
                            mode="dropdown",
                        )
                    )
                }
            ),
        )

    async def _create_entry_for_device(self, device_id: str) -> FlowResult:
        """Create the config entry for the selected device."""
        assert self._validated_user_input is not None

        # Use device_id as the unique_id so the same physical device can't be added twice.
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()

        data = dict(self._validated_user_input)
        data[CONF_DEVICE_ID] = device_id

        title = self._device_options.get(device_id) or data[CONF_USERNAME]

        return self.async_create_entry(title=title, data=data)

    async def async_step_import(self, import_config: dict) -> FlowResult:
        """Handle import.

        NOTE: Import can't prompt for device selection. If you need device binding when using
        YAML import, include `device_id:` in your YAML and we'll treat it as already selected.
        """
        if (err := await self._validate_credentials(import_config)) is not None:
            _LOGGER.error("Unable to import configuration.yaml configuration: %s", err)
            return self.async_abort(reason=err, description_placeholders={"error": err})

        # If device_id is provided in YAML, bind the entry to that device.
        if CONF_DEVICE_ID in import_config and import_config[CONF_DEVICE_ID]:
            await self.async_set_unique_id(import_config[CONF_DEVICE_ID])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=import_config.get(CONF_USERNAME, "Eight Sleep"),
                data=import_config,
            )

        # Otherwise, keep old behavior (one entry per username). This is imperfect for multi-device,
        # but avoids breaking existing YAML-based setups.
        await self.async_set_unique_id(import_config[CONF_USERNAME].lower())
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=import_config[CONF_USERNAME],
            data=import_config,
        )
