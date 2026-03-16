"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
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
  Download,
  BarChart3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

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

type StatusFilter = "all" | "success" | "error";

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

function isJsonString(str: string): boolean {
  const trimmed = str.trim();
  return (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  );
}

function formatJsonOutput(str: string): string {
  try {
    const parsed = JSON.parse(str);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return str;
  }
}

function SyntaxHighlightedJson({ text }: { text: string }) {
  if (!isJsonString(text)) {
    return (
      <pre className="whitespace-pre-wrap text-xs leading-relaxed">
        {text}
      </pre>
    );
  }

  const formatted = formatJsonOutput(text);

  // Simple JSON syntax highlighting
  const highlighted = formatted.replace(
    /("(?:[^"\\]|\\.)*")\s*:/g,
    '<span class="text-sky-400">$1</span>:'
  ).replace(
    /:\s*("(?:[^"\\]|\\.)*")/g,
    ': <span class="text-emerald-400">$1</span>'
  ).replace(
    /:\s*(\d+\.?\d*)/g,
    ': <span class="text-amber-400">$1</span>'
  ).replace(
    /:\s*(true|false|null)/g,
    ': <span class="text-purple-400">$1</span>'
  );

  return (
    <pre
      className="whitespace-pre-wrap text-xs leading-relaxed"
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  );
}

export function RunLogViewer({ agentId }: RunLogViewerProps) {
  const { getToken } = useAuth();
  const [runs, setRuns] = useState<RunLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [visibleCount, setVisibleCount] = useState(20);

  const fetchRuns = useCallback(async () => {
    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${agentId}/runs`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("Failed to fetch runs");
      const data = await response.json();
      setRuns(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load run history"
      );
    } finally {
      setLoading(false);
    }
  }, [agentId, getToken]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // Auto-refresh when there's a running task
  useEffect(() => {
    const hasRunning = runs.some((r) => r.status === "running");
    if (!hasRunning) return;

    const interval = setInterval(fetchRuns, 10000);
    return () => clearInterval(interval);
  }, [runs, fetchRuns]);

  // Summary stats
  const summaryStats = useMemo(() => {
    const total = runs.length;
    const successCount = runs.filter((r) => r.status === "success").length;
    const successRate = total > 0 ? ((successCount / total) * 100).toFixed(0) : "0";
    const durations = runs
      .map((r) => r.duration_ms)
      .filter((d): d is number => d !== null);
    const avgDuration =
      durations.length > 0
        ? durations.reduce((a, b) => a + b, 0) / durations.length
        : null;
    const totalTokens = runs.reduce(
      (sum, r) => sum + (r.tokens_used ?? 0),
      0
    );
    return { total, successRate, avgDuration, totalTokens };
  }, [runs]);

  // Filtered runs
  const filteredRuns = useMemo(() => {
    if (statusFilter === "all") return runs;
    return runs.filter((r) => r.status === statusFilter);
  }, [runs, statusFilter]);

  const visibleRuns = filteredRuns.slice(0, visibleCount);
  const hasMore = filteredRuns.length > visibleCount;

  function exportCsv() {
    const headers = [
      "ID",
      "Status",
      "Started At",
      "Finished At",
      "Duration (ms)",
      "Tokens Used",
      "Output",
      "Error",
    ];
    const csvRows = [
      headers.join(","),
      ...runs.map((r) =>
        [
          r.id,
          r.status,
          r.started_at,
          r.finished_at ?? "",
          r.duration_ms ?? "",
          r.tokens_used ?? "",
          `"${(r.output ?? "").replace(/"/g, '""')}"`,
          `"${(r.error_message ?? "").replace(/"/g, '""')}"`,
        ].join(",")
      ),
    ];
    const blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agent-${agentId}-runs.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

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

  const filterTabs: { key: StatusFilter; label: string }[] = [
    { key: "all", label: `All (${runs.length})` },
    {
      key: "success",
      label: `Success (${runs.filter((r) => r.status === "success").length})`,
    },
    {
      key: "error",
      label: `Error (${runs.filter((r) => r.status === "error").length})`,
    },
  ];

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-center">
          <p className="text-xs text-muted-foreground">Total Runs</p>
          <p className="text-lg font-bold">{summaryStats.total}</p>
        </div>
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-center">
          <p className="text-xs text-muted-foreground">Success Rate</p>
          <p className="text-lg font-bold">{summaryStats.successRate}%</p>
        </div>
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-center">
          <p className="text-xs text-muted-foreground">Avg Duration</p>
          <p className="text-lg font-bold">
            {formatDuration(summaryStats.avgDuration)}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-center">
          <p className="text-xs text-muted-foreground">Total Tokens</p>
          <p className="text-lg font-bold">
            {summaryStats.totalTokens > 0
              ? summaryStats.totalTokens.toLocaleString()
              : "--"}
          </p>
        </div>
      </div>

      {/* Filter tabs and export */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {filterTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => {
                setStatusFilter(tab.key);
                setVisibleCount(20);
              }}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                statusFilter === tab.key
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={exportCsv}
          className="gap-1.5"
        >
          <Download className="h-3.5 w-3.5" />
          Download CSV
        </Button>
      </div>

      {/* Run list */}
      <div className="rounded-lg border border-border bg-card">
        <div className="divide-y divide-border">
          {visibleRuns.map((run) => {
            const isExpanded = expandedId === run.id;
            const outputText = run.output || run.error_message || "No output available";
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
                    <SyntaxHighlightedJson text={outputText} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Load more */}
      {hasMore && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setVisibleCount((prev) => prev + 20)}
            className="gap-1.5"
          >
            <BarChart3 className="h-3.5 w-3.5" />
            Load More ({filteredRuns.length - visibleCount} remaining)
          </Button>
        </div>
      )}
    </div>
  );
}
