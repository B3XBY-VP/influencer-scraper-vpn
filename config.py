"""
config.py  ·  Minimal settings for the stand-alone VPN-scraper service
----------------------------------------------------------------------
• No Firebase / Firestore
• Reads everything from environment variables
"""

from __future__ import annotations
import os
from pathlib import Path

# ─────────────────── Server settings ───────────────────
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# ─────────────────── Scraper behaviour ─────────────────
DEFAULT_POST_LIMIT: int = int(os.getenv("DEFAULT_POST_LIMIT", "20"))
DEEP_POST_LIMIT:    int = int(os.getenv("DEEP_POST_LIMIT",    "100"))
HEADLESS:           bool = os.getenv("HEADLESS", "true").lower() == "true"
IG_REQUEST_TIMEOUT: int  = int(os.getenv("IG_REQUEST_TIMEOUT", "30"))

# ─────────────────── Optional OpenAI  ──────────────────
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL:   str        = os.getenv("OPENAI_MODEL", "gpt-4o")
AI_TIMEOUT:     float      = float(os.getenv("AI_TIMEOUT", "30"))

# ─────────────────── Deep-scan password  ───────────────
DEEP_SCAN_PASSWORD: str = os.getenv("DEEP_SCAN_PASSWORD", "")

# ─────────────────── Surfshark / VPN paths ─────────────
BASE_DIR = Path(__file__).resolve().parent
VPN_CONFIG_DIR: Path = Path(
    os.getenv("VPN_CONFIG_DIR", BASE_DIR / "vpn" / "configs" / "uk")
).resolve()
SURFSHARK_USER: str = os.getenv("SURFSHARK_USER", "")
SURFSHARK_PASS: str = os.getenv("SURFSHARK_PASS", "")

# ─────────────────── Firestore placeholder  ────────────
# rotate_ip.py imports `db` for the Fly version; here we stub it.
db = None

# ─────────────────── Sanity check  ─────────────────────
if __name__ == "__main__":
    print("Scraper-VPN config loaded:")
    for k, v in globals().items():
        if k.isupper():
            print(f"  {k:<18} = {v}")
