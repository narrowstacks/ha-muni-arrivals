"""Utility functions for Muni Times integration."""
from __future__ import annotations

import asyncio
import functools
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Callable, TypeVar

import aiohttp

from .exceptions import (
    MuniAPIError,
    MuniConnectionError,
    MuniRateLimitError,
    MuniTimeoutError,
    classify_connection_error,
    classify_http_error,
)

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retry logic with exponential backoff."""
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Don't retry on authentication errors or invalid stops
                    if isinstance(e, (aiohttp.ClientResponseError,)):
                        error_class = classify_http_error(e.status)
                        if error_class in (MuniAPIError, MuniConnectionError):
                            # These are retryable
                            pass
                        else:
                            # Authentication errors, invalid stops, etc. - don't retry
                            raise error_class(str(e)) from e
                    
                    if attempt == max_retries:
                        # Final attempt failed
                        if isinstance(e, aiohttp.ClientError):
                            if isinstance(e, aiohttp.ClientResponseError):
                                error_class = classify_http_error(e.status)
                                raise error_class(str(e)) from e
                            else:
                                error_class = classify_connection_error(e)
                                raise error_class(str(e)) from e
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    # Add jitter to prevent thundering herd
                    if jitter:
                        delay = delay * (0.5 + random.random() * 0.5)
                    
                    _LOGGER.warning(
                        "Attempt %d/%d failed for %s: %s. Retrying in %.2f seconds",
                        attempt + 1,
                        max_retries + 1,
                        func.__name__,
                        str(e),
                        delay,
                    )
                    
                    await asyncio.sleep(delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator


class ConnectionHealthMonitor:
    """Monitor connection health and track success/failure rates."""
    
    def __init__(self, window_size: int = 10) -> None:
        """Initialize the health monitor."""
        self.window_size = window_size
        self.success_history: list[bool] = []
        self.last_success: datetime | None = None
        self.last_failure: datetime | None = None
        self.consecutive_failures = 0
        
    def record_success(self) -> None:
        """Record a successful operation."""
        self.success_history.append(True)
        if len(self.success_history) > self.window_size:
            self.success_history.pop(0)
        
        self.last_success = datetime.now()
        self.consecutive_failures = 0
        
    def record_failure(self) -> None:
        """Record a failed operation."""
        self.success_history.append(False)
        if len(self.success_history) > self.window_size:
            self.success_history.pop(0)
        
        self.last_failure = datetime.now()
        self.consecutive_failures += 1
        
    @property
    def success_rate(self) -> float:
        """Get the current success rate."""
        if not self.success_history:
            return 0.0
        
        return sum(self.success_history) / len(self.success_history)
    
    @property
    def is_healthy(self) -> bool:
        """Check if the connection is considered healthy."""
        # Consider unhealthy if success rate is below 50% or more than 5 consecutive failures
        return self.success_rate >= 0.5 and self.consecutive_failures < 5
    
    @property
    def time_since_last_success(self) -> timedelta | None:
        """Get time since last successful operation."""
        if self.last_success is None:
            return None
        return datetime.now() - self.last_success
    
    @property
    def time_since_last_failure(self) -> timedelta | None:
        """Get time since last failed operation."""
        if self.last_failure is None:
            return None
        return datetime.now() - self.last_failure
    
    def get_health_info(self) -> dict[str, Any]:
        """Get comprehensive health information."""
        return {
            "success_rate": self.success_rate,
            "is_healthy": self.is_healthy,
            "consecutive_failures": self.consecutive_failures,
            "total_operations": len(self.success_history),
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "time_since_last_success_minutes": (
                self.time_since_last_success.total_seconds() / 60
                if self.time_since_last_success else None
            ),
            "time_since_last_failure_minutes": (
                self.time_since_last_failure.total_seconds() / 60
                if self.time_since_last_failure else None
            ),
        }


class RateLimiter:
    """Simple rate limiter to prevent API abuse."""
    
    def __init__(self, max_requests: int = 60, time_window: int = 60) -> None:
        """Initialize rate limiter."""
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: list[datetime] = []
        
    async def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        now = datetime.now()
        
        # Remove old requests outside the time window
        cutoff = now - timedelta(seconds=self.time_window)
        self.requests = [req_time for req_time in self.requests if req_time > cutoff]
        
        # Check if we need to wait
        if len(self.requests) >= self.max_requests:
            # Calculate how long to wait
            oldest_request = min(self.requests)
            wait_time = (oldest_request + timedelta(seconds=self.time_window) - now).total_seconds()
            
            if wait_time > 0:
                _LOGGER.warning(
                    "Rate limit reached. Waiting %.2f seconds before next request",
                    wait_time
                )
                await asyncio.sleep(wait_time)
                
        # Record this request
        self.requests.append(now)
    
    @property
    def current_rate(self) -> float:
        """Get current request rate (requests per minute)."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=60)  # Last minute
        recent_requests = [req_time for req_time in self.requests if req_time > cutoff]
        return len(recent_requests)
    
    @property
    def time_until_reset(self) -> float:
        """Get time until rate limit resets (in seconds)."""
        if not self.requests:
            return 0.0
            
        now = datetime.now()
        oldest_request = min(self.requests)
        reset_time = oldest_request + timedelta(seconds=self.time_window)
        
        return max(0.0, (reset_time - now).total_seconds())


def format_timedelta(td: timedelta) -> str:
    """Format a timedelta in a human-readable way."""
    total_seconds = int(td.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        if seconds == 0:
            return f"{minutes}m"
        return f"{minutes}m {seconds}s"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes == 0:
            return f"{hours}h"
        return f"{hours}h {minutes}m"


def sanitize_stop_code(stop_code: str) -> str:
    """Sanitize and validate a stop code."""
    if not stop_code:
        raise ValueError("Stop code cannot be empty")
    
    # Remove any non-alphanumeric characters except hyphens and underscores
    sanitized = "".join(c for c in stop_code if c.isalnum() or c in "-_")
    
    if not sanitized:
        raise ValueError(f"Invalid stop code: {stop_code}")
    
    return sanitized