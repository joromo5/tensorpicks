"""Scrape Twitter/X for business ideas and opportunities."""

import logging

import httpx
from bs4 import BeautifulSoup

from tensorpicks.core.config import settings

log = logging.getLogger(__name__)

# Twitter API v2 search endpoint
_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

# Search queries targeting business ideas, startup opportunities, side hustles
SEARCH_QUERIES = [
    "new business idea unique opportunity -is:retweet lang:en",
    "untapped market niche business -is:retweet lang:en",
    "side hustle idea 2025 -is:retweet lang:en",
    "startup idea nobody doing -is:retweet lang:en",
    "business opportunity underrated -is:retweet lang:en",
]


def fetch_tweets(max_per_query: int = 20) -> list[dict]:
    """Fetch recent tweets matching business opportunity queries.

    Returns a list of dicts with 'id', 'text', 'author_id', and 'created_at'.
    """
    if not settings.twitter_bearer_token:
        log.warning("No Twitter bearer token configured — using fallback sources")
        return _fallback_sources()

    headers = {"Authorization": f"Bearer {settings.twitter_bearer_token}"}
    all_tweets = []

    for query in SEARCH_QUERIES:
        try:
            resp = httpx.get(
                _SEARCH_URL,
                headers=headers,
                params={
                    "query": query,
                    "max_results": min(max_per_query, 100),
                    "tweet.fields": "created_at,author_id,text",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            tweets = data.get("data", [])
            all_tweets.extend(tweets)
            log.info("Fetched %d tweets for query: %s", len(tweets), query[:40])
        except httpx.HTTPError as e:
            log.error("Twitter API error for query '%s': %s", query[:40], e)

    # Deduplicate by tweet id
    seen = set()
    unique = []
    for t in all_tweets:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)

    return unique


def _fallback_sources() -> list[dict]:
    """Scrape free sources when no Twitter API key is available."""
    ideas = []

    # Hacker News – new stories often surface business ideas
    try:
        resp = httpx.get(
            "https://hacker-news.firebaseio.com/v0/newstories.json", timeout=10
        )
        story_ids = resp.json()[:30]
        for sid in story_ids:
            story = httpx.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10
            ).json()
            if story and story.get("title"):
                ideas.append(
                    {
                        "id": str(sid),
                        "text": f"{story['title']} — {story.get('url', 'no link')}",
                        "source": "hackernews",
                    }
                )
        log.info("Fetched %d stories from Hacker News", len(ideas))
    except httpx.HTTPError as e:
        log.error("Hacker News fetch failed: %s", e)

    # Reddit r/business_ideas
    try:
        resp = httpx.get(
            "https://www.reddit.com/r/business_ideas/new.json?limit=25",
            headers={"User-Agent": "tensorpicks/0.1"},
            timeout=10,
        )
        posts = resp.json().get("data", {}).get("children", [])
        for p in posts:
            d = p["data"]
            ideas.append(
                {
                    "id": d["id"],
                    "text": f"{d['title']} — {d.get('selftext', '')[:300]}",
                    "source": "reddit",
                }
            )
        log.info("Fetched %d posts from r/business_ideas", len(posts))
    except httpx.HTTPError as e:
        log.error("Reddit fetch failed: %s", e)

    return ideas
