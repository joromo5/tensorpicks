"""LLM-powered opportunity validation — deep dive on top-scored ideas.

Performs structured analysis: TAM/SAM/SOM estimation, competitor landscape,
moat assessment, revenue model analysis, and go-to-market strategy.
"""

import json
import logging

from tensorpicks.core import llm

log = logging.getLogger(__name__)

VALIDATION_PROMPT = """You are a thorough business analyst and startup advisor. Perform a deep
validation of this business opportunity. Be realistic and critical — most ideas have significant
weaknesses. Identify them honestly.

Business Idea:
{idea}

Category: {category}
Proposed Monetization: {monetization}

Source context:
{source_text}

Analyze and respond in JSON with these sections:

1. "tam_sam_som": {{
     "tam": "Total Addressable Market estimate with reasoning",
     "sam": "Serviceable Addressable Market estimate",
     "som": "Serviceable Obtainable Market (realistic first-year target)",
     "tam_usd": rough dollar estimate (number only)
   }}

2. "competitors": [
     {{"name": "...", "what_they_do": "...", "weakness": "how this idea could beat them"}}
   ] (list 3-5 competitors, or explain why there are none)

3. "moat": {{
     "score": 1-10,
     "type": "network effects / switching costs / brand / data / technology / none",
     "explanation": "..."
   }}

4. "revenue_model": {{
     "primary": "main revenue stream",
     "secondary": "additional revenue streams",
     "estimated_price_point": "$X/mo or $X one-time",
     "path_to_first_dollar": "concrete steps to first revenue",
     "months_to_revenue": estimated months (number)
   }}

5. "risks": [
     {{"risk": "...", "severity": "low/medium/high", "mitigation": "..."}}
   ] (list 3-5 key risks)

6. "go_to_market": {{
     "channels": ["list of best acquisition channels"],
     "first_100_customers": "how to get the first 100 customers",
     "estimated_cac": "$X estimated customer acquisition cost"
   }}

7. "verdict": {{
     "score": 1-10 overall viability,
     "recommendation": "PURSUE / EXPLORE_MORE / PASS",
     "one_line_reason": "..."
   }}

Output ONLY valid JSON. No markdown."""


def validate(opportunity: dict) -> dict | None:
    """Run deep validation on a stored opportunity.

    Args:
        opportunity: Record dict from database.py

    Returns validation dict or None on failure.
    """
    idea = opportunity.get("one_liner", "")
    category = opportunity.get("category", "Other")
    monetization = opportunity.get("monetization", "unknown")
    source_text = opportunity.get("source_text", "")

    if not idea:
        return None

    try:
        raw = llm.chat_json(VALIDATION_PROMPT.format(
            idea=idea,
            category=category,
            monetization=monetization,
            source_text=source_text,
        ))
        result = json.loads(raw)

        # Ensure verdict exists
        if "verdict" not in result:
            result["verdict"] = {
                "score": 5,
                "recommendation": "EXPLORE_MORE",
                "one_line_reason": "Validation incomplete",
            }

        # Clamp scores
        if "moat" in result:
            result["moat"]["score"] = max(1, min(10, result["moat"].get("score", 5)))
        if "verdict" in result:
            result["verdict"]["score"] = max(1, min(10, result["verdict"].get("score", 5)))

        log.info("Validated '%s': %s (score: %d)",
                 idea[:40],
                 result["verdict"]["recommendation"],
                 result["verdict"]["score"])

        return result

    except (json.JSONDecodeError, Exception) as e:
        log.error("Validation failed for '%s': %s", idea[:40], e)
        return None


def validate_top_opportunities(opportunities: list[dict], top_n: int = 3) -> list[dict]:
    """Validate the top N opportunities by composite score.

    Returns list of (opportunity, validation) tuples.
    """
    # Sort by composite score
    sorted_opps = sorted(
        opportunities,
        key=lambda o: o.get("composite_score", 0),
        reverse=True,
    )

    results = []
    for opp in sorted_opps[:top_n]:
        validation = validate(opp)
        if validation:
            results.append({
                "opportunity": opp,
                "validation": validation,
            })

    return results


def format_validation(validation: dict) -> str:
    """Format a validation result as a readable string for Slack."""
    lines = []

    verdict = validation.get("verdict", {})
    lines.append(f"*Verdict:* {verdict.get('recommendation', '?')} "
                 f"({verdict.get('score', '?')}/10)")
    lines.append(f"_{verdict.get('one_line_reason', '')}_")
    lines.append("")

    # TAM/SAM/SOM
    tam = validation.get("tam_sam_som", {})
    if tam:
        tam_usd = tam.get("tam_usd", 0)
        if isinstance(tam_usd, (int, float)) and tam_usd > 0:
            lines.append(f"*TAM:* ${tam_usd:,.0f}")
        lines.append(f"*SOM:* {tam.get('som', 'N/A')}")

    # Moat
    moat = validation.get("moat", {})
    if moat:
        lines.append(f"*Moat:* {moat.get('type', 'none')} ({moat.get('score', '?')}/10)")

    # Revenue
    rev = validation.get("revenue_model", {})
    if rev:
        lines.append(f"*Revenue:* {rev.get('primary', '?')} | "
                     f"{rev.get('estimated_price_point', '?')}")
        lines.append(f"*Time to revenue:* ~{rev.get('months_to_revenue', '?')} months")

    # Competitors
    comps = validation.get("competitors", [])
    if comps:
        lines.append(f"*Competitors:* {len(comps)} identified")
        for c in comps[:3]:
            lines.append(f"  - {c.get('name', '?')}: {c.get('weakness', '')[:60]}")

    # Top risks
    risks = validation.get("risks", [])
    if risks:
        high_risks = [r for r in risks if r.get("severity") == "high"]
        if high_risks:
            lines.append(f"*High risks:* {len(high_risks)}")
            for r in high_risks[:2]:
                lines.append(f"  :warning: {r.get('risk', '')[:80]}")

    # GTM
    gtm = validation.get("go_to_market", {})
    if gtm:
        channels = gtm.get("channels", [])
        if channels:
            lines.append(f"*GTM channels:* {', '.join(channels[:3])}")

    return "\n".join(lines)
