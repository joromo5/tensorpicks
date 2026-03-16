export default function AgentDetailPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Agent {params.id}
        </h1>
        <p className="text-muted-foreground">
          Agent performance, configuration, and trade history.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {[
          { label: "Status", value: "Inactive" },
          { label: "Trades", value: "0" },
          { label: "P&L", value: "$0.00" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-border bg-card p-6"
          >
            <p className="text-sm text-muted-foreground">{stat.label}</p>
            <p className="mt-2 text-xl font-bold">{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <p className="text-sm text-muted-foreground">
          Detailed agent view coming soon.
        </p>
      </div>
    </div>
  );
}
