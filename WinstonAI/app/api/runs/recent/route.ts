import { auth } from "@clerk/nextjs";
import { NextResponse } from "next/server";
import { engineFetch } from "@/lib/api";

interface RunLog {
  id: string;
  agent_id: string;
  agent_name?: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  tokens_used: number | null;
  output: string | null;
  error_message: string | null;
}

export async function GET() {
  const { userId, getToken } = auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const token = await getToken();

    // Fetch all agents first, then get recent runs from each
    const agents = await engineFetch<
      Array<{ id: string; name: string }>
    >("/agents", { token: token ?? undefined });

    if (!Array.isArray(agents) || agents.length === 0) {
      return NextResponse.json([]);
    }

    // Fetch runs for each agent in parallel
    const allRunsPromises = agents.map(async (agent) => {
      try {
        const runs = await engineFetch<RunLog[]>(
          `/agents/${agent.id}/runs`,
          { token: token ?? undefined }
        );
        return (Array.isArray(runs) ? runs : []).map((run) => ({
          ...run,
          agent_id: agent.id,
          agent_name: agent.name,
        }));
      } catch {
        return [];
      }
    });

    const allRunArrays = await Promise.all(allRunsPromises);
    const allRuns = allRunArrays.flat();

    // Sort by started_at descending and take first 5
    allRuns.sort(
      (a, b) =>
        new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
    );

    return NextResponse.json(allRuns.slice(0, 5));
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to fetch recent runs";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
