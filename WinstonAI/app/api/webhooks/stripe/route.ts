import { NextRequest, NextResponse } from "next/server";

const ENGINE_BASE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL ?? "http://localhost:8000";
const STRIPE_WEBHOOK_SECRET = process.env.STRIPE_WEBHOOK_SECRET;

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const signature = request.headers.get("stripe-signature");

    if (!signature) {
      return NextResponse.json(
        { error: "Missing stripe-signature header" },
        { status: 400 }
      );
    }

    // Forward the raw body and signature to the engine for verification
    const engineResponse = await fetch(
      `${ENGINE_BASE_URL}/billing/webhook`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "stripe-signature": signature,
          ...(STRIPE_WEBHOOK_SECRET
            ? { "x-webhook-secret": STRIPE_WEBHOOK_SECRET }
            : {}),
        },
        body,
      }
    );

    if (!engineResponse.ok) {
      const errorText = await engineResponse.text().catch(() => "Unknown error");
      console.error(
        `Stripe webhook proxy error ${engineResponse.status}: ${errorText}`
      );
      return NextResponse.json(
        { error: "Webhook processing failed" },
        { status: engineResponse.status }
      );
    }

    return NextResponse.json({ received: true }, { status: 200 });
  } catch (error) {
    console.error("Stripe webhook error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
