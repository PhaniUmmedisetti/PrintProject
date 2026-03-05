# Pi Kiosk Setup Guide

Use this guide to run the PrintProject kiosk agent + touchscreen UI on Raspberry Pi.
This version is aligned to the current PrintNest device API flow and 800x480 display.

---

## 0) One-Command `.env` Bootstrap (optional)

If PrintNest API is already running, auto-create kiosk env files:

```bash
python3 pi/backend/scripts/bootstrap_kiosk_env.py
```

This writes:
- `pi/backend/.env`
- `pi/frontend/.env`

---

## 1) System Dependencies

Run once on a fresh Pi:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  git curl \
  python3 python3-pip python3-venv python3-dev \
  cups cups-client python3-cups \
  build-essential pkg-config libcups2-dev libcupsimage2-dev \
  libreoffice --no-install-recommends \
  chromium
```

Node 20:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Verify:

```bash
python3 --version
node --version
lpstat -p
```

---

## 2) Backend Setup

```bash
cd ~/PrintProject/pi/backend
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Create `pi/backend/.env`:

```env
CLOUD_API_URL=http://<printnest-host>:5000
DEVICE_ID=dev_store_xxx
SHARED_SECRET=<base64-secret>
STORE_ID=store_xxx
DOCUMENT_PRINTER_NAME=DeskJet_2300
PHOTO_PRINTER_NAME=
TEMP_DIR=/tmp/printjobs
HEARTBEAT_INTERVAL=60
```

Notes:
- Use `lpstat -p` and copy printer name exactly.
- `python3-cups` is installed via apt (not pip).

---

## 3) Frontend Setup

```bash
cd ~/PrintProject/pi/frontend
npm install
```

Create `pi/frontend/.env`:

```env
VITE_PI_API_URL=http://localhost:8001
VITE_WEBAPP_URL=https://your-customer-webapp.example.com
```

Build:

```bash
npm run build
```

---

## 4) Manual Run Test (before services)

Terminal A (backend):

```bash
cd ~/PrintProject/pi/backend
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Terminal B (frontend preview):

```bash
cd ~/PrintProject/pi/frontend
npm run preview -- --host --port 4173
```

Terminal C (kiosk browser):

```bash
cd ~/PrintProject/pi/frontend
bash ./start-kiosk.sh http://localhost:4173
```

Quick health checks:

```bash
curl http://localhost:8001/health
curl http://localhost:8001/local/printers
```

---

## 5) Install as Auto-Start Services

These are template units (`@.service`) so any Pi username works.
Below uses `<USER>` (example: `phani_pi`).

Install unit files:

```bash
sudo cp ~/PrintProject/pi/backend/printproject-pi@.service /etc/systemd/system/
sudo cp ~/PrintProject/pi/frontend/printproject-frontend-serve@.service /etc/systemd/system/
sudo cp ~/PrintProject/pi/frontend/printproject-kiosk@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Enable + start:

```bash
sudo systemctl enable printproject-pi@<USER>
sudo systemctl enable printproject-frontend-serve@<USER>
sudo systemctl enable printproject-kiosk@<USER>

sudo systemctl start printproject-pi@<USER>
sudo systemctl start printproject-frontend-serve@<USER>
sudo systemctl start printproject-kiosk@<USER>
```

Status:

```bash
sudo systemctl status printproject-pi@<USER>
sudo systemctl status printproject-frontend-serve@<USER>
sudo systemctl status printproject-kiosk@<USER>
```

Logs:

```bash
sudo journalctl -u printproject-pi@<USER> -f
sudo journalctl -u printproject-frontend-serve@<USER> -f
sudo journalctl -u printproject-kiosk@<USER> -f
```

---

## 6) 800x480 Display Notes

The kiosk launcher (`start-kiosk.sh`) already enforces:
- `--window-size=800,480`
- `--force-device-scale-factor=1`
- `--kiosk --start-fullscreen`
- keyring/popup suppression flags (`--password-store=basic`, `--use-mock-keychain`)

So it should not crop/zoom on official 7-inch display.

---

## 7) OTP Print Verification Checklist

Expected real flow:
1. Enter OTP on kiosk.
2. Backend `/local/print` returns job and starts download.
3. `/local/confirm/{jobId}` submits CUPS job.
4. CUPS queue shows new job (`lpstat -o`).
5. Paper prints.
6. Local status moves to `DONE`.
7. Success screen appears.

Useful live checks during print:

```bash
lpstat -o
lpstat -W not-completed -o
sudo tail -f /var/log/cups/error_log
```

