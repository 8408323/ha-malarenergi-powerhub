"""Constants for the Mälarenergi PowerHub integration."""

DOMAIN = "malarenergi_powerhub"

# Config entry keys
CONF_TOKEN = "token"
CONF_FACILITY_ID = "facility_id"

# Update interval — API has 15-min buckets, no point polling faster
DEFAULT_SCAN_INTERVAL = 60  # seconds
