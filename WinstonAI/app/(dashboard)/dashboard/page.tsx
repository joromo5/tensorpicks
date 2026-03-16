"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import {
  Bot,
  Activity,
  Zap,
  Link2,
  Plus,
  Key,
  Loader2,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DashboardAgent {
  id: string;
  name: string;
  is_active: boolean;
}

interface RecentRun {
  id: string;
  agent_id: string;
  agent_name?: string;
  status: "success" | "error" | "running" | "pending";
  started_at: string;
  duration_ms: number | null;
  output: string | null;
  error_message: string | null;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "--";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function relativeTime(dateString: string): string {
  const now = Date.now();
  const then = new Date(dateString).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(dateString).toLocaleDateString();
}

export default function DashboardPage() {
  const { getToken } = useAuth();
  const [agents, setAgents] = useState<DashboardAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [runsToday, setRunsToday] = useState<number | null>(null);
  const [connections, setConnections] = useState<number | null>(null);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [recentRunsLoading, setRecentRunsLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const token = await getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};

      // Fetch agents, billing status, bot connections, and recent runs in parallel
      const [agentsRes, billingRes, botsRes, runsRes] = await Promise.allSettled([
        fetch("/api/agents", { headers }),
        fetch("/api/billing/status", { headers }),
        fetch("/api/bots/status", { headers }),
        fetch("/api/runs/recent", { headers }),
      ]);

      if (agentsRes.status === "fulfilled" && agentsRes.value.ok) {
        const data = await agentsRes.value.json();
        setAgents(Array.isArray(data) ? data : []);
      }

      if (billingRes.status === "fulfilled" && billingRes.value.ok) {
        try {
          const data = await billingRes.value.json();
          if (typeof data.runs_today === "number") {
            setRunsToday(data.runs_today);
          }
        } catch {
          // Non-critical
        }
      }

      if (botsRes.status === "fulfilled" && botsRes.value.ok) {
        try {
          const data = await botsRes.value.json();
          if (typeof data.connected === "number") {
            setConnections(data.connected);
          } else if (Array.isArray(data)) {
            setConnections(data.length);
          }
        } catch {
          // Non-critical
        }
      }

      if (runsRes.status === "fulfilled" && runsRes.value.ok) {
        try {
          const data = await runsRes.value.json();
          setRecentRuns(Array.isArray(data) ? data : []);
        } catch {
          // Non-critical
        }
      }
    } catch {
      // Non-critical for dashboard
    } finally {
      setLoading(false);
      setRecentRunsLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const activeCount = agents.filter((a) => a.is_active).length;

  const stats = [
    {
      label: "Active Agents",
      value: loading ? "--" : String(activeCount),
      icon: Bot,
    },
    {
      label: "Total Agents",
      value: loading ? "--" : String(agents.length),
      icon: Activity,
    },
    {
      label: "Runs Today",
      value: loading ? "--" : runsToday !== null ? String(runsToday) : "0",
      icon: Zap,
    },
    {
      label: "Connections",
      value: loading ? "--" : connections !== null ? String(connections) : "0",
      icon: Link2,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of your autonomous AI agents and performance.
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-border bg-card p-6"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">{stat.label}</p>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="mt-2 text-2xl font-bold">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid gap-4 md:grid-cols-2">
        <Link href="/agents/new" className="block">
          <div className="group rounded-lg border border-border bg-card p-6 transition-colors hover:border-primary/30">
            <div className="flex items-center gap-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <Plus className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1">
                <h3 className="font-medium">Create Agent</h3>
                <p className="text-sm text-muted-foreground">
                  Describe what you want and let AI configure it.
                </p>
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
          </div>
        </Link>
        <Link href="/settings" className="block">
          <div className="group rounded-lg border border-border bg-card p-6 transition-colors hover:border-primary/30">
            <div className="flex items-center gap-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
                <Key className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="flex-1">
                <h3 className="font-medium">Add API Key</h3>
                <p className="text-sm text-muted-foreground">
                  Connect your external services and integrations.
                </p>
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
          </div>
        </Link>
      </div>

      {/* Recent Runs */}
      <div className="rounded-lg border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="font-semibold">Recent Runs</h2>
        </div>
        <div className="p-6">
          {recentRunsLoading && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}
          {!recentRunsLoading && recentRuns.length === 0 && (
            <p className="text-center text-sm text-muted-foreground">
              No recent runs. Run an agent to see activity here.
            </p>
          )}
          {!recentRunsLoading && recentRuns.length > 0 && (
            <div className="space-y-3">
              {recentRuns.map((run) => (
                <Link
                  key={run.id}
                  href={`/agents/${run.agent_id}`}
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {run.status === "success" ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                    ) : run.status === "error" ? (
                      <XCircle className="h-4 w-4 shrink-0 text-destructive" />
                    ) : (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-500" />
                    )}
                    <div className="min-w-0 flex-1">
                      <span className="font-medium">
                        {run.agent_name || "Agent"}
                      </span>
                      <p className="truncate text-xs text-muted-foreground">
                        {run.output
                          ? run.output.slice(0, 60) +
                            (run.output.length > 60 ? "..." : "")
                          : run.error_message
                            ? run.error_message.slice(0, 60)
                            : "No output"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 ml-3">
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {formatDuration(run.duration_ms)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {relativeTime(run.started_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent agents */}
      <div className="rounded-lg border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="font-semibold">Your Agents</h2>
          <Link
            href="/agents"
            className="text-sm text-primary hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="p-6">
          {loading && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}
          {!loading && agents.length === 0 && (
            <p className="text-center text-sm text-muted-foreground">
              No agents yet. Create your first agent to get started.
            </p>
          )}
          {!loading && agents.length > 0 && (
            <div className="space-y-3">
              {agents.slice(0, 5).map((agent) => (
                <Link
                  key={agent.id}
                  href={`/agents/${agent.id}`}
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent"
                >
                  <div className="flex items-center gap-3">
                    <Bot className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium">{agent.name}</span>
                  </div>
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                      agent.is_active
                        ? "bg-emerald-500/15 text-emerald-500"
                        : "bg-zinc-500/15 text-zinc-400"
                    )}
                  >
                    {agent.is_active ? "Active" : "Paused"}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
