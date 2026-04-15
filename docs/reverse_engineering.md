# Reverse Engineering Notes — Mälarenergi PowerHub

## Device Identification

| Property | Value | Source |
|---|---|---|
| IP (local) | 192.168.1.x | Direct observation |
| MAC | 94:54:C5:XX:XX:XX | Windows ARP table |
| MAC OUI | Espressif Inc. (Shanghai, CN) | maclookup.app |
| SoC | ESP32 | OUI `94:54:C5` is Espressif |
| Ping TTL received | 63 | ICMP (Linux-based firmware, 1 hop away) |
| Manufacturer | Bitvis AB, Linköping, Sweden | Official manual + bitvis.se |
| Product name | Power Hub (RJ45/HAN variant) | Manual: "Power Hub P1/HAN/RJ12" |

## Physical Specifications (from official Bitvis manual)

| Parameter | Value |
|---|---|
| Product type | HAN port reader |
| WiFi | 2.4 GHz only |
| Supply voltage | 5 VDC |
| Power consumption | Max 250 mA |
| Connection (Mälarenergi) | RJ45 (Norwegian HAN standard) |
| Connection (other variants) | RJ12 (Swedish P1) |
| USB-C | Power only, no data |
| Enclosure rating | IP20 |
| Weight | 29 g / 34 g (RJ45 variant) |
| Dimensions | 80 × 35 × 24 mm |

## Network Analysis

Full TCP port scan (ports 1–65535) run from Windows via PowerShell parallel runspaces.
**Result: NO open TCP ports found on the device.**

**Conclusion: The PowerHub is a cloud-only device.** It has no local HTTP server or API.
It communicates exclusively **outbound** to the Bitvis cloud over HTTPS/TLS.
Local setup is done via **Bluetooth** (BLE), after which the device operates fully cloud-connected.

No mDNS/Zeroconf services announced. Confirmed cloud-only.

## Device Protocol

- **Meter protocol**: P1 Companion Standard v5.0.2 (IEC 62056-21) — confirmed in official manual
- **HAN port (Mälarenergi)**: RJ45, Norwegian standard (Kaifa MA304 meter)
- **Data cadence**: Every ~10 seconds
- **Cloud transport**: HTTPS/TLS outbound to Bitvis infrastructure

## Electricity Meter (upstream)

- **Model**: Kaifa MA304
- **HAN port**: Norwegian RJ45 standard
- **Protocol**: P1 / DLMS/COSEM over M-Bus (IEC 62056-21)
- **Data fields** (typical for Kaifa MA304):
  - Active power import / export (W)
  - Phase voltages L1 / L2 / L3 (V)
  - Phase currents L1 / L2 / L3 (A)
  - Cumulative energy import / export (kWh)
  - Meter ID, timestamp

## Cloud API — Bitvis "Flow" PowerAPI

Discovered by intercepting HTTPS traffic from the Mälarenergi iPhone app using mitmproxy.

**Base URL**: `https://malarenergi.prod.flow.bitv.is/powerapi/v1`

**Authentication**: JWT Bearer token obtained via BankID (see below).
Header: `Authorization: Bearer <token>`

### Endpoints

#### Facilities

```
GET /account/facility
```
Returns a list of facilities (metering points) associated with the account.

Response (array):
```json
[
  {
    "facilityid": "uuid",
    "street": "EXAMPLE STREET",
    "houseNumber": 1,
    "city": "EXAMPLE CITY",
    "postcode": "00000",
    "countrycode": "SE",
    "latitude": 59.0000,
    "longitude": 18.0000,
    "utilityid": "example-utility-id",
    "utilityName": "example-utility",
    "metadata": {
      "netId": "EXAMPLE",
      "region": "SE3",
      "meterId": "example-meter-id"
    },
    "facilityOwnerName": "...",
    "facilityOwnerId": "uuid"
  }
]
```

#### Consumption

```
GET /facility/{facilityId}/facility_consumption_meter?interval=DAY&type=START&timestamp={ms}
```
Returns 15-minute energy consumption buckets (Wh) for the day starting at `timestamp` (Unix ms).

