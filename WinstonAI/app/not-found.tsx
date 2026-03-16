import Link from "next/link";
import { FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-secondary">
        <FileQuestion className="h-8 w-8 text-muted-foreground" />
      </div>
      <div>
        <h1 className="text-2xl font-bold">Page not found</h1>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          The page you are looking for does not exist or has been moved.
        </p>
      </div>
      <Link href="/dashboard">
        <Button>Go to Dashboard</Button>
      </Link>
    </div>
  );
}
