const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onSessionLost: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function setSessionLostHandler(handler: (() => void) | null) {
  onSessionLost = handler;
}

export type TokenResponse = {
  access_token: string;
  expires_in: number;
  user: { id: string; email: string; full_name: string; status: string };
};

async function rawFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: "include" });
}

/** Exchange the refresh cookie for a new access token. One call at a time. */
export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const response = await rawFetch("/auth/refresh", { method: "POST" });
        if (!response.ok) {
          accessToken = null;
          return false;
        }
        accessToken = ((await response.json()) as TokenResponse).access_token;
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => {
          refreshing = null;
        }, 0);
      }
    })();
  }
  return refreshing;
}

async function toError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  return new ApiError(
    body?.message ?? response.statusText,
    response.status,
    body?.code,
    body?.details,
  );
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await rawFetch(path, init);
  const canRetry = !path.startsWith("/auth/");
  if (response.status === 401 && canRetry) {
    const body = await response.clone().json().catch(() => null);
    if (body?.code === "token_expired" || body?.code === "unauthorized") {
      if (await refreshSession()) {
        response = await rawFetch(path, init);
      } else {
        onSessionLost?.();
      }
    } else {
      onSessionLost?.();
    }
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  const type = response.headers.get("content-type") ?? "";
  return (type.includes("json") ? await response.json() : await response.text()) as T;
}

export const get = <T>(path: string) => request<T>(path);
export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const del = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "DELETE", body: body === undefined ? undefined : JSON.stringify(body) });

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const response = await rawFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw await toError(response);
  const data = (await response.json()) as TokenResponse;
  accessToken = data.access_token;
  return data;
}

export async function logout(): Promise<void> {
  await rawFetch("/auth/logout", { method: "POST" }).catch(() => undefined);
  accessToken = null;
}

/** Message shown to the user for any thrown value. */
export function errorMessage(error: unknown, fallback = "Có lỗi xảy ra"): string {
  if (error instanceof ApiError) {
    const details = error.details as { errors?: string[] } | undefined;
    if (details?.errors?.length) return `${error.message}: ${details.errors.join("; ")}`;
    return error.message;
  }
  return fallback;
}
