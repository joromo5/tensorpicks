"use client";

import { Brain, BookOpen, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

interface AgentMemoryPanelProps {
  strategyNotes: string | null;
  memory: Record<string, unknown>;
  updatedAt: string;
}

export function AgentMemoryPanel({
  strategyNotes,
  memory,
  updatedAt,
}: AgentMemoryPanelProps) {
  const reflectionCount =
    typeof memory?.reflection_count === "number"
      ? memory.reflection_count
      : null;
  const lastReflection =
    typeof memory?.last_reflection === "string"
      ? memory.last_reflection
      : null;

  const hasContent = strategyNotes || reflectionCount;

  if (!hasContent) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
          <Brain className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="font-medium">No Memories Yet</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          This agent hasn&apos;t learned anything yet. It will start building
          memory after its first few runs.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
            <BookOpen className="h-3.5 w-3.5" />
            Reflections
          </div>
          <p className="mt-2 text-2xl font-bold">
            {reflectionCount ?? 0}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
            <Calendar className="h-3.5 w-3.5" />
            Last Reflection
          </div>
          <p className="mt-2 text-sm font-medium">
            {lastReflection
              ? new Date(lastReflection).toLocaleString()
              : "N/A"}
          </p>
        </div>
      </div>

      {/* Strategy Notes */}
      {strategyNotes && (
        <div className="rounded-lg border border-border bg-card p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Brain className="h-4 w-4 text-primary" />
            Strategy Notes
          </h3>
          <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
            {strategyNotes}
          </div>
        </div>
      )}

      {/* Additional memory keys */}
      {Object.keys(memory).filter(
        (k) => k !== "reflection_count" && k !== "last_reflection"
      ).length > 0 && (
        <div className="rounded-lg border border-border bg-card p-5">
          <h3 className="text-sm font-semibold">Memory Data</h3>
          <div className="mt-3 space-y-2">
            {Object.entries(memory)
              .filter(
                ([k]) =>
                  k !== "reflection_count" && k !== "last_reflection"
              )
              .map(([key, value]) => (
                <div
                  key={key}
                  className="flex items-start justify-between gap-4 rounded-md bg-secondary px-3 py-2 text-sm"
                >
                  <span className="font-mono text-xs text-muted-foreground">
                    {key}
                  </span>
                  <span className="text-right text-xs">
                    {typeof value === "object"
                      ? JSON.stringify(value)
                      : String(value)}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
