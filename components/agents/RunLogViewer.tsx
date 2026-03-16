"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  Zap,
  ChevronDown,
  ChevronUp,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface RunLog {
  id: string;
  status: "success" | "error" | "running" | "pending";
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  tokens_used: number | null;
  output: string | null;
  error_message: string | null;
}

interface RunLogViewerProps {
  agentId: string;
}

function StatusIcon({ status }: { status: RunLog["status"] }) {
  switch (status) {
    case "success":
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
    case "error":
      return <XCircle className="h-4 w-4 text-destructive" />;
    case "running":
      return <Loader2 className="h-4 w-4 animate-spin text-amber-500" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "--";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function RunLogViewer({ agentId }: RunLogViewerProps) {
  const { getToken } = useAuth();
  const [runs, setRuns] = useState<RunLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchRuns() {
      try {
        const token = await getToken();
        const response = await fetch(`/api/agents/${agentId}/runs`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!response.ok) throw new Error("Failed to fetch runs");
        const data = await response.json();
        if (!cancelled) {
          setRuns(Array.isArray(data) ? data : []);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load run history"
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchRuns();
    return () => {
      cancelled = true;
    };
  }, [agentId, getToken]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-card p-8">
        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading run history...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-border bg-card p-8">
        <p className="text-center text-sm text-destructive">{error}</p>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
          <Activity className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="font-medium">No Runs Yet</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          This agent hasn&apos;t been run yet. Trigger a manual run or wait for
          the scheduled run.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="divide-y divide-border">
        {runs.map((run) => {
          const isExpanded = expandedId === run.id;
          return (
            <div key={run.id}>
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : run.id)}
                className="flex w-full items-center gap-4 px-4 py-3 text-left text-sm transition-colors hover:bg-accent/50"
              >
                <StatusIcon status={run.status} />
                <span className="min-w-0 flex-1 truncate">
                  {run.output
                    ? run.output.slice(0, 80) +
                      (run.output.length > 80 ? "..." : "")
                    : run.error_message
                      ? run.error_message.slice(0, 80)
                      : run.status === "running"
                        ? "Running..."
                        : "No output"}
                </span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {formatDuration(run.duration_ms)}
                </span>
                {run.tokens_used !== null && (
                  <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                    <Zap className="h-3 w-3" />
                    {run.tokens_used.toLocaleString()}
                  </span>
                )}
                <span className="shrink-0 text-xs text-muted-foreground">
                  {new Date(run.started_at).toLocaleString()}
                </span>
                {isExpanded ? (
                  <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                )}
              </button>
              {isExpanded && (
                <div className="border-t border-border bg-secondary/30 px-4 py-4">
                  <pre className="whitespace-pre-wrap text-xs leading-relaxed">
                    {run.output || run.error_message || "No output available"}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
