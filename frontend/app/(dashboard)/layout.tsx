import { Suspense } from "react";
import { signOut } from "@/app/actions/auth";
import { Brand } from "@/components/layout/brand";
import { SideNav } from "@/components/layout/side-nav";
import { ROLE_LABEL } from "@/lib/mock/accounts";
import { requireSession } from "@/lib/session";

async function SessionPanel() {
  const { account } = await requireSession();
  return (
    <div className="flex flex-1 flex-col gap-4">
      <SideNav role={account.role} />
      <div className="mt-auto hidden border-t border-slate-800 pt-4 md:block">
        <p className="truncate text-sm font-medium text-white">{account.displayName}</p>
        <p className="text-xs text-slate-400">{ROLE_LABEL[account.role]}</p>
        <form action={signOut} className="mt-3">
          <button className="w-full rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800">
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}

async function MobileSignOut() {
  const { account } = await requireSession();
  return (
    <form action={signOut} className="md:hidden">
      <button
        className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-200"
        title={`Signed in as ${account.displayName}`}
      >
        Sign out
      </button>
    </form>
  );
}

export default function DashboardLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex flex-1 flex-col md:flex-row">
      <aside className="flex flex-col gap-4 bg-slate-900 px-4 py-4 md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:gap-8 md:py-6">
        <div className="flex items-center justify-between">
          <Brand light />
          <Suspense fallback={null}>
            <MobileSignOut />
          </Suspense>
        </div>
        <Suspense fallback={<div className="h-9 md:h-64" />}>
          <SessionPanel />
        </Suspense>
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
