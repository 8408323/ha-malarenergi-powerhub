# ha-malarenergi-powerhub

Home Assistant custom integration for [Mälarenergi PowerHub](https://www.malarenergi.se/el/elavtal/powerhub/) — a cloud-connected energy monitor manufactured by [Bitvis AB](https://bitvis.se/).

> **Status**: Working prototype — BankID auth + cloud API implemented.

## Hardware

| Property | Value |
|---|---|
| Manufacturer | Bitvis AB (OEM for Mälarenergi) |
| SoC | Espressif ESP32 (OUI `94:54:C5`) |
| Connectivity | Wi-Fi 2.4 GHz |
| HAN port | RJ45 (Norwegian standard, P1/IEC 62056-21) |
| Meter | Kaifa MA304 |
| Cloud backend | Bitvis "Flow" platform — `malarenergi.prod.flow.bitv.is` |

The device has **no local API** — all communication goes through Bitvis's cloud (confirmed by full TCP port scan: 0 open ports). This integration uses the same REST API as the Mälarenergi iPhone/Android app.

## Features

- HA Energy dashboard compatible import/export/spot-price sensors
- Real-time power and per-phase current (1-minute resolution)
- Monthly insights: your average price vs. market, year-to-date consumption and production, baseload estimate
- Device diagnostics: Wi-Fi signal, firmware, uptime, HAN port state
- Writable fuse/power limits and notification preferences
- Push notification mirroring (Mälarenergi → HA sensor)
- Facility sharing services (create / revoke invitations)
- Automatic token re-auth when JWT expires

See the **[user manual](docs/user_manual.md)** for the full entity list and usage.

## Authentication

Login uses **Swedish BankID** (same as the Mälarenergi app). During setup a QR code is displayed in the HA config flow — scan it with the BankID app on your phone.

The integration stores the JWT Bearer token in the HA config entry. When the token expires, HA triggers a re-auth flow automatically.

## Installation

### HACS (recommended — once listed)

1. Add this repo as a custom repository in HACS.
2. Install *Mälarenergi PowerHub*.
3. Restart Home Assistant.

### Manual

1. Copy `custom_components/malarenergi_powerhub/` to your HA `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for *Mälarenergi PowerHub*.
3. Scan the BankID QR code that appears with the BankID app.

See the **[full setup guide](docs/setup.md)** for step-by-step instructions with screenshots.

## Entities

The integration exposes ~40 entities — sensors, binary sensors, switches, numbers and selects. The full reference (entity IDs, units, writable controls, services) is in the [user manual](docs/user_manual.md).

## Development

### Requirements

```
pip install pytest pytest-asyncio aioresponses aiohttp
```

### Run tests

```bash
python3 -m pytest tests/ -v
```

### Traffic capture (for further reverse engineering)

```bash
# Install mitmproxy
pip install mitmproxy

# Start capture proxy (optionally filter by device/phone IP)
CAPTURE_PHONE_IP=192.168.1.x mitmdump -s tools/capture.py --listen-port 8080 --ssl-insecure
```

See [docs/reverse_engineering.md](docs/reverse_engineering.md) for full findings on the cloud API.

## Contributing

Pull requests are welcome. Please open an issue first to discuss what you'd like to change.

## License

MIT
