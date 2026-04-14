"""Constants for the Mälarenergi PowerHub integration."""

DOMAIN = "malarenergi_powerhub"

CONF_HOST = "host"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 10  # seconds — device updates every ~10s
DEFAULT_PORT = 80

# Known Espressif OUI prefix for device identification
POWERHUB_MAC_PREFIX = "94:54:C5"
