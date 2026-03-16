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

export default function DashboardPage() {
  const { getToken } = useAuth();
  const [agents, setAgents] = useState<DashboardAgent[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const token = await getToken();
      const response = await fetch("/api/agents", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (response.ok) {
        const data = await response.json();
        setAgents(Array.isArray(data) ? data : []);
      }
    } catch {
      // Non-critical for dashboard
    } finally {
      setLoading(false);
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
      value: "--",
      icon: Zap,
    },
    {
      label: "Connections",
      value: "--",
      icon: Link2,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of your trading agents and performance.
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
                  Connect your sportsbook or exchange accounts.
                </p>
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
          </div>
        </Link>
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
