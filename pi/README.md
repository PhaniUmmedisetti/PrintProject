# Pi — Setup & Operations Guide

Everything you need to get the kiosk running on a Raspberry Pi,
from first boot through production and day-to-day operations.

---

## Contents

1. [System Dependencies](#1-system-dependencies)
2. [Pi Backend Setup](#2-pi-backend-setup)
3. [Pi Frontend Setup](#3-pi-frontend-setup)
4. [First-Time Test Run (manual, no services)](#4-first-time-test-run)
5. [Install as System Services (production)](#5-install-as-system-services-production)
6. [Verify Startup is Working](#6-verify-startup-is-working)
7. [Exit Kiosk Mode & Shut Down Safely](#7-exit-kiosk-mode--shut-down-safely)
8. [Testing Without Real Credentials](#8-testing-without-real-credentials)

---

## 1. System Dependencies

Run once on a fresh Raspberry Pi OS installation:

```bash
sudo apt update && sudo apt upgrade -y

# Python build tools + CUPS dev headers (needed for pycups)
sudo apt install -y python3 python3-pip python3-venv \
                   libcups2-dev libcupsimage2-dev \
                   cups cups-client

# LibreOffice headless — converts DOCX/XLSX/PPTX → PDF before printing
sudo apt install -y libreoffice --no-install-recommends

# Node.js 20 LTS (for frontend build)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify installations
python3 --version      # should be 3.11+
node --version         # should be 20.x
lpstat -p              # list configured CUPS printers ← note the exact names
libreoffice --version  # should print version and exit
```

---

## 2. Pi Backend Setup

```bash
cd ~/PrintProject/pi/backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env file and fill in values
cp .env.example .env
nano .env
```

### `.env` values to fill in

```env
CLOUD_API_URL=https://your-cloud-api.example.com   # your deployed cloud backend URL
STORE_API_KEY=your-per-store-api-key-here          # generated from admin dashboard
STORE_ID=your-store-uuid-here                      # assigned when store is created

PHOTO_PRINTER_NAME=Canon_PIXMA_TS8320              # exact name from: lpstat -p
DOCUMENT_PRINTER_NAME=HP_LaserJet_Pro              # exact name from: lpstat -p

TEMP_DIR=/tmp/printjobs                            # leave as default
HEARTBEAT_INTERVAL=60                              # leave as default
```

> Run `lpstat -p` to find exact CUPS printer names. Copy them exactly — they are case-sensitive.

---

## 3. Pi Frontend Setup

```bash
cd ~/PrintProject/pi/frontend

# Install dependencies
npm install

# Copy env file and fill in values
cp .env.example .env
nano .env
```

```env
VITE_PI_API_URL=http://localhost:8001    # Pi backend — always localhost on Pi
VITE_WEBAPP_URL=https://your-webapp.com  # URL encoded into the QR code
```

Build the production bundle:

```bash
npm run build
# Output goes to pi/frontend/dist/
```

---

## 4. First-Time Test Run

Run both services manually in separate terminals to verify everything works
before installing them as system services.

### Terminal 1 — Backend

```bash
cd ~/PrintProject/pi/backend
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Expected output:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Database initialised
INFO:     Heartbeat started (interval=60s)
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8001
```

Verify it is running:
```bash
# In a third terminal
curl http://localhost:8001/health
# Expected: {"status":"ok"}

curl http://localhost:8001/local/printers
# Expected: {"printers":{"<photo_printer>":"idle","<doc_printer>":"idle"}}
```

**To stop:** Press `Ctrl+C` in Terminal 1.

---

### Terminal 2 — Frontend (browser preview)

```bash
cd ~/PrintProject/pi/frontend
npm run preview -- --host --port 4173
```

Expected output:
```
  ➜  Local:   http://localhost:4173/
  ➜  Network: http://192.168.x.x:4173/
```

Open a browser on the Pi:
```bash
chromium-browser http://localhost:4173
```

You should see the landing screen with the SELF/SECURE/FAST slideshow.

**To stop:** Press `Ctrl+C` in Terminal 2.

---

### Terminal 2 (alternative) — Frontend in kiosk mode for first test

```bash
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  http://localhost:4173
```

This opens the app full-screen. To exit during testing, see [Section 7](#7-exit-kiosk-mode--shut-down-safely).

---

## 5. Install as System Services (Production)

Once manual test passes, install both as systemd services so they
auto-start on boot and restart on crash.

### Backend service

```bash
# The service file is already in the repo
sudo cp ~/PrintProject/pi/backend/printproject-pi.service /etc/systemd/system/

# Reload systemd, enable and start
sudo systemctl daemon-reload
sudo systemctl enable printproject-pi
sudo systemctl start printproject-pi

# Verify it's running
sudo systemctl status printproject-pi
```

### Frontend service

Create the service file:

```bash
sudo nano /etc/systemd/system/printproject-kiosk.service
```

Paste:

```ini
[Unit]
Description=PrintProject Kiosk Frontend
After=network.target printproject-pi.service graphical.target
Wants=printproject-pi.service

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 5
ExecStart=chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-session-crashed-bubble \
    http://localhost:4173
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable printproject-kiosk
sudo systemctl start printproject-kiosk
```

### Serve the frontend build

The kiosk service opens `http://localhost:4173`, so you need something serving the `dist/` folder on that port. Create a simple serve service:

```bash
sudo nano /etc/systemd/system/printproject-frontend-serve.service
```

Paste:

```ini
[Unit]
Description=PrintProject Frontend Static Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/PrintProject/pi/frontend
ExecStart=/usr/bin/npx vite preview --host --port 4173
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable printproject-frontend-serve
sudo systemctl start printproject-frontend-serve
```

---

## 6. Verify Startup is Working

### Check all three services are running

```bash
sudo systemctl status printproject-pi              # backend
sudo systemctl status printproject-frontend-serve  # static file server
sudo systemctl status printproject-kiosk           # Chromium kiosk
```

All three should show `active (running)`.

### Watch live logs

```bash
# Backend logs (most useful — shows job processing, heartbeat, errors)
sudo journalctl -u printproject-pi -f

# Frontend serve logs
sudo journalctl -u printproject-frontend-serve -f

# All three together
sudo journalctl -u printproject-pi -u printproject-frontend-serve -u printproject-kiosk -f
```

### Test backend health endpoint

```bash
curl http://localhost:8001/health
# Expected: {"status":"ok"}
```

### Test printer detection

```bash
curl http://localhost:8001/local/printers
# Expected: {"printers":{"YourPhotoPrinter":"idle","YourDocPrinter":"idle"}}
# If printers show "offline", check CUPS: sudo systemctl status cups
```

### Simulate a cold boot

```bash
sudo reboot
# After reboot, SSH back in and run:
sudo systemctl status printproject-pi
sudo systemctl status printproject-frontend-serve
sudo systemctl status printproject-kiosk
curl http://localhost:8001/health
```

---

## 7. Exit Kiosk Mode & Shut Down Safely

### Exit kiosk mode during production

**Option A — keyboard shortcut** (if a keyboard is connected):
```
Alt+F4          → closes Chromium
Ctrl+Alt+T      → opens a terminal
```

**Option B — SSH from another machine** (recommended for headless exit):
```bash
ssh pi@<pi-ip-address>

# Stop just the kiosk (Chromium)
sudo systemctl stop printproject-kiosk

# Stop all three services
sudo systemctl stop printproject-kiosk printproject-frontend-serve printproject-pi
```

**Option C — kill Chromium directly** (emergency):
```bash
pkill chromium-browser
```

---

### Properly shut down the Pi

**Always** shut down via software — never just pull the power. Abrupt power cuts can corrupt the SD card.

```bash
# Graceful shutdown
sudo shutdown -h now

# Or schedule a shutdown in 1 minute (gives time to warn any active user)
sudo shutdown -h +1 "Kiosk shutting down in 1 minute"

# Reboot
sudo reboot
```

To shut down from the kiosk screen (if no keyboard), SSH in and run `sudo shutdown -h now`.

---

### Re-entering kiosk mode after maintenance

```bash
# Start all services again
sudo systemctl start printproject-pi
sudo systemctl start printproject-frontend-serve
sudo systemctl start printproject-kiosk
```

---

## 8. Testing Without Real Credentials

Use this section when the cloud backend is not yet set up but you want to
verify the frontend UI and backend startup work correctly on the Pi.

### Step 1 — Minimal `.env` (dummy values are fine for startup check)

```bash
cd ~/PrintProject/pi/backend
cat > .env << 'EOF'
CLOUD_API_URL=http://localhost:9999
STORE_API_KEY=test-key
STORE_ID=test-store
PHOTO_PRINTER_NAME=Test_Photo_Printer
DOCUMENT_PRINTER_NAME=Test_Doc_Printer
TEMP_DIR=/tmp/printjobs
HEARTBEAT_INTERVAL=60
EOF
```

> The backend will start successfully. The heartbeat will log a warning every 60s
> (can't reach `localhost:9999`) but this is harmless and non-crashing.

### Step 2 — Start the backend and check it is healthy

```bash
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001

# In another terminal:
curl http://localhost:8001/health
# ✓ Expected: {"status":"ok"}

curl http://localhost:8001/local/printers
# ✓ Expected: {"printers":{"Test_Photo_Printer":"offline","Test_Doc_Printer":"offline"}}
# "offline" is correct here because these printers don't exist in CUPS yet
```

### Step 3 — Start the frontend and verify all screens load

```bash
cd ~/PrintProject/pi/frontend
npm run preview -- --host --port 4173
```

Open `http://localhost:4173` in a browser and manually walk through every screen:

| Screen | How to reach | What to verify |
|---|---|---|
| Landing | App opens | Slideshow cycles SELF → SECURE → FAST, "Print Now" button visible |
| QR Code | Tap "Print Now" | QR code renders, "Enter Code" button visible |
| Keypad | Tap "Enter Code" | A–F and 0–9 keys work, 6 boxes fill as you type |
| Invalid code error | Enter any 6 chars, tap Confirm | Red error message appears, boxes shake and clear |
| Error screen | Tap "Try Again" then enter code again and let it fail | Error screen shows with Retry / Cancel buttons |
| Landing (reset) | Tap "Cancel" on error screen | Returns to landing |

> The keypad "Confirm" will always show "Invalid or expired code" until the cloud backend is running — that is expected.

### Step 4 — Check the SQLite DB was created

```bash
ls -lh ~/PrintProject/pi/backend/jobs.db
# Should exist after the backend starts (even with dummy env vars)

# Inspect it (optional)
sqlite3 ~/PrintProject/pi/backend/jobs.db ".schema"
sqlite3 ~/PrintProject/pi/backend/jobs.db "SELECT * FROM print_jobs;"
# Empty result is correct — no jobs have been submitted yet
```
