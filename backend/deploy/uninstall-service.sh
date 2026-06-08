#!/usr/bin/env bash
# Remove the coffee roaster systemd service (stop boot startup, delete unit file).
# Run on the Pi from the backend folder:
#   chmod +x deploy/uninstall-service.sh
#   sudo ./deploy/uninstall-service.sh

set -euo pipefail

SERVICE_NAME="coffee-roaster.service"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo ./deploy/uninstall-service.sh"
  exit 1
fi

if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
  systemctl stop "${SERVICE_NAME}"
  echo "Stopped ${SERVICE_NAME}"
fi

if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
  systemctl disable "${SERVICE_NAME}"
  echo "Disabled ${SERVICE_NAME}"
fi

if [[ -f "${UNIT_PATH}" ]]; then
  rm -f "${UNIT_PATH}"
  echo "Removed ${UNIT_PATH}"
else
  echo "No unit file at ${UNIT_PATH} (already removed?)"
fi

systemctl daemon-reload
systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true

echo ""
echo "Uninstalled ${SERVICE_NAME}"
echo "  Your repo, logs, and Python packages were not changed."
echo "  Re-install: sudo ./deploy/install-service.sh"
echo "  Confirm:    systemctl status ${SERVICE_NAME}  # should be 'not found'"
