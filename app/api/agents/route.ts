import { auth } from "@clerk/nextjs";
import { NextRequest, NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

export async function GET() {
  const { userId, getToken } = auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const token = await getToken();
    const data = await engineFetch("/agents", { token: token ?? undefined });
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to fetch agents";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const { userId, getToken } = auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const token = await getToken();
    const body = await request.json();
    const data = await engineFetch("/agents", {
      method: "POST",
      body,
      token: token ?? undefined,
    });
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to create agent";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
