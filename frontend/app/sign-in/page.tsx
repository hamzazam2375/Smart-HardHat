// UC-01 sign-in (F26-113 §4.8.1). No registration link: only an administrator creates accounts (UC-19).
import type { Metadata } from "next";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { Brand } from "@/components/layout/brand";
import { getSession } from "@/lib/session";
import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = { title: "Sign in" };

async function RedirectIfSignedIn() {
  // Backend down: stay on the sign-in page; the form reports the outage on submit.
  const session = await getSession().catch(() => null);
  if (session) redirect("/");
  return null;
}

function DevHint() {
  if (process.env.NODE_ENV === "production") return null;
  return (
    <p className="mt-6 rounded-lg border border-dashed border-amber-400 bg-amber-50 p-4 text-xs text-amber-900">
      <span className="font-semibold">Development:</span> sign in with a seeded account such as{" "}
      <code className="font-mono">sana.iqbal@mock.smarthardhat.test</code>. The password is{" "}
      <code className="font-mono">MOCK_ACCOUNT_PASSWORD</code> from the repo-root .env, applied when the seed ran.
    </p>
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
        <DevHint />
      </div>
    </main>
  );
}
