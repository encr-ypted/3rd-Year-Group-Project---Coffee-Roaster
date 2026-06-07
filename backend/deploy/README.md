# Deploying the Coffee Roaster on Raspberry Pi

This folder contains scripts to run the roast API (`api/main.py`) as a **systemd** service on boot. The service starts the WebSocket API on port **8000** and the SPI LCD dashboard in the same process (when `HARDWARE_MODE=pi`).

**These files live in your git repo.** Nothing is installed on the Pi until you copy or pull the code there and run the install script.

## Files in this folder

| File | Purpose |
|------|---------|
| `coffee-roaster.service` | systemd unit template |
| `install-service.sh` | Install, enable, and start the service |
| `uninstall-service.sh` | Stop, disable, and remove the service |
| `cleanup-services.sh` | Audit + stop/disable service, kill stray API processes |

The install script must be run from the folder that contains **`api/`** and **`deploy/`**. Two layouts work:

**Flat (common on the Pi)** — `CoffeeController` is the app root:

```
~/Desktop/CoffeeController/
├── .venv/
├── api/
├── deploy/
├── hardware/
└── requirements.txt
```

**Nested (git repo)** — `backend/` is the app root, venv one level up:

```
~/Desktop/CoffeeController/
├── .venv/
└── backend/
    ├── api/
    ├── deploy/
    └── requirements.txt
```

## Prerequisites

On the Pi, before installing the service:

1. **Clone or sync the repo** so `api/main.py` and `requirements.txt` are present.
2. **Python venv** with dependencies installed:

   Flat layout:

   ```bash
   cd ~/Desktop/CoffeeController
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

   Nested layout:

   ```bash
   cd ~/Desktop/CoffeeController
   python3 -m venv .venv
   .venv/bin/pip install -r backend/requirements.txt
   ```

   `install-service.sh` picks `.venv/bin/python3` next to `api/` or in the parent folder.

3. **SPI enabled** (thermocouple on SPI0, LCD on SPI1):

   ```bash
   sudo raspi-config   # Interface Options → SPI → Enable
   sudo reboot
   ls /dev/spidev*
   ```

4. **GPIO/SPI permissions** for the service user (e.g. `coffee`):

   ```bash
   sudo usermod -aG gpio,spi coffee
   ```

   Log out and back in (or reboot) after adding groups.

5. **Smoke-test manually once** before enabling boot startup:

   ```bash
   cd ~/Desktop/CoffeeController    # folder with api/
   .venv/bin/python3 api/main.py
   ```

   - Dashboard WebSocket: `ws://127.0.0.1:8000/ws/telemetry`
   - LCD wiring: see `docs/lcd_st7796_test.md`

   Press Ctrl+C when satisfied. Do **not** run `hardware_test.py` at the same time — it uses port **8001** and conflicts on GPIO.

## Install (boot on startup)

From the app directory on the Pi (contains `api/` and `deploy/`):

```bash
cd ~/Desktop/CoffeeController
chmod +x deploy/install-service.sh
sudo ./deploy/install-service.sh
```

The script:

- Writes `/etc/systemd/system/coffee-roaster.service`
- Sets `User` / `Group` to whoever owns the `backend/` folder (e.g. `coffee`, not only `pi`)
- Sets `WorkingDirectory` to the real `backend/` path
- Sets `ExecStart` to `CoffeeController/.venv/bin/python3` when that venv exists
- Runs `systemctl enable` and `systemctl restart`

### Customise the service

Edit `deploy/coffee-roaster.service` **before** installing if needed:

| Setting | Default | Notes |
|---------|---------|-------|
| `User` / `Group` | owner of `backend/` | Set automatically by `install-service.sh` |
| `WorkingDirectory` | `.../CoffeeController/backend` | Overwritten by `install-service.sh` |
| `ExecStart` | `.../CoffeeController/.venv/bin/python3 api/main.py` | Auto-detected; falls back to `/usr/bin/python3` if `.venv` is missing |
| `Environment` | `PYTHONUNBUFFERED=1` | Add `ROASTER_LCD=0` to disable LCD, or `ROASTER_HARDWARE_MODE=mock` for testing |

Example — LCD off but API on boot:

```ini
Environment=PYTHONUNBUFFERED=1 ROASTER_LCD=0
```

Re-run `sudo ./deploy/install-service.sh` after editing the template.

## Verify deployment

```bash
sudo systemctl status coffee-roaster
journalctl -u coffee-roaster -f
```

Healthy signs:

- `Active: active (running)`
- Logs show Uvicorn listening on `0.0.0.0:8000`
- No repeated crash/restart loop (`Restart=on-failure` with 5 s delay)

