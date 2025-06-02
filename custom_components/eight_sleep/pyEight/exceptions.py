"""Exceptions for eight sleep."""


from homeassistant.exceptions import HomeAssistantError


class BaseEightSleepError(Exception):
    """Base exception for eight sleep."""


class RequestError(HomeAssistantError):
    """Exception for eight sleep request failures."""


class NotAuthenticatedError(BaseEightSleepError):
    """Exception for eight sleep authentication errors.."""
