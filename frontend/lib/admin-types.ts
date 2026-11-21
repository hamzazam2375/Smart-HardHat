// Shapes of GET /api/admin/accounts and GET /api/admin/configurations
// (backend/app/routes/accounts.py, configuration.py). UC-19, UC-20.
import type { Role } from "@/lib/accounts";

export interface AdminAccount {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
  lastSignIn: string | null;
}

export interface ConfigField {
  key: string;
  unit: string;
  min: number;
  max: number;
  integer: boolean;
  label: string;
}

export interface Configuration {
  id: string;
  version: string;
  checksum: string;
  thresholds: Record<string, number>;
  timings: Record<string, number>;
  state: "draft" | "active" | "retired";
  reviewReason: string | null;
  reviewer: string | null;
  activatedAt: string | null;
  createdAt: string;
  telemetryCount: number;
}

export interface ConfigSnapshot {
  schema: { thresholds: ConfigField[]; timings: ConfigField[] };
  configurations: Configuration[];
  /** Version each hardhat actually reported in its latest status (null = unknown / never reported). */
  devices: { label: string; state: string; reportedVersion: string | null; receivedAt: string | null }[];
}
