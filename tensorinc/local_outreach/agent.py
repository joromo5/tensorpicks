"""Local Outreach Agent — finds businesses with no/bad websites and drafts outreach emails."""

import json
import logging

from tensorinc.core.agent import Agent
from tensorinc.core import llm, slack
from tensorinc.core.config import settings
from tensorinc.local_outreach.scraper import search_businesses, get_business_details
from tensorinc.local_outreach.checker import check_website, is_prospect
from tensorinc.local_outreach.emailer import draft_email, send_email

log = logging.getLogger(__name__)

SLACK_PROSPECT_TEMPLATE = """📧 *Local Outreach — New Prospect Found*

*{name}*
📍 {address}
🏷️ {business_type}
⭐ {rating} ({total_ratings} reviews)

*Website status:* {status}
*Issues:* {issues}

*Draft email subject:* {subject}
*Draft email body:*
```
{body}
```

_Reply with ✅ to approve sending, or ❌ to skip._"""

SLACK_SUMMARY_TEMPLATE = """📊 *Local Outreach — Daily Summary*

Scanned *{total}* businesses in *{location}*
Found *{prospects}* prospects (no website or poor quality)
Drafted *{drafted}* outreach emails

{details}"""


class LocalOutreachAgent(Agent):
    name = "local_outreach"

    def run(self) -> None:
        self.log.info("Starting local outreach scan...")
        auto_send = settings.outreach_auto_send

        # 1. Find local businesses
        businesses = search_businesses()
        if not businesses:
            self.log.warning("No businesses found")
            slack.post("⚠️ Local Outreach: No businesses found. Check location/API config.")
            return

        self.log.info("Found %d businesses to evaluate", len(businesses))

        prospects = []
        drafted = []

        # 2. Check each business's website
        for biz in businesses:
            details = get_business_details(biz["place_id"])
            website_url = details.get("website")
            biz["website"] = website_url
            biz["phone"] = details.get("formatted_phone_number")
            biz["full_address"] = details.get("formatted_address", biz["address"])

            check = check_website(website_url)

            if not is_prospect(check):
                continue

            prospects.append((biz, check))
            self.log.info("Prospect found: %s (%s)", biz["name"], check["status"])

            # 3. Draft a personalized email
            email = draft_email(biz, check)
            drafted.append((biz, check, email))

            # 4. Post to Slack for review
            business_type = biz.get("types", ["business"])[0].replace("_", " ")
            issues_str = ", ".join(check.get("issues", []))

            slack.post(SLACK_PROSPECT_TEMPLATE.format(
                name=biz["name"],
                address=biz.get("full_address", biz["address"]),
                business_type=business_type,
                rating=biz.get("rating", "N/A"),
                total_ratings=biz.get("total_ratings", 0),
                status=check["status"],
                issues=issues_str,
                subject=email["subject"],
                body=email["body"],
            ))

            # 5. Auto-send if configured (otherwise just drafts to Slack)
            if auto_send and biz.get("phone"):
                # We don't have their email from Google Maps — log this limitation
                self.log.info(
                    "Auto-send enabled but no email for %s (phone: %s)",
                    biz["name"], biz["phone"],
                )

        # 6. Post daily summary
        detail_lines = []
        for biz, check, email in drafted:
            detail_lines.append(f"  • {biz['name']} — {check['status']}")

        slack.post(SLACK_SUMMARY_TEMPLATE.format(
            total=len(businesses),
            location=settings.outreach_location,
            prospects=len(prospects),
            drafted=len(drafted),
            details="\n".join(detail_lines) if detail_lines else "No prospects today.",
        ))

        self.log.info(
            "Local outreach complete: %d scanned, %d prospects, %d drafted",
            len(businesses), len(prospects), len(drafted),
        )
