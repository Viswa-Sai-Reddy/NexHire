import { api } from "@/lib/axios";

export type UserRole =
  | "REFERRER"
  | "MENTOR"
  | "HR"
  | "IT_AD"
  | "ADMIN"
  | "PROGRAM_OWNER"
  | "CANDIDATE"
  | "SYSTEM";

export type RegistrableRole = Exclude<UserRole, "CANDIDATE" | "SYSTEM">;

export interface CurrentUser {
  user_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  can_mentor: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
  expires_in: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  full_name: string;
  password: string;
  role: RegistrableRole;
}

export async function loginWithCredentials(
  creds: LoginCredentials,
): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/login", creds);
  return data;
}

export async function registerUser(
  payload: RegisterPayload,
): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/register", payload);
  return data;
}

export async function refreshTokens(refreshToken: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return data;
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const { data } = await api.get<CurrentUser>("/auth/me");
  return data;
}

export async function logout(refreshToken: string | null): Promise<void> {
  await api.post(
    "/auth/logout",
    refreshToken ? { refresh_token: refreshToken } : undefined,
  );
}

export interface OutOfOfficeStatus {
  until: string | null;
}

export async function getOutOfOffice(): Promise<OutOfOfficeStatus> {
  const { data } = await api.get<OutOfOfficeStatus>("/auth/me/out-of-office");
  return data;
}

export async function setOutOfOffice(
  until: string | null,
): Promise<OutOfOfficeStatus> {
  const { data } = await api.put<OutOfOfficeStatus>(
    "/auth/me/out-of-office",
    { until },
  );
  return data;
}

export interface SkillsResponse {
  skills: string[];
}

export async function getMySkills(): Promise<SkillsResponse> {
  const { data } = await api.get<SkillsResponse>("/auth/me/skills");
  return data;
}

export async function setMySkills(skills: string[]): Promise<SkillsResponse> {
  const { data } = await api.put<SkillsResponse>("/auth/me/skills", { skills });
  return data;
}