Response:
```json
{
  "facilityid": "uuid",
  "start": 1776204000000,
  "end": 1776290400000,
  "count": 96,
  "data": [
    {"timestamp": 1776204000000, "value": 123.4},
    ...
  ]
}
```

#### Production

```
GET /facility/{facilityId}/facility_production_meter?interval=DAY&type=START&timestamp={ms}
```
Same structure as consumption. Returns 0 or empty `data` if no solar/production.

#### Spot Price

```
GET /facility/{facilityId}/nordpool_spot_price?interval=DAY&type=START&timestamp={ms}
```
Returns Nordpool spot prices (öre/kWh) for the facility's price region (SE1–SE4) in 15-minute buckets.

Response:
```json
{
  "facilityid": "uuid",
  "data": [
    {"timestamp": 1776204000000, "value": 77.88},
    ...
  ]
}
```

## BankID Authentication Flow

The Mälarenergi app uses Swedish BankID for authentication. The flow was fully captured and is implemented in the HA config flow.

### Step 1 — Start session

```
GET /bankid/auth
```
Response:
```json
{
  "transactionId": "00000000-0000-0000-0000-00000000bbb1",
  "autoStartToken": "00000000-0000-0000-0000-00000000bbb2"
}
```

### Step 2 — Poll until complete

```
GET /bankid/check/{transactionId}
```
Poll repeatedly until `status` is `"complete"` or `"failed"`.

Pending response (show `qrCode` to user as rotating QR):
```json
{
  "status": "pending",
  "qrCode": "bankid.abc.1.somehash",
  "token": null,
  "hintCode": "outstandingTransaction"
}
```

Complete response:
```json
{
  "status": "complete",
  "qrCode": null,
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "hintCode": null
}
```

The `token` is a JWT Bearer token. Store it and use for all subsequent API calls.
When it expires the API returns HTTP 401 — trigger re-auth.

### Note on mitmproxy capture of BankID

BankID itself (`app.bankid.com`) cannot be intercepted via mitmproxy as it uses certificate pinning. The BankID step must be performed without the proxy active. Only post-auth API calls need to be captured.

## Traffic Capture

See [tools/capture.py](../tools/capture.py) for a mitmproxy addon that captures all Bitvis/Mälarenergi API traffic.

```bash
CAPTURE_PHONE_IP=192.168.1.x mitmdump -s tools/capture.py --listen-port 8080 --ssl-insecure
```

Set your phone's Wi-Fi proxy to your PC's LAN IP on port 8080. Install the mitmproxy CA cert via `http://mitm.it`.

## Integration Strategy

The integration uses **cloud polling** (HA `iot_class: cloud_polling`):
- Polls `/facility/{id}/facility_consumption_meter`, `/facility/{id}/facility_production_meter`, and `/nordpool_spot_price` every 60 seconds
- Sums 15-minute Wh buckets from midnight up to the current time for today's totals
- On HTTP 401, triggers HA's built-in re-auth flow (re-scan BankID QR)

### Alternative: Local HAN port bridge

If cloud independence is desired, bypass the PowerHub entirely with a direct HAN port reader:
- [esphome-p1reader](https://github.com/psvanstrom/esphome-p1reader) — ESPHome firmware for P1/HAN
- [amshan-homeassistant](https://github.com/toreamun/amshan-homeassistant) — Python DLMS/COSEM library

## References

- [Bitvis Power Hub product page](https://bitvis.se/power-flow/power-hub/)
- [Bitvis Flow API documentation](https://docs.bitvis.io/advanced/flow-api/)
- [Mälarenergi PowerHub](https://www.malarenergi.se/el/elavtal/powerhub/)
- [HANporten.se — Mälarenergi uses Kaifa MA304 (Norwegian HAN)](https://hanporten.se/natbolag/)
- [amshan — Python library for DLMS/COSEM AMS/HAN](https://github.com/toreamun/amshan)
- [esphome-p1reader](https://github.com/psvanstrom/esphome-p1reader)
