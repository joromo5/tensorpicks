"""Business Finder Agent — discovers, scores, validates, and tracks business opportunities.

Daily pipeline:
  1. Scrape 7+ sources for raw posts (Twitter, HN, Reddit, PH, IndieHackers)
  2. Score all ideas on 6 dimensions (market, competition, feasibility, trend, revenue, uniqueness)
  3. Validate top 3 with deep LLM analysis (TAM/SAM, competitors, moat, risks)
  4. Store everything in the opportunity database
  5. Post daily top 3 picks + weekly digest to Slack
"""

import json
import logging
from datetime import datetime, timezone

from tensorpicks.core.agent import Agent
from tensorpicks.core import llm, slack
from tensorpicks.agents.business_finder.scraper import fetch_all_sources
from tensorpicks.agents.business_finder.scorer import score_batch
from tensorpicks.agents.business_finder.database import (
    store_batch,
    mark_posted,
    get_unposted,
    get_stats,
    get_weekly_digest,
)
from tensorpicks.agents.business_finder.validator import (
    validate,
    format_validation,
)
from tensorpicks.agents.business_finder.trends import (
    get_trending_searches,
    find_trending_opportunities,
)

log = logging.getLogger(__name__)

# Slack templates
DAILY_HEADER = """:mag: *Daily Business Opportunities — {date}*
_{total_scraped} posts scraped | {total_scored} scored | Top {posted_count} below_

"""

OPPORTUNITY_MSG = """:star: *#{rank} — {one_liner}*
Score: *{score}/10* | Category: {category} | Monetization: {monetization}

*Scores:*
  Market: {market}/10 | Competition: {competition}/10 | Feasibility: {feasibility}/10
  Trend: {trend}/10 | Revenue: {revenue}/10 | Uniqueness: {uniqueness}/10

{validation_section}
_Source: {source} | Engagement: {engagement}_"""

TREND_ALERT = """:chart_with_upwards_trend: *Trending Opportunity Spotted*

*{signal}*
Traffic: {traffic}

Related:
{articles}"""

WEEKLY_DIGEST_HEADER = """:clipboard: *Weekly Business Opportunity Digest*
_Top ideas discovered this week_

"""

WEEKLY_ITEM = """*{rank}. {one_liner}* ({score}/10)
  {category} | {monetization} | Status: {status}
"""

STATS_MSG = """:bar_chart: *Opportunity Pipeline Stats*
Total discovered: {total}
Avg score: {avg_score}/10 | Best: {top_score}/10

By category: {categories}
By source: {sources}
By status: {statuses}"""


class BusinessFinderAgent(Agent):
    name = "business_finder"

    def run(self) -> None:
        self.log.info("Starting business finder scan...")

        # 1. Check for trending opportunities
        trend_opps = self._check_trends()

        # 2. Scrape all sources
        posts = fetch_all_sources()
        if not posts:
            self.log.warning("No posts found — skipping")
            slack.post(":warning: Business Finder: No posts found today. Check data sources.")
            return

        self.log.info("Collected %d raw posts", len(posts))

        # 3. Score all posts — returns top 10
        scored = score_batch(posts, top_n=10)
        if not scored:
            self.log.warning("No ideas scored above threshold")
            slack.post(":warning: Business Finder: No strong ideas found today.")
            return

        self.log.info("Scored %d ideas, top composite: %.1f",
                      len(scored), scored[0]["composite"])

        # 4. Store in database
        stored = store_batch(scored)

        # 5. Validate top 3
        top3 = get_unposted(min_score=4.0, limit=3)
        validated = []
        for opp in top3:
            v = validate(opp)
            if v:
                from tensorpicks.agents.business_finder.database import update_validation
                update_validation(opp["id"], v)
                validated.append((opp, v))

        # 6. Post daily picks
        self._post_daily(
            validated=validated,
            total_scraped=len(posts),
            total_scored=len(scored),
        )

        # 7. Post trend alerts
        for t in trend_opps[:2]:
            self._post_trend_alert(t)

        # 8. Sunday weekly digest
        if datetime.now(timezone.utc).weekday() == 6:
            self._post_weekly_digest()

        self.log.info(
            "Business finder complete — %d scraped, %d scored, %d validated",
            len(posts), len(scored), len(validated),
        )

    def _check_trends(self) -> list[dict]:
        """Check Google Trends for business-relevant trending topics."""
        try:
            opps = find_trending_opportunities()
            if opps:
                self.log.info("Found %d trending business opportunities", len(opps))
            return opps
        except Exception as e:
            self.log.warning("Trends check failed: %s", e)
            return []

    def _post_daily(self, validated: list[tuple], total_scraped: int,
                    total_scored: int) -> None:
        """Post the daily top picks to Slack."""
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

        header = DAILY_HEADER.format(
            date=date_str,
            total_scraped=total_scraped,
            total_scored=total_scored,
            posted_count=len(validated),
        )
        slack.post(header)

        for rank, (opp, validation) in enumerate(validated, 1):
            scores = opp.get("scores", {})

            # Format validation section
            validation_section = ""
            if validation:
                validation_section = format_validation(validation)

            msg = OPPORTUNITY_MSG.format(
                rank=rank,
                one_liner=opp["one_liner"],
                score=opp["composite_score"],
                category=opp["category"],
                monetization=opp["monetization"],
                market=scores.get("market_size", "?"),
                competition=scores.get("competition", "?"),
                feasibility=scores.get("feasibility", "?"),
                trend=scores.get("trend_momentum", "?"),
                revenue=scores.get("revenue_potential", "?"),
                uniqueness=scores.get("uniqueness", "?"),
                validation_section=validation_section,
                source=opp.get("source", "unknown"),
                engagement=opp.get("source_engagement", 0),
            )

            slack.post(msg)
            mark_posted(opp["id"])

    def _post_trend_alert(self, trend: dict) -> None:
        """Post a trending opportunity alert to Slack."""
        articles = trend.get("related_articles", [])
        articles_str = "\n".join(
            f"  - {a.get('title', '')} ({a.get('source', '')})"
            for a in articles[:3]
        ) or "  No related articles"

        slack.post(TREND_ALERT.format(
            signal=trend.get("signal", ""),
            traffic=trend.get("traffic", "?"),
            articles=articles_str,
        ))

    def _post_weekly_digest(self) -> None:
        """Post a weekly digest of the best opportunities."""
        digest = get_weekly_digest()
        if not digest:
            return

        msg = WEEKLY_DIGEST_HEADER
        for rank, opp in enumerate(digest, 1):
            msg += WEEKLY_ITEM.format(
                rank=rank,
                one_liner=opp["one_liner"],
                score=opp["composite_score"],
                category=opp["category"],
                monetization=opp["monetization"],
                status=opp["status"],
            )

        # Add stats
        stats = get_stats()
        cats = ", ".join(f"{k}: {v}" for k, v in list(stats["by_category"].items())[:5])
        srcs = ", ".join(f"{k}: {v}" for k, v in list(stats["by_source"].items())[:5])
        statuses = ", ".join(f"{k}: {v}" for k, v in stats["by_status"].items())

        msg += "\n" + STATS_MSG.format(
            total=stats["total"],
            avg_score=stats["avg_score"],
            top_score=stats["top_score"],
            categories=cats,
            sources=srcs,
            statuses=statuses,
        )

        slack.post(msg)
