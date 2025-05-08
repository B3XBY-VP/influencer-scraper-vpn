# scraper/deep_scraper.py
"""
Deep-scan version of the IG scraper.

 ▸ Rotates IP             (Surfshark OpenVPN – UK only)
 ▸ Fetches up-to 100 posts (DEEP_POST_LIMIT)
 ▸ Optionally grabs recent comments for sentiment analysis
 ▸ Delegates the heavy parsing + AI calls to instagram_scraper.scrape()
"""

import asyncio
from typing import Dict

from vpn.rotate_ip import rotate_ip           # your helper, returns {"ip", "log_id"}
from bot.burner_login import get_available_burner
from scraper.instagram_scraper import scrape  # the function we just rewrote 🙂
from config import DEEP_POST_LIMIT


async def deep_scrape(handle: str) -> Dict:
    """
    Deep-scan up to DEEP_POST_LIMIT posts *after* rotating VPN IP
    and selecting a fresh burner session.

    Raises RuntimeError if no burner or rotation fails.
    """
    # 1) Rotate Surfshark IP (UK pool)  -----------------------------
    new_ip = await rotate_ip(region="uk")
    if not new_ip:
        raise RuntimeError("VPN rotation failed – deep scan aborted")

    # 2) Pick the least-recently-used *active* burner  --------------
    burner = await get_available_burner()
    if not burner:
        raise RuntimeError("No active burner sessions available")

    # 3) Run the high-volume scrape   -------------------------------
    data = await scrape(
        handle,
        session_cookie=burner["cookie"],
        post_limit=DEEP_POST_LIMIT,      # ⇐ key difference vs. default scrape
        fetch_comments=True,             # turn ON comment download
    )

    # ⤴ Your scrape() already:
    #   ▸ calculates engagement + follower/like ratio
    #   ▸ extracts hashtags / brand mentions
    #   ▸ calls OpenAI for contentType / tone / suggestedTags
    #   ▸ builds engagementQuality + commentSentiment
    #   so we simply return its dict ↓
    return {
        **data,
        "_meta": {
            "ip": new_ip,
            "burnerId": burner["id"],
            "postCount": DEEP_POST_LIMIT,
        },
    }


# -------------------------------------------------------------------------
# CLI sanity-check   >  python -m scraper.deep_scraper instagram           

if __name__ == "__main__":
    import sys, json, os, asyncio

    handle = sys.argv[1] if len(sys.argv) > 1 else "instagram"
    result = asyncio.run(deep_scrape(handle))
    print(json.dumps(result, indent=2))
