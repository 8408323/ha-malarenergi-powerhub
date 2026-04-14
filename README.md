# ha-malarenergi-powerhub

Home Assistant custom integration for [Mälarenergi PowerHub](https://www.malarenergi.se/el/elavtal/powerhub/) — a local real-time energy monitor manufactured by [Bitvis](https://bitvis.se/power-flow/power-hub/).

> **Status**: Early development / reverse engineering in progress.

## Hardware

| Property | Value |
|---|---|
| Manufacturer | Bitvis (OEM for Mälarenergi) |
| SoC | Espressif ESP32 (OUI `94:54:C5`) |
| Connectivity | Wi-Fi 2.4 GHz + Bluetooth |
| HAN port | RJ45 (Norwegian standard) |
| Meter | Kaifa MA304 |
| Meter protocol | DLMS/COSEM over M-Bus (IEC 62056) |
| Poll interval | ~10 seconds |

## Features (planned)

- Local polling — no cloud dependency
- Real-time power consumption (W)
- Cumulative energy (kWh)
- Per-phase voltage and current (if exposed)
- HA Energy dashboard compatible sensors

## Reverse Engineering Notes

See [docs/reverse_engineering.md](docs/reverse_engineering.md) for findings on the device's local network API.

## Installation

> Not yet available. Work in progress.

Manual installation via HACS or by copying the `custom_components/malarenergi_powerhub/` folder to your HA config directory.

## Configuration

After installation, go to **Settings → Devices & Services → Add Integration** and search for *Mälarenergi PowerHub*.

The integration discovers the device automatically via mDNS, or you can enter the IP address manually.

## Contributing

Pull requests are welcome. Please open an issue first to discuss what you'd like to change.

## License

MIT
