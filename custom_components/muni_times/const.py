"""Constants for Muni Times integration."""

DOMAIN = "muni_times"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_STOPS = "stops"
CONF_AGENCY = "agency"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_MAX_RESULTS = "max_results"
CONF_SHOW_LINE_ICONS = "show_line_icons"
CONF_TIME_FORMAT = "time_format"
CONF_TIME_ZONE = "time_zone"
CONF_CACHE_ENABLED = "cache_enabled"
CONF_CACHE_DURATION = "cache_duration"
CONF_CACHE_MAX_SIZE = "cache_max_size"
CONF_RETRY_MAX_ATTEMPTS = "retry_max_attempts"
CONF_RETRY_DELAY = "retry_delay"
CONF_REQUEST_TIMEOUT = "request_timeout"

# Default values
DEFAULT_AGENCY = "SF"
DEFAULT_UPDATE_INTERVAL = 60
DEFAULT_MAX_RESULTS = 3
DEFAULT_TIME_FORMAT = "minutes"
DEFAULT_TIME_ZONE = "America/Los_Angeles"
DEFAULT_SHOW_LINE_ICONS = True
DEFAULT_CACHE_ENABLED = True
DEFAULT_CACHE_DURATION = 30  # minutes
DEFAULT_CACHE_MAX_SIZE = 10  # MB
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds
DEFAULT_REQUEST_TIMEOUT = 30  # seconds

# API constants
API_ENDPOINT = "https://api.511.org/transit/StopMonitoring"

# Time format options
TIME_FORMAT_MINUTES = "minutes"
TIME_FORMAT_VERBOSE = "verbose"
TIME_FORMAT_FULL = "full"

# Line icons
LINE_ICONS = {
    "trolleybus": "🚎",
    "bus": "🚌",
    "cable_car": "🚟",
    "metro": "🚇",
    "owl": "🦉",
    "express": "🚀"
}

# Trolleybus routes in SF Muni
TROLLEYBUS_ROUTES = ["1", "2", "3", "5", "6", "7", "8", "14", "21", "22", "24", "30", "31", "33", "41", "45", "49"]

# Cable car lines
CABLE_CAR_LINES = ["C", "PM", "PH", "59", "60", "61"]

# Metro/streetcar lines
METRO_LINES = ["J", "K", "L", "M", "N", "T", "S", "E", "F"]

# Retry and error handling constants
RETRY_EXPONENTIAL_BASE = 2.0
RETRY_MAX_DELAY = 60.0  # seconds
RETRY_JITTER = True

# Connection and timeout constants
CONNECTION_POOL_SIZE = 10
CONNECTION_POOL_TTL = 300  # seconds
DNS_CACHE_TTL = 300  # seconds

# Rate limiting constants
DEFAULT_RATE_LIMIT_REQUESTS = 60  # requests per minute
DEFAULT_RATE_LIMIT_WINDOW = 60  # seconds

# Health monitoring constants
HEALTH_CHECK_WINDOW_SIZE = 10  # number of recent operations to track
HEALTH_CHECK_FAILURE_THRESHOLD = 5  # consecutive failures before marking unhealthy
HEALTH_CHECK_SUCCESS_RATE_THRESHOLD = 0.5  # minimum success rate to be considered healthy

# Cache constants
CACHE_FILE_NAME = "transit_data.json"
CACHE_METADATA_FILE_NAME = "cache_metadata.json"
CACHE_CLEANUP_INTERVAL = 300  # seconds
CACHE_VERSION = "1.0"

# Error retry classifications
RETRYABLE_HTTP_CODES = [429, 500, 502, 503, 504]  # HTTP codes that should trigger retries
NON_RETRYABLE_HTTP_CODES = [400, 401, 403, 404]  # HTTP codes that should not trigger retries

# Service constants
SERVICE_REFRESH_DATA = "refresh_data"
SERVICE_CLEAR_CACHE = "clear_cache"
SERVICE_TEST_CONNECTION = "test_connection"
SERVICE_GET_DIAGNOSTICS = "get_diagnostics"
SERVICE_RESET_ERROR_COUNT = "reset_error_count"

# Sensor attributes for error states
ATTR_ERROR_COUNT = "error_count"
ATTR_LAST_ERROR = "last_error"
ATTR_CONNECTION_STATUS = "connection_status"
ATTR_CACHE_STATUS = "cache_status"
ATTR_CACHED_DATA_AGE = "cached_data_age_minutes"
ATTR_API_HEALTH = "api_health"
ATTR_SUCCESS_RATE = "success_rate"