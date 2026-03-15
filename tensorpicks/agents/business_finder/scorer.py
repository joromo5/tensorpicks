"""Multi-factor scoring engine for business opportunities.

Scores each idea on 6 dimensions (0-10 each) and produces a composite score.
Uses a mix of heuristics (engagement signals, keyword analysis) and LLM evaluation.
"""

import json
import logging
import re

from tensorpicks.core import llm

log = logging.getLogger(__name__)

# Weights for composite score (must sum to 1.0)
WEIGHTS = {
    "market_size": 0.20,
    "competition": 0.15,
    "feasibility": 0.20,
    "trend_momentum": 0.15,
    "revenue_potential": 0.20,
    "uniqueness": 0.10,
}

# Keywords that signal different market characteristics
LARGE_MARKET_KEYWORDS = [
    "saas", "ai", "health", "fintech", "ecommerce", "education", "real estate",
    "b2b", "enterprise", "marketplace", "platform", "subscription",
]
SMALL_NICHE_KEYWORDS = [
    "local", "niche", "micro", "boutique", "handmade", "artisan", "custom",
]
HIGH_COMPETITION_KEYWORDS = [
    "dropshipping", "print on demand", "amazon fba", "social media agency",
    "web design", "seo agency", "coaching",
]
LOW_COMPETITION_KEYWORDS = [
    "untapped", "nobody", "underserved", "gap in the market", "underrated",
    "no one", "first to", "blue ocean",
]
TREND_KEYWORDS = [
    "ai", "gpt", "llm", "automation", "remote", "creator economy",
    "no-code", "web3", "climate", "sustainability", "tiktok",
]

LLM_SCORE_PROMPT = """Score this business idea on 6 dimensions from 0-10.
Be realistic and critical — most ideas should NOT score above 7.

Business idea:
{idea}

Source context:
{context}

Score each dimension:
1. market_size: How large is the addressable market? (0=tiny, 10=massive)
2. competition: How low is the competition? (0=extremely crowded, 10=wide open)
3. feasibility: How easy to start for a solo founder? (0=needs huge investment, 10=start today for free)
4. trend_momentum: Is this riding a growing trend? (0=declining, 10=exploding)
5. revenue_potential: How strong is the path to revenue? (0=hard to monetize, 10=obvious high margin)
6. uniqueness: How novel/differentiated is this? (0=been done 1000x, 10=truly new)

Also provide:
- one_liner: A punchy one-line description of the idea (your own improved wording)
- category: One of: SaaS, Marketplace, Agency, Content, Physical Product, Digital Product, Service, Community, Tool, Other
- monetization: Primary monetization strategy (subscription, one-time, ads, affiliate, service fee, etc.)

Output ONLY valid JSON. No markdown.
{{"market_size": 7, "competition": 6, "feasibility": 8, "trend_momentum": 7, "revenue_potential": 7, "uniqueness": 5, "one_liner": "...", "category": "...", "monetization": "..."}}"""


def score_idea(post: dict) -> dict | None:
    """Score a single business idea post.

    Args:
        post: Dict with at least 'text' and optionally 'source', 'score', 'url'

    Returns scored dict or None on failure.
    """
    text = post.get("text", "")
    if not text or len(text) < 20:
        return None

    # 1. Heuristic pre-scoring (fast, no LLM)
    heuristic = _heuristic_score(post)

    # 2. LLM deep scoring
    llm_scores = _llm_score(post)

    if not llm_scores:
        # Fall back to heuristic only
        return {
            "post": post,
            "scores": heuristic,
            "composite": _composite(heuristic),
            "one_liner": text[:100],
            "category": "Other",
            "monetization": "unknown",
            "source_method": "heuristic",
        }

    # 3. Blend heuristic + LLM (70% LLM, 30% heuristic)
    blended = {}
    for dim in WEIGHTS:
        h = heuristic.get(dim, 5)
        l = llm_scores.get(dim, 5)
        blended[dim] = round(l * 0.7 + h * 0.3, 1)

    return {
        "post": post,
        "scores": blended,
        "composite": _composite(blended),
        "one_liner": llm_scores.get("one_liner", text[:100]),
        "category": llm_scores.get("category", "Other"),
        "monetization": llm_scores.get("monetization", "unknown"),
        "source_method": "blended",
    }


