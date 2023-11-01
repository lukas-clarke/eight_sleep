"""Exceptions for eight sleep."""


class BaseEightSleepError(Exception):
    """Base exception for eight sleep."""


class RequestError(BaseEightSleepError):
    """Exception for eight sleep request failures."""


class NotAuthenticatedError(BaseEightSleepError):
    """Exception for eight sleep authentication errors.."""
