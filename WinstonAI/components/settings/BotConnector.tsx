"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  AlertCircle,
  Check,
  ExternalLink,
  Loader2,
  MessageSquare,
  Plus,
  Trash2,
  Eye,
  EyeOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface StoredKey {
  id: string;
  service: string;
  hint: string;
  created_at: string;
}

type PlatformId = "telegram" | "slack" | "discord";

interface PlatformMeta {
  id: PlatformId;
  label: string;
  color: string;
  comingSoon: boolean;
}

const PLATFORMS: PlatformMeta[] = [
  { id: "telegram", label: "Telegram", color: "text-sky-500", comingSoon: false },
  { id: "slack", label: "Slack", color: "text-purple-500", comingSoon: true },
  { id: "discord", label: "Discord", color: "text-indigo-500", comingSoon: true },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function BotConnector() {
  const { getToken } = useAuth();

  const [storedKeys, setStoredKeys] = useState<StoredKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Connect form state
  const [connecting, setConnecting] = useState<PlatformId | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [saving, setSaving] = useState(false);

  // Remove state
  const [removing, setRemoving] = useState<PlatformId | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<PlatformId | null>(null);

  /* ---- helpers --------------------------------------------------- */

  const apiFetch = useCallback(
    async (path: string, opts: RequestInit = {}) => {
      const token = await getToken();
      const res = await fetch(path, {
        ...opts,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(opts.headers ?? {}),
        },
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "Unknown error");
        throw new Error(body);
      }
      return res.json();
    },
    [getToken],
  );

  const fetchKeys = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data: StoredKey[] = await apiFetch("/api/keys");
      setStoredKeys(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load connections.",
      );
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  /* ---- actions --------------------------------------------------- */

  const handleConnect = async (platform: PlatformId) => {
    if (!tokenInput.trim()) return;
    try {
      setSaving(true);
      setError(null);
      await apiFetch("/api/keys", {
        method: "POST",
        body: JSON.stringify({ service: platform, api_key: tokenInput }),
      });
      setConnecting(null);
      setTokenInput("");
      setShowToken(false);
      await fetchKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to connect bot.",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = async (platform: PlatformId) => {
    try {
      setRemoving(platform);
      setError(null);
      await apiFetch(`/api/keys/${platform}`, { method: "DELETE" });
      setConfirmRemove(null);
      await fetchKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to disconnect bot.",
      );
    } finally {
      setRemoving(null);
    }
  };

  /* ---- derived --------------------------------------------------- */

  const keyByService = storedKeys.reduce<Record<string, StoredKey>>(
    (acc, k) => {
      acc[k.service] = k;
      return acc;
    },
    {},
  );

  /* ---- render ---------------------------------------------------- */

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Bot Connections</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect messaging platform bots to receive alerts and interact with
          your agents.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="ml-2 text-sm">Loading connections...</span>
        </div>
      ) : (
        <div className="grid gap-3">
          {PLATFORMS.map((platform) => {
            const stored = keyByService[platform.id];
            const isConnected = !!stored;

            return (
              <div
                key={platform.id}
                className="rounded-lg border border-border bg-card p-4"
              >
                <div className="flex items-center justify-between">
                  {/* Left: icon + name + status */}
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-md border border-border",
                        platform.color,
                      )}
                    >
                      <MessageSquare className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{platform.label}</p>
                        {platform.comingSoon && (
                          <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                            Coming soon
                          </span>
                        )}
                      </div>
                      {isConnected ? (
                        <div className="flex items-center gap-1.5">
                          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                          <span className="text-xs text-muted-foreground">
                            Connected &middot; {stored.hint}
                          </span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/40" />
                          <span className="text-xs text-muted-foreground">
                            Not connected
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right: action buttons */}
                  <div className="flex items-center gap-2">
                    {isConnected ? (
                      confirmRemove === platform.id ? (
                        <div className="flex items-center gap-1">
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={removing === platform.id}
                            onClick={() => handleDisconnect(platform.id)}
                          >
                            {removing === platform.id ? (
                              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                            )}
                            Confirm
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setConfirmRemove(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setConfirmRemove(platform.id)}
                        >
                          <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                          Disconnect
                        </Button>
                      )
                    ) : platform.comingSoon ? (
                      <Button variant="outline" size="sm" disabled>
                        <Plus className="mr-1.5 h-3.5 w-3.5" />
                        Connect
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setConnecting(platform.id);
                          setTokenInput("");
                          setShowToken(false);
                        }}
                      >
                        <Plus className="mr-1.5 h-3.5 w-3.5" />
                        Connect
                      </Button>
                    )}
                  </div>
                </div>

                {/* Inline connect form for Telegram */}
                {connecting === platform.id && !platform.comingSoon && (
                  <div className="mt-4 space-y-3 border-t border-border pt-4">
                    {platform.id === "telegram" && (
                      <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground space-y-1.5">
                        <p className="font-medium text-foreground text-sm">
                          How to create a Telegram bot
                        </p>
                        <ol className="list-decimal list-inside space-y-1">
                          <li>
                            Open Telegram and search for{" "}
                            <a
                              href="https://t.me/BotFather"
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-0.5 text-primary hover:underline"
                            >
                              @BotFather
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          </li>
                          <li>
                            Send <code className="rounded bg-muted px-1 py-0.5">/newbot</code>{" "}
                            and follow the prompts
                          </li>
                          <li>Copy the bot token provided by BotFather</li>
                          <li>Paste it below and click Connect</li>
                        </ol>
                      </div>
                    )}

                    <label className="block text-sm font-medium">
                      Bot Token
                    </label>
                    <div className="relative">
                      <input
                        type={showToken ? "text" : "password"}
                        className="h-10 w-full rounded-md border border-input bg-background px-3 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                        placeholder="Paste your bot token here..."
                        value={tokenInput}
                        onChange={(e) => setTokenInput(e.target.value)}
                        autoFocus
                      />
                      <button
                        type="button"
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                        onClick={() => setShowToken(!showToken)}
                        tabIndex={-1}
                      >
                        {showToken ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        disabled={saving || !tokenInput.trim()}
                        onClick={() => handleConnect(platform.id)}
                      >
                        {saving ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Check className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        Connect
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setConnecting(null);
                          setTokenInput("");
                          setShowToken(false);
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
