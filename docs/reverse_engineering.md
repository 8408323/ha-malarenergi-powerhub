# Reverse Engineering Notes — Mälarenergi PowerHub

## Device Identification

| Property | Value | Source |
|---|---|---|
| IP (local) | 192.168.1.157 | Direct observation |
| MAC | 94:54:C5:1E:B3:18 | Windows ARP table |
| MAC OUI | Espressif Inc. (Shanghai, CN) | maclookup.app |
| SoC | ESP32 or ESP8266 | OUI `94:54:C5` is Espressif |
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

## Open Ports (TCP scan results)

Scanned ports 1–9999 via WSL2 (confirmed direct LAN TCP access via router test).
**Result: NO open TCP ports found on the device.**

**Conclusion: The PowerHub is a cloud-only device.** It has no local HTTP server.
It only communicates **outbound** to the Bitvis cloud over HTTPS/TLS.
Local setup is done via **Bluetooth** (BLE), then device operates fully cloud-connected.

## Device Protocol / Software

- **Meter protocol read**: P1 Companion Standard v5.0.2 (IEC62056-21) — confirmed in official manual
- **HAN port (Mälarenergi)**: RJ45, Norwegian standard (Kaifa MA304 meter)
- **Data cadence**: Every ~10 seconds
- **Cloud transport**: HTTPS/TLS outbound to Bitvis infrastructure (no local API)

## Bitvis Cloud API (Flow API)

Bitvis runs a backend called **"Flow"** which exposes a WebSocket + HTTP REST API.

**URL pattern**: `https://<flow-instance>/api/<application>/<rpc-endpoint>/<object-id>`

**Authentication**:
- Basic Auth: `Authorization: Basic base64(username:password)`
- Token: `Flow-Auth-Token: <token>`

**HTTP methods**:
- `GET` → LIST / OPEN / DELETE
- `POST` → CREATE / UPDATE

**Request methods supported**: LIST, OPEN, UPDATE, DELETE, CREATE, INDEX, RUN

**Response envelope**:
```json
{
  "status": 200,
  "success": true,
  "data": {...},
  "dataType": "JSON",
  "count": 1
}
```

**Known demo/example instance**: `flow.maintrac.net` (referenced in Bitvis docs)

**Mälarenergi's Flow instance**: Unknown — needs to be discovered by:
1. Capturing HTTPS traffic from the PowerHub device (via router DNS logging or mitmproxy)
2. Capturing HTTPS traffic from the Mälarenergi mobile app
3. Contacting Bitvis support (fiber-support@bitvis.se) for OpenAPI spec

## Electricity Meter (upstream)

- **Model**: Kaifa MA304
- **HAN port (Mälarenergi)**: Norwegian RJ45 standard
- **Protocol**: P1 / DLMS/COSEM over M-Bus (IEC 62056-21)
- **Data cadence**: Every 2s (basic), every 10s (extended), every hour (cumulative)
- **Data fields** (typical for Kaifa MA304):
  - Active power import / export (W)
  - Reactive power (VAr)
  - Phase voltages L1 / L2 / L3 (V)
  - Phase currents L1 / L2 / L3 (A)
  - Cumulative energy import / export (kWh, kVArh)
  - Meter ID, timestamp

## App Traffic Analysis (TODO)

Android app: `se.malarenergi.malar` · iOS App Store ID: `6740694912`

To find cloud API endpoints, capture HTTPS traffic from either:
- **Mobile app** using [mitmproxy](https://mitmproxy.org/) with certificate pinning bypass
- **PowerHub device** via router-level DNS logging (e.g. Pi-hole query log while device is active)

Look for the Bitvis Flow API host used by Mälarenergi — likely something like:
`malarenergi.flow.bitvis.io` or `app.malarenergi.se/api/...`

## Integration Strategy Options

Given the device is cloud-only, the HA integration has two options:

### Option A — Cloud polling (current approach)
Poll the Bitvis Flow API authenticated with the user's credentials.
- ✅ Works without hardware modification
- ⚠️ Depends on Bitvis cloud availability
- ⚠️ Requires reverse-engineering the cloud API or official access
- HA `iot_class`: `cloud_polling`

### Option B — Local HAN port bridge (alternative)
Use a separate ESP32/Pi directly connected to the meter HAN port via RJ45,
running ESPHome or similar firmware (bypasses PowerHub entirely).
- ✅ Fully local, no cloud
- ❌ Requires additional hardware
- Existing projects: [esphome-p1reader](https://github.com/psvanstrom/esphome-p1reader), [amshan-homeassistant](https://github.com/toreamun/amshan-homeassistant)

## mDNS / Zeroconf

No mDNS services announced by the device. Confirmed cloud-only.

## References

- [Bitvis Power Hub product page](https://bitvis.se/power-flow/power-hub/)
- [Bitvis official manual (PDF) — RJ12/P1 variant](https://www.vaasansahko.fi/wp-content/uploads/2025/06/bitvis_powerhub_manual_rj12_en.pdf)
- [Bitvis Flow API documentation](https://docs.bitvis.io/advanced/flow-api/)
- [Mälarenergi PowerHub](https://www.malarenergi.se/el/elavtal/powerhub/)
- [HANporten.se — Mälarenergi uses Kaifa MA304 (Norwegian HAN)](https://hanporten.se/natbolag/)
- [Reading a Kaifa MA304 via M-Bus](https://piers.rocks/2020/04/01/reading-kaifa-ma304-meter.html)
- [amshan — Python library for DLMS/COSEM AMS/HAN](https://github.com/toreamun/amshan)
- [amshan Home Assistant integration](https://github.com/toreamun/amshan-homeassistant)
- [esphome-p1reader](https://github.com/psvanstrom/esphome-p1reader)
