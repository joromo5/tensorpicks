"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import {
  Bot,
  Play,
  Pause,
  Trash2,
  Loader2,
  ArrowLeft,
  Clock,
  Zap,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  MessageSquare,
  Activity,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { AgentMemoryPanel } from "@/components/agents/AgentMemoryPanel";
import { AgentPerformancePanel } from "@/components/agents/AgentPerformancePanel";
import { RunLogViewer } from "@/components/agents/RunLogViewer";
import type { AgentResponse } from "@/components/agents/AgentCard";

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

function cronToHuman(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length < 5) return cron;
  const [minute, hour, dayOfMonth, , dayOfWeek] = parts;
  if (dayOfMonth === "*" && dayOfWeek === "*") {
    if (hour === "*") {
      if (minute === "0") return "Every hour";
      if (minute.startsWith("*/")) return `Every ${minute.slice(2)} minutes`;
      return `Every hour at :${minute.padStart(2, "0")}`;
    }
    if (hour.startsWith("*/")) return `Every ${hour.slice(2)} hours`;
    const h = parseInt(hour, 10);
    const m = parseInt(minute, 10);
    const period = h >= 12 ? "PM" : "AM";
    const displayHour = h === 0 ? 12 : h > 12 ? h - 12 : h;
    return `Every day at ${displayHour}:${String(m).padStart(2, "0")} ${period}`;
  }
  return cron;
}

