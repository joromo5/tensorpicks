import { NextRequest, NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

/**
 * DELETE /api/keys/[service] — remove a stored API key (proxied to engine).
 */
export async function DELETE(
  req: NextRequest,
  { params }: { params: { service: string } },
) {
  const token = req.headers.get("authorization")?.replace("Bearer ", "");

  try {
    const data = await engineFetch(`/keys/${params.service}`, {
      method: "DELETE",
      token,
    });
    return NextResponse.json(data);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to delete key";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
