"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { Bot, Plus, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentCard, type AgentResponse } from "@/components/agents/AgentCard";

export default function AgentsPage() {
  const { getToken } = useAuth();
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());
  const [togglingIds, setTogglingIds] = useState<Set<string>>(new Set());

  const fetchAgents = useCallback(async () => {
    try {
      const token = await getToken();
      const response = await fetch("/api/agents", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("Failed to fetch agents");
      const data = await response.json();
      setAgents(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  async function handleRun(id: string) {
    setRunningIds((prev) => new Set(prev).add(id));
    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${id}/run`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("Failed to run agent");
    } catch {
      // Silently handle - could add toast notifications
    } finally {
      setRunningIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  async function handleToggle(id: string, isActive: boolean) {
    setTogglingIds((prev) => new Set(prev).add(id));
    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ is_active: !isActive }),
      });
      if (!response.ok) throw new Error("Failed to update agent");
      setAgents((prev) =>
        prev.map((a) => (a.id === id ? { ...a, is_active: !isActive } : a))
      );
    } catch {
      // Silently handle
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
          <p className="text-muted-foreground">
            Manage your autonomous AI agents.
          </p>
        </div>
        <Link href="/agents/new">
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            New Agent
          </Button>
        </Link>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && agents.length === 0 && (
        <div className="rounded-lg border border-border bg-card p-12 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-secondary">
            <Bot className="h-7 w-7 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-medium">No agents yet</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Create your first agent to get started with automation.
          </p>
          <Link href="/agents/new">
            <Button className="mt-6 gap-2">
              <Plus className="h-4 w-4" />
              Create Your First Agent
            </Button>
          </Link>
        </div>
      )}

      {!loading && !error && agents.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onRun={handleRun}
              onToggle={handleToggle}
              isRunning={runningIds.has(agent.id)}
              isToggling={togglingIds.has(agent.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
