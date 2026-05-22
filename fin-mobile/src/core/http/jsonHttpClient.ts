/**
 * Transport-only JSON client — same responsibility split as web `HttpClient`.
 */
export type JsonRequest = {
  path: string;
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
};

export type JsonHttpClient = {
  requestJson<T>(req: JsonRequest): Promise<T>;
};

export function createJsonHttpClient(options: {
  getBaseUrl: () => string;
  credentials?: RequestCredentials;
}): JsonHttpClient {
  const credentials = options.credentials ?? "include";

  return {
    async requestJson<T>(req: JsonRequest): Promise<T> {
      const base = options.getBaseUrl().replace(/\/$/, "");
      if (!base) {
        throw new Error("Set EXPO_PUBLIC_API_BASE_URL in .env or app config.");
      }
      const path = req.path.startsWith("/") ? req.path : `/${req.path}`;
      const url = `${base}${path}`;
      const headers: Record<string, string> = { Accept: "application/json" };
      if (req.body !== undefined) {
        headers["Content-Type"] = "application/json";
      }
      const res = await fetch(url, {
        method: req.method ?? "GET",
        headers,
        body: req.body !== undefined ? JSON.stringify(req.body) : undefined,
        credentials,
      });
      if (res.status === 204) {
        return undefined as T;
      }
      const text = await res.text();
      if (!res.ok) {
        throw new Error(text || res.statusText || "Request failed");
      }
      if (!text) return undefined as T;
      return JSON.parse(text) as T;
    },
  };
}
