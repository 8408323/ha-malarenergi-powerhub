"""Constants for the Mälarenergi PowerHub integration."""

DOMAIN = "malarenergi_powerhub"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FLOW_URL = "flow_url"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 10  # seconds — device updates every ~10s

# The PowerHub device (MAC OUI 94:54:C5 = Espressif) is cloud-only.
# It connects outbound to Bitvis Flow infrastructure over HTTPS.
# No local TCP ports are open on the device itself.
#
# NOTE: The Bitvis Flow API base URL for Mälarenergi is not yet known.
# It must be discovered by capturing traffic from the mobile app.
# See docs/reverse_engineering.md for details.
BITVIS_FLOW_URL_PLACEHOLDER = "https://<malarenergi-flow-instance>/api"
