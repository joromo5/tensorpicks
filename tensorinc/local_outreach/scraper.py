"""Find local businesses using Google Maps Places API."""

import logging

import httpx

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Business types that commonly need websites
TARGET_TYPES = [
    "restaurant",
    "hair_care",
    "beauty_salon",
    "plumber",
    "electrician",
    "dentist",
    "lawyer",
    "accounting",
    "car_repair",
    "locksmith",
    "roofing_contractor",
    "painter",
    "moving_company",
    "pet_store",
    "bakery",
    "florist",
    "dry_cleaning",
    "gym",
]


def search_businesses(
    location: str | None = None,
    radius_m: int = 15000,
    max_results: int = 60,
) -> list[dict]:
    """Search for local businesses in the configured area.

    Returns list of dicts with: name, address, place_id, types, rating, website (if any),
    phone, email.
    """
    loc = location or settings.outreach_location
    if not loc:
        log.error("No location configured — set OUTREACH_LOCATION in .env")
        return []

    # First geocode the location string to lat/lng
    coords = _geocode(loc)
    if not coords:
        return []

    all_businesses = []

    for btype in TARGET_TYPES:
        try:
            resp = httpx.get(
                _NEARBY_URL,
                params={
                    "location": f"{coords[0]},{coords[1]}",
                    "radius": radius_m,
                    "type": btype,
                    "key": settings.google_maps_api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

            for place in results:
                all_businesses.append({
                    "name": place.get("name"),
                    "address": place.get("vicinity", ""),
                    "place_id": place.get("place_id"),
                    "types": place.get("types", []),
                    "rating": place.get("rating"),
                    "total_ratings": place.get("user_ratings_total", 0),
                })

            log.info("Found %d businesses for type '%s'", len(results), btype)
        except httpx.HTTPError as e:
            log.error("Google Maps API error for type '%s': %s", btype, e)

        if len(all_businesses) >= max_results:
            break

    # Deduplicate by place_id
    seen = set()
    unique = []
    for b in all_businesses:
        if b["place_id"] not in seen:
            seen.add(b["place_id"])
            unique.append(b)

    return unique[:max_results]


def get_business_details(place_id: str) -> dict:
    """Get full details for a business including website and contact info."""
    try:
        resp = httpx.get(
            _DETAILS_URL,
            params={
                "place_id": place_id,
                "fields": "name,formatted_address,website,formatted_phone_number,"
                          "opening_hours,reviews,url",
                "key": settings.google_maps_api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("result", {})
    except httpx.HTTPError as e:
        log.error("Google Maps details error for %s: %s", place_id, e)
        return {}


def _geocode(location: str) -> tuple[float, float] | None:
    """Convert a location string to lat/lng coordinates."""
    try:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": location, "key": settings.google_maps_api_key},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            loc = results[0]["geometry"]["location"]
            return (loc["lat"], loc["lng"])
        log.error("Could not geocode location: %s", location)
    except httpx.HTTPError as e:
        log.error("Geocoding failed: %s", e)
    return None
