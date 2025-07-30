"""Custom exceptions for Muni Times integration."""
from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class MuniTimesError(HomeAssistantError):
    """Base exception for Muni Times integration."""


class MuniAPIError(MuniTimesError):
    """Exception for API-related errors."""


class MuniConnectionError(MuniAPIError):
    """Exception for connection-related errors."""


class MuniAuthenticationError(MuniAPIError):
    """Exception for authentication errors."""


class MuniRateLimitError(MuniAPIError):
    """Exception for rate limit errors."""


class MuniTimeoutError(MuniAPIError):
    """Exception for timeout errors."""


class MuniInvalidStopError(MuniAPIError):
    """Exception for invalid stop codes."""


class MuniServiceUnavailableError(MuniAPIError):
    """Exception for service unavailable errors."""


class MuniDataFormatError(MuniAPIError):
    """Exception for unexpected data format errors."""


class MuniCacheError(MuniTimesError):
    """Exception for cache-related errors."""


class MuniConfigurationError(MuniTimesError):
    """Exception for configuration-related errors."""


# Error classification helpers
def classify_http_error(status_code: int) -> type[MuniAPIError]:
    """Classify HTTP errors into specific exception types."""
    if status_code == 401:
        return MuniAuthenticationError
    elif status_code == 403:
        return MuniAuthenticationError
    elif status_code == 404:
        return MuniInvalidStopError
    elif status_code == 429:
        return MuniRateLimitError
    elif status_code >= 500:
        return MuniServiceUnavailableError
    elif status_code >= 400:
        return MuniAPIError
    else:
        return MuniConnectionError


def classify_connection_error(error: Exception) -> type[MuniAPIError]:
    """Classify connection errors into specific exception types."""
    error_str = str(error).lower()
    
    if "timeout" in error_str:
        return MuniTimeoutError
    elif "connection" in error_str or "network" in error_str:
        return MuniConnectionError
    elif "ssl" in error_str or "certificate" in error_str:
        return MuniConnectionError
    else:
        return MuniAPIError