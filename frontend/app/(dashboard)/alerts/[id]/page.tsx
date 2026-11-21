// Alert detail and acknowledgment (F26-113 §4.8.3; UC-11). Supervisor roles only (Table 4.34).
import type { Metadata } from "next";
import { Suspense } from "react";
import { AlertDetailView } from "@/components/alerts/alert-detail";
import { PageSkeleton, SupervisorOnly } from "@/components/layout/supervisor-only";
import { canSupervise } from "@/lib/accounts";
import { loadAlertDetail } from "@/lib/alerts";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Alert detail" };

async function AlertContent({ params }: { params: Promise<{ id: string }> }) {
  const { account, token } = await requireSession();
  if (!canSupervise(account.role)) return <SupervisorOnly name={account.displayName} />;
  const { id } = await params;
  const detail = await loadAlertDetail(token, id);
  return <AlertDetailView detail={detail} />;
}

export default function AlertDetailPage(props: PageProps<"/alerts/[id]">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading alert…" />}>
      <AlertContent params={props.params} />
    </Suspense>
  );
}
