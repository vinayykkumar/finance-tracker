import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createAuthApi, type SessionUser } from "../api/authApi";
import { createJsonHttpClient } from "../core/http/jsonHttpClient";
import { getApiBaseUrl, getDefaultTimeoutMs, isApiConfigured } from "../core/config";
import { ApiError } from "../core/api/ApiError";

type AuthContextValue = {
  user: SessionUser | null;
  isAuthenticated: boolean;
  isHydrated: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function createHttp() {
  return createJsonHttpClient({
    getBaseUrl: getApiBaseUrl,
    defaultTimeoutMs: getDefaultTimeoutMs(),
  });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const http = useMemo(() => createHttp(), []);
  const authApi = useMemo(() => createAuthApi(http), [http]);

  const [user, setUser] = useState<SessionUser | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);

  const applySession = useCallback(async () => {
    if (!isApiConfigured()) {
      setUser(null);
      return;
    }
    try {
      const s = await authApi.session();
      setUser(s.authenticated && s.user ? s.user : null);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        setUser(null);
        return;
      }
      setUser(null);
    }
  }, [authApi]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await applySession();
      if (!cancelled) setIsHydrated(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [applySession]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      await authApi.login(email, password);
      await applySession();
    },
    [authApi, applySession]
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await authApi.register(email, password);
      await applySession();
    },
    [authApi, applySession]
  );

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* best-effort */
    }
    setUser(null);
  }, [authApi]);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isHydrated,
      signIn,
      register,
      signOut,
      refreshSession: applySession,
    }),
    [user, isHydrated, signIn, register, signOut, applySession]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
