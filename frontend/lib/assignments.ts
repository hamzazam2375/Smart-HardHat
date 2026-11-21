// Workers + assignments loader: GET /api/workers + GET /api/assignments (server-side, supervisor session).
import type { AssignmentsSnapshot, Worker } from "@/lib/assignment-types";
import { api } from "@/lib/api";

export async function loadAssignments(token: string): Promise<AssignmentsSnapshot> {
  const [w, a] = await Promise.all([
    api<{ workers: Worker[] }>("/api/workers", { token }),
    api<Omit<AssignmentsSnapshot, "workers">>("/api/assignments", { token }),
  ]);
  return { workers: w.workers, ...a };
}
