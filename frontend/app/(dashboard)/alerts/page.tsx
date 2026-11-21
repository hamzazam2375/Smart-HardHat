// Active alerts list (UC-05, UC-11). Supervisor roles only (Table 4.34).
import type { Metadata } from "next";
import { Suspense } from "react";
import { AlertsBoard } from "@/components/alerts/alerts-board";
import { PageSkeleton, SupervisorOnly } from "@/components/layout/supervisor-only";
import { canSupervise } from "@/lib/accounts";
import { api } from "@/lib/api";
import type { ActiveAlert } from "@/lib/overview-types";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Alerts" };

async function AlertsContent() {
  const { account, token } = await requireSession();
  if (!canSupervise(account.role)) return <SupervisorOnly name={account.displayName} />;
  const { alerts, generatedAt } = await api<{ alerts: ActiveAlert[]; generatedAt: string }>("/api/events", { token });
  return <AlertsBoard alerts={alerts} generatedAt={generatedAt} />;
}

export default function AlertsRoute() {
  return (
    <Suspense fallback={<PageSkeleton label="Loading alerts…" />}>
      <AlertsContent />
    </Suspense>
  );
}
