import { NextRequest, NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

/**
 * POST /api/keys/[service]/validate — test if a stored key works (proxied to engine).
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { service: string } },
) {
  const token = req.headers.get("authorization")?.replace("Bearer ", "");

  try {
    const data = await engineFetch<{ valid: boolean }>(
      `/keys/${params.service}/validate`,
      {
        method: "POST",
        token,
      },
    );
    return NextResponse.json(data);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Validation failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
