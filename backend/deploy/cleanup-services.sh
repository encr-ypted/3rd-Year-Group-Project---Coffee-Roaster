#!/usr/bin/env bash
# Stop and disable coffee-roaster (and related) services, kill stray API processes.
# Safe to run when deployment is messed up — does not delete your repo or .venv.
#
# On the Pi:
#   cd ~/Desktop/CoffeeController
#   chmod +x deploy/cleanup-services.sh
#   sudo ./deploy/cleanup-services.sh

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo ./deploy/cleanup-services.sh"
  exit 1
fi

echo "=== Custom systemd units (coffee / roaster / CoffeeController) ==="
FOUND=0
while IFS= read -r unit; do
  FOUND=1
  echo "  ${unit}"
done < <(grep -l -E 'coffee|roaster|CoffeeController|api/main\.py' /etc/systemd/system/*.service 2>/dev/null || true)

if [[ "${FOUND}" -eq 0 ]]; then
  echo "  (none matched in /etc/systemd/system/)"
fi

echo ""
echo "=== coffee-roaster.service status ==="
systemctl status coffee-roaster --no-pager 2>&1 || true

echo ""
echo "=== All enabled custom units in /etc/systemd/system/ ==="
systemctl list-unit-files --type=service --state=enabled \
  --no-pager /etc/systemd/system/*.service 2>/dev/null || true

echo ""
echo "=== Stopping and disabling coffee-roaster ==="
systemctl stop coffee-roaster 2>/dev/null && echo "  stopped coffee-roaster" || echo "  coffee-roaster not running"
systemctl disable coffee-roaster 2>/dev/null && echo "  disabled coffee-roaster" || echo "  coffee-roaster not enabled"

if [[ -f /etc/systemd/system/coffee-roaster.service ]]; then
  rm -f /etc/systemd/system/coffee-roaster.service
  echo "  removed /etc/systemd/system/coffee-roaster.service"
fi

systemctl daemon-reload
systemctl reset-failed coffee-roaster 2>/dev/null || true

echo ""
echo "=== Stray roaster Python processes ==="
if pgrep -af 'api/main\.py|api/hardware_test\.py|hardware/display/lcd\.py' 2>/dev/null; then
  pkill -f 'api/main\.py' 2>/dev/null || true
  pkill -f 'api/hardware_test\.py' 2>/dev/null || true
  pkill -f 'hardware/display/lcd\.py' 2>/dev/null || true
  sleep 1
  echo "  sent SIGTERM to matching processes"
else
  echo "  none found"
fi

echo ""
echo "=== Listeners on ports 8000 / 8001 ==="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp '( sport = :8000 or sport = :8001 )' 2>/dev/null || echo "  ports free"
elif command -v netstat >/dev/null 2>&1; then
  netstat -tlnp 2>/dev/null | grep -E ':8000|:8001' || echo "  ports free"
else
  echo "  (ss/netstat not available)"
fi

echo ""
echo "=== Done ==="
echo "  coffee-roaster should be gone: systemctl status coffee-roaster"
echo "  Re-install when ready:         sudo ./deploy/install-service.sh"
echo "  Manual API test:               .venv/bin/python3 api/main.py"
