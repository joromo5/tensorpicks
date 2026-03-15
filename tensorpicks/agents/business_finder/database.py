"""Opportunity database — persist, query, and manage discovered business ideas.

Stores all scored opportunities in a JSON file with status tracking.
Supports the full pipeline: discovered → scored → posted → archived.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
DB_FILE = DATA_DIR / "opportunities.json"


def _load() -> list[dict]:
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return []


def _save(records: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_FILE.write_text(json.dumps(records, indent=2, default=str))


def store_opportunity(scored: dict) -> dict:
    """Store a scored opportunity in the database.

    Args:
        scored: Dict from scorer.py (has post, scores, composite, one_liner, etc.)

    Returns the stored record with an ID and metadata.
    """
    records = _load()

    # Check for duplicate (same one_liner or same source post)
    one_liner = scored.get("one_liner", "")
    source_text = scored.get("post", {}).get("text", "")[:100]
    for existing in records:
        if (existing.get("one_liner", "").lower() == one_liner.lower() or
                existing.get("source_text", "")[:100].lower() == source_text.lower()):
            log.debug("Duplicate opportunity skipped: %s", one_liner[:60])
            return existing

    record = {
        "id": len(records) + 1,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "status": "discovered",  # discovered | posted | archived | acted_on
        "one_liner": one_liner,
        "category": scored.get("category", "Other"),
        "monetization": scored.get("monetization", "unknown"),
        "composite_score": scored.get("composite", 0),
        "scores": scored.get("scores", {}),
        "source": scored.get("post", {}).get("source", "unknown"),
        "source_url": scored.get("post", {}).get("url", ""),
        "source_text": source_text,
        "source_engagement": scored.get("post", {}).get("score", 0),
        "validation": None,  # filled by validator.py later
        "posted_at": None,
        "notes": "",
    }

    records.append(record)
    _save(records)
    log.info("Stored opportunity #%d: %s (%.1f)", record["id"], one_liner[:50], record["composite_score"])
    return record


def store_batch(scored_list: list[dict]) -> list[dict]:
    """Store multiple scored opportunities. Returns list of stored records."""
    results = []
    for scored in scored_list:
        record = store_opportunity(scored)
        results.append(record)
    return results


def mark_posted(opp_id: int) -> dict | None:
    """Mark an opportunity as posted to Slack."""
    records = _load()
    for r in records:
        if r["id"] == opp_id:
            r["status"] = "posted"
            r["posted_at"] = datetime.now(timezone.utc).isoformat()
            _save(records)
            return r
    return None


def mark_archived(opp_id: int, notes: str = "") -> dict | None:
    """Archive an opportunity (e.g., already saturated, not viable)."""
    records = _load()
    for r in records:
        if r["id"] == opp_id:
            r["status"] = "archived"
            r["notes"] = notes
            _save(records)
            return r
    return None


def mark_acted_on(opp_id: int, notes: str = "") -> dict | None:
    """Mark an opportunity as acted on (user is pursuing it)."""
    records = _load()
    for r in records:
        if r["id"] == opp_id:
            r["status"] = "acted_on"
            r["notes"] = notes
            _save(records)
            return r
    return None


def update_validation(opp_id: int, validation: dict) -> dict | None:
    """Attach validation results from validator.py."""
    records = _load()
    for r in records:
        if r["id"] == opp_id:
            r["validation"] = validation
            _save(records)
            return r
    return None


def get_unposted(min_score: float = 0.0, limit: int = 10) -> list[dict]:
    """Get top unposted opportunities above a minimum score."""
    records = _load()
    unposted = [
        r for r in records
        if r["status"] == "discovered" and r["composite_score"] >= min_score
    ]
    unposted.sort(key=lambda r: r["composite_score"], reverse=True)
    return unposted[:limit]


def get_all(status: str | None = None) -> list[dict]:
    """Get all records, optionally filtered by status."""
    records = _load()
    if status:
        return [r for r in records if r["status"] == status]
    return records


def get_stats() -> dict:
    """Get database statistics."""
    records = _load()
    statuses = {}
    categories = {}
    sources = {}
    scores = []

    for r in records:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        categories[r["category"]] = categories.get(r["category"], 0) + 1
        sources[r["source"]] = sources.get(r["source"], 0) + 1
        scores.append(r["composite_score"])

    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "total": len(records),
        "by_status": statuses,
        "by_category": categories,
        "by_source": sources,
        "avg_score": round(avg_score, 2),
        "top_score": max(scores) if scores else 0,
    }


def get_weekly_digest() -> list[dict]:
    """Get the top opportunities from the past 7 days for a weekly digest."""
    records = _load()
    now = datetime.now(timezone.utc)

    recent = []
    for r in records:
        discovered = datetime.fromisoformat(r["discovered_at"])
        if (now - discovered).days <= 7:
            recent.append(r)

    recent.sort(key=lambda r: r["composite_score"], reverse=True)
    return recent[:10]
