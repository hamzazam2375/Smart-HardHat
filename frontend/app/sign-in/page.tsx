// UC-01 sign-in (F26-113 §4.8.1). No registration link: only an administrator creates accounts (UC-19).
import type { Metadata } from "next";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { Brand } from "@/components/layout/brand";
import { MOCK_ACCOUNTS, ROLE_LABEL, mockPassword } from "@/lib/mock/accounts";
import { getSession } from "@/lib/session";
import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = { title: "Sign in" };

async function RedirectIfSignedIn() {
  if (await getSession()) redirect("/");
  return null;
}

function MockAccountsHint() {
  const password = mockPassword();
  if (process.env.NODE_ENV === "production" || !password) return null;
  return (
    <div className="mt-6 rounded-lg border border-dashed border-amber-400 bg-amber-50 p-4 text-xs text-amber-900">
      <p className="font-semibold">Development only: mock accounts</p>
      <p className="mt-1">
        Password for all: <code className="font-mono">{password}</code>
      </p>
      <ul className="mt-2 space-y-0.5">
        {MOCK_ACCOUNTS.map((a) => (
          <li key={a.id}>
            <code className="font-mono">{a.email}</code> · {ROLE_LABEL[a.role]}
            {!a.enabled && " · disabled"}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function SignInPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-12">
      <Suspense fallback={null}>
        <RedirectIfSignedIn />
      </Suspense>
      <div className="w-full max-w-sm">
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <Brand />
          <h1 className="mt-8 text-xl font-semibold">Supervisor sign in</h1>
          <p className="mt-1 mb-6 text-sm text-slate-500">
            Use your individual account. Worker data is shown only after sign-in.
          </p>
          <SignInForm />
          <p className="mt-6 text-xs text-slate-500">
            No account? Accounts are created by a project administrator.
          </p>
        </div>
        <MockAccountsHint />
      </div>
    </main>
  );
}
