import { Navigate } from "react-router-dom";

import { useAuth } from "@/app/providers/AuthProvider";
import type { UserRole } from "@/modules/auth/api";
import { LandingPage } from "@/modules/auth/components/LandingPage";

/**
 * `/` is dual-purpose:
 *   - Anonymous → marketing landing page with the Sign-in CTA.
 *   - Authenticated → redirect to the role's home page.
 */
const ROLE_HOME: Record<UserRole, string> = {
  REFERRER: "/referrals/new",
  MENTOR: "/mentor/interns",
  HR: "/hr",
  PROGRAM_OWNER: "/admin",
  IT_AD: "/tasks",
  ADMIN: "/tasks",
  CANDIDATE: "/candidate/status",
  SYSTEM: "/referrals/new",
};

export function HomeRedirect() {
  const { state } = useAuth();
  if (state.status === "authenticated") {
    return <Navigate to={ROLE_HOME[state.user.role]} replace />;
  }
  return <LandingPage />;
}
