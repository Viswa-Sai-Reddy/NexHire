import axios, { type AxiosError } from "axios";

/**
 * NexHire API client.
 *
 * - `Authorization` header set from the in-memory JWT (set by AuthProvider).
 * - `X-Request-Id` propagated when the SPA already has one (for traces).
 * - All errors deserialized into the standard envelope from
 *   `error_handler.py` so callers get a typed `NexHireApiError` instead
 *   of an opaque AxiosError.
 */

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export interface NexHireErrorEnvelope {
  error: {
    code: string;
    category:
      | "VALIDATION_ERROR"
      | "AUTH_ERROR"
      | "BUSINESS_RULE_ERROR"
      | "INTEGRATION_ERROR"
      | "SYSTEM_ERROR";
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
    timestamp: string;
    docs_url?: string;
  };
}

export class NexHireApiError extends Error {
  readonly code: string;
  readonly category: NexHireErrorEnvelope["error"]["category"];
  readonly status: number;
  readonly details: Record<string, unknown>;
  readonly requestId?: string;

  constructor(envelope: NexHireErrorEnvelope, status: number) {
    super(envelope.error.message);
    this.name = "NexHireApiError";
    this.code = envelope.error.code;
    this.category = envelope.error.category;
    this.status = status;
    this.details = envelope.error.details ?? {};
    if (envelope.error.request_id !== undefined) {
      this.requestId = envelope.error.request_id;
    }
  }
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: false,
  timeout: 30_000,
});

api.interceptors.request.use((config) => {
  if (accessToken !== null) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<NexHireErrorEnvelope>) => {
    const data = error.response?.data;
    if (data && "error" in data) {
      throw new NexHireApiError(data, error.response?.status ?? 500);
    }
    // Network / unknown — synthesize a system-error envelope.
    throw new NexHireApiError(
      {
        error: {
          code: "NETWORK_ERROR",
          category: "SYSTEM_ERROR",
          message:
            "Connection lost. Please check your network and retry.",
          timestamp: new Date().toISOString(),
        },
      },
      0,
    );
  },
);
