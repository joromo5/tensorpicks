const ENGINE_BASE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL ?? "http://localhost:8000";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  token?: string;
}

/**
 * API client for the Python agent engine.
 * Handles JSON serialization and auth token forwarding.
 */
export async function engineFetch<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, headers = {}, token } = options;

  const requestHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...headers,
  };

  if (token) {
    requestHeaders["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${ENGINE_BASE_URL}${path}`, {
    method,
    headers: requestHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => "Unknown error");
    throw new Error(
      `Engine API error ${response.status}: ${errorBody}`
    );
  }

  return response.json() as Promise<T>;
}
