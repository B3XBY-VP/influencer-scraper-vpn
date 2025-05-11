# bot/burner_login.py
"""
Stubbed burner-account helpers for the VPN scraper.
If you add a real Firestore-backed burner pool later, replace these.
"""

import asyncio
import random
from typing import Optional, Dict

# A hard-coded “dummy” burner session (replace with real ones)
_DUMMY_BURNERS = [
    {
        "id": "stub-1",
        "cookie": "",          # leave empty → scrape() runs as guest
        "status": "active",
    }
]

async def get_available_burner() -> Optional[Dict]:
    """Return the next active burner or None."""
    active = [b for b in _DUMMY_BURNERS if b["status"] == "active"]
    return random.choice(active) if active else None

async def login_and_store(*args, **kwargs):  # no-op
    return None

def refresh_session_sync(*args, **kwargs):   # no-op alias
    return None
