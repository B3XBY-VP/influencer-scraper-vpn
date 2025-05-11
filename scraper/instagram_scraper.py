# scraper/instagram_scraper.py   (Playwright + stealth + UA rotation)
import asyncio, json, math, random, re, statistics, time
from typing import List, Dict, Optional

import httpx
from playwright.async_api import async_playwright
from openai import AsyncOpenAI

from config import (
    DEFAULT_POST_LIMIT,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    AI_TIMEOUT,
    HEADLESS,
    IG_REQUEST_TIMEOUT,
)

# ─── Anti-bot helpers ────────────────────────────────────────────────────────
_MOBILE_UAS = [
    # Recent Chrome/Android & Safari/iOS strings (rotated each session)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
]

def _random_viewport() -> Dict[str, int]:
    """Return a plausible mobile viewport (width, height)."""
    width  = random.randint(360, 428)
    height = random.randint(640, 960)
    return {"width": width, "height": height}

def _human_delay(mean: float = 4.0, jitter: float = 2.0):
    """Sleep for N seconds with ±jitter randomness."""
    time.sleep(max(0.5, random.gauss(mean, jitter)))

# ─── Regex helpers (unchanged) ───────────────────────────────────────────────
HASHTAG_RE   = re.compile(r"#(\w+)")
MENTION_RE   = re.compile(r"@(\w+)")
EMOJI_ONLY   = re.compile(r"^(?:\s*[\U00010000-\U0010ffff]+\s*)+$", flags=re.UNICODE)
QUERY_HASH   = "472f257a40c653c64c666ce877d59d2b"      # IG web query

# ─── OpenAI client (optional) ────────────────────────────────────────────────
CLIENT: Optional[AsyncOpenAI] = None
if OPENAI_API_KEY:
    CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ─── AI classification helper (unchanged except CLIENT None-check) ──────────
async def classify_ai(samples: List[str]) -> Dict[str, str]:
    if not CLIENT:
        return {"contentType": "", "tone": "", "suggestedTags": []}

    prompt = (
        "You are an influencer-intelligence assistant. "
        "Given these Instagram post captions, return JSON with keys:\n"
        "content_type, tone, suggested_tags.\n\n"
        f"CAPTIONS:\n{json.dumps(samples[:5], ensure_ascii=False)}"
    )
    try:
        resp = await CLIENT.chat.completions.create(
            model=OPENAI_MODEL,
            timeout=AI_TIMEOUT,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(resp.choices[0].message.content)
        return {
            "contentType": data.get("content_type", ""),
            "tone": data.get("tone", ""),
            "suggestedTags": [t.strip() for t in data.get("suggested_tags", "").split(",") if t.strip()],
        }
    except Exception as e:
        print("AI classification failed:", e)
        return {"contentType": "", "tone": "", "suggestedTags": []}

# ─── Main scrape() ───────────────────────────────────────────────────────────
async def scrape(
    handle: str,
    *,
    session_cookie: str | None = None,
    post_limit: int = DEFAULT_POST_LIMIT,
    fetch_comments: bool = False,
) -> Dict:
    """Scrape up to `post_limit` posts from @handle and return metrics dict."""
    ua = random.choice(_MOBILE_UAS)
    viewport = _random_viewport()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)       # headful optional
        context = await browser.new_context(
            user_agent=ua,
            viewport=viewport,
            locale="en-GB",
        )

        # ▸ stealth: remove navigator.webdriver
        await context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        if session_cookie:
            await context.add_cookies(
                [
                    {
                        "name": "sessionid",
                        "value": session_cookie,
                        "domain": ".instagram.com",
                        "path": "/",
                    }
                ]
            )

        page = await context.new_page()
        await page.goto(f"https://www.instagram.com/{handle}/", timeout=60000)
        _human_delay()                                            # natural pause

        shared = await page.evaluate("() => window._sharedData?.entry_data?.ProfilePage?.[0]")
        if not shared:
            raise RuntimeError("Profile JSON missing – login or IP flagged.")
        user = shared["graphql"]["user"]
        user_id       = user["id"]
        follower_cnt  = user["edge_followed_by"]["count"]

        variables = {"id": user_id, "first": post_limit}
        url = (
            f"https://www.instagram.com/graphql/query/"
            f"?query_hash={QUERY_HASH}&variables={json.dumps(variables)}"
        )
        # graceful 429 retry loop
        backoff = 1
        for attempt in range(5):
            res = await page.evaluate("""async u => {
                const r = await fetch(u, {credentials:'include'});
                return {status: r.status, text: await r.text()}
            }""", url)
            if res["status"] == 429:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            posts_json = json.loads(res["text"])
            break
        else:
            raise RuntimeError("Repeated 429s from IG – aborting")

        edges = posts_json["data"]["user"]["edge_owner_to_timeline_media"]["edges"]

        like_counts, comment_counts, all_captions, posts = [], [], [], []
        comment_texts, commenter_ids = [], []

        for edge in edges:
            node = edge["node"]
            caption_text = (
                node["edge_media_to_caption"]["edges"][0]["node"]["text"]
                if node["edge_media_to_caption"]["edges"] else ""
            )
            like_count    = node["edge_liked_by"]["count"]
            comment_count = node["edge_media_to_comment"]["count"]
            post_type     = "Reel" if node.get("is_video") else "Grid"

            like_counts.append(like_count)
            comment_counts.append(comment_count)
            all_captions.append(caption_text)

            posts.append(
                {
                    "thumbnail": node["thumbnail_src"],
                    "caption": caption_text,
                    "timestamp": node["taken_at_timestamp"],
                    "hashtags": _extract_hashtags(caption_text),
                    "brandMentions": _extract_brand_mentions(caption_text),
                    "postType": post_type,
                    "likeCount": like_count,
                    "commentCount": comment_count,
                }
            )

            if fetch_comments and comment_count:
                pass  # placeholder for comment-scrape routine

        await browser.close()

    engagement     = (sum(like_counts) + sum(comment_counts)) / follower_cnt if follower_cnt else 0
    engagement_pct = round(engagement * 100, 2)
    follower_like_ratio = statistics.mean(like_counts) / follower_cnt if follower_cnt else 0

    ai_meta = await classify_ai(all_captions)

    return {
        "followers": follower_cnt,
        "recentPosts": posts,
        "engagementRate": engagement_pct,
        "followerLikeRatio": round(follower_like_ratio, 3),
        **ai_meta,
        # default comment / engagement-quality metrics left blank
        "commentSentiment": {"positive": 0, "neutral": 0, "negative": 0},
        "engagementQuality": {"emojiPct": 0, "uniquePct": 0},
    }

# CLI test (unchanged) --------------------------------------------------------
if __name__ == "__main__":
    import sys, json, os
    h = sys.argv[1] if len(sys.argv) > 1 else "instagram"
    cookie = os.getenv("IG_SESSIONID", "")
    print(json.dumps(asyncio.run(scrape(h, session_cookie=cookie)), indent=2))

