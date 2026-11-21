// Configuration review (F26-113 §4.8.7; UC-20). Administrator roles only (Table 4.34).
import type { Metadata } from "next";
import { Suspense } from "react";
import { AdminOnly, PageSkeleton } from "@/components/layout/supervisor-only";
import { ConfigReview } from "@/components/settings/config-review";
import { canAdminister } from "@/lib/accounts";
import { loadConfigurations } from "@/lib/admin";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Configuration review" };

async function SettingsContent() {
  const { account, token } = await requireSession();
  if (!canAdminister(account.role)) return <AdminOnly name={account.displayName} />;
  const snapshot = await loadConfigurations(token);
  return <ConfigReview snapshot={snapshot} />;
}

export default function SettingsRoute() {
  return (
    <Suspense fallback={<PageSkeleton label="Loading configuration…" />}>
      <SettingsContent />
    </Suspense>
  );
}
