# Run this script ONCE as Administrator in PowerShell on Windows
# It opens port 8080 in the firewall and forwards it from Windows LAN to WSL2
#
# Right-click PowerShell → "Run as administrator", then:
#   .\tools\setup_proxy_windows.ps1

$wslIp = (wsl hostname -I).Trim().Split(' ')[0]
Write-Host "WSL2 IP: $wslIp" -ForegroundColor Cyan

# Forward Windows port 8080 → WSL2 port 8080
netsh interface portproxy delete v4tov4 listenport=8080 listenaddress=0.0.0.0 2>$null
netsh interface portproxy add    v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=$wslIp
Write-Host "Port proxy 0.0.0.0:8080 → $wslIp:8080 configured" -ForegroundColor Green

# Open firewall
netsh advfirewall firewall delete rule name="mitmproxy-8080" 2>$null
netsh advfirewall firewall add rule name="mitmproxy-8080" protocol=TCP dir=in localport=8080 action=allow
Write-Host "Firewall rule added" -ForegroundColor Green

Write-Host ""
Write-Host "Done! You can now start the proxy in WSL2:" -ForegroundColor Yellow
Write-Host "  bash tools/start_capture.sh"
Write-Host ""
Write-Host "Phone proxy settings:"
Write-Host "  Host: $(((Get-NetIPAddress -AddressFamily IPv4) | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object -First 1).IPAddress)"
Write-Host "  Port: 8080"
