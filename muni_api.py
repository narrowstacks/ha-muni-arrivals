"""API client for 511.org transit data."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import (
    API_ENDPOINT,
    CABLE_CAR_LINES,
    CONNECTION_POOL_SIZE,
    CONNECTION_POOL_TTL,
    DEFAULT_RATE_LIMIT_REQUESTS,
    DEFAULT_RATE_LIMIT_WINDOW,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_RETRY_DELAY,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DNS_CACHE_TTL,
    HEALTH_CHECK_FAILURE_THRESHOLD,
    HEALTH_CHECK_SUCCESS_RATE_THRESHOLD,
    HEALTH_CHECK_WINDOW_SIZE,
    LINE_ICONS,
    METRO_LINES,
    NON_RETRYABLE_HTTP_CODES,
    RETRYABLE_HTTP_CODES,
    RETRY_EXPONENTIAL_BASE,
    RETRY_JITTER,
    RETRY_MAX_DELAY,
    TIME_FORMAT_FULL,
    TIME_FORMAT_MINUTES,
    TIME_FORMAT_VERBOSE,
    TROLLEYBUS_ROUTES,
)
from .exceptions import (
    MuniAPIError,
    MuniAuthenticationError,
    MuniConnectionError,
    MuniDataFormatError,
    MuniInvalidStopError,
    MuniRateLimitError,
    MuniServiceUnavailableError,
    MuniTimeoutError,
    classify_connection_error,
    classify_http_error,
)
from .utils import ConnectionHealthMonitor, RateLimiter, retry_on_failure, sanitize_stop_code

_LOGGER = logging.getLogger(__name__)


class MuniAPI:
    """API client for 511.org transit data with enhanced error handling and retry logic."""

    def __init__(
        self,
        api_key: str,
        agency: str = "SF",
        session: aiohttp.ClientSession | None = None,
        max_retries: int = DEFAULT_RETRY_MAX_ATTEMPTS,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
        rate_limit_requests: int = DEFAULT_RATE_LIMIT_REQUESTS,
        rate_limit_window: int = DEFAULT_RATE_LIMIT_WINDOW,
    ) -> None:
        """Initialize the API client with enhanced error handling."""
        self.api_key = api_key
        self.agency = agency
        self._session = session
        self._close_session = False
        
        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.request_timeout = request_timeout
        
        # Health monitoring
        self.health_monitor = ConnectionHealthMonitor(window_size=HEALTH_CHECK_WINDOW_SIZE)
        
        # Rate limiting
        self.rate_limiter = RateLimiter(
            max_requests=rate_limit_requests,
            time_window=rate_limit_window,
        )
        
        # Connection configuration
        self._connector_kwargs = {
            "limit": CONNECTION_POOL_SIZE,
            "ttl_dns_cache": DNS_CACHE_TTL,
            "use_dns_cache": True,
            "keepalive_timeout": CONNECTION_POOL_TTL,
            "enable_cleanup_closed": True,
        }

    @retry_on_failure(
        max_retries=DEFAULT_RETRY_MAX_ATTEMPTS,
        base_delay=DEFAULT_RETRY_DELAY,
        max_delay=RETRY_MAX_DELAY,
        exponential_base=RETRY_EXPONENTIAL_BASE,
        jitter=RETRY_JITTER,
    )
    async def get_arrivals(self, stop_code: str) -> list[dict[str, Any]]:
        """Get arrival information for a stop with retry logic and error handling."""
        try:
            # Sanitize stop code
            sanitized_stop_code = sanitize_stop_code(stop_code)
            
            # Apply rate limiting
            await self.rate_limiter.wait_if_needed()
            
            # Build URL
            url = f"{API_ENDPOINT}?api_key={self.api_key}&agency={self.agency}&stopcode={sanitized_stop_code}&format=json"
            
            session = await self._get_session()
            
            # Make request with timeout
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            
            async with session.get(url, timeout=timeout) as response:
                # Handle HTTP errors
                if response.status in NON_RETRYABLE_HTTP_CODES:
                    error_class = classify_http_error(response.status)
                    error_msg = f"API request failed with status {response.status}"
                    _LOGGER.error("%s for stop %s", error_msg, sanitized_stop_code)
                    self.health_monitor.record_failure()
                    raise error_class(error_msg)
                
                elif response.status in RETRYABLE_HTTP_CODES:
                    error_class = classify_http_error(response.status)
                    error_msg = f"API request failed with retryable status {response.status}"
                    _LOGGER.warning("%s for stop %s", error_msg, sanitized_stop_code)
                    self.health_monitor.record_failure()
                    raise error_class(error_msg)
                
                elif response.status != 200:
                    error_msg = f"API request failed with unexpected status {response.status}"
                    _LOGGER.error("%s for stop %s", error_msg, sanitized_stop_code)
                    self.health_monitor.record_failure()
                    raise MuniAPIError(error_msg)
                
                # Read and process response
                try:
                    text = await response.text()
                    # Handle BOM character
                    clean_text = text.encode().decode('utf-8-sig')
                    data = json.loads(clean_text)
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON response: {e}"
                    _LOGGER.error("%s for stop %s", error_msg, sanitized_stop_code)
                    self.health_monitor.record_failure()
                    raise MuniDataFormatError(error_msg) from e
                
                # Format arrivals
                formatted_arrivals = self._format_arrivals(data)
                
                # Record success
                self.health_monitor.record_success()
                
                _LOGGER.debug(
                    "Successfully fetched %d arrivals for stop %s",
                    len(formatted_arrivals), sanitized_stop_code
                )
                
                return formatted_arrivals
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Handle connection errors
            error_class = classify_connection_error(e)
            error_msg = f"Connection error: {e}"
            _LOGGER.error("%s for stop %s", error_msg, stop_code)
            self.health_monitor.record_failure()
            raise error_class(error_msg) from e
        
        except MuniAPIError:
            # Re-raise our custom exceptions
            raise
        
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Unexpected error: {e}"
            _LOGGER.error("%s for stop %s", error_msg, stop_code)
            self.health_monitor.record_failure()
            raise MuniAPIError(error_msg) from e

    def _format_arrivals(self, data: dict) -> list[dict[str, Any]]:
        """Format arrival data from API response with enhanced error handling."""
        try:
            arrivals = {}
            
            # Validate response structure
            if not isinstance(data, dict):
                raise MuniDataFormatError("Response is not a valid JSON object")
            
            service_delivery = data.get("ServiceDelivery")
            if not service_delivery:
                _LOGGER.debug("No ServiceDelivery in response")
                return []
            
            stop_monitoring = service_delivery.get("StopMonitoringDelivery")
            if not stop_monitoring:
                _LOGGER.debug("No StopMonitoringDelivery in response")
                return []
            
            visits = stop_monitoring.get("MonitoredStopVisit")
            if not visits:
                _LOGGER.debug("No MonitoredStopVisit in response")
                return []
            
            # Handle both single visit (dict) and multiple visits (list)
            if isinstance(visits, dict):
                visits = [visits]
            elif not isinstance(visits, list):
                raise MuniDataFormatError("MonitoredStopVisit is not a list or dict")
            
            for visit in visits:
                try:
                    journey = visit.get("MonitoredVehicleJourney", {})
                    if not journey or not journey.get("MonitoredCall"):
                        continue
                    
                    line_ref = journey.get("LineRef", "").upper()
                    destination = journey.get("DestinationName", "")
                    arrival_time = journey.get("MonitoredCall", {}).get("ExpectedArrivalTime")
                    
                    if not arrival_time or not line_ref:
                        continue
                    
                    # Calculate arrival time info
                    minutes_until = self._calculate_minutes_until_arrival(arrival_time)
                    
                    # Get line icon
                    line_icon = self._get_line_icon(line_ref)
                    
                    # Format line name with icon
                    line_with_icon = f"{line_icon} {line_ref}" if line_icon else line_ref
                    
                    # Group arrivals by line
                    if line_with_icon not in arrivals:
                        arrivals[line_with_icon] = {
                            "line": line_with_icon,
                            "line_ref": line_ref,
                            "destinations": set(),
                            "times": []
                        }
                    
                    arrivals[line_with_icon]["times"].append({
                        "minutes": minutes_until,
                        "arrival_time": arrival_time,
                        "destination": destination,
                        "formatted_time": f"{minutes_until} min" if minutes_until != "?" else "?"
                    })
                    
                    if destination:
                        arrivals[line_with_icon]["destinations"].add(destination)
                
                except Exception as e:
                    _LOGGER.warning("Error processing individual visit: %s", e)
                    continue
            
            # Convert to list and sort
            formatted_arrivals = []
            for line_data in arrivals.values():
                try:
                    # Sort times by minutes
                    line_data["times"].sort(key=lambda x: int(x["minutes"]) if x["minutes"] != "?" else 999)
                    # Convert destinations set to list
                    line_data["destinations"] = list(line_data["destinations"])
                    formatted_arrivals.append(line_data)
                except Exception as e:
                    _LOGGER.warning("Error processing line data: %s", e)
                    continue
            
            # Sort by earliest arrival
            try:
                formatted_arrivals.sort(key=lambda x: int(x["times"][0]["minutes"]) if x["times"] and x["times"][0]["minutes"] != "?" else 999)
            except Exception as e:
                _LOGGER.warning("Error sorting arrivals: %s", e)
            
            _LOGGER.debug("Formatted %d arrival lines", len(formatted_arrivals))
            return formatted_arrivals
            
        except MuniDataFormatError:
            # Re-raise data format errors
            raise
        except Exception as e:
            error_msg = f"Error formatting arrivals: {e}"
            _LOGGER.error(error_msg)
            raise MuniDataFormatError(error_msg) from e

    def _calculate_minutes_until_arrival(self, arrival_time_str: str) -> str:
        """Calculate minutes until arrival."""
        try:
            arrival_time = datetime.fromisoformat(arrival_time_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = arrival_time - now
            minutes = max(0, int(diff.total_seconds() / 60))
            return str(minutes)
        except Exception:
            return "?"

    def _get_line_icon(self, line_ref: str) -> str:
        """Get appropriate icon for line."""
        # Check if it's a number-based route
        if line_ref.isdigit():
            if line_ref in TROLLEYBUS_ROUTES:
                return LINE_ICONS["trolleybus"]
            else:
                return LINE_ICONS["bus"]
        
        # Cable car lines
        elif line_ref in CABLE_CAR_LINES:
            return LINE_ICONS["cable_car"]
        
        # Metro/streetcar lines
        elif line_ref in METRO_LINES:
            return LINE_ICONS["metro"]
        
        # Special services
        elif line_ref == "91" or "OWL" in line_ref:
            return LINE_ICONS["owl"]
        elif "R" in line_ref:
            return LINE_ICONS["express"]
        
        return ""

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling."""
        if self._session is None:
            # Create connector with connection pooling
            connector = aiohttp.TCPConnector(**self._connector_kwargs)
            
            # Create session with connector
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers={
                    'User-Agent': 'HomeAssistant-MuniTimes/1.0',
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate',
                },
                timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                raise_for_status=False,  # We handle status codes manually
            )
            self._close_session = True
            
            _LOGGER.debug("Created new aiohttp session with connection pooling")
        
        return self._session

    async def test_connection(self, test_stop_code: str = "13543") -> bool:
        """Test the API connection with a known stop code."""
        try:
            # Try to fetch data for a test stop
            await self.get_arrivals(test_stop_code)
            return True
        except MuniAuthenticationError:
            # Authentication errors mean the connection works but credentials are bad
            return False
        except Exception as e:
            _LOGGER.error("Connection test failed: %s", e)
            return False

    def get_health_status(self) -> dict[str, Any]:
        """Get current health status of the API client."""
        health_info = self.health_monitor.get_health_info()
        
        return {
            "is_healthy": self.health_monitor.is_healthy,
            "success_rate": health_info["success_rate"],
            "consecutive_failures": health_info["consecutive_failures"],
            "last_success": health_info["last_success"],
            "last_failure": health_info["last_failure"],
            "current_rate_limit": self.rate_limiter.current_rate,
            "time_until_rate_reset": self.rate_limiter.time_until_reset,
        }

    def reset_health_monitoring(self) -> None:
        """Reset health monitoring statistics."""
        self.health_monitor = ConnectionHealthMonitor(window_size=HEALTH_CHECK_WINDOW_SIZE)
        _LOGGER.info("Health monitoring statistics reset")

    async def close(self) -> None:
        """Close the session and clean up resources."""
        if self._session and self._close_session:
            await self._session.close()
            _LOGGER.debug("Closed aiohttp session")
        
        # Reset session reference
        self._session = None
        self._close_session = False