import { ApiError } from "@lib/api/ApiError";
import { isApiConfigured } from "@lib/env";
import type { HttpClient } from "@lib/http/HttpClient";
import { z } from "zod";

const AuthSessionResponseSchema = z.object({
  authenticated: z.boolean(),
  user: z
    .object({
      id: z.string(),
      email: z.string().optional(),
    })
    .optional(),
});

export type AuthMode = "none" | "demo" | "api";

export type AuthHydration = {
  isAuthenticated: boolean;
  mode: AuthMode;
};

/**
 * Session lifecycle without React (Single Responsibility / testable).
 */
export interface AuthCoordinator {
  hydrate(): Promise<AuthHydration>;
  signInDemo(): Promise<void>;
  signInWithApi(email: string, password: string): Promise<void>;
  registerWithApi(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
}

export function createLiveAuthCoordinator(deps: {
  http: HttpClient;
  demoStorageKey: string;
}): AuthCoordinator {
  const { http, demoStorageKey } = deps;

  const hasApi = () => isApiConfigured();

  return {
    async hydrate(): Promise<AuthHydration> {
      if (hasApi()) {
        try {
          const data = await http.requestJson<unknown>({
            path: "/v1/auth/session",
            method: "GET",
          });
          const parsed = AuthSessionResponseSchema.safeParse(data);
          if (parsed.success) {
            if (parsed.data.authenticated) {
              return { isAuthenticated: true, mode: "api" };
            }
            /* API reachable and reports logged out — do not fall through to demo session. */
            return { isAuthenticated: false, mode: "none" };
          }
        } catch (e) {
          if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
            return { isAuthenticated: false, mode: "none" };
          }
          /* else: network / 5xx — fall through to demo session for local dev */
        }
      }

      if (typeof window !== "undefined" && window.localStorage.getItem(demoStorageKey) === "1") {
        return { isAuthenticated: true, mode: "demo" };
      }

      return { isAuthenticated: false, mode: "none" };
    },

    async signInDemo(): Promise<void> {
      if (typeof window !== "undefined") {
        window.localStorage.setItem(demoStorageKey, "1");
      }
    },

    async signInWithApi(email: string, password: string): Promise<void> {
      if (!hasApi()) throw new Error("API is not configured (set VITE_API_BASE_URL for local Vite).");
      await http.requestJson<unknown>({
        path: "/v1/auth/login",
        method: "POST",
        body: { email, password },
      });
    },

    async registerWithApi(email: string, password: string): Promise<void> {
      if (!hasApi()) throw new Error("API is not configured (set VITE_API_BASE_URL for local Vite).");
      await http.requestJson<unknown>({
        path: "/v1/auth/register",
        method: "POST",
        body: { email, password },
      });
    },

    async signOut(): Promise<void> {
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(demoStorageKey);
      }
      if (hasApi()) {
        try {
          await http.requestJson<unknown>({
            path: "/v1/auth/logout",
            method: "POST",
          });
        } catch {
          /* best-effort logout */
        }
      }
    },
  };
}
