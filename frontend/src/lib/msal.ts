import {
  type Configuration,
  type SilentRequest,
  type RedirectRequest,
  PublicClientApplication,
} from "@azure/msal-browser";

/**
 * MSAL configuration for Azure AD SSO.
 *
 * Flow:
 *  1. user clicks "Sign in" → loginRedirect() → Azure AD login page.
 *  2. AAD redirects back to /auth/callback with an ID token.
 *  3. AuthProvider catches the redirect, posts the id_token to
 *     /api/v1/auth/login, gets the NexHire JWT, stores it in memory.
 */
const tenantId = import.meta.env.VITE_AZURE_AD_TENANT_ID;
const clientId = import.meta.env.VITE_AZURE_AD_CLIENT_ID;
const redirectUri = import.meta.env.VITE_AZURE_AD_REDIRECT_URI;

export const msalConfig: Configuration = {
  auth: {
    clientId,
    authority: tenantId
      ? `https://login.microsoftonline.com/${tenantId}`
      : "https://login.microsoftonline.com/common",
    redirectUri,
    postLogoutRedirectUri: window.location.origin,
    navigateToLoginRequestUrl: true,
  },
  cache: {
    // sessionStorage is recommended over localStorage to limit XSS reach.
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      logLevel: import.meta.env.DEV ? 3 : 1,
      loggerCallback: (_lvl, msg) => {
        if (import.meta.env.DEV) {
          // eslint-disable-next-line no-console
          console.log("[MSAL]", msg);
        }
      },
    },
  },
};

/** OIDC scopes — `openid profile email` give us the ID-token claims. */
export const loginRequest: RedirectRequest = {
  scopes: ["openid", "profile", "email"],
};

/** Silent acquisition for refresh — used by axios interceptor. */
export const silentRequest: SilentRequest = {
  scopes: ["openid", "profile", "email"],
};

/**
 * Single MSAL instance for the whole app. Initialized lazily so unit
 * tests that don't exercise auth don't need real tenant config.
 */
let _instance: PublicClientApplication | null = null;

export function getMsalInstance(): PublicClientApplication {
  if (_instance === null) {
    _instance = new PublicClientApplication(msalConfig);
  }
  return _instance;
}
