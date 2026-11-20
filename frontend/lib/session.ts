// Server-only session helpers. Signed, HttpOnly cookie; revocation via account.sessionVersion
// (matches the "no session table" DB decision). The signing key comes from SESSION_SECRET;
// in development a random per-process key is used, so restarting the server signs everyone out.
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { findAccountById, type Account } from "@/lib/mock/accounts";

export const SESSION_COOKIE = "hh_session";
const MAX_AGE_S = 8 * 60 * 60; // one shift

interface Payload {
  a: string; // account id
  v: number; // session version
  e: number; // expiry (ms since epoch)
}

function secret(): Buffer {
  const env = process.env.SESSION_SECRET;
  if (env && env.length >= 32) return Buffer.from(env);
  if (process.env.NODE_ENV === "production") {
    throw new Error("SESSION_SECRET (32+ chars) must be set in production");
  }
  const g = globalThis as { __hhDevSessionKey?: Buffer };
  g.__hhDevSessionKey ??= randomBytes(32);
  return g.__hhDevSessionKey;
}

const sign = (data: string) => createHmac("sha256", secret()).update(data).digest("base64url");

function decode(token: string): Payload | null {
  const [data, sig] = token.split(".");
  if (!data || !sig) return null;
  const a = Buffer.from(sig);
  const b = Buffer.from(sign(data));
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const p = JSON.parse(Buffer.from(data, "base64url").toString()) as Payload;
    return p.e > Date.now() ? p : null;
  } catch {
    return null;
  }
}

export interface Session {
  account: Account;
}

/** Valid session or null. Disabled accounts and bumped session versions are rejected. */
export const getSession = cache(async (): Promise<Session | null> => {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  await connection(); // expiry check reads the clock at request time
  const p = decode(token);
  if (!p) return null;
  const account = findAccountById(p.a);
  if (!account || !account.enabled || account.sessionVersion !== p.v) return null;
  return { account };
});

/** Use in every protected server component: redirects to sign-in when there is no valid session. */
export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) redirect("/sign-in");
  return session;
}

export async function startSession(account: Account): Promise<void> {
  const payload: Payload = { a: account.id, v: account.sessionVersion, e: Date.now() + MAX_AGE_S * 1000 };
  const data = Buffer.from(JSON.stringify(payload)).toString("base64url");
  (await cookies()).set(SESSION_COOKIE, `${data}.${sign(data)}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_S,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
