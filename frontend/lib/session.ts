// Server-only session helpers. The cookie holds the backend-signed session token (HttpOnly).
// Every request re-validates it with GET /api/auth/session, so disabled accounts and bumped
// session versions are rejected by the backend (no session table; DB decision).
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";
import type { Account } from "@/lib/accounts";
import { api, ApiAuthError } from "@/lib/api";

export const SESSION_COOKIE = "hh_session";

export interface Session {
  account: Account;
  token: string;
}

/** Valid session, or null when signed out / rejected. Throws ApiUnavailableError if the backend is down. */
export const getSession = cache(async (): Promise<Session | null> => {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  await connection();
  try {
    const { account } = await api<{ account: Account }>("/api/auth/session", { token });
    return { account, token };
  } catch (e) {
    if (e instanceof ApiAuthError) return null;
    throw e;
  }
});

/** Use in every protected server component: redirects to sign-in when there is no valid session. */
export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) redirect("/sign-in");
  return session;
}

export async function startSession(token: string, expiresAt: number): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: Math.max(0, expiresAt - Math.floor(Date.now() / 1000)),
  });
}

export async function endSession(): Promise<void> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  jar.delete(SESSION_COOKIE);
  if (token) await api("/api/auth/session", { method: "DELETE", token }).catch(() => undefined);
}
