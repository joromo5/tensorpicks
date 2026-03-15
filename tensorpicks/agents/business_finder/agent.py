"""Business Finder Agent — discovers unique business ideas and posts to Slack daily."""

import json
import logging

from tensorpicks.core.agent import Agent
from tensorpicks.core import llm, slack
from tensorpicks.agents.business_finder.scraper import fetch_tweets

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a sharp business analyst who identifies unique, actionable business
opportunities. You focus on ideas that are:
- Novel or underserved (not oversaturated)
- Feasible for a small team or solo founder
- Have clear revenue potential
- Leverage current trends or technology

You are direct and concise. No fluff."""

FILTER_PROMPT = """Below are raw posts scraped from social media about business ideas and
opportunities. Analyze them and pick the single BEST, most unique and actionable business
opportunity. Ignore generic advice, motivational posts, and anything that's already mainstream.

Raw posts:
{posts}

Respond in JSON with these fields:
- "idea": a clear, one-line description of the business idea (your own words, improved)
- "why": 2-3 sentences on why this is a good opportunity right now
- "how_to_start": 2-3 concrete first steps to get started
- "source_snippet": the original post text that inspired this pick
- "market_size": your rough estimate (small/medium/large)
- "competition": your assessment (low/medium/high)
"""

SLACK_TEMPLATE = """🔍 *Daily Business Opportunity*

*{idea}*

*Why now:* {why}

*How to start:*
{how_to_start}

*Market size:* {market_size} | *Competition:* {competition}

_Source: {source_snippet}_"""


class BusinessFinderAgent(Agent):
    name = "business_finder"

    def run(self) -> None:
        self.log.info("Starting business finder scan...")

        # 1. Scrape sources
        posts = fetch_tweets()
        if not posts:
            self.log.warning("No posts found — skipping")
            slack.post("⚠️ Business Finder: No posts found today. Check data sources.")
            return

        self.log.info("Collected %d raw posts", len(posts))

        # 2. Feed to LLM for analysis
        posts_text = "\n---\n".join(p["text"] for p in posts[:50])  # cap context size
        prompt = FILTER_PROMPT.format(posts=posts_text)

        raw_response = llm.chat_json(prompt, system=SYSTEM_PROMPT)

        try:
            result = json.loads(raw_response)
        except json.JSONDecodeError:
            self.log.error("LLM returned invalid JSON: %s", raw_response[:200])
            slack.post("⚠️ Business Finder: LLM response was not valid JSON today.")
            return

        # 3. Format and post to Slack
        how_to_start = "\n".join(
            f"  • {step}" for step in result.get("how_to_start", ["N/A"])
        )
        if isinstance(result.get("how_to_start"), str):
            how_to_start = f"  • {result['how_to_start']}"

        message = SLACK_TEMPLATE.format(
            idea=result.get("idea", "Unknown"),
            why=result.get("why", "N/A"),
            how_to_start=how_to_start,
            market_size=result.get("market_size", "?"),
            competition=result.get("competition", "?"),
            source_snippet=result.get("source_snippet", "")[:200],
        )

        success = slack.post(message)
        if success:
            self.log.info("Posted daily business opportunity to Slack")
        else:
            self.log.error("Failed to post to Slack")
