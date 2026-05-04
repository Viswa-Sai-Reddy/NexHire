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
import { useMsal } from "@azure/msal-react";
import { InteractionStatus } from "@azure/msal-browser";

import { setAccessToken } from "@/lib/axios";
import {
  type CurrentUser,
  type TokenResponse,
  getCurrentUser,
  loginWithAzureToken,
  logout as apiLogout,
} from "@/modules/auth/api";
import { loginRequest } from "@/lib/msal";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "error"; message: string };

interface AuthContextValue {
  state: AuthState;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside <AuthProvider>");
  return ctx;
}

export function AuthProvider({ children }: PropsWithChildren) {
  const { instance: msal, accounts, inProgress } = useMsal();
  const [state, setState] = useState<AuthState>({ status: "loading" });
  // Refresh token never crosses React state — kept in a ref so it can't
  // accidentally end up in DevTools snapshots.
  const refreshTokenRef = useRef<string | null>(null);

  const exchangeAndLoad = useCallback(async (idToken: string) => {
    try {
      const tokens: TokenResponse = await loginWithAzureToken(idToken);
      setAccessToken(tokens.access_token);
      refreshTokenRef.current = tokens.refresh_token;
      const user = await getCurrentUser();
      setState({ status: "authenticated", user });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Authentication failed.";
      setState({ status: "error", message });
    }
  }, []);

  // On initial mount, look at MSAL's account state and either
  // silently reuse or remain anonymous.
  useEffect(() => {
    if (inProgress !== InteractionStatus.None) return;

    const account = accounts[0];
    if (!account) {
      setState({ status: "anonymous" });
      return;
    }

    void msal
      .acquireTokenSilent({ ...loginRequest, account })
      .then((result) => exchangeAndLoad(result.idToken))
      .catch(() => setState({ status: "anonymous" }));
  }, [accounts, inProgress, msal, exchangeAndLoad]);

  const signIn = useCallback(async () => {
    setState({ status: "loading" });
    await msal.loginRedirect(loginRequest);
  }, [msal]);

  const signOut = useCallback(async () => {
    try {
      await apiLogout(refreshTokenRef.current);
    } catch {
      // Best-effort.
    }
    setAccessToken(null);
    refreshTokenRef.current = null;
    await msal.logoutRedirect();
    setState({ status: "anonymous" });
  }, [msal]);

  const value = useMemo<AuthContextValue>(
    () => ({ state, signIn, signOut }),
    [state, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
