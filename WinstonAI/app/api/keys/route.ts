import { NextRequest, NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

/**
 * GET /api/keys — list stored API keys (proxied to engine).
 */
export async function GET(req: NextRequest) {
  const token = req.headers.get("authorization")?.replace("Bearer ", "");

  try {
    const data = await engineFetch("/keys", { token });
    return NextResponse.json(data);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to fetch keys";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

/**
 * POST /api/keys — store a new API key (proxied to engine).
 * Body: { service: string, api_key: string }
 */
export async function POST(req: NextRequest) {
  const token = req.headers.get("authorization")?.replace("Bearer ", "");

  try {
    const body = await req.json();
    const data = await engineFetch("/keys", {
      method: "POST",
      body,
      token,
    });
    return NextResponse.json(data);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to store key";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
