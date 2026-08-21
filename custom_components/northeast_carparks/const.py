"""Constants for the Northeast Car Parks integration."""

DOMAIN = "northeast_carparks"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CARPARK_ID = "carpark_id"

API_STATIC_URL = "https://www.netraveldata.co.uk/api/v2/carpark/static"
API_DYNAMIC_URL = "https://www.netraveldata.co.uk/api/v2/carpark/dynamic"

SCAN_INTERVAL_SECONDS = 60
STATIC_CACHE_TTL_SECONDS = 24 * 60 * 60

API_RETRY_MAX_ATTEMPTS = 3
API_RETRY_BASE_DELAY_SECONDS = 1

MANUFACTURER = "NECA Tyne & Wear UTMC"

# UTMC blocks requests without a recognizable User-Agent (403 otherwise).
USER_AGENT = "HomeAssistant/NortheastCarParks/1.0.3"

# Car parks with reliable live occupancy (UTMC / netraveldata.co.uk)
LIVE_DATA_CARPARK_IDS: frozenset[str] = frozenset(
    {
        "CP_NC_ELLSPL",
        "CP_NC_MANORS",
        "CP0021",
        "CP0049",
        "CP0050",
        "PR001",
        "PR002",
        "PR003",
        "PR004",
        "PR005",
        "PR007",
        "PR009",
        "PR010",
        "PR012",
        "VMSLCP002",
        "VMSLCP003",
    }
)

STATE_DESCRIPTIONS = (
    "SPACES",
    "ALMOST FULL",
    "FULL",
    "OPEN",
    "CLOSED",
    "UNKNOWN",
    "FAULTY",
)
