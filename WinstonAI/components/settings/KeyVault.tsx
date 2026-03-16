"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  Key,
  Eye,
  EyeOff,
  Check,
  X,
  AlertCircle,
  Loader2,
  Plus,
  Trash2,
  ShieldCheck,
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

type ServiceId = "anthropic" | "openai" | "groq";

interface ServiceMeta {
  id: ServiceId;
  label: string;
  color: string;
  placeholder: string;
}

const SERVICES: ServiceMeta[] = [
  {
    id: "anthropic",
    label: "Anthropic",
    color: "text-amber-500",
    placeholder: "sk-ant-api03-...",
  },
  {
    id: "openai",
    label: "OpenAI",
    color: "text-emerald-500",
    placeholder: "sk-proj-...",
  },
  {
    id: "groq",
    label: "Groq",
    color: "text-blue-500",
    placeholder: "gsk_...",
  },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function KeyVault() {
  const { getToken } = useAuth();

  const [storedKeys, setStoredKeys] = useState<StoredKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add-key form state
  const [addingService, setAddingService] = useState<ServiceId | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);

  // Per-service action states
  const [validating, setValidating] = useState<ServiceId | null>(null);
  const [validationResult, setValidationResult] = useState<
    Record<string, boolean | null>
  >({});
  const [removing, setRemoving] = useState<ServiceId | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<ServiceId | null>(null);

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
        err instanceof Error ? err.message : "Failed to load API keys.",
      );
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  /* ---- actions --------------------------------------------------- */

  const handleSaveKey = async () => {
    if (!addingService || !keyInput.trim()) return;
    try {
      setSaving(true);
      setError(null);
      await apiFetch("/api/keys", {
        method: "POST",
        body: JSON.stringify({ service: addingService, api_key: keyInput }),
      });
      setAddingService(null);
      setKeyInput("");
      setShowKey(false);
      await fetchKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save API key.",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async (service: ServiceId) => {
    try {
      setValidating(service);
      setValidationResult((prev) => ({ ...prev, [service]: null }));
      const data = await apiFetch(`/api/keys/${service}/validate`, {
        method: "POST",
      });
      setValidationResult((prev) => ({ ...prev, [service]: data.valid }));
    } catch {
      setValidationResult((prev) => ({ ...prev, [service]: false }));
    } finally {
      setValidating(null);
    }
  };

  const handleRemove = async (service: ServiceId) => {
    try {
      setRemoving(service);
      setError(null);
      await apiFetch(`/api/keys/${service}`, { method: "DELETE" });
      setConfirmRemove(null);
      setValidationResult((prev) => {
        const next = { ...prev };
        delete next[service];
        return next;
      });
      await fetchKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to remove API key.",
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
        <h2 className="text-lg font-semibold">LLM API Keys</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Bring your own keys (BYOK) for the LLM providers your agents use.
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
          <span className="ml-2 text-sm">Loading keys...</span>
        </div>
      ) : (
        <div className="grid gap-3">
          {SERVICES.map((svc) => {
            const stored = keyByService[svc.id];
            const isConnected = !!stored;
            const vResult = validationResult[svc.id];

            return (
              <div
                key={svc.id}
                className="rounded-lg border border-border bg-card p-4"
              >
                <div className="flex items-center justify-between">
                  {/* Left: icon + name + status */}
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-md border border-border",
                        svc.color,
                      )}
                    >
                      <Key className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{svc.label}</p>
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
                      <>
                        {/* Validation result indicator */}
                        {vResult === true && (
                          <span className="flex items-center gap-1 text-xs text-emerald-500">
                            <Check className="h-3.5 w-3.5" /> Valid
                          </span>
                        )}
                        {vResult === false && (
                          <span className="flex items-center gap-1 text-xs text-destructive">
                            <X className="h-3.5 w-3.5" /> Invalid
                          </span>
                        )}

                        <Button
                          variant="outline"
                          size="sm"
                          disabled={validating === svc.id}
                          onClick={() => handleValidate(svc.id)}
                        >
                          {validating === svc.id ? (
                            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
                          )}
                          Validate
                        </Button>

                        {confirmRemove === svc.id ? (
                          <div className="flex items-center gap-1">
                            <Button
                              variant="destructive"
                              size="sm"
                              disabled={removing === svc.id}
                              onClick={() => handleRemove(svc.id)}
                            >
                              {removing === svc.id ? (
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
                            onClick={() => setConfirmRemove(svc.id)}
                          >
                            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                            Remove
                          </Button>
                        )}
                      </>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setAddingService(svc.id);
                          setKeyInput("");
                          setShowKey(false);
                        }}
                      >
                        <Plus className="mr-1.5 h-3.5 w-3.5" />
                        Add Key
                      </Button>
                    )}
                  </div>
                </div>

                {/* Inline add-key form */}
                {addingService === svc.id && (
                  <div className="mt-4 space-y-3 border-t border-border pt-4">
                    <label className="block text-sm font-medium">
                      {svc.label} API Key
                    </label>
                    <div className="relative">
                      <input
                        type={showKey ? "text" : "password"}
                        className="h-10 w-full rounded-md border border-input bg-background px-3 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                        placeholder={svc.placeholder}
                        value={keyInput}
                        onChange={(e) => setKeyInput(e.target.value)}
                        autoFocus
                      />
                      <button
                        type="button"
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                        onClick={() => setShowKey(!showKey)}
                        tabIndex={-1}
                      >
                        {showKey ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        disabled={saving || !keyInput.trim()}
                        onClick={handleSaveKey}
                      >
                        {saving && (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        )}
                        Save Key
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setAddingService(null);
                          setKeyInput("");
                          setShowKey(false);
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
