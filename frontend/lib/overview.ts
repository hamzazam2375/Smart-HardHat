// Overview data loader: GET /api/status + GET /api/events (server-side, supervisor session).
import type { ActiveAlert, OverviewSnapshot } from "@/lib/overview-types";
import { api } from "@/lib/api";

type Status = Omit<OverviewSnapshot, "alerts">;

export async function loadOverviewSnapshot(token: string): Promise<OverviewSnapshot> {
  const [status, events] = await Promise.all([
    api<Status>("/api/status", { token }),
    api<{ alerts: ActiveAlert[] }>("/api/events", { token }),
  ]);
  return { ...status, alerts: events.alerts };
}
