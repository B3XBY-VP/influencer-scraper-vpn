# scraper/deep_scraper.py
"""
Deep-scan: rotate IP, pick a burner session, scrape DEEP_POST_LIMIT posts.
"""

import asyncio, time
from typing import Dict

from vpn.rotate_ip import rotate_ip
from bot.burner_login import get_available_burner
from scraper.instagram_scraper import scrape
from config import DEEP_POST_LIMIT

# cache last IP rotation to avoid thrashing VPN
_LAST_ROTATE_TS = 0
_ROTATE_INTERVAL = 300  # 5 min

async def deep_scrape(handle: str) -> Dict:
    global _LAST_ROTATE_TS
    now = time.time()
    if now - _LAST_ROTATE_TS > _ROTATE_INTERVAL:
        new_ip = await rotate_ip(region="uk")
        if not new_ip:
            raise RuntimeError("VPN rotation failed – deep scan aborted")
        _LAST_ROTATE_TS = now
    else:
        new_ip = "unchanged"

    burner = await get_available_burner()
    if not burner:
        raise RuntimeError("No active burner sessions available")

    data = await scrape(
        handle,
        session_cookie=burner["cookie"],
        post_limit=DEEP_POST_LIMIT,
        fetch_comments=True,
    )

    return {
        **data,
        "_meta": {
            "ip": new_ip,
            "burnerId": burner["id"],
            "postCount": DEEP_POST_LIMIT,
        },
    }

if __name__ == "__main__":
    import sys, json
    h = sys.argv[1] if len(sys.argv) > 1 else "instagram"
    print(json.dumps(asyncio.run(deep_scrape(h)), indent=2))