export default function AgentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { getToken } = useAuth();
  const agentId = params.id as string;

  const [agent, setAgent] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isToggling, setIsToggling] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [activeSection, setActiveSection] = useState<
    "overview" | "memory" | "performance" | "runs" | "config"
  >("overview");
  const [lastRun, setLastRun] = useState<RunLog | null>(null);

  const fetchAgent = useCallback(async () => {
    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${agentId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("Failed to fetch agent");
      const data = await response.json();
      setAgent(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agent");
    } finally {
      setLoading(false);
    }
  }, [agentId, getToken]);

  const fetchLastRun = useCallback(async () => {
    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${agentId}/runs`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data) && data.length > 0) {
        setLastRun(data[0]);
      }
    } catch {
      // Non-critical
    }
  }, [agentId, getToken]);

  useEffect(() => {
    fetchAgent();
    fetchLastRun();
  }, [fetchAgent, fetchLastRun]);

  async function handleRun() {
    setIsRunning(true);
    try {
      const token = await getToken();
      await fetch(`/api/agents/${agentId}/run`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      // Could show toast
    } finally {
      setIsRunning(false);
    }
  }

  async function handleToggle() {
    if (!agent) return;
    setIsToggling(true);
    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${agentId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ is_active: !agent.is_active }),
      });
      if (!response.ok) throw new Error("Failed to update agent");
      setAgent((prev) =>
        prev ? { ...prev, is_active: !prev.is_active } : prev
      );
    } catch {
      // Could show toast
    } finally {
      setIsToggling(false);
    }
  }

  async function handleDelete() {
    setIsDeleting(true);
    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${agentId}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("Failed to delete agent");
      router.push("/agents");
    } catch {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="space-y-4">
        <Link
          href="/agents"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Agents
        </Link>
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-6 text-center text-sm text-destructive">
          {error || "Agent not found"}
        </div>
      </div>
    );
  }

  const statusColor = agent.is_active
    ? "bg-emerald-500/15 text-emerald-500"
    : "bg-zinc-500/15 text-zinc-400";
  const statusLabel = agent.is_active ? "Active" : "Paused";

  // Type-safe to include output_channel if present
  const agentAny = agent as AgentResponse & { output_channel?: string };

  const sections = [
    { key: "overview" as const, label: "Overview" },
    { key: "memory" as const, label: "Memory" },
    { key: "performance" as const, label: "Performance" },
    { key: "runs" as const, label: "Run History" },
    { key: "config" as const, label: "Configuration" },
  ];

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Agents
      </Link>

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">
                {agent.name}
              </h1>
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                  statusColor
                )}
              >
                {statusLabel}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Created {new Date(agent.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRun}
            disabled={isRunning}
            className="gap-1.5"
          >
            {isRunning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {isRunning ? "Running..." : "Run Now"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleToggle}
            disabled={isToggling}
            className="gap-1.5"
          >
            {agent.is_active ? (
              <>
                <Pause className="h-3.5 w-3.5" />
                Pause
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                Resume
              </>
            )}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDeleteConfirm(true)}
            className="gap-1.5 text-destructive hover:text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      </div>

      {/* Delete confirmation */}
      {showDeleteConfirm && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
            <div className="flex-1">
              <h3 className="font-medium text-destructive">
                Delete this agent?
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                This will archive the agent and stop all scheduled runs. This
                action cannot be undone.
              </p>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className="gap-1.5"
                >
                  {isDeleting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                  {isDeleting ? "Deleting..." : "Yes, Delete"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDeleteConfirm(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab navigation */}
      <div className="flex gap-1 border-b border-border">
        {sections.map((section) => (
          <button
            key={section.key}
            type="button"
            onClick={() => setActiveSection(section.key)}
            className={cn(
              "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              activeSection === section.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {section.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeSection === "overview" && (
        <div className="space-y-4">
          {/* Description */}
          <div className="rounded-lg border border-border bg-card p-5">
            <h3 className="text-sm font-semibold">Description</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              {agent.description}
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {/* Schedule */}
            <div className="rounded-lg border border-border bg-card p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Clock className="h-4 w-4 text-muted-foreground" />
                Schedule
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">
                {agent.schedule
                  ? cronToHuman(agent.schedule)
                  : "On-demand only"}
              </p>
            </div>

            {/* Tools */}
            <div className="rounded-lg border border-border bg-card p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Zap className="h-4 w-4 text-muted-foreground" />
                Tools
              </h3>
              {agent.tools.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {agent.tools.map((tool) => (
                    <span
                      key={tool}
                      className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  No tools configured
                </p>
              )}
            </div>
          </div>

          {/* Output Channel */}
          {agentAny.output_channel && (
            <div className="rounded-lg border border-border bg-card p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
                Output Channel
              </h3>
              <p className="mt-2 text-sm text-muted-foreground">
                {agentAny.output_channel}
              </p>
            </div>
          )}

          {/* Last Run Output Preview */}
          {lastRun && (
            <div className="rounded-lg border border-border bg-card p-5">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  Last Run Output
                </h3>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                    lastRun.status === "success"
                      ? "bg-emerald-500/15 text-emerald-500"
                      : lastRun.status === "error"
                        ? "bg-destructive/15 text-destructive"
                        : lastRun.status === "running"
                          ? "bg-amber-500/15 text-amber-500"
                          : "bg-zinc-500/15 text-zinc-400"
                  )}
                >
                  {lastRun.status}
                </span>
              </div>
              <div className="mt-3 rounded-md bg-secondary/50 p-3">
                <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-secondary-foreground">
                  {lastRun.output ||
                    lastRun.error_message ||
                    "No output available"}
                </pre>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {new Date(lastRun.started_at).toLocaleString()}
                {lastRun.duration_ms !== null &&
                  ` - ${lastRun.duration_ms < 1000 ? `${lastRun.duration_ms}ms` : `${(lastRun.duration_ms / 1000).toFixed(1)}s`}`}
              </p>
            </div>
          )}
        </div>
      )}

      {activeSection === "memory" && (
        <AgentMemoryPanel
          strategyNotes={agent.strategy_notes}
          memory={agent.memory}
          updatedAt={agent.updated_at}
        />
      )}

      {activeSection === "performance" && (
        <AgentPerformancePanel agentId={agentId} />
      )}

      {activeSection === "runs" && <RunLogViewer agentId={agentId} />}

      {activeSection === "config" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-card">
            <button
              type="button"
              onClick={() => setShowSystemPrompt(!showSystemPrompt)}
              className="flex w-full items-center justify-between p-5 text-left"
            >
              <h3 className="text-sm font-semibold">System Prompt</h3>
              {showSystemPrompt ? (
                <ChevronUp className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
            {showSystemPrompt && (
              <div className="border-t border-border px-5 pb-5 pt-3">
                <pre className="whitespace-pre-wrap rounded-md bg-secondary p-4 text-xs leading-relaxed text-secondary-foreground">
                  {agent.system_prompt}
                </pre>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-border bg-card p-5">
            <h3 className="text-sm font-semibold">Agent Details</h3>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Agent ID</dt>
                <dd className="font-mono text-xs">{agent.id}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Created</dt>
                <dd>{new Date(agent.created_at).toLocaleString()}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Last Updated</dt>
                <dd>{new Date(agent.updated_at).toLocaleString()}</dd>
              </div>
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
