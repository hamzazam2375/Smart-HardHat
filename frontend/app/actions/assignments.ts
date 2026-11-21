"use server";

// Worker records and hardhat assignments (UC-02, UC-03; FR-27, FR-28). The backend re-checks
// every change on submit, since another supervisor may have changed it while the form was open.
import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiAuthError, ApiRequestError, refusalMessage } from "@/lib/api";
import type { FormState } from "@/lib/form-state";
import { requireSession } from "@/lib/session";

const UNREACHABLE = "The server is not reachable. Nothing was saved. Try again.";

async function send(
  path: string,
  body: unknown,
  seq: number,
  success: string,
  refused: string,
  values?: Record<string, string>,
): Promise<FormState> {
  const { token } = await requireSession();
  try {
    await api(path, { method: "POST", token, body: JSON.stringify(body) });
  } catch (e) {
    if (e instanceof ApiAuthError) redirect("/sign-in");
    if (e instanceof ApiRequestError) {
      refresh();
      return { ok: false, message: refusalMessage(e, refused), seq, values };
    }
    return { ok: false, message: UNREACHABLE, seq, values };
  }
  refresh();
  return { ok: true, message: success, seq };
}

export async function createWorker(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const code = String(formData.get("code") ?? "").trim().toUpperCase();
  const name = String(formData.get("name") ?? "").trim().replace(/\s+/g, " ");
  const values = { code, name };
  if (!code || !name) return { ok: false, message: "Enter both the worker ID and the display name.", seq, values };
  if (code.length > 32) return { ok: false, message: "Worker ID must be 32 characters or fewer.", seq, values };
  if (name.length > 100) return { ok: false, message: "Display name must be 100 characters or fewer.", seq, values };
  return send("/api/workers", { code, name }, seq, `Worker ${code} created.`, "The worker was not created.", values);
}

export async function createAssignment(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const workerId = String(formData.get("workerId") ?? "");
  const deviceId = String(formData.get("deviceId") ?? "");
  const closeAssignmentIds = formData.getAll("close").map(String).filter(Boolean);
  if (!workerId || !deviceId) return { ok: false, message: "Select a worker and a hardhat.", seq };
  if (formData.get("confirm") !== "yes") return { ok: false, message: "Confirm the assignment shown above.", seq };
  return send("/api/assignments", { workerId, deviceId, closeAssignmentIds }, seq, "Assignment started.",
    "The assignment was not saved.");
}

export async function endAssignment(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const id = String(formData.get("assignmentId") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  const values = { reason };
  if (!id) return { ok: false, message: "Invalid request. Reload the page.", seq };
  if (reason.length > 200) return { ok: false, message: "Reason must be 200 characters or fewer.", seq, values };
  return send(`/api/assignments/${encodeURIComponent(id)}/end`, { reason: reason || null }, seq,
    "Assignment ended.", "The assignment was not ended.", values);
}
