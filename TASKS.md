# PrintProject — Task Breakdown

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Phase 0 — Project Setup

- [x] Write project README and architecture overview
- [x] Write task breakdown (this file)
- [x] Initialize git repository
- [x] Create directory structure (cloud/frontend, cloud/backend, pi/frontend, pi/backend, docs, infra)
- [x] Write `.gitignore` (Node, Python, .NET, OS files)
- [x] Decide and document final answers to open questions in README

---

## Phase 1 — Cloud Backend (.NET 8 / ASP.NET Core)

### 1.1 Project Scaffolding
- [ ] `dotnet new webapi` in `cloud/backend/`
- [ ] Add packages: EF Core, Npgsql, AWSSDK.S3, Razorpay SDK, FluentValidation
- [ ] Configure appsettings + environment-based config (dev / prod)
- [ ] Set up PostgreSQL connection with EF Core

### 1.2 Database Schema
- [ ] Design and create EF Core models:
  - `Store` — id, name, address, api_key (hashed), is_active, created_at
  - `PrintJob` — id, store_id (FK), code, status, file_key (S3), original_filename, file_type, printer_type, options (JSON), created_at, expires_at, claimed_at, completed_at
  - `Payment` — id, job_id (FK), store_id (FK), razorpay_order_id, razorpay_payment_id, amount_paise, status, created_at
- [ ] Run initial EF Core migration

### 1.3 File Upload API
- [ ] `POST /api/jobs/upload` — accept multipart file, validate type (PDF, DOCX, XLSX, PPTX, JPG, PNG) and size (**max 50 MB**), upload original to S3
- [ ] Store file_key and original_filename on job record
- [ ] Return `job_id` and draft job details

### 1.4 Payment API
- [ ] `POST /api/payments/create-order` — create Razorpay order for job_id
- [ ] `POST /api/payments/verify` — verify Razorpay signature, mark payment complete
- [ ] On payment success: generate one-time print code, set job status to `PAID`, set expiry TTL

### 1.5 Pi Validation API
- [ ] `POST /api/jobs/validate-code` — authenticate Pi via store API key, validate code, return job metadata + signed S3 download URL
- [ ] Mark job as `CLAIMED` on first successful validation (prevent reuse)
- [ ] Return 404 / 410 for invalid or already-used codes
- [ ] Scope code lookup to the calling store (a code from store A cannot be used at store B)

### 1.6 Job Lifecycle
- [ ] `GET /api/jobs/{id}/status` — return current print job status (for kiosk polling)
- [ ] `PATCH /api/jobs/{id}/status` — Pi backend updates status (PRINTING, DONE, FAILED)
- [ ] Delete file from S3 immediately on successful print status update from Pi
- [ ] S3 lifecycle rule: auto-delete objects in the jobs bucket after **5 days** (safety net)
- [ ] Scheduled cleanup job: mark jobs `EXPIRED` and purge DB records older than 5 days

### 1.7 Admin API
- [ ] Admin JWT auth (separate from Pi API key auth) — seed one superadmin account
- [ ] `GET /api/admin/stores` — list all stores
- [ ] `POST /api/admin/stores` — create a store, return generated API key (shown once)
- [ ] `GET /api/admin/stores/{id}/jobs` — paginated job list with filters (status, date)
- [ ] `GET /api/admin/stores/{id}/revenue` — daily/monthly revenue breakdown
- [ ] `GET /api/admin/stores/{id}/printer-status` — last heartbeat, printer states
- [ ] `POST /api/admin/stores/{id}/heartbeat` — Pi posts printer health every 60s

### 1.8 Security & Config
- [ ] HTTPS only; CORS locked to kiosk origin and web app origin
- [ ] Rate limiting on validate-code endpoint (prevent brute force)
- [ ] Per-store API key auth for Pi ↔ cloud; store keys hashed in DB (bcrypt)
- [ ] Input validation on all endpoints

---

## Phase 2 — Cloud Frontend (React + Vite)

### 2.1 Project Scaffolding
- [ ] `npm create vite@latest` in `cloud/frontend/` with React + TypeScript template
- [ ] Add: React Router, Axios, Tailwind CSS, Razorpay checkout script, React Query

### 2.2 Customer Pages & Components
- [ ] **Landing / Home** — tagline, "Print Now" CTA, QR description
- [ ] **Upload Page**
  - File picker (drag & drop + button), type/size validation on client
  - Accepted: PDF, DOCX, XLSX, PPTX, JPG, PNG
  - Print options: type (document/photo), color/BW, copies, paper size
  - File preview (PDF preview, image thumbnail)
- [ ] **Payment Page**
  - Order summary (file name, options, price)
  - Razorpay checkout integration
  - Loading/success/failure states
- [ ] **Code Display Page**
  - Large, clear display of alphanumeric print code (e.g. `A4K9-2X`)
  - "Save to phone" / copy button
  - Instructions for using the kiosk
- [ ] **Error / Expired Page**

### 2.3 Admin Pages (protected — `/admin/*`)
- [ ] Admin login page (JWT, separate credential from customer flow)
- [ ] **Dashboard** — total revenue, jobs today, active stores
- [ ] **Stores list** — create store, view API key (once), toggle active
- [ ] **Store detail** — live job queue (polling), revenue chart, printer health widget
- [ ] **Job detail** — status history, file info, payment details

### 2.4 Pricing Logic
- [ ] Define pricing table (BW per page, color per page, photo sizes)
- [ ] Client-side price calculation based on options

---

## Phase 3 — Pi Backend (Python 3 / FastAPI)

