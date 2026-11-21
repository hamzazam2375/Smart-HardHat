// History loader: GET /api/history (server-side, supervisor session).
import { api, ApiRequestError, refusalMessage } from "@/lib/api";
import type { HistoryPage, HistoryQuery } from "@/lib/history-types";

const FORWARDED = ["from", "to", "workerId", "deviceId", "type", "state", "cursor"] as const;

/** Rejected filters (422) come back as `error` so the page can show them next to the form. */
export async function loadHistory(
  token: string,
  query: HistoryQuery,
): Promise<{ page: HistoryPage; error: null } | { page: null; error: string }> {
  const qs = new URLSearchParams();
  for (const k of FORWARDED) {
    const v = query[k];
    if (v) qs.set(k, v);
  }
  try {
    return { page: await api<HistoryPage>(`/api/history?${qs}`, { token }), error: null };
  } catch (e) {
    if (e instanceof ApiRequestError && (e.status === 422 || e.status === 400)) {
      return { page: null, error: refusalMessage(e, "These filters are not valid.") };
    }
    throw e;
  }
}
