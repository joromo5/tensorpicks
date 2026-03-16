"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

// ── Types ───────────────────────────────────────────────────────────

interface BillingStatus {
  plan: string;
  agent_count: number;
  agent_limit: number;
  runs_today: number;
  run_limit: number;
  stripe_customer_id: string | null;
}

interface PlanCard {
  name: string;
  key: string;
  price: string;
  priceNote: string;
  features: string[];
}

// ── Plan data ───────────────────────────────────────────────────────

const PLANS: PlanCard[] = [
  {
    name: "Free",
    key: "free",
    price: "$0",
    priceNote: "forever",
    features: [
      "2 agents",
      "10 runs per day",
      "Community support",
      "Basic tools",
    ],
  },
  {
    name: "Starter",
    key: "starter",
    price: "$19",
    priceNote: "per month",
    features: [
      "5 agents",
      "50 runs per day",
      "Email support",
      "All tools",
      "Strategy reflections",
    ],
  },
  {
    name: "Pro",
    key: "pro",
    price: "$49",
    priceNote: "per month",
    features: [
      "20 agents",
      "500 runs per day",
      "Priority support",
      "All tools",
      "Advanced reflections",
      "Custom schedules",
    ],
  },
  {
    name: "Agency",
    key: "agency",
    price: "$149",
    priceNote: "per month",
    features: [
      "100 agents",
      "5,000 runs per day",
      "Dedicated support",
      "All tools",
      "Advanced reflections",
      "Custom schedules",
      "Team management",
      "API access",
    ],
  },
];

// ── Component ───────────────────────────────────────────────────────

export default function BillingPage() {
  const { getToken } = useAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Fetch billing status on mount ─────────────────────────────────

  useEffect(() => {
    async function fetchStatus() {
      try {
        const token = await getToken();
        const resp = await fetch("/api/billing/status", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) throw new Error("Failed to load billing status");
        const data: BillingStatus = await resp.json();
        setStatus(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    fetchStatus();
  }, [getToken]);

  // ── Handlers ──────────────────────────────────────────────────────

  async function handleUpgrade(plan: string) {
    setUpgrading(plan);
    setError(null);
    try {
      const token = await getToken();
      const resp = await fetch("/api/billing/create-checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ plan }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.error || "Failed to create checkout session");
      }
      const data = await resp.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
    } finally {
      setUpgrading(null);
    }
  }

  async function handleManageSubscription() {
    setPortalLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const resp = await fetch("/api/billing/create-portal", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.error || "Failed to create portal session");
      }
      const data = await resp.json();
      if (data.portal_url) {
        window.location.href = data.portal_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal redirect failed");
    } finally {
      setPortalLoading(false);
    }
  }

  // ── Loading state ─────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Billing</h1>
          <p className="text-muted-foreground">Loading billing information...</p>
        </div>
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      </div>
    );
  }

  const currentPlan = status?.plan ?? "free";

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Billing</h1>
        <p className="text-muted-foreground">
          Manage your subscription and monitor usage.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          {error}
        </div>
      )}

      {/* Current plan + usage */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Plan badge */}
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm font-medium text-muted-foreground">
            Current Plan
          </p>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-2xl font-bold capitalize">{currentPlan}</span>
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
              Active
            </span>
          </div>
        </div>

        {/* Agents used */}
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm font-medium text-muted-foreground">Agents</p>
          <p className="mt-2 text-2xl font-bold">
            {status?.agent_count ?? 0}
            <span className="text-base font-normal text-muted-foreground">
              {" "}
              / {status?.agent_limit ?? 2}
            </span>
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{
                width: `${Math.min(
                  100,
                  ((status?.agent_count ?? 0) / (status?.agent_limit ?? 2)) * 100
                )}%`,
              }}
            />
          </div>
        </div>

        {/* Runs today */}
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm font-medium text-muted-foreground">
            Runs Today
          </p>
          <p className="mt-2 text-2xl font-bold">
            {status?.runs_today ?? 0}
            <span className="text-base font-normal text-muted-foreground">
              {" "}
              / {status?.run_limit ?? 10}
            </span>
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{
                width: `${Math.min(
                  100,
                  ((status?.runs_today ?? 0) / (status?.run_limit ?? 10)) * 100
                )}%`,
              }}
            />
          </div>
        </div>

        {/* Manage button */}
        <div className="flex items-center justify-center rounded-lg border border-border bg-card p-5">
          {currentPlan !== "free" ? (
            <button
              onClick={handleManageSubscription}
              disabled={portalLoading}
              className="inline-flex items-center gap-2 rounded-md bg-secondary px-4 py-2 text-sm font-medium text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:opacity-50"
            >
              {portalLoading ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Loading...
                </>
              ) : (
                "Manage Subscription"
              )}
            </button>
          ) : (
            <p className="text-center text-sm text-muted-foreground">
              Upgrade below to unlock more features
            </p>
          )}
        </div>
      </div>

      {/* Plan comparison cards */}
      <div>
        <h2 className="mb-4 text-lg font-semibold">Plans</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((plan) => {
            const isCurrent = plan.key === currentPlan;
            const isDowngrade =
              !isCurrent &&
              plan.key === "free" &&
              currentPlan !== "free";
            const canUpgrade =
              !isCurrent &&
              plan.key !== "free" &&
              !isDowngrade;

            return (
              <div
                key={plan.key}
                className={`relative flex flex-col rounded-lg border p-6 transition-shadow ${
                  isCurrent
                    ? "border-primary bg-primary/5 shadow-md"
                    : "border-border bg-card hover:shadow-sm"
                }`}
              >
                {isCurrent && (
                  <span className="absolute -top-2.5 left-4 rounded-full bg-primary px-3 py-0.5 text-xs font-semibold text-primary-foreground">
                    Current plan
                  </span>
                )}

                <div className="mb-4">
                  <h3 className="text-lg font-bold">{plan.name}</h3>
                  <div className="mt-1">
                    <span className="text-3xl font-extrabold">{plan.price}</span>
                    <span className="ml-1 text-sm text-muted-foreground">
                      / {plan.priceNote}
                    </span>
                  </div>
                </div>

                <ul className="mb-6 flex-1 space-y-2">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-2 text-sm text-muted-foreground"
                    >
                      <svg
                        className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={2.5}
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M4.5 12.75l6 6 9-13.5"
                        />
                      </svg>
                      {feature}
                    </li>
                  ))}
                </ul>

                <div className="mt-auto">
                  {isCurrent ? (
                    <button
                      disabled
                      className="w-full rounded-md bg-primary/20 px-4 py-2 text-sm font-medium text-primary"
                    >
                      Current plan
                    </button>
                  ) : canUpgrade ? (
                    <button
                      onClick={() => handleUpgrade(plan.key)}
                      disabled={upgrading === plan.key}
                      className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                    >
                      {upgrading === plan.key ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          Redirecting...
                        </span>
                      ) : (
                        "Upgrade"
                      )}
                    </button>
                  ) : isDowngrade ? (
                    <p className="text-center text-xs text-muted-foreground">
                      Use &ldquo;Manage Subscription&rdquo; to downgrade
                    </p>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
