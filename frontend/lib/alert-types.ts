// Shape of GET /api/events/{id} (backend/app/services/events.py). F26-113 §4.8.3, FR-34..FR-36.
import type { ActiveAlert, Reading, WorkerRef } from "@/lib/overview-types";

export type WorkflowState = "open" | "acknowledged" | "resolved";

export type EventLocation =
  | { state: "fix"; lat: number; lon: number; fixAt: string | null; fixAgeS: number | null }
  | { state: "no_fix"; lastKnown: { lat: number; lon: number; fixAt: string } | null };

export type EventAssignment =
  | { state: "resolved"; worker: WorkerRef; startAt: string; endAt: string | null }
  | { state: "unresolved"; reason: string };

/** Readings captured with the event. null = none were recorded with it. */
export interface EventReadings {
  co: Reading;
  temperature: Reading;
  humidity: Reading;
  heatIndex: Reading;
  accelPeak: Reading;
  battery: Reading;
}

export interface AlertDetailEvent extends Omit<ActiveAlert, "state"> {
  state: WorkflowState;
  rowVersion: number;
  deviceId: string;
  sourceEventKey: string;
  readings: EventReadings | null;
  location: EventLocation;
  assignment: EventAssignment;
  evidence: { key: string; value: string | number | boolean }[];
  isMock: boolean;
}

export interface AlertAction {
  id: string;
  type: "acknowledge" | "note" | "resolve";
  note: string | null;
  by: string;
  at: string; // server time
}

export interface Recommendation {
  code: string;
  message: string;
  version: string;
}

export interface AlertDetail {
  generatedAt: string;
  alert: AlertDetailEvent;
  actions: AlertAction[];
  recommendations: Recommendation[];
}
