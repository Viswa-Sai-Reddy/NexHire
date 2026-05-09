import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { AuthProvider } from "@/app/providers/AuthProvider";
import { QueryProvider } from "@/app/providers/QueryProvider";
import { routes } from "@/app/routes";

const router = createBrowserRouter(routes);

/**
 * App composition root.
 *
 * Provider order:
 *   QueryProvider — needed by referral hooks under the router.
 *   AuthProvider  — exposes the NexHire JWT context to the gate +
 *                   the SignedInShell.
 *   RouterProvider — drives all routes from `routes/index.tsx`.
 */
export function App() {
  return (
    <QueryProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryProvider>
  );
}
