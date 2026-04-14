#!/usr/bin/env bash
# Start mitmproxy to capture Mälarenergi / Bitvis PowerHub traffic.
# Run from repo root:  bash tools/start_capture.sh

set -e
cd "$(dirname "$0")/.."

PROXY_PORT=8080

# Find the Windows host IP (the LAN IP your phone will connect to)
# In WSL2, the Windows host IP is the default gateway
HOST_IP=$(ip route show default | awk '/default/ {print $3}' | head -1)
# Also get the actual LAN IP of the Windows host
LAN_IP=$(powershell.exe -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { \$_.IPAddress -like '192.168.*' -or \$_.IPAddress -like '10.*' } | Select-Object -First 1).IPAddress" 2>/dev/null | tr -d '\r\n')
[ -z "$LAN_IP" ] && LAN_IP="$HOST_IP"

echo "========================================================"
echo "  Mälarenergi PowerHub — Traffic Capture"
echo "========================================================"
echo ""
echo "  Proxy port : $PROXY_PORT"
echo "  Your LAN IP: $LAN_IP"
echo ""
echo "  PHONE SETUP:"
echo "  1. Go to Wi-Fi settings on your phone"
echo "  2. Long-press your network → Modify network"
echo "  3. Set proxy: Manual"
echo "     Host: $LAN_IP"
echo "     Port: $PROXY_PORT"
echo "  4. Open http://mitm.it in phone browser"
echo "     → Download & install the certificate for your OS"
echo "     (Android: install as 'CA certificate' under Security)"
echo "  5. Open the Mälarenergi app and use it normally"
echo ""
echo "  Captured traffic → tools/captured_traffic.log"
echo "  Machine-readable → tools/captured_traffic.jsonl"
echo ""
echo "  Press Ctrl+C to stop."
echo "========================================================"
echo ""

# Make sure output dir exists
mkdir -p tools

# Start mitmdump with our addon
~/.local/bin/mitmdump \
    --listen-host 0.0.0.0 \
    --listen-port "$PROXY_PORT" \
    --ssl-insecure \
    -s tools/capture.py \
    --set block_global=false
