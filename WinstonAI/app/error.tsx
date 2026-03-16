"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
        <AlertTriangle className="h-8 w-8 text-destructive" />
      </div>
      <div>
        <h1 className="text-2xl font-bold">Something went wrong</h1>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          An unexpected error occurred. Please try again or return to the
          dashboard.
        </p>
      </div>
      <div className="flex gap-3">
        <Button onClick={reset} variant="outline">
          Try again
        </Button>
        <Link href="/dashboard">
          <Button>Go to Dashboard</Button>
        </Link>
      </div>
    </div>
  );
}
