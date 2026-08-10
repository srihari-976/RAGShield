import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { IdentityInfo } from "../lib/types";
import { clearTokens, getAccessToken, getIdentity, login as apiLogin } from "../lib/api";

interface AuthCtx {
  identity: IdentityInfo | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  refresh: () => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>({
  identity: null,
  loading: true,
  login: async () => {},
  refresh: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<IdentityInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getAccessToken()) {
      setIdentity(null);
      setLoading(false);
      return;
    }
    try {
      setIdentity(await getIdentity());
    } catch {
      setIdentity(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin(username, password);
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    clearTokens();
    setIdentity(null);
    window.location.href = "/login";
  }, []);

  return (
    <Ctx.Provider value={{ identity, loading, login, refresh, logout }}>{children}</Ctx.Provider>
  );
}

export function useAuth() {
  return useContext(Ctx);
}

export function usePerm(perm: string): boolean {
  const { identity } = useAuth();
  if (!identity) return false;
  return identity.is_admin || identity.permissions.includes(perm);
}