### 3.1 Project Scaffolding
- [ ] Create `pi/backend/` Python project with `venv`
- [ ] Add packages: `fastapi`, `uvicorn`, `pycups`, `httpx`, `python-dotenv`, `aiofiles`, `aiosqlite`
- [ ] Configure environment variables (cloud API URL, store API key, printer names, store ID)
- [ ] Verify LibreOffice is installed on Pi (`libreoffice --headless` available)

### 3.2 Code Validation & File Download
- [ ] `POST /local/print` — accept code from kiosk UI
- [ ] Call cloud `validate-code` API with the entered code
- [ ] On success: download file from the returned signed S3 URL to local temp dir
- [ ] Handle errors: invalid code, expired, network failure

### 3.3 File Conversion (LibreOffice)
- [ ] After download, check file extension
- [ ] If DOCX / XLSX / PPTX: run `libreoffice --headless --convert-to pdf <file>` via subprocess
- [ ] Wait for conversion, verify output PDF exists, handle failure
- [ ] Use converted PDF path for CUPS submission; delete intermediate files after print

### 3.4 CUPS Print Queue Integration
- [ ] Detect printer type from job metadata (`COLOR_PHOTO` or `LASER_DOCUMENT`)
- [ ] Map printer type to correct CUPS printer name (from config)
- [ ] Submit job to CUPS via `pycups` with correct options (copies, paper size, color mode)
- [ ] Monitor CUPS job status and poll until complete/failed
- [ ] Report final status back to cloud API (`PRINTING` → `DONE` / `FAILED`)

### 3.5 Local Job State
- [ ] Maintain a lightweight local SQLite DB (via `aiosqlite`) for in-flight jobs
  - Survives Pi restarts; prevents re-downloading on reconnect
- [ ] **Print-and-delete**: immediately remove temp dir (original file + converted PDF) after CUPS job completes or fails
- [ ] Pi temp dir budget: never accumulates — one job at a time, cleaned on completion

### 3.6 Heartbeat
- [ ] Background task: POST to `/api/admin/stores/{id}/heartbeat` every 60s
- [ ] Include printer status from CUPS (idle / printing / offline) for each configured printer

### 3.7 System Service
- [ ] Write `systemd` unit file for pi backend auto-start on boot
- [ ] Auto-restart on crash policy

---

## Phase 4 — Pi Frontend (React + Vite — Kiosk UI)

### 4.1 Project Scaffolding
- [ ] `npm create vite@latest` in `pi/frontend/` with React + TypeScript
- [ ] Tailwind CSS; design for **touch display** (large tap targets, high contrast)
- [ ] Configure to connect to Pi backend (localhost)

### 4.2 Screens
- [ ] **Idle / Attract Screen**
  - Animated QR code for cloud web app URL
  - "Scan to upload" instruction
  - "Already have a code? Tap here" button
  - Rotating store branding / promotional content
- [ ] **Enter Code Screen**
  - Large on-screen numpad or alphanumeric keyboard
  - Code input field with clear visual feedback
  - Submit / Cancel buttons
- [ ] **Processing Screen**
  - "Downloading your file..." with progress indicator
  - "Sending to printer..." status
- [ ] **Success Screen**
  - Confirmation message, estimated wait time
  - Auto-return to idle after timeout
- [ ] **Error Screen**
  - Clear error messages (invalid code / printer offline / network error)
  - Retry / Return to idle options

### 4.3 Kiosk Hardening
- [ ] Chromium kiosk mode launch script (full-screen, no address bar)
- [ ] Disable right-click and keyboard shortcuts in app
- [ ] Auto-refresh / watchdog for frontend process
- [ ] Write `systemd` unit file for frontend auto-start

---

## Phase 5 — Integration & Testing

- [ ] End-to-end test: upload → pay → get code → enter on kiosk → printed
- [ ] Test code expiry behavior
- [ ] Test printer queue when both printers busy
- [ ] Test network drop between Pi download and print
- [ ] Test large file handling (multi-page PDF)
- [ ] Test concurrent users (multiple uploads at once)
- [ ] Validate Razorpay webhook signature handling

---

## Phase 6 — Infrastructure & Deployment

### Cloud
- [ ] Choose AWS deployment: EC2 (simple) or ECS Fargate (scalable)
- [ ] Set up RDS PostgreSQL instance
- [ ] Create S3 bucket with lifecycle policies (auto-delete after TTL)
- [ ] Configure environment variables / AWS Secrets Manager
- [ ] Set up domain + SSL (ACM + ALB or Cloudflare)
- [ ] CI/CD pipeline (GitHub Actions) for cloud backend and frontend

### Pi
- [ ] Write Pi setup script (`setup.sh`): install Python, Node, CUPS, deps, systemd services
- [ ] Configure Pi auto-login and kiosk auto-start on boot
- [ ] Configure CUPS printers (already tested — document steps in `docs/deployment.md`)
- [ ] Test cold boot to kiosk ready

---

## Phase 7 — Nice to Haves (Post-MVP)

- [ ] SMS/WhatsApp notification to customer with print code (MSG91 / Twilio)
- [ ] Print job history for customers (optional account / phone-based)
- [ ] USB walk-up printing (local upload at kiosk)
- [ ] Printer ink/paper level alerts (CUPS supply levels via `pycups`)
- [ ] Remote Pi management (Tailscale or reverse SSH tunnel)
- [ ] Per-store pricing configuration from admin dashboard
- [ ] Customer-facing job status page (poll by code, no login needed)
