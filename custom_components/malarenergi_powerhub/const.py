"""Constants for the PowerHub integration (Mälarenergi, Boo Energi, Norrtälje Energi)."""

DOMAIN = "malarenergi_powerhub"

# Config entry keys
CONF_TOKEN = "token"
CONF_FACILITY_ID = "facility_id"
CONF_PROVIDER = "provider"

# Energy companies that resell the Bitvis PowerHub. Each one has its own Flow
# backend at https://<slug>.prod.flow.bitv.is; the Power backend is shared.
# Entries created before multi-provider support have no provider key and are
# Mälarenergi.
PROVIDERS = {
    "malarenergi": "Mälarenergi",
    "booenergi": "Boo Energi",
    "norrtaljeenergi": "Norrtälje Energi",
}
DEFAULT_PROVIDER = "malarenergi"

# Update interval — API has 15-min buckets, no point polling faster
DEFAULT_SCAN_INTERVAL = 60  # seconds
