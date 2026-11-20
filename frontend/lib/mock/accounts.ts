// MOCK accounts, mirroring backend/scripts/seed_mock_data.py (ACCOUNTS).
// Replace with POST /api/auth/session once the FastAPI auth service exists.
// Real accounts use Argon2id hashes on the server; nothing here is a real credential.
import { createHash, timingSafeEqual } from "node:crypto";

export type Role = "supervisor" | "admin" | "admin_supervisor";

export interface Account {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  enabled: boolean;
  sessionVersion: number;
}

const DOMAIN = "mock.smarthardhat.test";

export const MOCK_ACCOUNTS: Account[] = [
  { id: "acc-usman", email: `usman.tariq@${DOMAIN}`, displayName: "Usman Tariq (mock)", role: "admin", enabled: true, sessionVersion: 0 },
  { id: "acc-sana", email: `sana.iqbal@${DOMAIN}`, displayName: "Sana Iqbal (mock)", role: "supervisor", enabled: true, sessionVersion: 1 },
  { id: "acc-kamran", email: `kamran.akhtar@${DOMAIN}`, displayName: "Kamran Akhtar (mock)", role: "admin_supervisor", enabled: true, sessionVersion: 0 },
  { id: "acc-fatima", email: `fatima.noor@${DOMAIN}`, displayName: "Fatima Noor (mock)", role: "supervisor", enabled: false, sessionVersion: 3 },
];

export const canSupervise = (role: Role) => role === "supervisor" || role === "admin_supervisor";
export const canAdminister = (role: Role) => role === "admin" || role === "admin_supervisor";

export const ROLE_LABEL: Record<Role, string> = {
  supervisor: "Supervisor",
  admin: "Administrator",
  admin_supervisor: "Administrator + supervisor",
};

/** Shared dev-only password for all mock accounts. Disabled in production builds. */
export function mockPassword(): string | null {
  if (process.env.MOCK_SIGNIN_PASSWORD) return process.env.MOCK_SIGNIN_PASSWORD;
  return process.env.NODE_ENV === "production" ? null : "hardhat-demo";
}

export function findAccountById(id: string): Account | undefined {
  return MOCK_ACCOUNTS.find((a) => a.id === id);
}

const digest = (s: string) => createHash("sha256").update(s).digest();

/**
 * UC-01: returns the account only if it exists, is enabled and the password matches.
 * Every failure returns null so the caller shows one general error (no account enumeration).
 */
export function verifyCredentials(email: string, password: string): Account | null {
  const expected = mockPassword();
  const account = MOCK_ACCOUNTS.find((a) => a.email === email);
  const ok = expected !== null && timingSafeEqual(digest(password), digest(expected));
  if (!account || !account.enabled || !ok) return null;
  return account;
}
