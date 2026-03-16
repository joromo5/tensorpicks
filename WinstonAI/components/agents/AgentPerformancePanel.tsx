"use client";

import { useEffect, useState, useMemo } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Loader2,
  TrendingUp,
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

interface DayStats {
  date: string;
  label: string;
  total: number;
  success: number;
  error: number;
}

interface AgentPerformancePanelProps {
  agentId: string;
}

export function AgentPerformancePanel({
  agentId,
}: AgentPerformancePanelProps) {
  const { getToken } = useAuth();
  const [runs, setRuns] = useState<RunLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
            err instanceof Error ? err.message : "Failed to load performance data"
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

  const stats = useMemo(() => {
    const total = runs.length;
    const successCount = runs.filter((r) => r.status === "success").length;
    const errorCount = runs.filter((r) => r.status === "error").length;
    const successRate = total > 0 ? (successCount / total) * 100 : 0;

    const durationsMs = runs
      .map((r) => r.duration_ms)
      .filter((d): d is number => d !== null);
    const avgDuration =
      durationsMs.length > 0
        ? durationsMs.reduce((a, b) => a + b, 0) / durationsMs.length
        : 0;

    const totalTokens = runs.reduce(
      (sum, r) => sum + (r.tokens_used ?? 0),
      0
    );

    return { total, successCount, errorCount, successRate, avgDuration, totalTokens };
  }, [runs]);

  const dailyStats = useMemo(() => {
    const days: DayStats[] = [];
    const now = new Date();

    for (let i = 6; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      const dateStr = date.toISOString().split("T")[0];
      const dayLabel = i === 0 ? "Today" : i === 1 ? "Yesterday" : date.toLocaleDateString("en-US", { weekday: "short" });

      const dayRuns = runs.filter(
        (r) => r.started_at.split("T")[0] === dateStr
      );
      days.push({
        date: dateStr,
        label: dayLabel,
        total: dayRuns.length,
        success: dayRuns.filter((r) => r.status === "success").length,
        error: dayRuns.filter((r) => r.status === "error").length,
      });
    }

    return days;
  }, [runs]);

  const maxDailyRuns = Math.max(...dailyStats.map((d) => d.total), 1);

  function formatDuration(ms: number): string {
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-card p-8">
        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading performance data...
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

  const rateColor =
    stats.successRate > 80
      ? "text-emerald-400"
      : stats.successRate >= 50
        ? "text-amber-400"
        : "text-destructive";

  const rateBgColor =
    stats.successRate > 80
      ? "bg-emerald-500/10"
      : stats.successRate >= 50
        ? "bg-amber-500/10"
        : "bg-destructive/10";

  return (
    <div className="space-y-4">
      {/* Key metrics */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Success Rate */}
        <div
          className={cn(
            "rounded-lg border border-border p-5 text-center",
            rateBgColor
          )}
        >
          <p className="text-sm text-muted-foreground">Success Rate</p>
          <p className={cn("mt-1 text-3xl font-bold", rateColor)}>
            {stats.total > 0 ? `${stats.successRate.toFixed(0)}%` : "--"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {stats.successCount} of {stats.total} runs
          </p>
        </div>

        {/* Avg Response Time */}
        <div className="rounded-lg border border-border bg-card p-5 text-center">
          <p className="text-sm text-muted-foreground">Avg Response Time</p>
          <p className="mt-1 text-3xl font-bold">
            {stats.avgDuration > 0 ? formatDuration(stats.avgDuration) : "--"}
          </p>
          <div className="mt-1 flex items-center justify-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            per run
          </div>
        </div>

        {/* Total Tokens */}
        <div className="rounded-lg border border-border bg-card p-5 text-center">
          <p className="text-sm text-muted-foreground">Total Tokens</p>
          <p className="mt-1 text-3xl font-bold">
            {stats.totalTokens > 0
              ? stats.totalTokens.toLocaleString()
              : "--"}
          </p>
          <div className="mt-1 flex items-center justify-center gap-1 text-xs text-muted-foreground">
            <Zap className="h-3 w-3" />
            consumed
          </div>
        </div>

        {/* Total Runs */}
        <div className="rounded-lg border border-border bg-card p-5 text-center">
          <p className="text-sm text-muted-foreground">Total Runs</p>
          <p className="mt-1 text-3xl font-bold">{stats.total}</p>
          <div className="mt-1 flex items-center justify-center gap-1 text-xs text-muted-foreground">
            <TrendingUp className="h-3 w-3" />
            all time
          </div>
        </div>
      </div>

      {/* Runs per day bar chart */}
      <div className="rounded-lg border border-border bg-card p-5">
        <h3 className="text-sm font-semibold">Runs Per Day (Last 7 Days)</h3>
        <div className="mt-4 flex items-end gap-2" style={{ height: 120 }}>
          {dailyStats.map((day) => {
            const heightPercent =
              day.total > 0 ? (day.total / maxDailyRuns) * 100 : 0;
            const successPercent =
              day.total > 0 ? (day.success / day.total) * 100 : 0;
            return (
              <div
                key={day.date}
                className="flex flex-1 flex-col items-center gap-1"
              >
                <span className="text-xs font-medium text-muted-foreground">
                  {day.total > 0 ? day.total : ""}
                </span>
                <div
                  className="relative w-full max-w-[40px] overflow-hidden rounded-t-sm"
                  style={{
                    height: `${Math.max(heightPercent, day.total > 0 ? 8 : 2)}%`,
                    minHeight: day.total > 0 ? 8 : 2,
                  }}
                >
                  {/* Success portion */}
                  <div
                    className="absolute bottom-0 w-full bg-emerald-500/60"
                    style={{ height: `${successPercent}%` }}
                  />
                  {/* Error portion on top */}
                  <div
                    className="absolute top-0 w-full bg-destructive/60"
                    style={{
                      height: `${100 - successPercent}%`,
                    }}
                  />
                  {/* Empty state bar */}
                  {day.total === 0 && (
                    <div className="h-full w-full bg-muted" />
                  )}
                </div>
                <span className="text-[10px] text-muted-foreground">
                  {day.label}
                </span>
              </div>
            );
          })}
        </div>
        <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <div className="h-2.5 w-2.5 rounded-sm bg-emerald-500/60" />
            Success
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-2.5 w-2.5 rounded-sm bg-destructive/60" />
            Error
          </div>
        </div>
      </div>

      {/* Success/Error breakdown */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
          <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          <div>
            <p className="text-sm font-medium">Successful Runs</p>
            <p className="text-2xl font-bold text-emerald-400">
              {stats.successCount}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
          <XCircle className="h-5 w-5 text-destructive" />
          <div>
            <p className="text-sm font-medium">Failed Runs</p>
            <p className="text-2xl font-bold text-destructive">
              {stats.errorCount}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
