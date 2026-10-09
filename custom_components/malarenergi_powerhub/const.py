"""Constants for the PowerHub integration (Bitvis Power Flow energy companies)."""

DOMAIN = "malarenergi_powerhub"

# Config entry keys
CONF_TOKEN = "token"
CONF_FACILITY_ID = "facility_id"
CONF_PROVIDER = "provider"

# Energy companies on Bitvis' Power Flow platform. Each one has its own Flow
# backend at https://<slug>.prod.flow.bitv.is; the Power backend is shared.
# Slugs come from Bitvis' TLS certificates (certificate transparency logs) and
# were checked to serve the BankID login. Entries created before multi-provider
# support have no provider key and are Mälarenergi.
PROVIDERS = {
    "malarenergi": "Mälarenergi",
    "bjarekraft": "Bjäre Kraft",
    "booenergi": "Boo Energi",
    "boraselhandel": "Borås Elhandel",
    "dalaenergi": "Dala Energi",
    "faluenergi": "Falu Energi",
    "kinnekulleenergi": "Kinnekulle Energi",
    "kraftringen": "Kraftringen",
    "kvanumenergi": "Kvänum Energi",
    "landskronaenergi": "Landskrona Energi",
    "norrtaljeenergi": "Norrtälje Energi",
    "nossebroenergi": "Nossebro Energi",
    "skanskaenergi": "Skånska Energi",
    "sodrahallandskraft": "Södra Hallands Kraft",
    "tranasenergi": "Tranås Energi",
    "trelleborgsenergi": "Trelleborgs Energi",
    "vaggerydsenergi": "Vaggeryds Energi",
    "vanerenergi": "Vänerenergi",
    "varbergsortenselkraft": "Varbergsortens Elkraft",
}
DEFAULT_PROVIDER = "malarenergi"

# Update interval — API has 15-min buckets, no point polling faster
DEFAULT_SCAN_INTERVAL = 60  # seconds
