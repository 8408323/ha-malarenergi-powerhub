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

- Today's energy consumption (Wh, summed from 15-minute buckets)
- Today's energy production (Wh, if applicable)
- Current spot price (öre/kWh, from Nordpool via Bitvis)
- HA Energy dashboard compatible sensors
- Automatic token re-auth when JWT expires

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
3. Scan the BankID QR code that appears.
4. Select which facility to monitor (if you have multiple).

## Sensors

| Entity | Unit | Description |
|---|---|---|
| `sensor.malarenergi_consumption_today` | Wh | Cumulative consumption since midnight |
| `sensor.malarenergi_production_today` | Wh | Cumulative production since midnight |
| `sensor.malarenergi_spot_price` | öre/kWh | Current Nordpool spot price |

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
