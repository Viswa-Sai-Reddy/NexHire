import {
  type PropsWithChildren,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { setAccessToken } from "@/lib/axios";
import {
  type CurrentUser,
  type RegisterPayload,
  type TokenResponse,
  getCurrentUser,
  loginWithCredentials,
  logout as apiLogout,
  registerUser,
} from "@/modules/auth/api";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "error"; message: string };

interface AuthContextValue {
  state: AuthState;
  signIn: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside <AuthProvider>");
  return ctx;
}

function extractApiMessage(err: unknown): string {
  // Pull a useful message out of an Axios error response, falling back
  // to the JS error message and finally a generic copy.
  if (typeof err === "object" && err !== null && "response" in err) {
    const resp = (err as { response?: { data?: { user_message?: string; detail?: string } } })
      .response;
    return (
      resp?.data?.user_message ??
      resp?.data?.detail ??
      (err instanceof Error ? err.message : "Authentication failed.")
    );
  }
  return err instanceof Error ? err.message : "Authentication failed.";
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<AuthState>({ status: "anonymous" });
  // Refresh token never crosses React state — kept in a ref so it can't
  // accidentally end up in DevTools snapshots.
  const refreshTokenRef = useRef<string | null>(null);

  const applyTokens = useCallback(async (tokens: TokenResponse) => {
    setAccessToken(tokens.access_token);
    refreshTokenRef.current = tokens.refresh_token;
    const user = await getCurrentUser();
    setState({ status: "authenticated", user });
  }, []);

  const signIn = useCallback(
    async (email: string, password: string) => {
      setState({ status: "loading" });
      try {
        const tokens = await loginWithCredentials({ email, password });
        await applyTokens(tokens);
      } catch (err) {
        setState({ status: "error", message: extractApiMessage(err) });
      }
    },
    [applyTokens],
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      setState({ status: "loading" });
      try {
        const tokens = await registerUser(payload);
        await applyTokens(tokens);
      } catch (err) {
        setState({ status: "error", message: extractApiMessage(err) });
      }
    },
    [applyTokens],
  );

  const signOut = useCallback(async () => {
    try {
      await apiLogout(refreshTokenRef.current);
    } catch {
      // Best-effort.
    }
    setAccessToken(null);
    refreshTokenRef.current = null;
    setState({ status: "anonymous" });
  }, []);

  // Make sure the axios baseline is cleared if we mount with no token.
  useEffect(() => {
    setAccessToken(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ state, signIn, register, signOut }),
    [state, signIn, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
