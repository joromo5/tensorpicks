import { auth } from "@clerk/nextjs";
import { NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

export async function GET() {
  const { userId, getToken } = auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const token = await getToken();
    const data = await engineFetch("/billing/status", {
      token: token ?? undefined,
    });
    return NextResponse.json(data);
  } catch (error) {
    // Return a default response if billing endpoint is not available
    const message =
      error instanceof Error ? error.message : "Failed to fetch billing status";
    // If engine doesn't have billing yet, return safe defaults
    if (message.includes("404") || message.includes("Not Found")) {
      return NextResponse.json({ runs_today: 0, plan: "free" });
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
