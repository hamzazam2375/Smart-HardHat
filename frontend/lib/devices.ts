// Device-health loader: GET /api/devices (server-side; any signed-in role).
import { api } from "@/lib/api";
import type { DevicesSnapshot } from "@/lib/device-types";

export function loadDevices(token: string): Promise<DevicesSnapshot> {
  return api<DevicesSnapshot>("/api/devices", { token });
}
