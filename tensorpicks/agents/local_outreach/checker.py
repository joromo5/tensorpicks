"""Check if a business has no website or a low-quality one."""

import logging

import httpx
from bs4 import BeautifulSoup

from tensorpicks.core import llm

log = logging.getLogger(__name__)


def check_website(url: str | None) -> dict:
    """Analyze a business website and return a quality assessment.

    Returns:
        {
            "has_website": bool,
            "status": "none" | "broken" | "poor" | "ok",
            "issues": [str],
            "score": int (0-100),
        }
    """
    if not url:
        return {"has_website": False, "status": "none", "issues": ["No website"], "score": 0}

    # Try to fetch the site
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
    except httpx.HTTPError:
        return {
            "has_website": True,
            "status": "broken",
            "issues": ["Website is unreachable or broken"],
            "score": 5,
        }

    if resp.status_code >= 400:
        return {
            "has_website": True,
            "status": "broken",
            "issues": [f"Website returns HTTP {resp.status_code}"],
            "score": 5,
        }

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    issues = []

    # Check for basic quality signals
    if not soup.find("meta", attrs={"name": "viewport"}):
        issues.append("Not mobile-responsive")

    if not soup.find("meta", attrs={"name": "description"}):
        issues.append("Missing meta description (bad for SEO)")

    if not soup.title or not soup.title.string or len(soup.title.string.strip()) < 5:
        issues.append("Missing or generic page title")

    # Check if it's just a parked domain or placeholder
    text_content = soup.get_text(strip=True)
    if len(text_content) < 200:
        issues.append("Very little content — likely a placeholder page")

    if not soup.find_all("img"):
        issues.append("No images on the page")

    # Check for HTTPS
    if not url.startswith("https"):
        issues.append("Not using HTTPS")

    # Score it
    score = 100 - (len(issues) * 15)
    score = max(score, 10)

    status = "ok" if score >= 70 else "poor"

    return {
        "has_website": True,
        "status": status,
        "issues": issues,
        "score": score,
    }


def is_prospect(website_check: dict) -> bool:
    """Return True if this business is a good outreach prospect."""
    return website_check["status"] in ("none", "broken", "poor")
