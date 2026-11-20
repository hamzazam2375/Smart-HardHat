"use server";

import { redirect } from "next/navigation";
import { verifyCredentials } from "@/lib/mock/accounts";
import { endSession, startSession } from "@/lib/session";

export interface SignInState {
  error: string | null;
  email: string;
}

// One message for unknown account, wrong password and disabled account (UC-01).
const GENERAL_ERROR = "Sign-in failed. Check your email address and password, or contact an administrator.";

export async function signIn(_prev: SignInState, formData: FormData): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) {
    return { error: "Enter your email address and password.", email };
  }
  const account = verifyCredentials(email, password);
  if (!account) return { error: GENERAL_ERROR, email };
  await startSession(account);
  redirect("/");
}

export async function signOut(): Promise<void> {
  await endSession();
  redirect("/sign-in");
}
