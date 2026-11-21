// Shape of GET /api/history (backend/app/routes/history.py). F26-113 §4.8.5; UC-13.
import type { ActiveAlert } from "@/lib/overview-types";
import type { WorkflowState } from "@/lib/alert-types";

export interface HistoryItem extends Omit<ActiveAlert, "state"> {
  state: WorkflowState;
  resolved?: { by: string; at: string };
}

export interface HistoryPage {
  generatedAt: string;
  /** Effective bounds on SERVER RECEIPT time; `from` is clamped to the 30-day retention start. */
  range: { from: string; to: string; retentionStart: string; clamped: boolean };
  items: HistoryItem[];
  nextCursor: string | null;
  options: {
    workers: { id: string; code: string; name: string }[];
    devices: { id: string; label: string; state: string }[];
  };
}

export const HISTORY_PARAMS = ["from", "to", "workerId", "deviceId", "type", "state", "cursor", "page"] as const;
export type HistoryQuery = Partial<Record<(typeof HISTORY_PARAMS)[number], string>>;
