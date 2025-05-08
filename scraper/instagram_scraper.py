#scraper/instagram_scraper.py
import asyncio, json, re, statistics, time, httpx
from typing import List, Dict

from playwright.async_api import async_playwright
from openai import AsyncOpenAI
from config import (
    DEFAULT_POST_LIMIT,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    AI_TIMEOUT,
)

CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)


HASHTAG_RE   = re.compile(r"#(\w+)")
MENTION_RE   = re.compile(r"@(\w+)")
EMOJI_ONLY   = re.compile(r"^(?:\s*[\U00010000-\U0010ffff]+\s*)+$", flags=re.UNICODE)
QUERY_HASH   = "472f257a40c653c64c666ce877d59d2b"  # IG web “posts” query


# ---------- helpers ----------------------------------------------------------
def _extract_hashtags(text: str) -> List[str]:
    return [m.lower() for m in HASHTAG_RE.findall(text or "")]


def _extract_brand_mentions(text: str) -> List[str]:
    return [
        m.lower()
        for m in MENTION_RE.findall(text or "")
        if m.lower() not in ("instagram",)  # ignore generic @… mentions
    ]


def _emoji_only_pct(comments: List[str]) -> float:
    if not comments:
        return 0.0
    emoji_comments = sum(1 for c in comments if EMOJI_ONLY.match(c))
    return emoji_comments / len(comments)


def _unique_commenter_pct(owners: List[str]) -> float:
    if not owners:
        return 0.0
    return len(set(owners)) / len(owners)


async def classify_ai(samples: List[str]) -> Dict[str, str]:
    """Ask GPT to guess content type, tone and give suggested tags (comma-sep)."""
    prompt = (
        "You are an influencer-intelligence assistant. "
        "Given these Instagram post captions, return JSON with keys:\n"
        "content_type (e.g. DIY, Parenting, Beauty, Fitness, HomeDecor),\n"
        "tone (e.g. Aesthetic, Funny, Helpful, Inspirational) and\n"
        "suggested_tags (comma-separated, 1-3 short phrases like Mumfluencer).\n\n"
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
        # fall back silently – don't break the whole scrape
        print("AI classification failed:", e)
        return {"contentType": "", "tone": "", "suggestedTags": []}


# ---------- main scrape ------------------------------------------------------
async def scrape(handle: str, session_cookie: str | None = None) -> Dict:
    """
    Scrape the latest DEFAULT_POST_LIMIT posts from an Instagram handle.

    Returns a dict ready to upsert into Firestore.
    """
    async with async_playwright() as p:
        browser  = await p.chromium.launch(headless=True)
        context  = await browser.new_context()
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

        # Pull user id & follower count from window._sharedData
        shared = await page.evaluate("() => window._sharedData?.entry_data?.ProfilePage?.[0]")
        if not shared:
            raise RuntimeError("Failed to load profile JSON – login probably blocked.")
        user = shared["graphql"]["user"]
        user_id       = user["id"]
        follower_cnt  = user["edge_followed_by"]["count"]

        # Query posts JSON
        variables = {
            "id": user_id,
            "first": DEFAULT_POST_LIMIT,
        }
        url = f"https://www.instagram.com/graphql/query/?query_hash={QUERY_HASH}&variables={json.dumps(variables)}"
        posts_json = await page.evaluate(
            """async (u) => (await fetch(u)).json()""", url
        )
        edges = posts_json["data"]["user"]["edge_owner_to_timeline_media"]["edges"]

        posts = []
        like_counts, comment_counts, all_captions = [], [], []
        comment_texts, commenter_ids = [], []

        for edge in edges:
            node = edge["node"]
            caption_text = (
                node["edge_media_to_caption"]["edges"][0]["node"]["text"]
                if node["edge_media_to_caption"]["edges"]
                else ""
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

            # --- OPTIONAL: pull first N comments for quality metrics ---------
            # If comment_count > 0:
            #   fetch /comments/ with another graphql query
            #   append to comment_texts / commenter_ids
            # To keep the default scrape fast we skip this.

        await browser.close()

    # ---------- derived metrics ---------------------------------------------
    total_likes    = sum(like_counts)
    total_comments = sum(comment_counts)
    engagement     = (total_likes + total_comments) / follower_cnt if follower_cnt else 0
    engagement_pct = round(engagement * 100, 2)

    follower_like_ratio = (
        statistics.mean(like_counts) / follower_cnt if follower_cnt else 0
    )

    # We didn’t fetch comments above – set 0 for default scrape
    comment_sentiment = {"positive": 0, "neutral": 0, "negative": 0}
    engagement_quality = {"emojiPct": 0, "uniquePct": 0}

    # ---------- AI classification -------------------------------------------
    ai_meta = await classify_ai(all_captions)

    # ---------- build response ---------------------------------------------
    return {
        "followers": follower_cnt,
        "recentPosts": posts,
        "engagementRate": engagement_pct,
        "followerLikeRatio": round(follower_like_ratio, 3),
        "commentSentiment": comment_sentiment,
        "engagementQuality": engagement_quality,
        **ai_meta,  # merges contentType, tone, suggestedTags
    }


# quick CLI test --------------------------------------------------------------
if __name__ == "__main__":  #  > python scraper/instagram_scraper.py jackcreates
    import sys, asyncio, os

    h = sys.argv[1]
    cookie = os.getenv("IG_SESSIONID", "")
    result = asyncio.run(scrape(h, cookie))
    print(json.dumps(result, indent=2))
