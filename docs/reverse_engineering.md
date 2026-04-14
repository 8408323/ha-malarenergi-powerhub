# Reverse Engineering Notes — Mälarenergi PowerHub

## Device Identification

| Property | Value | Source |
|---|---|---|
| IP (local) | 192.168.1.157 | Direct observation |
| MAC | 94:54:C5:1E:B3:18 | Windows ARP table |
| MAC OUI | Espressif Inc. | maclookup.app |
| Likely SoC | ESP32 or ESP8266 | OUI lookup |
| Ping TTL | 63 | ICMP reply (Linux TCP/IP stack, 1 hop) |
| Manufacturer | Bitvis | malarenergi.se / bitvis.se |

## Open Ports

> Port scan in progress. Update when complete.

No open TCP ports found yet on ports 1-2000. The device may:
- Only communicate outbound (cloud-only device with no local server)
- Use a non-standard high port
- Require Bluetooth for local setup only, then operates cloud-only

## Known Communication

- Device connects to Bitvis cloud infrastructure over HTTPS/TLS (outbound)
- Data is read from the electricity meter HAN port (RJ45, Norwegian standard) via serial DLMS/COSEM M-Bus at 2400 baud, 8N1
- Data is pushed every ~10 seconds

## Electricity Meter (upstream)

- **Model**: Kaifa MA304
- **HAN port**: Norwegian RJ45 standard
- **Protocol**: DLMS/COSEM over M-Bus (IEC 62056-21 / IEC 62056-7-5)
- **Baud rate**: 2400, 8N1
- **Data cadence**: Every 2s (basic), every 10s (extended), every hour (cumulative)
- **Data fields** (typical for Kaifa MA304):
  - Active power import/export (W)
  - Reactive power (VAr)
  - Phase voltages L1/L2/L3 (V)
  - Phase currents L1/L2/L3 (A)
  - Cumulative energy import/export (kWh, kVArh)
  - Meter ID, timestamp

## App Communication (TODO)

- Android app: `se.malarenergi.malar` (Google Play)
- iOS app: App Store ID `6740694912`
- Likely communicates with Bitvis backend API over HTTPS
- TODO: Capture app traffic with mitmproxy/Charles to find API endpoints

## mDNS / Zeroconf (TODO)

No mDNS services found for the device on the local network yet.
Common ESP32-based devices advertise via `_http._tcp.local` or `_arduino._tcp.local`.

## Potential Local API Paths to Try (TODO)

Based on common ESP32 firmware patterns:

```
GET /
GET /status
GET /data
GET /api/v1/data
GET /metrics
GET /energy
GET /config
GET /info
```

## References

- [Bitvis Power Hub product page](https://bitvis.se/power-flow/power-hub/)
- [Mälarenergi PowerHub](https://www.malarenergi.se/el/elavtal/powerhub/)
- [HANporten.se — Mälarenergi uses Kaifa MA304](https://hanporten.se/natbolag/)
- [Reading a Kaifa MA304 via M-Bus](https://piers.rocks/2020/04/01/reading-kaifa-ma304-meter.html)
- [amshan — Python library for DLMS/COSEM AMS/HAN data](https://github.com/toreamun/amshan)
- [amshan Home Assistant integration](https://github.com/toreamun/amshan-homeassistant)
