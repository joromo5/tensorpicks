"""Stripe billing endpoints — checkout, portal, status, webhooks."""

from __future__ import annotations

import logging
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from engine.auth import get_current_user
from engine.config import settings
from engine import db
from engine.plan_limits import PLAN_LIMITS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

# ── Stripe SDK setup ────────────────────────────────────────────────

stripe.api_key = settings.STRIPE_SECRET_KEY

# ── Valid plans ──────────────────────────────────────────────────────

PAID_PLANS = {"starter", "pro", "agency"}


# ── Request models ──────────────────────────────────────────────────


class CreateCheckoutRequest(BaseModel):
    """Body for creating a Stripe Checkout session."""

    plan: str = Field(
        ..., description="Target plan: 'starter', 'pro', or 'agency'"
    )


# ── Helpers ──────────────────────────────────────────────────────────


async def _ensure_stripe_customer(user_id: str) -> str:
    """Return the Stripe customer ID for a user, creating one if needed."""
    profile = await db.get_user_profile(user_id)
    if profile and profile.get("stripe_customer_id"):
        return profile["stripe_customer_id"]

    # Create a Stripe customer
    customer = stripe.Customer.create(metadata={"clerk_user_id": user_id})
    await db.upsert_user_profile(user_id, stripe_customer_id=customer.id)
    return customer.id


# ── POST /billing/create-checkout ───────────────────────────────────


@router.post("/create-checkout")
async def create_checkout(
    body: CreateCheckoutRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    """Create a Stripe Checkout session for a plan upgrade.

    Returns ``{ checkout_url }`` which the frontend redirects to.
    """
    if body.plan not in PAID_PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan '{body.plan}'. Choose from: {', '.join(sorted(PAID_PLANS))}",
        )

    price_id = settings.STRIPE_PRICE_IDS.get(body.plan)
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No Stripe price configured for plan '{body.plan}'",
        )

    customer_id = await _ensure_stripe_customer(user_id)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.CORS_ORIGINS[0]}/billing?success=true",
        cancel_url=f"{settings.CORS_ORIGINS[0]}/billing?canceled=true",
        metadata={"clerk_user_id": user_id, "plan": body.plan},
    )

    return {"checkout_url": session.url}


# ── POST /billing/create-portal ─────────────────────────────────────


@router.post("/create-portal")
async def create_portal(
    user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    """Create a Stripe Customer Portal session for managing subscription.

    Returns ``{ portal_url }`` which the frontend redirects to.
    """
    customer_id = await _ensure_stripe_customer(user_id)

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.CORS_ORIGINS[0]}/billing",
    )

    return {"portal_url": session.url}


# ── GET /billing/status ─────────────────────────────────────────────


@router.get("/status")
async def billing_status(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Return current plan, usage stats, and limits."""
    profile = await db.get_user_profile(user_id)

    plan = "free"
    stripe_customer_id: str | None = None
    if profile:
        plan = profile.get("plan", "free")
        stripe_customer_id = profile.get("stripe_customer_id")

    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    agents = await db.list_agents(user_id)
    runs_today = await db.count_runs_today(user_id)

    return {
        "plan": plan,
        "agent_count": len(agents),
        "agent_limit": limits.max_agents,
        "runs_today": runs_today,
        "run_limit": limits.max_runs_per_day,
        "stripe_customer_id": stripe_customer_id,
    }


# ── POST /billing/webhook ───────────────────────────────────────────


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict[str, str]:
    """Handle incoming Stripe webhook events.

    This endpoint does NOT require Clerk auth — it uses Stripe's
    signature verification instead.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe signature",
        )
    except Exception as exc:
        logger.error("Stripe webhook error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook parsing error",
        )

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data)
    else:
        logger.debug("Unhandled Stripe event type: %s", event_type)

    return {"status": "ok"}


# ── Webhook handlers ────────────────────────────────────────────────


async def _handle_checkout_completed(session: dict[str, Any]) -> None:
    """Update user plan after successful checkout."""
    metadata = session.get("metadata") or {}
    clerk_user_id = metadata.get("clerk_user_id")
    plan = metadata.get("plan")

    if not clerk_user_id or not plan:
        logger.warning(
            "checkout.session.completed missing metadata: clerk_user_id=%s plan=%s",
            clerk_user_id, plan,
        )
        return

    await db.upsert_user_profile(
        clerk_user_id,
        plan=plan,
        stripe_customer_id=session.get("customer"),
    )
    logger.info("User %s upgraded to plan '%s' via checkout", clerk_user_id, plan)


async def _handle_subscription_updated(subscription: dict[str, Any]) -> None:
    """Update user plan when their subscription changes."""
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    # Look up user by stripe_customer_id
    profile = await _find_profile_by_customer(customer_id)
    if not profile:
        logger.warning("No user profile found for Stripe customer %s", customer_id)
        return

    # Determine the new plan from the subscription's price
    items = subscription.get("items", {}).get("data", [])
    if not items:
        return

    price_id = items[0].get("price", {}).get("id", "")
    new_plan = _price_id_to_plan(price_id)

    await db.upsert_user_profile(profile["clerk_user_id"], plan=new_plan)
    logger.info(
        "User %s subscription updated to plan '%s'",
        profile["clerk_user_id"], new_plan,
    )


async def _handle_subscription_deleted(subscription: dict[str, Any]) -> None:
    """Downgrade user to free when subscription is canceled."""
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    profile = await _find_profile_by_customer(customer_id)
    if not profile:
        logger.warning("No user profile found for Stripe customer %s", customer_id)
        return

    await db.upsert_user_profile(profile["clerk_user_id"], plan="free")
    logger.info(
        "User %s downgraded to free (subscription deleted)",
        profile["clerk_user_id"],
    )


def _handle_payment_failed(invoice: dict[str, Any]) -> None:
    """Log a warning when a payment fails — no plan change yet."""
    customer_id = invoice.get("customer")
    logger.warning(
        "Payment failed for Stripe customer %s — invoice %s",
        customer_id,
        invoice.get("id"),
    )


# ── Internal helpers ─────────────────────────────────────────────────


async def _find_profile_by_customer(stripe_customer_id: str) -> dict[str, Any] | None:
    """Look up a user profile by their Stripe customer ID."""
    resp = (
        db.get_client()
        .table("user_profiles")
        .select("*")
        .eq("stripe_customer_id", stripe_customer_id)
        .maybe_single()
        .execute()
    )
    return resp.data


def _price_id_to_plan(price_id: str) -> str:
    """Reverse-map a Stripe Price ID to a plan name."""
    for plan_name, pid in settings.STRIPE_PRICE_IDS.items():
        if pid == price_id:
            return plan_name
    logger.warning("Unknown Stripe price ID: %s — defaulting to 'free'", price_id)
    return "free"
