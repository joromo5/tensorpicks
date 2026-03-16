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
    const data = await engineFetch(`/agents/${params.id}`, {
      token: token ?? undefined,
    });
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to fetch agent";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const { userId, getToken } = auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const token = await getToken();
    const body = await request.json();
    const data = await engineFetch(`/agents/${params.id}`, {
      method: "PATCH",
      body,
      token: token ?? undefined,
    });
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to update agent";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const { userId, getToken } = auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const token = await getToken();
    const data = await engineFetch(`/agents/${params.id}`, {
      method: "DELETE",
      token: token ?? undefined,
    });
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to delete agent";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
