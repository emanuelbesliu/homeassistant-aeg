"""Constants for the AEG (Electrolux OCP) integration."""

from __future__ import annotations

DOMAIN = "aeg"

# OCP API Base URLs
API_BASE_URL = "https://api.ocp.electrolux.one"
WS_BASE_URL = "wss://ws.ocp.electrolux.one"

# API Keys (per brand)
API_KEY_AEG = "PEdfAP7N7sUc95GJPePDU54e2Pybbt6DZtdww7dz"
API_KEY_ELECTROLUX = "2AMqwEV5MqVhTKrRCyYfVF8gmKrd2rAmp7cUsfky"

# OAuth Client Credentials (per brand)
CLIENT_ID_AEG = "AEGOneApp"
CLIENT_SECRET_AEG = (
    "G6PZWyneWAZH6kZePRjZAdBbyyIu3qUgDGUDkat7obfU9ByQSgJPNy8xRo99vzcg"
    "WExX9N48gMJo3GWaHbMJsohIYOQ54zH2Hid332UnRZdvWOCWvWNnMNLalHoyH7xU"
)
CLIENT_ID_ELECTROLUX = "ElxOneApp"
CLIENT_SECRET_ELECTROLUX = (
    "8UKrsKD7jH9zvTV7rz5HeCLkit67Mmj68FvRVTlYygwJYy4dW6KF2cVLPKeWzUQUd6"
    "KJMtTifFf4NkDnjI7ZLdfnwcPtTSNtYvbP7OzEkmQD9IjhMOf5e1zeAQYtt2yN"
)

# Supported brands
BRAND_AEG = "AEG"
BRAND_ELECTROLUX = "Electrolux"

BRANDS = {
    BRAND_AEG: {
        "api_key": API_KEY_AEG,
        "client_id": CLIENT_ID_AEG,
        "client_secret": CLIENT_SECRET_AEG,
    },
    BRAND_ELECTROLUX: {
        "api_key": API_KEY_ELECTROLUX,
        "client_id": CLIENT_ID_ELECTROLUX,
        "client_secret": CLIENT_SECRET_ELECTROLUX,
    },
}

# OCP API Endpoints (relative to API_BASE_URL)
ENDPOINT_TOKEN = "/one-account-authorization/api/v1/token"
ENDPOINT_IDENTITY_PROVIDERS = (
    "/one-account-user/api/v1/identity-providers?brand={brand}&countryCode={country}"
)
ENDPOINT_CURRENT_USER = "/one-account-user/api/v1/users/current"
ENDPOINT_APPLIANCES = "/appliance/api/v2/appliances"
ENDPOINT_APPLIANCE = "/appliance/api/v2/appliances/{appliance_id}"
ENDPOINT_APPLIANCE_CAPABILITIES = (
    "/appliance/api/v2/appliances/{appliance_id}/capabilities"
)
ENDPOINT_APPLIANCE_COMMAND = (
    "/appliance/api/v2/appliances/{appliance_id}/command"
)
ENDPOINT_APPLIANCES_INFO = "/appliance/api/v2/appliances/info"

# Token Grant Types
GRANT_CLIENT_CREDENTIALS = "client_credentials"
GRANT_TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
GRANT_REFRESH_TOKEN = "refresh_token"

# Config Entry Keys
CONF_BRAND = "brand"
CONF_COUNTRY_CODE = "country_code"

# WebSocket
WS_HEARTBEAT_INTERVAL = 300  # 5 minutes
WS_RECONNECT_DELAY = 30  # seconds

# Update intervals
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes (fallback if WebSocket disconnects)

# Appliance States
APPLIANCE_STATE_OFF = "OFF"
APPLIANCE_STATE_IDLE = "IDLE"
APPLIANCE_STATE_READY = "READY_TO_START"
APPLIANCE_STATE_RUNNING = "RUNNING"
APPLIANCE_STATE_PAUSED = "PAUSED"
APPLIANCE_STATE_DELAYED = "DELAYED_START"
APPLIANCE_STATE_END = "END_OF_CYCLE"
APPLIANCE_STATE_ALARM = "ALARM"

# Execute Commands
COMMAND_ON = "ON"
COMMAND_OFF = "OFF"
COMMAND_START = "START"
COMMAND_PAUSE = "PAUSE"
COMMAND_RESUME = "RESUME"
COMMAND_STOPRESET = "STOPRESET"

# Appliance Categories
CATEGORY_WASHING_MACHINE = "WM"
CATEGORY_WASHER_DRYER = "WD"
CATEGORY_TUMBLE_DRYER = "TD"
CATEGORY_DISHWASHER = "DW"
CATEGORY_OVEN = "OV"
CATEGORY_HOB = "HB"
CATEGORY_COOKER = "CR"
CATEGORY_AIR_CONDITIONER = "AC"
CATEGORY_DEHUMIDIFIER = "DH"
CATEGORY_AIR_PURIFIER = "HD"

# Human-readable category names
CATEGORY_NAMES = {
    "WM": "Washing Machine",
    "WM_TOP": "Top-Load Washing Machine",
    "WD": "Washer Dryer",
    "TD": "Tumble Dryer",
    "DW": "Dishwasher",
    "OV": "Oven",
    "DOUBLE_OV": "Double Oven",
    "HB": "Hob",
    "CR": "Cooker",
    "AC": "Air Conditioner",
    "AC_SPLIT": "Split Air Conditioner",
    "WRAC": "Window/Room Air Conditioner",
    "DH": "Dehumidifier",
    "HD": "Air Purifier",
}
