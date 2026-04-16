"""
FCM listener — receives Firebase Cloud Messaging pushes from the Mälarenergi /
Bitvis PowerHub backend in real time.

Usage:
  python tools/fcm_listen.py [--token <api_bearer_token>]

The script registers a fake Android device with FCM (using the app's Firebase
project config), subscribes to the same notification topics the app uses, and
prints every incoming message to stdout. Messages are also appended (JSON lines)
to tools/captures/fcm_YYYYMMDD_HHMMSS.jsonl for later analysis.

FCM credentials (the registration token + keys) are persisted to
  tools/captures/fcm_credentials.json
so re-runs reuse the same FCM registration rather than creating a new device.

Firebase project config — extracted from the Mälarenergi Android APK:
  tools/captures/firebase_config.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from firebase_messaging import FcmPushClient, FcmRegisterConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
_LOGGER = logging.getLogger("fcm_listen")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).parent
_CAPTURES_DIR = _TOOLS_DIR / "captures"
_CAPTURES_DIR.mkdir(exist_ok=True)

_FIREBASE_CONFIG_FILE = _CAPTURES_DIR / "firebase_config.json"
_CREDENTIALS_FILE = _CAPTURES_DIR / "fcm_credentials.json"

_SESSION_TS = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
_OUT_JSONL = _CAPTURES_DIR / f"fcm_{_SESSION_TS}.jsonl"

# ---------------------------------------------------------------------------
# Firebase project config (from APK extraction)
# ---------------------------------------------------------------------------

def _load_firebase_config() -> dict:
    if not _FIREBASE_CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Firebase config not found at {_FIREBASE_CONFIG_FILE}\n"
            "Extract it from the APK first — see tools/capture.py or run the "
            "extraction script documented in docs/firebase_extraction.md"
        )
    return json.loads(_FIREBASE_CONFIG_FILE.read_text())


# ---------------------------------------------------------------------------
# Credentials persistence
# ---------------------------------------------------------------------------

def _load_credentials() -> dict | None:
    if _CREDENTIALS_FILE.exists():
        try:
            return json.loads(_CREDENTIALS_FILE.read_text())
        except Exception:
            pass
    return None


def _save_credentials(creds: dict) -> None:
    _CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2))
    _LOGGER.info("FCM credentials saved → %s", _CREDENTIALS_FILE)


# ---------------------------------------------------------------------------
# Message callback
# ---------------------------------------------------------------------------

def _on_message(message: dict, persistent_id: str, context: object) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": ts,
        "persistent_id": persistent_id,
        "message": message,
    }

    # Pretty-print to stdout
    sep = "─" * 72
    lines = [
        sep,
        f"[{ts}]  FCM message  (id: {persistent_id})",
    ]

    data = message.get("data") or {}
    notif = message.get("notification") or {}
    if notif:
        lines.append(f"  NOTIFICATION: {notif.get('title', '')} — {notif.get('body', '')}")
    if data:
        lines.append("  DATA: " + json.dumps(data, ensure_ascii=False))
    lines.append("")
    print("\n".join(lines), flush=True)

    # Append to JSONL
    with _OUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _run(token: str | None) -> None:
    config = _load_firebase_config()
    _LOGGER.info(
        "Firebase project: %s  app: %s",
        config.get("projectId"),
        config.get("appId"),
    )

    fcm_config = FcmRegisterConfig(
        project_id=config["projectId"],
        app_id=config["appId"],
        api_key=config["apiKey"],
        messaging_sender_id=config["messagingSenderId"],
        bundle_id="se.malarenergi.malar",
    )

    credentials = _load_credentials()

    client = FcmPushClient(
        callback=_on_message,
        fcm_config=fcm_config,
        credentials=credentials,
        credentials_updated_callback=_save_credentials,
    )

    _LOGGER.info("Registering / checking in with FCM…")
    fcm_token = await client.checkin_or_register()
    _LOGGER.info("FCM token: %s", fcm_token)

    if token:
        # Register the FCM token with the Mälarenergi backend so it receives pushes
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                base = "https://malarenergi.prod.flow.bitv.is/powerapi/v1"
                headers = {"Authorization": f"Bearer {token}"}
                topics = "operatingStatus,todaySpotPrice,generic"
                url = (
                    f"{base}/notifications"
                    f"?firebase_token={fcm_token}&topics={topics}&page=1&page_size=1"
                )
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    _LOGGER.info("Notification endpoint: HTTP %d", resp.status)
        except Exception as exc:
            _LOGGER.warning("Could not ping notification endpoint: %s", exc)

    _LOGGER.info("Listening for FCM messages… (Ctrl-C to stop)")
    _LOGGER.info("Output → %s", _OUT_JSONL)

    await client.start()

    try:
        await asyncio.get_running_loop().create_future()  # run forever
    except asyncio.CancelledError:
        pass
    finally:
        await client.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="FCM listener for Mälarenergi PowerHub")
    parser.add_argument(
        "--token",
        metavar="BEARER_TOKEN",
        default=None,
        help="Mälarenergi API bearer token (registers FCM token with backend)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_run(args.token))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
