// Shape of GET /api/devices (backend/app/services/devices.py). F26-113 §4.8.6; UC-14, UC-15.
import type { GatewayStatus, TimeQuality, WorkerRef } from "@/lib/overview-types";

export type ChannelState = "valid" | "partial" | "invalid" | "missing" | "low" | "critical" | "no_fix";

export interface Channel {
  state: ChannelState;
  summary: string;
  affects: string | null; // the function affected when the channel is not valid
}

export interface DeviceHealth {
  deviceId: string;
  label: string;
  radioId: number;
  state: "registered" | "disabled" | "retired";
  hardwareRevision: string;
  firmwareVersion: string;
  registeredAt: string;
  lastSeenAt: string | null; // last radio contact
  openFaults: number;
  /** Present only for supervisor roles; null = no active assignment. */
  worker?: WorkerRef | null;
  /** unknown = never sent an accepted status. Never shown as healthy. */
  status: "current" | "stale" | "unknown";
  receivedAt: string | null; // server acceptance of the latest status
  timeQuality: TimeQuality | null;
  channels: { co: Channel; environment: Channel; motion: Channel; battery: Channel; gps: Channel } | null;
  config: { version: string; state: string } | null;
  calibration: { sensorSerial: string; result: "pass" | "fail" | "limited"; checkedAt: string; dueAt: string | null; overdue: boolean } | null;
  gateway: { code: string; lastSeenAt: string | null } | null;
}

export interface DevicesSnapshot {
  generatedAt: string;
  devices: DeviceHealth[];
  gateways: GatewayStatus[];
  activeConfig: { version: string; activatedAt: string | null } | null;
}
