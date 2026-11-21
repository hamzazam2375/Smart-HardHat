// Alert detail loader: GET /api/events/{id} (server-side, supervisor session).
import { notFound } from "next/navigation";
import type { AlertDetail } from "@/lib/alert-types";
import { api, ApiRequestError } from "@/lib/api";

export async function loadAlertDetail(token: string, eventId: string): Promise<AlertDetail> {
  try {
    return await api<AlertDetail>(`/api/events/${encodeURIComponent(eventId)}`, { token });
  } catch (e) {
    if (e instanceof ApiRequestError && e.status === 404) notFound();
    throw e;
  }
}