def score_batch(posts: list[dict], top_n: int = 10) -> list[dict]:
    """Score a batch of posts and return top N by composite score.

    First does a quick heuristic pass to filter to top candidates,
    then runs LLM scoring only on the best ones (to save API calls).
    """
    # Quick heuristic pass on everything
    heuristic_scored = []
    for post in posts:
        h = _heuristic_score(post)
        comp = _composite(h)
        heuristic_scored.append((post, h, comp))

    # Sort by heuristic composite and take top candidates for LLM scoring
    heuristic_scored.sort(key=lambda x: x[2], reverse=True)
    candidates = heuristic_scored[:top_n * 2]  # 2x for buffer

    log.info("Heuristic pass: %d posts → %d candidates for LLM scoring",
             len(posts), len(candidates))

    # Full scoring on candidates
    results = []
    for post, _, _ in candidates:
        scored = score_idea(post)
        if scored:
            results.append(scored)

    # Sort by composite and return top N
    results.sort(key=lambda x: x["composite"], reverse=True)
    return results[:top_n]


def _composite(scores: dict) -> float:
    """Compute weighted composite score (0-10)."""
    total = sum(scores.get(dim, 0) * weight for dim, weight in WEIGHTS.items())
    return round(total, 2)


def _heuristic_score(post: dict) -> dict:
    """Quick heuristic scoring based on keywords and engagement."""
    text = post.get("text", "").lower()
    engagement = post.get("score", 0)

    # Market size
    market = 5
    if any(kw in text for kw in LARGE_MARKET_KEYWORDS):
        market = 7
    if any(kw in text for kw in SMALL_NICHE_KEYWORDS):
        market = 4

    # Competition
    competition = 5
    if any(kw in text for kw in LOW_COMPETITION_KEYWORDS):
        competition = 7
    if any(kw in text for kw in HIGH_COMPETITION_KEYWORDS):
        competition = 3

    # Feasibility — longer, more detailed posts suggest more thought-out ideas
    feasibility = 5
    word_count = len(text.split())
    if word_count > 100:
        feasibility = 7
    elif word_count < 30:
        feasibility = 4

    # Trend momentum
    trend = 5
    trend_hits = sum(1 for kw in TREND_KEYWORDS if kw in text)
    trend = min(5 + trend_hits, 9)

    # Revenue potential
    revenue = 5
    revenue_signals = ["revenue", "profit", "monetiz", "customers", "paying",
                       "mrr", "arr", "subscription", "charge", "$"]
    rev_hits = sum(1 for kw in revenue_signals if kw in text)
    revenue = min(5 + rev_hits, 9)

    # Uniqueness — engagement is a proxy (viral = novel)
    uniqueness = 5
    if engagement > 100:
        uniqueness = 7
    elif engagement > 500:
        uniqueness = 8

    return {
        "market_size": market,
        "competition": competition,
        "feasibility": feasibility,
        "trend_momentum": trend,
        "revenue_potential": revenue,
        "uniqueness": uniqueness,
    }


def _llm_score(post: dict) -> dict | None:
    """LLM-based deep scoring of a business idea."""
    text = post.get("text", "")
    context = f"Source: {post.get('source', 'unknown')} | Engagement: {post.get('score', 0)}"

    try:
        raw = llm.chat_json(LLM_SCORE_PROMPT.format(idea=text, context=context))
        result = json.loads(raw)

        # Validate all required fields are present and numeric
        for dim in WEIGHTS:
            if dim not in result or not isinstance(result[dim], (int, float)):
                result[dim] = 5
            result[dim] = max(0, min(10, result[dim]))

        return result
    except (json.JSONDecodeError, Exception) as e:
        log.warning("LLM scoring failed: %s", e)
        return None
