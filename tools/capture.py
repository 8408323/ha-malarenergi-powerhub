"""
mitmproxy addon — captures Mälarenergi / Bitvis PowerHub API traffic.

Usage:
  mitmdump -s tools/capture.py --listen-port 8080 --ssl-insecure

Configure source IPs via environment variables (optional):
  CAPTURE_PHONE_IP=192.168.1.x   — capture ALL traffic from this IP (phone)
  CAPTURE_DEVICE_IP=192.168.1.x  — capture ALL traffic from this IP (PowerHub)

  CAPTURE_FIREBASE=1             — also capture Firebase / Google API traffic
                                   (default: 0, disabled — Firebase uses certificate
                                    pinning so these calls often fail through mitmproxy)

If not set, only traffic to known Mälarenergi/Bitvis domains is captured.

Install mitmproxy CA cert on phone:
  Open http://mitm.it in the phone browser while proxy is active.

Output (per capture session, timestamped):
  tools/captures/YYYYMMDD_HHMMSS.jsonl  — one JSON record per line (machine-readable)
  tools/captures/YYYYMMDD_HHMMSS.log    — human-readable log
  tools/captures/firebase_config.json   — auto-extracted Firebase project config (if found)

WARNING: Output files may contain auth tokens. They are .gitignored.
         Never commit them.
"""

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mitmproxy import http

# --- configuration -------------------------------------------------------

CAPTURE_DOMAINS = [
    "malarenergi",
    "bitvis",
    "maintrac",
    "powerhub",
    "power-hub",
    "powerflow",
    "power-flow",
    "bitv.is",
]

# Firebase / Google domains — only included when CAPTURE_FIREBASE=1
FIREBASE_DOMAINS = [
    "firebase",
    "firebaseapp",
    "googleapis.com",
    "fcm.googleapis.com",
    "firebaseinstallations.googleapis.com",
    "firebaseremoteconfig.googleapis.com",
]

# Whether to capture Firebase traffic (disabled by default — Firebase uses
# certificate pinning which causes app connectivity issues through mitmproxy)
CAPTURE_FIREBASE: bool = os.environ.get("CAPTURE_FIREBASE", "0") not in ("", "0", "false", "no")

if CAPTURE_FIREBASE:
    CAPTURE_DOMAINS.extend(FIREBASE_DOMAINS)

# Firebase project config keys we want to extract (only relevant when CAPTURE_FIREBASE=1)
FIREBASE_CONFIG_KEYS = {
    "projectId", "appId", "apiKey", "messagingSenderId",
    "storageBucket", "authDomain",
}

# Load source IPs from env — no defaults so nothing personal is hardcoded
_CAPTURE_SOURCE_IPS: set[str] = set(filter(None, [
    os.environ.get("CAPTURE_PHONE_IP", ""),
    os.environ.get("CAPTURE_DEVICE_IP", ""),
]))

REDACT_HEADERS = {
    "authorization",
    "flow-auth-token",
    "cookie",
    "set-cookie",
    "x-auth-token",
    "x-api-key",
    "x-session-token",
    "x-access-token",
}

# Timestamped output directory — one session per run, never overwrites old captures
_SESSION_TS = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
_CAPTURES_DIR = Path(__file__).parent / "captures"
_CAPTURES_DIR.mkdir(exist_ok=True)

OUT_JSONL    = _CAPTURES_DIR / f"{_SESSION_TS}.jsonl"
OUT_LOG      = _CAPTURES_DIR / f"{_SESSION_TS}.log"
OUT_FIREBASE = _CAPTURES_DIR / "firebase_config.json"

# -------------------------------------------------------------------------


def _should_capture(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host.lower()
    client_ip = flow.client_conn.peername[0] if flow.client_conn.peername else ""
    if any(d in host for d in CAPTURE_DOMAINS):
        return True
    if _CAPTURE_SOURCE_IPS and client_ip in _CAPTURE_SOURCE_IPS:
        return True
    return False


def _redact(headers: dict) -> dict:
    return {
        k: ("***REDACTED***" if k.lower() in REDACT_HEADERS else v)
        for k, v in headers.items()
    }


def _is_binary_content_type(headers) -> bool:
    ct = headers.get("content-type", "").lower()
    return (
        "protobuf" in ct
        or "octet-stream" in ct
        or ct.startswith("image/")
        or ct.startswith("audio/")
        or ct.startswith("video/")
    )


def _summarize_body(body: object, limit: int) -> str:
    """Render a captured body for the human-readable log. Binary bodies (base64)
    show as a short marker instead of dumping the full blob."""
    if isinstance(body, dict) and "__b64__" in body and len(body) == 1:
        b64 = body["__b64__"]
        raw_len = (len(b64) * 3) // 4 - b64.count("=")
        return f"<binary {raw_len} bytes, base64 in .jsonl>"
    return json.dumps(body, ensure_ascii=False)[:limit]


def _encode_body(body: bytes, headers) -> object:
    """Return a JSON-safe representation of a response/request body.

    - JSON → parsed dict/list
    - Binary (protobuf, octet-stream, media) → {"__b64__": "<base64>"}
    - Otherwise → text with replacement chars, truncated at 4000
    """
    if _is_binary_content_type(headers):
        return {"__b64__": base64.b64encode(body).decode("ascii")}
    try:
        return json.loads(body)
    except Exception:
        text = body.decode("utf-8", errors="replace")
        return text if len(text) < 4000 else text[:4000] + "…"


def response(flow: http.HTTPFlow) -> None:
    if not _should_capture(flow):
        return

    req = flow.request
    resp = flow.response
    client_ip = flow.client_conn.peername[0] if flow.client_conn.peername else "?"

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "client_ip": client_ip,
        "request": {
            "method": req.method,
            "url": req.pretty_url,
            "headers": _redact(dict(req.headers)),
            "body": _encode_body(req.content, req.headers) if req.content else None,
        },
        "response": {
            "status": resp.status_code,
            "headers": _redact(dict(resp.headers)),
            "body": _encode_body(resp.content, resp.headers) if resp.content else None,
        },
    }

    with OUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Extract Firebase project config if present in response body
    body = record["response"]["body"]
    if isinstance(body, dict):
        found = {k: body[k] for k in FIREBASE_CONFIG_KEYS if k in body}
        if found and not OUT_FIREBASE.exists():
            OUT_FIREBASE.write_text(json.dumps(found, indent=2, ensure_ascii=False))
            print(f"\n🔥 Firebase config extracted → {OUT_FIREBASE}\n{json.dumps(found, indent=2)}\n")

    sep = "─" * 72
    lines = [
        sep,
        f"[{record['timestamp']}]  client: {client_ip}",
        f"▶ {req.method} {req.pretty_url}",
        f"◀ {resp.status_code} {resp.reason}",
    ]
    interesting = {k: v for k, v in record["request"]["headers"].items()
                   if k.lower() not in ("user-agent", "accept-encoding",
                                        "accept-language", "accept", "connection")}
    if interesting:
        lines.append("  REQ HEADERS: " + json.dumps(interesting, ensure_ascii=False))
    if record["request"]["body"]:
        lines.append("  REQ BODY:    " + _summarize_body(record["request"]["body"], 800))
    if record["response"]["body"]:
        lines.append("  RESP BODY:   " + _summarize_body(record["response"]["body"], 1500))
    lines.append("")
    text = "\n".join(lines)

    with OUT_LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
