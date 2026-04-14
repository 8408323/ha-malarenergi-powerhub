"""
mitmproxy addon — captures Mälarenergi / Bitvis PowerHub API traffic.

Usage:
  mitmdump -s tools/capture.py --listen-port 8080 --ssl-insecure

Then configure your phone's Wi-Fi proxy to point at this machine:
  Host: <your PC LAN IP, e.g. 192.168.1.147>  Port: 8080
Install the mitmproxy CA cert on your phone:
  Open http://mitm.it in the phone browser while proxy is active.

All captured requests/responses are written to:
  tools/captured_traffic.jsonl  (one JSON object per line)
  tools/captured_traffic.log    (human-readable)
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from mitmproxy import http

# --- configuration -------------------------------------------------------

# Domains/keywords to capture — ANY substring match on the host (case-insensitive)
CAPTURE_DOMAINS = [
    "malarenergi",
    "bitvis",
    "maintrac",
    "powerhub",
    "power-hub",
    "power_hub",
    "powerflow",
    "power-flow",
]

# Source IPs to capture ALL traffic from (e.g. phone, PowerHub device)
# Add more IPs here if needed
CAPTURE_SOURCE_IPS = [
    "192.168.1.x",   # phone
    "192.168.1.x",   # PowerHub device (unlikely to use proxy, but just in case)
]

# Headers whose VALUES should be redacted in logs (never committed to git)
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

OUT_JSONL = Path(__file__).parent / "captured_traffic.jsonl"
OUT_LOG   = Path(__file__).parent / "captured_traffic.log"

# -------------------------------------------------------------------------


def _should_capture(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host.lower()
    client_ip = flow.client_conn.peername[0] if flow.client_conn.peername else ""

    # Capture if host matches known Mälarenergi/Bitvis domains
    if any(d in host for d in CAPTURE_DOMAINS):
        return True
    # Capture ALL traffic from phone/device IPs (broad sweep to find unknown domains)
    if client_ip in CAPTURE_SOURCE_IPS:
        return True
    return False


def _redact(headers: dict) -> dict:
    return {
        k: ("***REDACTED***" if k.lower() in REDACT_HEADERS else v)
        for k, v in headers.items()
    }


def _try_json(body: bytes) -> object:
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
            "body": _try_json(req.content) if req.content else None,
        },
        "response": {
            "status": resp.status_code,
            "headers": _redact(dict(resp.headers)),
            "body": _try_json(resp.content) if resp.content else None,
        },
    }

    # --- write JSONL ---------------------------------------------------------
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # --- write human-readable log --------------------------------------------
    sep = "─" * 72
    lines = [
        sep,
        f"[{record['timestamp']}]  client: {client_ip}",
        f"▶ {req.method} {req.pretty_url}",
        f"◀ {resp.status_code} {resp.reason}",
    ]

    interesting_req = {k: v for k, v in record["request"]["headers"].items()
                       if k.lower() not in ("user-agent", "accept-encoding",
                                            "accept-language", "accept", "connection")}
    if interesting_req:
        lines.append("  REQ HEADERS: " + json.dumps(interesting_req, ensure_ascii=False))

    if record["request"]["body"]:
        lines.append("  REQ BODY:    " + json.dumps(record["request"]["body"], ensure_ascii=False)[:800])

    if record["response"]["body"]:
        lines.append("  RESP BODY:   " + json.dumps(record["response"]["body"], ensure_ascii=False)[:1500])

    lines.append("")
    text = "\n".join(lines)

    with OUT_LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")

    print(text)
