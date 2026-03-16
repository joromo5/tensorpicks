import { auth } from "@clerk/nextjs";
import { NextRequest, NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const { userId, getToken } = auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const token = await getToken();
    const data = await engineFetch(`/agents/${params.id}/runs`, {
      token: token ?? undefined,
    });
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to fetch runs";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
