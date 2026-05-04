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

export async function loginWithAzureToken(idToken: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/login", {
    azure_id_token: idToken,
  });
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
