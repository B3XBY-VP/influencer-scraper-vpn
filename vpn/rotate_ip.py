# backend/vpn/rotate_ip.py

from __future__ import annotations
import platform
import random
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests
from firebase_admin import firestore  # for SERVER_TIMESTAMP
from config import VPN_CONFIG_DIR, SURFSHARK_USER, SURFSHARK_PASS, db

def _kill_existing_openvpn() -> None:
    """Best-effort kill of any running OpenVPN process."""
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/IM", "openvpn.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        # use -9 to be sure nothing lingers
        subprocess.run(
            ["pkill", "-9", "-f", "openvpn"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

def _write_creds_file(creds_path: Path) -> None:
    """Write Surfshark credential file consumed by .ovpn configs."""
    creds_path.write_text(f"{SURFSHARK_USER}\n{SURFSHARK_PASS}\n", encoding="utf-8")

def _random_uk_config() -> Path:
    """
    Pick a random .ovpn inside VPN_CONFIG_DIR.
    VPN_CONFIG_DIR should point at .../vpn/configs/uk.
    """
    uk_dir = Path(VPN_CONFIG_DIR)
    ovpns = list(uk_dir.glob("uk-*.ovpn"))
    if not ovpns:
        raise FileNotFoundError(f"No uk-*.ovpn files found in {uk_dir}")
    return random.choice(ovpns)

def _start_openvpn(cfg: Path, creds_path: Path) -> subprocess.Popen:
    """
    Launch OpenVPN with the chosen config in the background,
    and redirect ALL IPv4 traffic through it.
    """
    cmd = [
        "openvpn",
        "--config", str(cfg),
        "--auth-user-pass", str(creds_path),
        "--redirect-gateway", "def1",   # ← force all traffic down the tunnel
        "--daemon",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def rotate_ip(*, burner_id: Optional[str] = None) -> str:
    """
    Kill any existing VPN, connect to a random UK Surfshark server,
    wait ~15s for tunnel, fetch the new public IP over the tunnel,
    write Firestore audit-log, and return it.
    """
    # 1) choose config & write creds
    cfg = _random_uk_config()
    print(f"🔄 Rotating VPN using config: {cfg.name}")
    creds_file = Path(__file__).parent / "surfshark_creds.txt"
    _write_creds_file(creds_file)

    # 2) kill any existing tunnel & start a new one
    _kill_existing_openvpn()
    _start_openvpn(cfg, creds_file)

    # 3) wait for tunnel to establish
    time.sleep(15)

    # 4) fetch new IP (now over the VPN)
    new_ip = requests.get("https://api.ipify.org", timeout=10).text.strip()
    print(f"🌐 New public IP: {new_ip}")

    # 5) log to Firestore
    db.collection("ipRotationLogs").add({
        "timestamp": firestore.SERVER_TIMESTAMP,
        "ip": new_ip,
        "configFile": cfg.name,
        "burnerId": burner_id or "",
    })

    return new_ip

