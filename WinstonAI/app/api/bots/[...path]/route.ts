import { NextRequest, NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

/**
 * Catch-all proxy for /api/bots/* → engine /bots/*
 *
 * Forwards the Clerk JWT and request body to the Python engine,
 * supporting all HTTP methods used by the bots router.
 */

function extractPath(req: NextRequest): string {
  const url = new URL(req.url);
  // Strip /api prefix to get the engine path: /api/bots/... → /bots/...
  const match = url.pathname.match(/^\/api(\/bots\/.*)$/);
  return match?.[1] ?? "/bots";
}

async function proxyToEngine(req: NextRequest, method: string) {
  const token = req.headers.get("authorization")?.replace("Bearer ", "");
  const path = extractPath(req);

  try {
    let body: unknown = undefined;
    if (method !== "GET" && method !== "DELETE") {
      try {
        body = await req.json();
      } catch {
        // No body or invalid JSON — that's fine for some endpoints
      }
    }

    const data = await engineFetch(path, { method: method as "GET" | "POST" | "PUT" | "PATCH" | "DELETE", body, token });
    return NextResponse.json(data);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to proxy request to engine";

    // Try to extract status code from error message
    const statusMatch = message.match(/Engine API error (\d+)/);
    const statusCode = statusMatch ? parseInt(statusMatch[1], 10) : 502;

    return NextResponse.json({ error: message }, { status: statusCode });
  }
}

export async function GET(req: NextRequest) {
  return proxyToEngine(req, "GET");
}

export async function POST(req: NextRequest) {
  return proxyToEngine(req, "POST");
}

export async function DELETE(req: NextRequest) {
  return proxyToEngine(req, "DELETE");
}

export async function PATCH(req: NextRequest) {
  return proxyToEngine(req, "PATCH");
}
