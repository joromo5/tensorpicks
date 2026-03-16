export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account and platform preferences.
        </p>
      </div>

      <div className="max-w-2xl space-y-4">
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold">Profile</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Profile settings are managed through Clerk. Click your avatar to
            update your profile.
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold">API Keys</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Exchange API key management coming soon.
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-lg font-semibold">Notifications</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Notification preferences coming soon.
          </p>
        </div>
      </div>
    </div>
  );
}
