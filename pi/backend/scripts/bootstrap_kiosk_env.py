#!/usr/bin/env python3
"""Auto-provision a PrintNest device and write kiosk .env files."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_dotenv(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    bearer_token: str | None = None,
) -> tuple[int, dict]:
    url = f"{base_url.rstrip('/')}{path}"
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    req = Request(url=url, method=method.upper(), data=body, headers=headers)
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, parsed
    except HTTPError as exc:
        raw = exc.read()
        parsed = {}
        if raw:
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                parsed = {"raw": raw.decode("utf-8", errors="replace")}
        return exc.code, parsed
    except URLError as exc:
        raise RuntimeError(f"Cannot reach PrintNest API at {url}: {exc}") from exc


def find_printnest_env(repo_root: Path) -> Path | None:
    candidates = []
    env_override = os.getenv("PRINTNEST_ENV_FILE")
    if env_override:
        candidates.append(Path(env_override))

    candidates.extend(
        [
            repo_root.parent / "printnest" / "infra" / ".env",
            Path(r"C:\Users\phani\Desktop\printnest\infra\.env"),
            Path("/home/pi/printnest/infra/.env"),
            Path("/home/pi/PrintNest/infra/.env"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def write_env(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]

    parser = argparse.ArgumentParser(description="Bootstrap kiosk .env files from PrintNest API.")
    parser.add_argument("--api-base-url", default="http://localhost:5000")
    parser.add_argument("--store-id", default="store_supermart_01")
    parser.add_argument("--store-name", default="SuperMart Hitech City")
    parser.add_argument("--store-address", default="Hitech City, Hyderabad, Telangana 500081")
    parser.add_argument("--store-latitude", type=float, default=17.4486)
    parser.add_argument("--store-longitude", type=float, default=78.3908)
    parser.add_argument("--device-prefix", default="dev_store_supermart")
    parser.add_argument("--staff-username")
    parser.add_argument("--staff-password")
    parser.add_argument("--document-printer", default="HP_LaserJet_Pro")
    parser.add_argument("--photo-printer", default="")
    parser.add_argument("--webapp-url", default="http://localhost:3000")
    parser.add_argument("--backend-env", default=str(repo_root / "pi" / "backend" / ".env"))
    parser.add_argument("--frontend-env", default=str(repo_root / "pi" / "frontend" / ".env"))
    args = parser.parse_args()

    staff_username = args.staff_username
    staff_password = args.staff_password

    source_env = find_printnest_env(repo_root)
    if (not staff_username or not staff_password) and source_env:
        env_map = parse_dotenv(source_env)
        staff_username = staff_username or env_map.get("STAFF_AUTH_BOOTSTRAP_USERNAME")
        staff_password = staff_password or env_map.get("STAFF_AUTH_BOOTSTRAP_PASSWORD")

    if not staff_username or not staff_password:
        raise RuntimeError(
            "Missing staff credentials. Pass --staff-username/--staff-password "
            "or set PRINTNEST_ENV_FILE pointing to printnest infra/.env."
        )

    login_status, login_body = request_json(
        args.api_base_url,
        "POST",
        "/api/v1/staff/auth/login",
        payload={"username": staff_username, "password": staff_password},
    )
    if login_status != 200:
        raise RuntimeError(f"Staff login failed ({login_status}): {login_body}")

    token = login_body.get("accessToken")
    if not token:
        raise RuntimeError("Staff login response missing accessToken.")

    store_payload = {
        "storeId": args.store_id,
        "name": args.store_name,
        "address": args.store_address,
        "latitude": args.store_latitude,
        "longitude": args.store_longitude,
    }
    store_status, store_body = request_json(
        args.api_base_url,
        "POST",
        "/api/v1/admin/stores",
        payload=store_payload,
        bearer_token=token,
    )
    if store_status not in (200, 409):
        raise RuntimeError(f"Store create failed ({store_status}): {store_body}")

    timestamp = time.strftime("%Y%m%d%H%M%S")
    device_id = f"{args.device_prefix}_{timestamp}"
    if not device_id.startswith("dev_"):
        raise RuntimeError("Device prefix must produce a deviceId starting with 'dev_'.")

    device_status, device_body = request_json(
        args.api_base_url,
        "POST",
        "/api/v1/admin/devices",
        payload={"deviceId": device_id, "storeId": args.store_id},
        bearer_token=token,
    )
    if device_status != 200:
        raise RuntimeError(f"Device registration failed ({device_status}): {device_body}")

    shared_secret = device_body.get("sharedSecret")
    if not shared_secret:
        raise RuntimeError("Device registration response missing sharedSecret.")

    backend_env_path = Path(args.backend_env).resolve()
    frontend_env_path = Path(args.frontend_env).resolve()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    write_env(
        backend_env_path,
        [
            f"# Auto-generated on {now}",
            f"CLOUD_API_URL={args.api_base_url.rstrip('/')}",
            f"DEVICE_ID={device_id}",
            f"SHARED_SECRET={shared_secret}",
            f"STORE_ID={args.store_id}",
            f"DOCUMENT_PRINTER_NAME={args.document_printer}",
            f"PHOTO_PRINTER_NAME={args.photo_printer}",
            "TEMP_DIR=/tmp/printjobs",
            "HEARTBEAT_INTERVAL=60",
        ],
    )

    write_env(
        frontend_env_path,
        [
            f"# Auto-generated on {now}",
            "VITE_PI_API_URL=http://localhost:8001",
            f"VITE_WEBAPP_URL={args.webapp_url}",
        ],
    )

    print("Bootstrap complete.")
    print(f"Store ID: {args.store_id}")
    print(f"Device ID: {device_id}")
    print(f"Backend env: {backend_env_path}")
    print(f"Frontend env: {frontend_env_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
