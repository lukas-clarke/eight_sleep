"""Exceptions for eight sleep."""

from typing import Any

from homeassistant.exceptions import HomeAssistantError


class BaseEightSleepError(Exception):
    """Base exception for eight sleep."""


class RequestError(HomeAssistantError):
    """Exception for eight sleep request failures."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        error_details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_details = error_details


class NotAuthenticatedError(BaseEightSleepError):
    """Exception for eight sleep authentication errors.."""
