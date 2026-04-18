# tools/

Reverse-engineering and traffic-capture helpers used while developing this
integration. **Not required at runtime** — the HA custom component itself lives
under `custom_components/malarenergi_powerhub/`.

Everything that could contain personal data (captures, `.env`, APK patches) is
gitignored. Do not commit files from this directory without checking
`.gitignore` first.

## Configuration

The capture scripts read network addresses from environment variables so
nothing personal is hard-coded. Copy the template and fill in your own values:

```bash
cp tools/.env.example tools/.env
$EDITOR tools/.env
```

Then source it before running any capture command:

```bash
set -a; source tools/.env; set +a
```

`tools/.env` is gitignored.

### Variables

| Variable | Purpose | Required |
|---|---|---|
| `CAPTURE_PHONE_IP` | LAN IP of the phone running the Mälarenergi app. `capture.py` keeps every flow from this IP even if the host isn't on its allow-list. | Recommended |
| `CAPTURE_DEVICE_IP` | LAN IP of the PowerHub device. Only useful if you also want to inspect direct device traffic (the device phones home via HTTPS — no local API). | Optional |
| `CAPTURE_FIREBASE` | Set to `1` to also capture `firebase*` / `googleapis.com` traffic. Off by default because Firebase uses certificate pinning and breaks through mitmproxy. | Optional |

## Scripts

| File | Purpose |
|---|---|
| `capture.py` | mitmproxy addon. Logs every captured request/response to a timestamped `captures/<ts>.jsonl` and `.log`. Redacts auth headers. Binary bodies (protobuf, octet-stream, media) are preserved as `{"__b64__": "..."}` in the JSONL so they round-trip cleanly; the `.log` shows `<binary N bytes>` markers instead of the full blob. |
| `start_capture.sh` | Convenience wrapper — prints the LAN IP to set on the phone and starts `mitmdump` with `capture.py` on port 8080. |
| `fcm_listen.py` | Registers a fake Android client with Firebase Cloud Messaging and prints push notifications from the Bitvis backend in real time. Requires Firebase project config (extracted from the APK). |
| `setup_proxy_windows.ps1` | PowerShell helper for routing Windows traffic through mitmproxy (rarely needed; phone is the usual source). |

## Typical workflow

1. Install mitmproxy (`uv tool install mitmproxy` or pipx).
2. Fill in `tools/.env` (at least `CAPTURE_PHONE_IP`).
3. Start the capture:
   ```bash
   bash tools/start_capture.sh
   ```
4. On the phone, set the Wi-Fi proxy to the LAN IP printed by the script,
   port 8080. Install the mitmproxy CA cert via `http://mitm.it`.
5. Use the Mälarenergi app — each flow is written to
   `tools/captures/<timestamp>.jsonl` and `.log`.
6. Stop with Ctrl+C. Inspect the `.log` for human review; parse the `.jsonl`
   for automation.

## Captures directory

`tools/captures/` is gitignored (apart from `.gitkeep`) because captures can
contain JWTs, facility UUIDs, addresses and other personal data. Treat every
file under it as sensitive.

## APK artifacts

`tools/apk_patch/` holds large binaries from the APK-patching experiments
(pinning bypass, smali dumps). Gitignored — keep locally or remove entirely;
nothing in the integration depends on it.
