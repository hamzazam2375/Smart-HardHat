import type { Metadata } from "next";
import { Suspense } from "react";
import { OverviewDashboard } from "@/components/overview/overview-dashboard";
import { canSupervise } from "@/lib/accounts";
import { loadOverviewSnapshot } from "@/lib/overview";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Overview" };

async function OverviewContent() {
  const { account, token } = await requireSession();

  // Table 4.34: worker names, readings and locations are for supervisor roles only.
  if (!canSupervise(account.role)) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 md:px-8">
        <h1 className="text-2xl font-semibold">Welcome, {account.displayName}</h1>
        <p className="mt-2 text-sm text-slate-600">
          Your account has administrator permissions only. Live worker
          readings are shown to supervisors. Use Accounts, Devices and Settings in the menu.
        </p>
      </div>
    );
  }

  const snapshot = await loadOverviewSnapshot(token);
  return <OverviewDashboard initial={snapshot} />;
}

function OverviewSkeleton() {
  return (
    <div className="mx-auto max-w-7xl animate-pulse space-y-6 px-4 py-6 md:px-8" aria-busy="true">
      <div className="h-8 w-48 rounded bg-slate-200" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-xl bg-slate-200" />
        ))}
      </div>
      <div className="h-40 rounded-xl bg-slate-200" />
      <p className="text-sm text-slate-500">Loading current status…</p>
    </div>
  );
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<OverviewSkeleton />}>
      <OverviewContent />
    </Suspense>
  );
}
