// Device health (F26-113 §4.8.6; UC-14, UC-15, UC-18). Viewable by every signed-in role;
// worker names only for supervisors, register/disable/retire controls only for administrators.
import type { Metadata } from "next";
import { Suspense } from "react";
import { DeviceHealthView } from "@/components/devices/device-health";
import { PageSkeleton } from "@/components/layout/supervisor-only";
import { canAdminister } from "@/lib/accounts";
import { loadDevices } from "@/lib/devices";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Device health" };

async function DevicesContent() {
  const { account, token } = await requireSession();
  const snapshot = await loadDevices(token);
  return <DeviceHealthView snapshot={snapshot} isAdmin={canAdminister(account.role)} />;
}

export default function DevicesRoute() {
  return (
    <Suspense fallback={<PageSkeleton label="Loading device health…" />}>
      <DevicesContent />
    </Suspense>
  );
}
