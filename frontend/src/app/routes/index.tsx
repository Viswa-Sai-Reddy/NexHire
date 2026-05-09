import { Outlet, type RouteObject } from "react-router-dom";

import { AuthGate } from "@/modules/auth/components/AuthGate";
import { HomeRedirect } from "@/modules/auth/components/HomeRedirect";
import { RegisterPage } from "@/modules/auth/components/RegisterPage";
import { AuditSlaReportPage } from "@/modules/admin/components/AuditSlaReportPage";
import { ConfigPanelPage } from "@/modules/admin/components/ConfigPanelPage";
import { ExecutiveDashboardPage } from "@/modules/admin/components/ExecutiveDashboardPage";
import { CandidateAccessPage } from "@/modules/candidate/components/CandidateAccessPage";
import { CandidateLoginPage } from "@/modules/candidate/components/CandidateLoginPage";
import { CandidateNdaPage } from "@/modules/candidate/components/CandidateNdaPage";
import { CandidateStatusPage } from "@/modules/candidate/components/CandidateStatusPage";
import { JoiningFormPage } from "@/modules/candidate/components/JoiningFormPage";
import { HrDashboardPage } from "@/modules/hr/components/HrDashboardPage";
import { HrInternsPage } from "@/modules/hr/components/HrInternsPage";
import { HrReviewPage } from "@/modules/hr/components/HrReviewPage";
import { MentorActionPage } from "@/modules/mentor/components/MentorActionPage";
import { MentorWorkspacePage } from "@/modules/mentor/components/MentorWorkspacePage";
import { MyReferralsPage } from "@/modules/referral/components/MyReferralsPage";
import { ReferralFormPage } from "@/modules/referral/components/ReferralFormPage";
import { TaskQueuePage } from "@/modules/tasks/components/TaskQueuePage";

/**
 * Top-level route table.
 *
 *  Public:
 *    /                     — marketing landing + Sign in
 *    /action/mentor        — token-gated mentor action page (no SSO)
 *
 *  Authenticated (AuthGate wraps via layout route):
 *    /referrals/new        — submit a new referral
 *    /referrals            — list of submitted referrals (with terminate)
 *    /referrals/mine       — same as /referrals
 *    /mentor/interns       — S18/S19/S20 mentor workspace
 *    /hr                   — HR dashboard (S11)
 *    /hr/referrals/:id     — HR review panel (S12)
 *    /tasks                — S21/S22 IT/Admin task queue
 *    /admin                — S23 executive overview + AI-9 chatbot
 *    /admin/audit          — S24 audit + SLA report
 *    /admin/config         — S25 program-owner config panel
 */
export const routes: RouteObject[] = [
  { path: "/", element: <HomeRedirect /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/action/mentor", element: <MentorActionPage /> },
  { path: "/candidate/access", element: <CandidateAccessPage /> },
  { path: "/candidate/login", element: <CandidateLoginPage /> },
  { path: "/candidate/joining-form", element: <JoiningFormPage /> },
  { path: "/candidate/status", element: <CandidateStatusPage /> },
  { path: "/candidate/nda", element: <CandidateNdaPage /> },
  { path: "/candidate/certificate", element: <CandidateStatusPage /> },
  {
    element: (
      <AuthGate>
        <Outlet />
      </AuthGate>
    ),
    children: [
      { path: "/referrals/new", element: <ReferralFormPage /> },
      { path: "/referrals", element: <MyReferralsPage /> },
      { path: "/referrals/mine", element: <MyReferralsPage /> },
      { path: "/mentor/interns", element: <MentorWorkspacePage /> },
      { path: "/hr", element: <HrDashboardPage /> },
      { path: "/hr/interns", element: <HrInternsPage /> },
      { path: "/hr/referrals/:referralId", element: <HrReviewPage /> },
      { path: "/tasks", element: <TaskQueuePage /> },
      { path: "/admin", element: <ExecutiveDashboardPage /> },
      { path: "/admin/audit", element: <AuditSlaReportPage /> },
      { path: "/admin/config", element: <ConfigPanelPage /> },
    ],
  },
];
