// Shapes of GET /api/workers and GET /api/assignments (backend/app/routes/workers.py, assignments.py).
// F26-113 §4.8.4; UC-02, UC-03; FR-27, FR-28.

export interface Worker {
  id: string;
  code: string;
  name: string;
  active: boolean;
  createdAt: string;
  createdBy: string;
  currentAssignment: { assignmentId: string; deviceId: string; deviceLabel: string; startAt: string } | null;
}

export interface Assignment {
  id: string;
  worker: { id: string; code: string; name: string };
  device: { id: string; label: string };
  startAt: string;
  endAt: string | null; // null = active
  reason: string | null; // end reason
  createdBy: string;
  endedBy: string | null;
}

export interface AssignableDevice {
  id: string;
  label: string;
  state: "registered" | "disabled";
  lastSeenAt: string | null;
  eligible: boolean; // only registered hardhats can be assigned
  activeAssignmentId: string | null;
}

export interface AssignmentsSnapshot {
  workers: Worker[];
  devices: AssignableDevice[];
  active: Assignment[];
  history: Assignment[]; // ended within the 30-day retention window
}
