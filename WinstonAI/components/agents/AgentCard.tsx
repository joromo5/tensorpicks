"use client";

import Link from "next/link";
import {
  Bot,
  Play,
  Pause,
  Clock,
  Zap,
  MoreVertical,
  Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface AgentResponse {
  id: string;
  user_id: string;
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  schedule: string | null;
  strategy_notes: string | null;
  memory: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
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

interface AgentCardProps {
  agent: AgentResponse;
  onRun: (id: string) => void;
  onToggle: (id: string, isActive: boolean) => void;
  isRunning?: boolean;
  isToggling?: boolean;
}

export function AgentCard({
  agent,
  onRun,
  onToggle,
  isRunning,
  isToggling,
}: AgentCardProps) {
  const statusColor = agent.is_active
    ? "bg-emerald-500/15 text-emerald-500"
    : "bg-zinc-500/15 text-zinc-400";
  const statusLabel = agent.is_active ? "Active" : "Paused";

  return (
    <div className="group rounded-lg border border-border bg-card p-5 transition-colors hover:border-primary/30">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Bot className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Link
                href={`/agents/${agent.id}`}
                className="font-semibold truncate hover:text-primary transition-colors"
              >
                {agent.name}
              </Link>
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                  statusColor
                )}
              >
                {statusLabel}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
              {agent.description}
            </p>
          </div>
        </div>
      </div>

      {/* Meta info */}
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
        {agent.schedule && (
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {cronToHuman(agent.schedule)}
          </span>
        )}
        <span className="flex items-center gap-1">
          <Zap className="h-3.5 w-3.5" />
          Updated {relativeTime(agent.updated_at)}
        </span>
      </div>

      {/* Tools */}
      {agent.tools.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {agent.tools.map((tool) => (
            <span
              key={tool}
              className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
            >
              {tool}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2 border-t border-border pt-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onRun(agent.id)}
          disabled={isRunning}
          className="gap-1.5"
        >
          <Play className="h-3.5 w-3.5" />
          {isRunning ? "Running..." : "Run Now"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onToggle(agent.id, agent.is_active)}
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
        <Link href={`/agents/${agent.id}`} className="ml-auto">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <Eye className="h-3.5 w-3.5" />
            Details
          </Button>
        </Link>
      </div>
    </div>
  );
}
