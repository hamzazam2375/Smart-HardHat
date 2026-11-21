// Server-only client for the FastAPI backend. The browser never calls the API directly;
// the session token stays in an HttpOnly cookie and is forwarded as a Bearer token.
// Import only from server code (server components, server actions, lib/session.ts).

const BASE = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

/** Backend unreachable or failing. Callers must not treat this as "no data" or "safe". */
export class ApiUnavailableError extends Error {
  constructor(detail: string) {
    super(`Backend unavailable: ${detail}`);
    this.name = "ApiUnavailableError";
  }
}

/** 401/403 from the backend. */
export class ApiAuthError extends Error {
  constructor(readonly status: number) {
    super(`Backend refused the request (${status})`);
    this.name = "ApiAuthError";
  }
}

/** 400/404/409/422: the request was refused (not found, conflict, invalid). `detail` is the backend body. */
export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `Request refused (${status})`);
    this.name = "ApiRequestError";
  }
}

const REFUSED = new Set([400, 404, 409, 413, 422]);

export async function api<T>(path: string, init: RequestInit & { token?: string } = {}): Promise<T> {
  const { token, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...rest,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(rest.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      signal: AbortSignal.timeout(10_000),
    });
  } catch (e) {
    throw new ApiUnavailableError(e instanceof Error ? e.message : String(e));
  }
  if (res.status === 401 || res.status === 403) throw new ApiAuthError(res.status);
  if (REFUSED.has(res.status)) {
    const body = await res.json().catch(() => null);
    throw new ApiRequestError(res.status, body && typeof body === "object" && "detail" in body ? body.detail : null);
  }
  if (!res.ok) throw new ApiUnavailableError(`HTTP ${res.status} from ${path}`);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** Human-readable message for a refused request (FastAPI `detail` may be a string, object or list). */
export function refusalMessage(e: ApiRequestError, fallback: string): string {
  const d = e.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && !Array.isArray(d) && "message" in d && typeof d.message === "string") return d.message;
  return fallback;
}

/** Field-level messages when the backend detail is `{message, errors: [...]}`. */
export function refusalErrors(e: ApiRequestError): string[] | undefined {
  const d = e.detail;
  if (d && typeof d === "object" && !Array.isArray(d) && "errors" in d && Array.isArray(d.errors)) {
    return d.errors.filter((x): x is string => typeof x === "string");
  }
  return undefined;
}
