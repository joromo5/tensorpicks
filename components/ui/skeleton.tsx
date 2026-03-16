import { cn } from "@/lib/utils";

interface SkeletonProps {
  variant?: "text" | "circle" | "card";
  className?: string;
}

export function Skeleton({ variant = "text", className }: SkeletonProps) {
  const baseStyles = "animate-pulse rounded bg-muted";

  const variantStyles: Record<string, string> = {
    text: "h-4 w-full rounded-md",
    circle: "h-10 w-10 rounded-full",
    card: "h-32 w-full rounded-lg",
  };

  return (
    <div className={cn(baseStyles, variantStyles[variant], className)} />
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Skeleton variant="circle" />
        <div className="flex-1 space-y-2">
          <Skeleton variant="text" className="h-4 w-1/3" />
          <Skeleton variant="text" className="h-3 w-2/3" />
        </div>
      </div>
      <Skeleton variant="text" className="h-3 w-full" />
      <Skeleton variant="text" className="h-3 w-4/5" />
    </div>
  );
}

export function SkeletonList({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} variant="text" className="h-12 w-full rounded-lg" />
      ))}
    </div>
  );
}
