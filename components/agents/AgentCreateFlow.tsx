"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import {
  Bot,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Check,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface GeneratedAgent {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  schedule: string | null;
  strategy_notes: string | null;
  is_active: boolean;
}

const SCHEDULE_PRESETS = [
  { label: "On-demand only", value: "" },
  { label: "Every hour", value: "0 * * * *" },
  { label: "Every 4 hours", value: "0 */4 * * *" },
  { label: "Daily at 9:00 AM", value: "0 9 * * *" },
  { label: "Daily at 6:00 PM", value: "0 18 * * *" },
  { label: "Every weekday at 9:00 AM", value: "0 9 * * 1-5" },
  { label: "Custom", value: "custom" },
];

const OUTPUT_CHANNELS = [
  { label: "None", value: "none" },
  { label: "Telegram", value: "telegram" },
  { label: "Slack", value: "slack" },
  { label: "Discord", value: "discord" },
];

export function AgentCreateFlow() {
  const { getToken } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [description, setDescription] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generatedAgent, setGeneratedAgent] = useState<GeneratedAgent | null>(
    null
  );

  // Step 2 overrides
  const [nameOverride, setNameOverride] = useState("");
  const [schedulePreset, setSchedulePreset] = useState("");
  const [customCron, setCustomCron] = useState("");
  const [outputChannel, setOutputChannel] = useState("none");
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);

  const charCount = description.length;
  const isDescriptionValid = charCount >= 10 && charCount <= 2000;

  async function handleGenerate() {
    if (!isDescriptionValid) return;
    setError(null);
    setIsGenerating(true);

    try {
      const token = await getToken();
      const response = await fetch("/api/agents", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ description }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Request failed (${response.status})`);
      }

      const agent = (await response.json()) as GeneratedAgent;
      setGeneratedAgent(agent);
      setNameOverride(agent.name);
      setSchedulePreset(agent.schedule ?? "");
      setStep(2);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to generate agent config"
      );
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleCreate() {
    if (!generatedAgent) return;
    setError(null);
    setIsCreating(true);

    const schedule =
      schedulePreset === "custom"
        ? customCron || null
        : schedulePreset || null;

    try {
      const token = await getToken();
      const response = await fetch(`/api/agents/${generatedAgent.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          name: nameOverride || generatedAgent.name,
          schedule,
          is_active: true,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Request failed (${response.status})`);
      }

      setStep(3);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create agent"
      );
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      {/* Step indicator */}
      <div className="mb-8 flex items-center justify-center gap-2">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium",
                step >= s
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-muted-foreground"
              )}
            >
              {step > s ? <Check className="h-4 w-4" /> : s}
            </div>
            {s < 3 && (
              <div
                className={cn(
                  "h-0.5 w-12",
                  step > s ? "bg-primary" : "bg-secondary"
                )}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step 1: Describe */}
      {step === 1 && (
        <div className="space-y-6">
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <Sparkles className="h-6 w-6 text-primary" />
            </div>
            <h2 className="text-xl font-semibold">Describe Your Agent</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Tell us what you want your agent to do in plain English. Our AI
              will configure everything for you.
            </p>
          </div>

          <div className="rounded-lg border border-border bg-card p-6">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Example: Monitor UFC odds across major sportsbooks every morning. Alert me via Telegram when there's a line discrepancy of more than 5% on main card fights. Focus on underdogs with shifting lines."
              className="w-full resize-none rounded-md border border-border bg-background px-4 py-3 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              rows={6}
              maxLength={2000}
            />
            <div className="mt-2 flex items-center justify-between">
              <p
                className={cn(
                  "text-xs",
                  charCount < 10
                    ? "text-muted-foreground"
                    : charCount > 1800
                      ? "text-amber-500"
                      : "text-muted-foreground"
                )}
              >
                {charCount}/2000 characters
                {charCount < 10 && " (minimum 10)"}
              </p>
            </div>

            {error && (
              <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <Button
              className="mt-4 w-full gap-2"
              onClick={handleGenerate}
              disabled={!isDescriptionValid || isGenerating}
            >
              {isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Generate Agent
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Step 2: Review */}
      {step === 2 && generatedAgent && (
        <div className="space-y-6">
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <h2 className="text-xl font-semibold">Review Your Agent</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              We generated a configuration based on your description. Customize
              it before creating.
            </p>
          </div>

          <div className="space-y-4">
            {/* Agent name */}
            <div className="rounded-lg border border-border bg-card p-4">
              <label className="text-xs font-medium uppercase text-muted-foreground">
                Agent Name
              </label>
              <input
                type="text"
                value={nameOverride}
                onChange={(e) => setNameOverride(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {/* Description */}
            <div className="rounded-lg border border-border bg-card p-4">
              <label className="text-xs font-medium uppercase text-muted-foreground">
                Description
              </label>
              <p className="mt-1 text-sm">{generatedAgent.description}</p>
            </div>

            {/* Tools */}
            {generatedAgent.tools.length > 0 && (
              <div className="rounded-lg border border-border bg-card p-4">
                <label className="text-xs font-medium uppercase text-muted-foreground">
                  Tools
                </label>
                <div className="mt-2 flex flex-wrap gap-2">
                  {generatedAgent.tools.map((tool) => (
                    <span
                      key={tool}
                      className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Schedule */}
            <div className="rounded-lg border border-border bg-card p-4">
              <label className="text-xs font-medium uppercase text-muted-foreground">
                Schedule
              </label>
              <select
                value={schedulePreset}
                onChange={(e) => setSchedulePreset(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {SCHEDULE_PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}
                  </option>
                ))}
              </select>
              {schedulePreset === "custom" && (
                <input
                  type="text"
                  value={customCron}
                  onChange={(e) => setCustomCron(e.target.value)}
                  placeholder="e.g., 0 */6 * * *"
                  className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              )}
            </div>

            {/* Output channel */}
            <div className="rounded-lg border border-border bg-card p-4">
              <label className="text-xs font-medium uppercase text-muted-foreground">
                Output Channel
              </label>
              <select
                value={outputChannel}
                onChange={(e) => setOutputChannel(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {OUTPUT_CHANNELS.map((ch) => (
                  <option key={ch.value} value={ch.value}>
                    {ch.label}
                  </option>
                ))}
              </select>
            </div>

            {/* System prompt (collapsible) */}
            <div className="rounded-lg border border-border bg-card">
              <button
                type="button"
                onClick={() => setShowSystemPrompt(!showSystemPrompt)}
                className="flex w-full items-center justify-between p-4 text-left"
              >
                <span className="text-xs font-medium uppercase text-muted-foreground">
                  System Prompt
                </span>
                {showSystemPrompt ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </button>
              {showSystemPrompt && (
                <div className="border-t border-border px-4 pb-4 pt-3">
                  <pre className="whitespace-pre-wrap rounded-md bg-secondary p-3 text-xs leading-relaxed text-secondary-foreground">
                    {generatedAgent.system_prompt}
                  </pre>
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => {
                setStep(1);
                setError(null);
              }}
              className="gap-1.5"
            >
              <ChevronLeft className="h-4 w-4" />
              Edit Description
            </Button>
            <Button
              className="flex-1 gap-2"
              onClick={handleCreate}
              disabled={isCreating}
            >
              {isCreating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Check className="h-4 w-4" />
                  Create Agent
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: Success */}
      {step === 3 && generatedAgent && (
        <div className="space-y-6 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10">
            <Check className="h-8 w-8 text-emerald-500" />
          </div>
          <div>
            <h2 className="text-xl font-semibold">Agent Created</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Your agent &ldquo;{nameOverride || generatedAgent.name}&rdquo; is
              ready to go. You can trigger a manual run or let it run on its
              schedule.
            </p>
          </div>
          <div className="flex justify-center gap-3">
            <Button
              variant="outline"
              onClick={() => {
                setStep(1);
                setDescription("");
                setGeneratedAgent(null);
                setNameOverride("");
                setSchedulePreset("");
                setCustomCron("");
                setOutputChannel("none");
                setError(null);
              }}
            >
              Create Another
            </Button>
            <Button
              onClick={() => router.push(`/agents/${generatedAgent.id}`)}
              className="gap-1.5"
            >
              View Agent
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
