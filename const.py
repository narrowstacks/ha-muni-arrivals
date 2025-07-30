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

# Default values
DEFAULT_AGENCY = "SF"
DEFAULT_UPDATE_INTERVAL = 60
DEFAULT_MAX_RESULTS = 3
DEFAULT_TIME_FORMAT = "minutes"
DEFAULT_TIME_ZONE = "America/Los_Angeles"
DEFAULT_SHOW_LINE_ICONS = True

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