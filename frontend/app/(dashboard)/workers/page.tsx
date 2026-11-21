// Workers and worker-to-device assignment (F26-113 §4.8.4; UC-02, UC-03). Supervisor roles only.
import type { Metadata } from "next";
import { Suspense } from "react";
import { PageSkeleton, SupervisorOnly } from "@/components/layout/supervisor-only";
import { WorkersPage } from "@/components/workers/workers-page";
import { canSupervise } from "@/lib/accounts";
import { loadAssignments } from "@/lib/assignments";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Workers and assignments" };

async function WorkersContent() {
  const { account, token } = await requireSession();
  if (!canSupervise(account.role)) return <SupervisorOnly name={account.displayName} />;
  const snapshot = await loadAssignments(token);
  return <WorkersPage snapshot={snapshot} />;
}

export default function WorkersRoute() {
  return (
    <Suspense fallback={<PageSkeleton label="Loading workers and assignments…" />}>
      <WorkersContent />
    </Suspense>
  );
}
