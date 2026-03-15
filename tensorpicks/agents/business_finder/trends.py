"""Google Trends integration — measure search demand and momentum for business ideas.

Uses the unofficial Google Trends endpoint (no API key needed) to fetch
interest-over-time data for keywords related to business opportunities.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

# Google Trends explore endpoint (public, no auth)
_TRENDS_URL = "https://trends.google.com/trends/api/dailytrends"
_INTEREST_URL = "https://trends.google.com/trends/api/explore"

# Fallback: use the suggest endpoint for related queries
_SUGGEST_URL = "https://trends.google.com/trends/api/autocomplete"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def get_trending_searches(geo: str = "US") -> list[dict]:
    """Get today's trending searches from Google Trends.

    Returns list of dicts with title, traffic volume, and related queries.
    """
    try:
        resp = httpx.get(
            _TRENDS_URL,
            params={"hl": "en-US", "tz": "-300", "geo": geo, "ns": 15},
            headers=_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning("Google Trends daily returned %d", resp.status_code)
            return []

        # Response has a security prefix we need to strip
        text = resp.text
        if text.startswith(")]}'"):
            text = text[5:]

        import json
        data = json.loads(text)

        trends = []
        for day in data.get("default", {}).get("trendingSearchesDays", []):
            for search in day.get("trendingSearches", []):
                query = search.get("title", {}).get("query", "")
                traffic = search.get("formattedTraffic", "0")
                articles = search.get("articles", [])

                related = []
                for article in articles[:3]:
                    related.append({
                        "title": article.get("title", ""),
                        "url": article.get("url", ""),
                        "source": article.get("source", ""),
                    })

                trends.append({
                    "query": query,
                    "traffic": traffic,
                    "related_articles": related,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        log.info("Fetched %d trending searches from Google Trends", len(trends))
        return trends

    except (httpx.HTTPError, Exception) as e:
        log.error("Google Trends fetch failed: %s", e)
        return []


def get_related_queries(keyword: str) -> list[str]:
    """Get Google Trends autocomplete suggestions for a keyword.

    Useful for finding related niches and expanding keyword research.
    """
    try:
        resp = httpx.get(
            f"{_SUGGEST_URL}/{quote(keyword)}",
            params={"hl": "en-US"},
            headers=_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        text = resp.text
        if text.startswith(")]}'"):
            text = text[5:]

        import json
        data = json.loads(text)

        suggestions = []
        for topic in data.get("default", {}).get("topics", []):
            mid = topic.get("mid", "")
            title = topic.get("title", "")
            topic_type = topic.get("type", "")
            if title:
                suggestions.append(title)

        return suggestions

    except (httpx.HTTPError, Exception) as e:
        log.warning("Trends suggestions failed for '%s': %s", keyword, e)
        return []


def estimate_trend_score(keyword: str) -> dict:
    """Estimate a trend momentum score for a keyword.

    Uses related queries count and trending searches overlap as proxies.
    Returns dict with score (0-10), related queries, and whether it's trending.

    This is a lightweight approach that doesn't require pytrends.
    """
    related = get_related_queries(keyword)
    trending = get_trending_searches()

    # Check if keyword overlaps with any trending search
    is_trending = False
    keyword_lower = keyword.lower()
    for t in trending:
        if keyword_lower in t["query"].lower() or t["query"].lower() in keyword_lower:
            is_trending = True
            break

    # Score based on signals
    score = 5  # baseline
    if is_trending:
        score += 3
    if len(related) > 5:
        score += 1
    if len(related) > 10:
        score += 1

    score = min(score, 10)

    return {
        "keyword": keyword,
        "score": score,
        "is_trending": is_trending,
        "related_queries": related[:10],
        "trending_overlap": is_trending,
    }


def find_trending_opportunities(business_keywords: list[str] | None = None) -> list[dict]:
    """Cross-reference trending searches with business opportunity keywords.

    Returns opportunities where trending topics intersect with business potential.
    """
    if business_keywords is None:
        business_keywords = [
            "app", "saas", "tool", "platform", "service", "software",
            "startup", "business", "product", "ai", "automation",
        ]

    trending = get_trending_searches()
    opportunities = []

    for trend in trending:
        query = trend["query"].lower()
        for bkw in business_keywords:
            if bkw in query:
                opportunities.append({
                    "trend_query": trend["query"],
                    "traffic": trend["traffic"],
                    "business_keyword": bkw,
                    "related_articles": trend["related_articles"],
                    "signal": f"Trending '{trend['query']}' intersects with '{bkw}'",
                })
                break

    log.info("Found %d trending business opportunities", len(opportunities))
    return opportunities
