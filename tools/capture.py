"""
mitmproxy addon — captures Mälarenergi / Bitvis PowerHub API traffic.

Usage:
  mitmdump -s tools/capture.py --listen-port 8080 --ssl-insecure

Configure source IPs via environment variables (optional):
  CAPTURE_PHONE_IP=192.168.1.x   — capture ALL traffic from this IP (phone)
  CAPTURE_DEVICE_IP=192.168.1.x  — capture ALL traffic from this IP (PowerHub)

If not set, only traffic to known Mälarenergi/Bitvis domains is captured.

Install mitmproxy CA cert on phone:
  Open http://mitm.it in the phone browser while proxy is active.

Output:
  tools/captured_traffic.jsonl  — one JSON record per line (machine-readable)
  tools/captured_traffic.log    — human-readable log

WARNING: Output files may contain auth tokens. They are .gitignored.
         Never commit them.
"""

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

OUT_JSONL = Path(__file__).parent / "captured_traffic.jsonl"
OUT_LOG   = Path(__file__).parent / "captured_traffic.log"

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

    with OUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

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
        lines.append("  REQ BODY:    " + json.dumps(record["request"]["body"], ensure_ascii=False)[:800])
    if record["response"]["body"]:
        lines.append("  RESP BODY:   " + json.dumps(record["response"]["body"], ensure_ascii=False)[:1500])
    lines.append("")
    text = "\n".join(lines)

    with OUT_LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
