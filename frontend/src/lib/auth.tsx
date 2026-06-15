import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  api,
  bootstrapSession,
  loginRequest,
  logoutRequest,
  registerFirstAdminRequest,
  setOnAuthLost,
} from "./apiClient";
import type { UserOut } from "../types/api";

interface AuthState {
  user: UserOut | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  registerFirstAdmin: (email: string, password: string, fullName: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    const me = await api.get<UserOut>("/me");
    setUser(me);
  }, []);

  useEffect(() => {
    setOnAuthLost(() => setUser(null));
    (async () => {
      try {
        if (await bootstrapSession()) {
          await loadMe();
        }
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [loadMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      await loginRequest(email, password);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    await logoutRequest();
    setUser(null);
  }, []);

  const registerFirstAdmin = useCallback(
    async (email: string, password: string, fullName: string) => {
      await registerFirstAdminRequest(email, password, fullName);
      await loadMe();
    },
    [loadMe],
  );

  const value = useMemo(
    () => ({ user, loading, login, logout, registerFirstAdmin }),
    [user, loading, login, logout, registerFirstAdmin],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth muss innerhalb von AuthProvider verwendet werden");
  return ctx;
}
