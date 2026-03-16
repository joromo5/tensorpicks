"use client";

import KeyVault from "@/components/settings/KeyVault";
import BotConnector from "@/components/settings/BotConnector";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account and platform preferences.
        </p>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* Profile — managed by Clerk */}
        <section className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold">Profile</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Profile settings are managed through Clerk. Click your avatar in the
            sidebar to update your profile, email, or password.
          </p>
        </section>

        {/* LLM API Keys */}
        <section className="rounded-lg border border-border bg-card p-6">
          <KeyVault />
        </section>

        {/* Bot Connections */}
        <section className="rounded-lg border border-border bg-card p-6">
          <BotConnector />
        </section>
      </div>
    </div>
  );
}
