import { MsalProvider } from "@azure/msal-react";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { AuthProvider } from "@/app/providers/AuthProvider";
import { QueryProvider } from "@/app/providers/QueryProvider";
import { routes } from "@/app/routes";
import { getMsalInstance } from "@/lib/msal";

const router = createBrowserRouter(routes);

/**
 * App composition root.
 *
 * Provider order:
 *   MsalProvider  — needed by AuthProvider's `useMsal()`.
 *   QueryProvider — needed by referral hooks under the router.
 *   AuthProvider  — exposes the NexHire JWT context to the gate +
 *                   the SignedInShell.
 *   RouterProvider — drives all routes from `routes/index.tsx`.
 */
export function App() {
  const msal = getMsalInstance();
  return (
    <MsalProvider instance={msal}>
      <QueryProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </QueryProvider>
    </MsalProvider>
  );
}
