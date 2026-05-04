import { Navigate } from "react-router-dom";

import { useAuth } from "@/app/providers/AuthProvider";
import { LandingPage } from "@/modules/auth/components/LandingPage";

/**
 * `/` is dual-purpose:
 *   - Anonymous → marketing landing page with the Sign-in CTA.
 *   - Authenticated → redirect into the role's home (S1: referral form
 *     for everyone except CANDIDATE; S2 wires per-role homes).
 */
export function HomeRedirect() {
  const { state } = useAuth();
  if (state.status === "authenticated") {
    return <Navigate to="/referrals/new" replace />;
  }
  return <LandingPage />;
}
