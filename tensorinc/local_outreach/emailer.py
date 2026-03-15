"""Draft and send outreach emails via Gmail SMTP."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from tensorinc.core.config import settings
from tensorinc.core import llm

log = logging.getLogger(__name__)

DRAFT_PROMPT = """You are writing a short, friendly cold email to a local business owner.
You are offering web design / website improvement services.

Business info:
- Name: {name}
- Address: {address}
- Type: {business_type}
- Current website issues: {issues}

Rules:
- Keep it under 150 words
- Be genuine and specific — mention their business by name and location
- Point out a specific issue with their current site (or lack of one) without being insulting
- Offer a free mockup or consultation as a hook
- Include a clear call to action
- Sound like a real person, not a template
- Sign off with the sender name provided

Sender name: {sender_name}
Sender business: {sender_business}

Write ONLY the email body, no subject line."""

SUBJECT_PROMPT = """Write a short, non-spammy email subject line for a cold outreach email
to {name}, a {business_type} in {address}. You're offering to improve their website.
Keep it under 8 words. Be specific to their business. Output ONLY the subject line."""


def draft_email(business: dict, website_check: dict) -> dict:
    """Use the LLM to draft a personalized outreach email.

    Returns: {"to_name": str, "subject": str, "body": str}
    """
    issues_str = ", ".join(website_check.get("issues", ["no website"]))
    business_type = business.get("types", ["business"])[0].replace("_", " ")

    body = llm.chat(
        DRAFT_PROMPT.format(
            name=business["name"],
            address=business.get("address", "your area"),
            business_type=business_type,
            issues=issues_str,
            sender_name=settings.outreach_sender_name,
            sender_business=settings.outreach_sender_business,
        )
    )

    subject = llm.chat(
        SUBJECT_PROMPT.format(
            name=business["name"],
            business_type=business_type,
            address=business.get("address", ""),
        )
    ).strip().strip('"')

    return {
        "to_name": business["name"],
        "subject": subject,
        "body": body,
    }


def send_email(to_address: str, subject: str, body: str) -> bool:
    """Send an email via Gmail SMTP. Returns True on success."""
    if not settings.gmail_address or not settings.gmail_app_password:
        log.error("Gmail credentials not configured")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"{settings.outreach_sender_name} <{settings.gmail_address}>"
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.gmail_address, settings.gmail_app_password)
            server.send_message(msg)
        log.info("Email sent to %s", to_address)
        return True
    except Exception as e:
        log.error("Failed to send email to %s: %s", to_address, e)
        return False
