"use server";

import { redirect } from "next/navigation";
import type { Account } from "@/lib/accounts";
import { api, ApiAuthError } from "@/lib/api";
import { endSession, startSession } from "@/lib/session";

export interface SignInState {
  error: string | null;
  email: string;
}

// One message for unknown account, wrong password and disabled account (UC-01).
const GENERAL_ERROR = "Sign-in failed. Check your email address and password, or contact an administrator.";
const SERVICE_ERROR = "The sign-in service is not reachable right now. Try again shortly.";

export async function signIn(_prev: SignInState, formData: FormData): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) {
    return { error: "Enter your email address and password.", email };
  }
  try {
    const res = await api<{ token: string; expiresAt: number; account: Account }>("/api/auth/session", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    await startSession(res.token, res.expiresAt);
  } catch (e) {
    return { error: e instanceof ApiAuthError ? GENERAL_ERROR : SERVICE_ERROR, email };
  }
  redirect("/");
}

export async function signOut(): Promise<void> {
  await endSession();
  redirect("/sign-in");
}
