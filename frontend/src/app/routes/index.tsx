import { Navigate, Outlet, type RouteObject } from "react-router-dom";

import { AuthGate } from "@/modules/auth/components/AuthGate";
import { HomeRedirect } from "@/modules/auth/components/HomeRedirect";
import { CandidateAccessPage } from "@/modules/candidate/components/CandidateAccessPage";
import { CandidateStatusPage } from "@/modules/candidate/components/CandidateStatusPage";
import { JoiningFormPage } from "@/modules/candidate/components/JoiningFormPage";
import { HrDashboardPage } from "@/modules/hr/components/HrDashboardPage";
import { HrReviewPage } from "@/modules/hr/components/HrReviewPage";
import { MentorActionPage } from "@/modules/mentor/components/MentorActionPage";
import { ReferralFormPage } from "@/modules/referral/components/ReferralFormPage";

/**
 * Top-level route table.
 *
 *  Public:
 *    /                     — marketing landing + Sign in
 *    /action/mentor        — token-gated mentor action page (no SSO)
 *
 *  Authenticated (AuthGate wraps via layout route):
 *    /referrals/new        — submit a new referral
 *    /referrals            — alias for /referrals/new
 *    /hr                   — HR dashboard (S11; HR/PO permission via API)
 *    /hr/referrals/:id     — HR review panel (S12)
 */
export const routes: RouteObject[] = [
  { path: "/", element: <HomeRedirect /> },
  { path: "/action/mentor", element: <MentorActionPage /> },
  { path: "/candidate/access", element: <CandidateAccessPage /> },
  { path: "/candidate/joining-form", element: <JoiningFormPage /> },
  { path: "/candidate/status", element: <CandidateStatusPage /> },
  { path: "/candidate/nda", element: <CandidateStatusPage /> },
  { path: "/candidate/certificate", element: <CandidateStatusPage /> },
  {
    element: (
      <AuthGate>
        <Outlet />
      </AuthGate>
    ),
    children: [
      { path: "/referrals/new", element: <ReferralFormPage /> },
      { path: "/referrals", element: <Navigate to="/referrals/new" replace /> },
      { path: "/hr", element: <HrDashboardPage /> },
      { path: "/hr/referrals/:referralId", element: <HrReviewPage /> },
    ],
  },
];