Useful commands:

```bash
sudo systemctl restart coffee-roaster   # after code or config changes
sudo systemctl stop coffee-roaster      # stop until next boot (if enabled)
sudo systemctl disable coffee-roaster   # stop boot startup, keep unit file
```

After pulling new code, restart the service:

```bash
cd ~/Desktop/CoffeeController
git pull
.venv/bin/pip install -r backend/requirements.txt    # if dependencies changed
sudo systemctl restart coffee-roaster
```

## Clear deployment (uninstall service)

If things are broken and you want a full reset (stop service, remove unit, kill stray `main.py`):

```bash
cd ~/Desktop/CoffeeController
chmod +x deploy/cleanup-services.sh
sudo ./deploy/cleanup-services.sh
```

To only remove the systemd unit (no process audit):

```bash
cd ~/Desktop/CoffeeController
chmod +x deploy/uninstall-service.sh
sudo ./deploy/uninstall-service.sh
```

This stops the service, disables it, removes `/etc/systemd/system/coffee-roaster.service`, and reloads systemd. **It does not delete your repo, logs, or Python packages.**

### Manual uninstall

If you prefer not to use the script:

```bash
sudo systemctl stop coffee-roaster
sudo systemctl disable coffee-roaster
sudo rm -f /etc/systemd/system/coffee-roaster.service
sudo systemctl daemon-reload
sudo systemctl reset-failed coffee-roaster 2>/dev/null || true
```

Confirm removal:

```bash
systemctl status coffee-roaster   # should report "could not be found"
```

### Stop a manual run (no systemd)

If you started the API by hand (`python3 api/main.py`) and never installed the service:

- Press **Ctrl+C** in that terminal, or
- `pkill -f "api/main.py"` (only if no other Python job should match)

### Optional cleanup (not done by uninstall)

| What | Command / action |
|------|------------------|
| Roast CSV logs | `rm -rf backend/logs/*` — only if you intend to wipe history |
| Python venv | Remove the venv directory you created |
| SPI / gpio groups | `sudo gpasswd -d pi spi` etc. — rarely needed |

## Troubleshooting

### Unit not found

The service was never installed. Run `sudo ./deploy/install-service.sh`.

### `status=217/USER` — “Failed to determine user credentials”

The unit still has `User=pi` but your login is different (e.g. `coffee`). Re-install from **`backend/`**, not the project root:

```bash
cd ~/Desktop/CoffeeController/backend
sudo ./deploy/install-service.sh
```

Confirm the installed unit:

```bash
grep -E '^(User|Group|ExecStart|WorkingDirectory)=' /etc/systemd/system/coffee-roaster.service
```

You should see `User=coffee`, `.venv/bin/python3`, and `WorkingDirectory=.../backend`.

Add GPIO/SPI for that user:

```bash
sudo usermod -aG gpio,spi coffee
```

Reboot or re-login after `usermod`.

### `ModuleNotFoundError: No module named 'fastapi'`

The service is using the wrong Python (system `/usr/bin/python3` instead of `.venv`). Fix deps, then re-install:

```bash
cd ~/Desktop/CoffeeController
.venv/bin/pip install -r requirements.txt
sudo ./deploy/install-service.sh
```

Check the unit uses the venv:

```bash
grep ExecStart= /etc/systemd/system/coffee-roaster.service
# should be: .../CoffeeController/.venv/bin/python3 api/main.py
```

### Service starts then exits (restart loop)

```bash
journalctl -u coffee-roaster -n 50 --no-pager
```

Common causes:

- Wrong `WorkingDirectory` or missing `requirements.txt` packages
- GPIO/SPI permission denied — check `gpio,spi` group membership
- Port 8000 already in use — stop a leftover `main.py` or other process
- Import errors after a partial git sync — pull full `backend/` tree

### WebSocket 403 on `/ws/telemetry`

Port 8000 is serving the **bench** API or another app. Only `api/main.py` should own 8000. Bench uses `hardware_test.py` on **8001**.

### LCD blank but API works

- Run LCD smoke test: `../.venv/bin/python3 hardware/display/st7796.py` (from `backend/`)
- Check SPI1 overlay and wiring: `docs/lcd_st7796_test.md`
- Disable LCD temporarily: `ROASTER_LCD=0` in the service `Environment` line

### Two APIs at once

Never run `main.py` and `hardware_test.py` together on the Pi — shared GPIO will conflict.

## Related docs

- Backend overview: `../README.md`
- LCD hardware: `../docs/lcd_st7796_test.md`
- Bench / dev testing: `../api/hardware_test.py` (port 8001, not for production boot)
