"""Scrape multiple sources for business ideas and opportunities.

Sources:
  - Twitter/X API (if key configured)
  - Hacker News (new + top stories)
  - Reddit (multiple business/startup subreddits)
  - Product Hunt (trending products)
  - IndieHackers (recent posts)
"""

import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

# Twitter API v2 search endpoint
_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

# Search queries targeting business ideas
SEARCH_QUERIES = [
    "new business idea unique opportunity -is:retweet lang:en",
    "untapped market niche business -is:retweet lang:en",
    "side hustle idea 2025 -is:retweet lang:en",
    "startup idea nobody doing -is:retweet lang:en",
    "business opportunity underrated -is:retweet lang:en",
    "micro saas idea -is:retweet lang:en",
    "passive income idea unique -is:retweet lang:en",
]

# Reddit subreddits to scrape
SUBREDDITS = [
    "business_ideas",
    "Entrepreneur",
    "SideProject",
    "startups",
    "smallbusiness",
    "microsaas",
    "passive_income",
    "juststart",
]

_HEADERS = {"User-Agent": "tensorinc/0.1 (business research bot)"}


def fetch_all_sources() -> list[dict]:
    """Fetch business ideas from all configured sources.

    Returns list of dicts with:
        id, text, source, url (optional), score (optional), timestamp
    """
    all_posts = []

    sources = {
        "twitter": _fetch_twitter,
        "hackernews": _fetch_hackernews,
        "reddit": _fetch_reddit,
        "producthunt": _fetch_producthunt,
        "indiehackers": _fetch_indiehackers,
    }

    for name, fetcher in sources.items():
        try:
            posts = fetcher()
            log.info("Source %s returned %d posts", name, len(posts))
            all_posts.extend(posts)
        except Exception as e:
            log.error("Source %s crashed: %s", name, e)

    # Deduplicate by text similarity (exact match on first 100 chars)
    seen = set()
    unique = []
    for p in all_posts:
        key = p["text"][:100].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    log.info("Total unique posts collected: %d (from %d raw)", len(unique), len(all_posts))
    return unique


# Keep the old name as an alias for backward compat with agent.py
fetch_tweets = fetch_all_sources


def _fetch_twitter(max_per_query: int = 20) -> list[dict]:
    """Fetch recent tweets matching business opportunity queries."""
    if not settings.twitter_bearer_token:
        log.info("No Twitter bearer token — skipping Twitter")
        return []

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
                    "tweet.fields": "created_at,author_id,text,public_metrics",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            tweets = data.get("data", [])

            for t in tweets:
                metrics = t.get("public_metrics", {})
                all_tweets.append({
                    "id": f"tw_{t['id']}",
                    "text": t.get("text", ""),
                    "source": "twitter",
                    "url": f"https://x.com/i/status/{t['id']}",
                    "score": (metrics.get("like_count", 0) +
                              metrics.get("retweet_count", 0) * 3 +
                              metrics.get("reply_count", 0) * 2),
                    "timestamp": t.get("created_at", ""),
                })

            log.info("Fetched %d tweets for: %s", len(tweets), query[:40])
        except httpx.HTTPError as e:
            log.error("Twitter API error: %s", e)

    return all_tweets


def _fetch_hackernews() -> list[dict]:
    """Fetch from Hacker News — top and new stories."""
    posts = []

    for endpoint in ["topstories", "newstories"]:
        try:
            resp = httpx.get(
                f"https://hacker-news.firebaseio.com/v0/{endpoint}.json",
                timeout=10,
            )
            story_ids = resp.json()[:30]

            for sid in story_ids:
                try:
                    story = httpx.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                        timeout=10,
                    ).json()
                    if story and story.get("title"):
                        posts.append({
                            "id": f"hn_{sid}",
                            "text": f"{story['title']} — {story.get('url', 'no link')}",
                            "source": "hackernews",
                            "url": story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                            "score": story.get("score", 0),
                            "timestamp": datetime.fromtimestamp(
                                story.get("time", 0), tz=timezone.utc
                            ).isoformat(),
                        })
                except httpx.HTTPError:
                    continue

            log.info("Fetched %d from HN %s", len(posts), endpoint)
        except httpx.HTTPError as e:
            log.error("Hacker News %s failed: %s", endpoint, e)

    return posts


def _fetch_reddit() -> list[dict]:
    """Fetch from multiple business-related subreddits."""
    posts = []

    for sub in SUBREDDITS:
        try:
            resp = httpx.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=25",
                headers=_HEADERS,
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            children = resp.json().get("data", {}).get("children", [])
            for p in children:
                d = p["data"]
                # Skip pinned/stickied posts
                if d.get("stickied"):
                    continue

                selftext = d.get("selftext", "")[:500]
                text = f"{d['title']}"
                if selftext:
                    text += f" — {selftext}"

                posts.append({
                    "id": f"rd_{d['id']}",
                    "text": text,
                    "source": f"reddit/r/{sub}",
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "score": d.get("score", 0),
                    "timestamp": datetime.fromtimestamp(
                        d.get("created_utc", 0), tz=timezone.utc
                    ).isoformat(),
                })

            log.info("Fetched %d from r/%s", len(children), sub)
        except httpx.HTTPError as e:
            log.error("Reddit r/%s failed: %s", sub, e)

    return posts


def _fetch_producthunt() -> list[dict]:
    """Scrape Product Hunt front page for trending products."""
    posts = []
    try:
        resp = httpx.get(
            "https://www.producthunt.com",
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return posts

        soup = BeautifulSoup(resp.text, "html.parser")

        # PH renders mostly via JS, but og/meta tags and some static HTML
        # can still give us product info. Also try the unofficial API.
        # Fallback: use their RSS-like endpoints
        resp2 = httpx.get(
            "https://www.producthunt.com/feed",
            headers=_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        if resp2.status_code == 200:
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            for item in soup2.find_all("item")[:20]:
                title = item.find("title")
                desc = item.find("description")
                link = item.find("link")
                if title:
                    text = title.get_text()
                    if desc:
                        text += f" — {desc.get_text()[:300]}"
                    posts.append({
                        "id": f"ph_{hash(text) % 10**8}",
                        "text": text,
                        "source": "producthunt",
                        "url": link.get_text() if link else "",
                        "score": 0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

        log.info("Fetched %d from Product Hunt", len(posts))
    except httpx.HTTPError as e:
        log.error("Product Hunt failed: %s", e)

    return posts


def _fetch_indiehackers() -> list[dict]:
    """Scrape IndieHackers for recent posts and milestones."""
    posts = []
    try:
        resp = httpx.get(
            "https://www.indiehackers.com",
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return posts

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract post titles and descriptions from the feed
        for article in soup.find_all("article")[:20]:
            title_tag = article.find(["h2", "h3", "a"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            desc_tag = article.find("p")
            text = title
            if desc_tag:
                text += f" — {desc_tag.get_text(strip=True)[:300]}"

            link = title_tag.get("href", "")
            if link and not link.startswith("http"):
                link = f"https://www.indiehackers.com{link}"

            posts.append({
                "id": f"ih_{hash(title) % 10**8}",
                "text": text,
                "source": "indiehackers",
                "url": link,
                "score": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        log.info("Fetched %d from IndieHackers", len(posts))
    except httpx.HTTPError as e:
        log.error("IndieHackers failed: %s", e)

    return posts
