// MOCK overview snapshot for the current shift, matching the scenarios in
// backend/scripts/seed_mock_data.py (HAT-01..HAT-06, HAT-09). Times are relative to `nowMs`.
// Replace with /api/status + /api/events (and SSE /api/stream) once the backend exists.
import { connection } from "next/server";
import type { DeviceStatus, OverviewSnapshot } from "@/lib/overview-types";

const v = (value: number) => ({ value, quality: "valid" as const });
const missing = { value: null, quality: "missing" as const };
const W = (n: number, name: string) => ({ code: `MOCK-W-00${n}`, name: `${name} (mock)` });

export function getMockOverview(nowMs: number): OverviewSnapshot {
  const ago = (s: number) => new Date(nowMs - s * 1000).toISOString();

  const devices: DeviceStatus[] = [
    {
      // Normal; a fall pre-alert earlier was cancelled by the worker (resolved).
      deviceId: "dev-01", label: "MOCK-HAT-01", worker: W(1, "Ali Raza"),
      receivedAt: ago(34), timeQuality: "synced",
      co: v(4), temperature: v(29.4), humidity: v(45), heatIndex: v(29.9),
      battery: { ...v(76), isEstimate: false }, motion: { state: "normal", quality: "valid" },
      gps: { state: "fix", fixAt: ago(36), lat: 31.4815, lon: 74.3032 },
      risk: { state: "available", level: "low", source: "model", modelVersion: "mock-v2", assessedAt: ago(40) },
      mockLive: true,
    },
    {
      // CO warning open (an urgent episode earlier was resolved).
      deviceId: "dev-02", label: "MOCK-HAT-02", worker: W(2, "Bilal Hussain"),
      receivedAt: ago(12), timeQuality: "synced",
      co: v(48), temperature: v(30.1), humidity: v(52), heatIndex: v(31.6),
      battery: { ...v(64), isEstimate: false }, motion: { state: "normal", quality: "valid" },
      gps: { state: "fix", fixAt: ago(15), lat: 31.4819, lon: 74.3041 },
      risk: { state: "available", level: "moderate", source: "model", modelVersion: "mock-v2", assessedAt: ago(20) },
      mockLive: true,
    },
    {
      // Possible fall 12 min ago: acknowledged by supervisor and on the hardhat, not resolved.
      deviceId: "dev-03", label: "MOCK-HAT-03", worker: W(3, "Imran Khan"),
      receivedAt: ago(20), timeQuality: "synced",
      co: v(2), temperature: v(28.7), humidity: v(50), heatIndex: v(29.3),
      battery: { ...v(58), isEstimate: false }, motion: { state: "still_after_impact", quality: "valid" },
      gps: { state: "no_fix", fixAt: ago(14 * 60) },
      risk: { state: "available", level: "critical", source: "rule_override", modelVersion: null, assessedAt: ago(12 * 60) },
      mockLive: true,
    },
    {
      // Rebooted (time estimated), low battery open, STALE: last data 6 min ago.
      deviceId: "dev-04", label: "MOCK-HAT-04", worker: W(4, "Nadeem Abbas"),
      receivedAt: ago(6 * 60), timeQuality: "estimated",
      co: v(3), temperature: v(30.5), humidity: v(47), heatIndex: v(31.2),
      battery: { ...v(18), isEstimate: true }, motion: { state: "normal", quality: "valid" },
      gps: { state: "fix", fixAt: ago(6 * 60 + 10), lat: 31.4811, lon: 74.3027 },
      risk: { state: "unavailable", reason: "Input data is stale" },
    },
    {
      // SOS earlier (resolved), IMU fault open, no data for 1 h 30 min.
      deviceId: "dev-05", label: "MOCK-HAT-05", worker: W(5, "Shahid Mehmood"),
      receivedAt: ago(90 * 60), timeQuality: "synced",
      co: v(1), temperature: v(27.9), humidity: v(55), heatIndex: v(28.6),
      battery: { ...v(41), isEstimate: false }, motion: { state: null, quality: "invalid" },
      gps: { state: "no_fix", fixAt: null },
      risk: { state: "unavailable", reason: "Motion channel invalid; device not reporting" },
    },
    {
      // Spare on the charger, reporting with no assignment.
      deviceId: "dev-06", label: "MOCK-HAT-06", worker: null,
      receivedAt: ago(50), timeQuality: "synced",
      co: v(0), temperature: v(26.2), humidity: v(44), heatIndex: v(26.4),
      battery: { ...v(100), isEstimate: false, charging: true }, motion: { state: "normal", quality: "valid" },
      gps: { state: "no_fix", fixAt: null },
      risk: { state: "unavailable", reason: "No worker assigned" },
      mockLive: true,
    },
    {
      // Registered yesterday, never seen.
      deviceId: "dev-09", label: "MOCK-HAT-09", worker: null,
      receivedAt: null, timeQuality: "unknown",
      co: missing, temperature: missing, humidity: missing, heatIndex: missing,
      battery: { ...missing, isEstimate: false }, motion: { state: null, quality: "missing" },
      gps: { state: "no_fix", fixAt: null },
      risk: { state: "unavailable", reason: "Device has never reported" },
    },
  ];

  return {
    generatedAt: new Date(nowMs).toISOString(),
    site: "Prototype trial site (mock)",
    devices,
    alerts: [
      {
        eventId: "evt-0031", code: "E-00031", type: "possible_fall", priority: 1, state: "acknowledged",
        deviceLabel: "MOCK-HAT-03", worker: W(3, "Imran Khan"),
        detectedAt: ago(12 * 60), timeQuality: "synced", receivedAt: ago(12 * 60 - 3),
        detail: "Impact, orientation change and inactivity. The 15 s cancel window expired.",
        supervisorAck: { by: "Sana Iqbal (mock)", at: ago(10 * 60 + 30) },
        physicalAckAt: ago(9 * 60),
      },
      {
        eventId: "evt-0034", code: "E-00034", type: "co_warning", priority: 4, state: "open",
        deviceLabel: "MOCK-HAT-02", worker: W(2, "Bilal Hussain"),
        detectedAt: ago(3 * 60), timeQuality: "synced", receivedAt: ago(3 * 60 - 2),
        detail: "CO 41 ppm at detection (screening warning at 35 ppm; urgent at 200 ppm).",
      },
      {
        eventId: "evt-0027", code: "E-00027", type: "sensor_fault", priority: 3, state: "open",
        deviceLabel: "MOCK-HAT-05", worker: W(5, "Shahid Mehmood"),
        detectedAt: ago(92 * 60), timeQuality: "synced", receivedAt: ago(92 * 60 - 4),
        detail: "Motion sensor (IMU) not responding. Fall detection is unavailable on this hardhat.",
      },
      {
        eventId: "evt-0033", code: "E-00033", type: "battery_low", priority: 5, state: "open",
        deviceLabel: "MOCK-HAT-04", worker: W(4, "Nadeem Abbas"),
        detectedAt: null, timeQuality: "unknown", receivedAt: ago(9 * 60),
        detail: "Battery 19% (estimate) after a reboot.",
      },
    ],
    gateways: [
      { code: "MOCK-GW-01", enabled: true, lastSeenAt: ago(20), firmware: "0.2.3", queueDepth: 2, lossCount: 4, mockLive: true },
      { code: "MOCK-GW-02", enabled: false, lastSeenAt: ago(3 * 86400), firmware: "0.2.1", queueDepth: 0, lossCount: 17 },
    ],
    model: { state: "active", version: "mock-v2", activatedAt: ago(4 * 86400) },
  };
}

/** Data loader for the overview page. MOCK: later fetches /api/status + /api/events. */
export async function loadOverviewSnapshot(): Promise<OverviewSnapshot> {
  await connection(); // per-request timestamps (Cache Components)
  return getMockOverview(Date.now());
}
