#!/usr/bin/env bash
# Install the coffee roaster API as a systemd service (Pi boot startup + LCD).
# Run on the Pi from the app folder (contains api/ and deploy/):
#   chmod +x deploy/install-service.sh
#   sudo ./deploy/install-service.sh

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="coffee-roaster.service"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}"

if [[ ! -f "${BACKEND_DIR}/api/main.py" ]]; then
  echo "Error: api/main.py not found in ${BACKEND_DIR}"
  echo "Run install from the folder that contains api/ and deploy/, e.g.:"
  echo "  cd ~/Desktop/CoffeeController && sudo ./deploy/install-service.sh"
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo ./deploy/install-service.sh"
  exit 1
fi

SERVICE_USER="$(stat -c '%U' "${BACKEND_DIR}")"
SERVICE_GROUP="$(stat -c '%G' "${BACKEND_DIR}")"

# .venv may sit next to api/ (flat layout) or one level up (repo: CoffeeController/.venv + backend/)
PYTHON=""
for candidate in \
  "${BACKEND_DIR}/.venv/bin/python3" \
  "$(dirname "${BACKEND_DIR}")/.venv/bin/python3"; do
  if [[ -x "${candidate}" ]]; then
    PYTHON="${candidate}"
    break
  fi
done

if [[ -z "${PYTHON}" ]]; then
  echo "Error: no .venv found. Expected one of:"
  echo "  ${BACKEND_DIR}/.venv/bin/python3"
  echo "  $(dirname "${BACKEND_DIR}")/.venv/bin/python3"
  echo "Create it, then install deps:"
  echo "  cd ${BACKEND_DIR} && python3 -m venv .venv"
  echo "  .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! "${PYTHON}" -c "import fastapi" 2>/dev/null; then
  REQ="${BACKEND_DIR}/requirements.txt"
  echo "Error: fastapi is not installed in ${PYTHON}"
  if [[ -f "${REQ}" ]]; then
    echo "  ${PYTHON} -m pip install -r ${REQ}"
  else
    echo "  ${PYTHON} -m pip install -r requirements.txt"
  fi
  exit 1
fi

sed -e "s|^User=.*|User=${SERVICE_USER}|" \
    -e "s|^Group=.*|Group=${SERVICE_GROUP}|" \
    -e "s|WorkingDirectory=.*|WorkingDirectory=${BACKEND_DIR}|" \
    -e "s|ExecStart=.*|ExecStart=${PYTHON} api/main.py|" \
  "${BACKEND_DIR}/deploy/coffee-roaster.service" > "${UNIT_PATH}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "Installed ${SERVICE_NAME}"
echo "  user:      ${SERVICE_USER} (owner of ${BACKEND_DIR})"
echo "  python:    ${PYTHON}"
echo "  status:    sudo systemctl status ${SERVICE_NAME}"
echo "  logs:      journalctl -u ${SERVICE_NAME} -f"
echo "  restart:   sudo systemctl restart ${SERVICE_NAME}"
echo "  uninstall: sudo ./deploy/uninstall-service.sh"
echo "  docs:      deploy/README.md"
