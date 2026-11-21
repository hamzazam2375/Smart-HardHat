// Shape of the overview snapshot = GET /api/status + GET /api/events (backend/app/services/overview.py). Missing / invalid / stale / unavailable are explicit, never zero or "safe".

/** F26-113: device status is stale after >180 s without a valid update (3 missed 60 s intervals). */
export const STALE_AFTER_S = 180;
/** Screening + urgent thresholds shown next to readings (the rules themselves run on the hardhat). */
export const CO_WARNING_PPM = 35;
export const CO_URGENT_PPM = 200;
export const HEAT_WARNING_C = 32;
export const BATTERY_LOW_PCT = 20;
export const BATTERY_CRITICAL_PCT = 10;

/** "unsupported" = no value because the input is outside the formula's range (e.g. heat index when cool). */
export type ChannelQuality = "valid" | "invalid" | "missing" | "unsupported";
export type TimeQuality = "trusted" | "estimated" | "unknown";

export interface Reading {
  value: number | null;
  quality: ChannelQuality;
}

export interface WorkerRef {
  code: string;
  name: string;
}

export type MotionState = "normal" | "still_after_impact" | "fall_pre_alert";

export interface GpsStatus {
  state: "fix" | "no_fix" | "invalid";
  fixAt: string | null; // time of the last valid fix
  lat?: number;
  lon?: number;
}

export type RiskStatus =
  | {
      state: "available";
      level: "low" | "moderate" | "high" | "critical";
      source: "model" | "rule_override";
      modelVersion: string | null;
      assessedAt: string;
    }
  | { state: "unavailable"; reason: string };

export interface DeviceStatus {
  deviceId: string;
  label: string;
  worker: WorkerRef | null;
  receivedAt: string | null; // server acceptance time of the latest status; null = never reported
  timeQuality: TimeQuality;
  co: Reading; // ppm
  temperature: Reading; // degC
  humidity: Reading; // %RH
  heatIndex: Reading; // degC (NWS)
  battery: Reading & { isEstimate: boolean };
  motion: { state: MotionState | null; quality: ChannelQuality };
  gps: GpsStatus;
  risk: RiskStatus;
}

export type EventType =
  | "sos"
  | "possible_fall"
  | "fall_pre_alert"
  | "cancellation"
  | "co_urgent"
  | "co_warning"
  | "sensor_fault"
  | "heat_warning"
  | "battery_low"
  | "battery_critical";

/** Spec priority: 1 CO/SOS/fall emergency, 2 fall pre-alert, 3 sensor fault, 4 heat, 5 battery. */
export type Priority = 1 | 2 | 3 | 4 | 5;

export interface ActiveAlert {
  eventId: string;
  code: string;
  type: EventType;
  priority: Priority;
  state: "open" | "acknowledged"; // resolved alerts are not on the overview
  deviceLabel: string;
  worker: WorkerRef | null; // null = assignment uncertain
  detectedAt: string | null; // null = detection time unknown
  timeQuality: TimeQuality;
  receivedAt: string;
  detail: string;
  supervisorAck?: { by: string; at: string };
  /** Hardhat-side state, separate from the supervisor workflow state. */
  localState: "active" | "physically_acknowledged" | "cleared" | "unknown";
}

export interface GatewayStatus {
  code: string;
  enabled: boolean;
  lastSeenAt: string | null;
  firmware: string;
  queueDepth: number;
  lossCount: number;
}

export type ModelStatus =
  | { state: "active"; version: string; activatedAt: string }
  | { state: "unavailable"; reason: string };

export interface OverviewSnapshot {
  generatedAt: string;
  site: string;
  devices: DeviceStatus[];
  alerts: ActiveAlert[];
  gateways: GatewayStatus[];
  model: ModelStatus;
}
