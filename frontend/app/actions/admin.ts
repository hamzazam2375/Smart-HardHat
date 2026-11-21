"use server";

// Administrator actions: accounts (UC-19; FR-24, FR-25) and configuration review (UC-20; FR-47,
// FR-48). The backend enforces the administrator role on every call (403 otherwise).
import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiAuthError, ApiRequestError, refusalErrors, refusalMessage } from "@/lib/api";
import type { FormState } from "@/lib/form-state";
import { requireSession } from "@/lib/session";

const UNREACHABLE = "The server is not reachable. Nothing was saved. Try again.";
const ROLES = new Set(["supervisor", "admin", "admin_supervisor"]);

type PostResult<T> = { ok: true; data: T } | { ok: false; state: FormState };

async function post<T>(path: string, body: unknown, seq: number, values?: Record<string, string>): Promise<PostResult<T>> {
  const { token } = await requireSession();
  try {
    const data = await api<T>(path, { method: "POST", token, body: JSON.stringify(body ?? {}) });
    refresh();
    return { ok: true, data };
  } catch (e) {
    if (e instanceof ApiAuthError) {
      if (e.status === 403) return { ok: false, state: { ok: false, message: "Administrator role required.", seq, values } };
      redirect("/sign-in");
    }
    if (e instanceof ApiRequestError) {
      refresh();
      return {
        ok: false,
        state: { ok: false, message: refusalMessage(e, "The change was not saved."), errors: refusalErrors(e), seq, values },
      };
    }
    return { ok: false, state: { ok: false, message: UNREACHABLE, seq, values } };
  }
}

// ----------------------------------------------------------------- accounts ---
export async function createAccount(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const values = {
    email: String(formData.get("email") ?? "").trim().toLowerCase(),
    displayName: String(formData.get("displayName") ?? "").trim(),
    role: String(formData.get("role") ?? ""),
  };
  if (!values.email || !values.displayName) {
    return { ok: false, message: "Enter an email address and a display name.", seq, values };
  }
  if (!ROLES.has(values.role)) return { ok: false, message: "Choose a role.", seq, values };
  const r = await post<{ temporaryPassword: string }>("/api/admin/accounts", values, seq, values);
  if (!r.ok) return r.state;
  return { ok: true, message: `Account created for ${values.email}.`, secret: r.data.temporaryPassword, seq };
}

export async function updateAccount(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const id = encodeURIComponent(String(formData.get("accountId") ?? ""));
  const op = String(formData.get("op") ?? "");
  if (!id) return { ok: false, message: "Invalid request. Reload the page.", seq };

  if (op === "enable" || op === "disable") {
    const r = await post(`/api/admin/accounts/${id}/enabled`, { enabled: op === "enable" }, seq);
    if (!r.ok) return r.state;
    return { ok: true, message: op === "enable" ? "Account enabled." : "Account disabled; its sessions are revoked.", seq };
  }
  if (op === "role") {
    const role = String(formData.get("role") ?? "");
    if (!ROLES.has(role)) return { ok: false, message: "Choose a role.", seq };
    const r = await post(`/api/admin/accounts/${id}/role`, { role }, seq);
    return r.ok ? { ok: true, message: "Role changed; the account must sign in again.", seq } : r.state;
  }
  if (op === "reset") {
    const r = await post<{ temporaryPassword: string }>(`/api/admin/accounts/${id}/reset-password`, {}, seq);
    if (!r.ok) return r.state;
    return { ok: true, message: "Password reset; existing sessions are revoked.", secret: r.data.temporaryPassword, seq };
  }
  return { ok: false, message: "Unknown action.", seq };
}

// ------------------------------------------------------------ configuration ---
export async function createConfigDraft(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const version = String(formData.get("version") ?? "").trim();
  const thresholds: Record<string, number> = {};
  const timings: Record<string, number> = {};
  const values: Record<string, string> = { version };
  const bad: string[] = [];
  for (const [name, raw] of formData.entries()) {
    if (typeof raw !== "string") continue;
    const [group, key] = name.split(".", 2);
    if ((group !== "t" && group !== "m") || !key) continue;
    values[name] = raw;
    const n = Number(raw.trim());
    if (raw.trim() === "" || !Number.isFinite(n)) {
      bad.push(`${key} must be a number.`);
      continue;
    }
    (group === "t" ? thresholds : timings)[key] = n;
  }
  if (!version) return { ok: false, message: "Enter a version name.", seq, values };
  if (bad.length) return { ok: false, message: "Fix the values below.", errors: bad, seq, values };
  const r = await post("/api/admin/configurations", { version, thresholds, timings }, seq, values);
  return r.ok ? { ok: true, message: `Draft ${version} saved. No hardhat has been changed.`, seq } : r.state;
}

export async function approveConfig(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const id = encodeURIComponent(String(formData.get("configId") ?? ""));
  const reason = String(formData.get("reason") ?? "").trim();
  const values = { reason };
  if (!id) return { ok: false, message: "Invalid request. Reload the page.", seq };
  if (!reason) return { ok: false, message: "Record the review reason before approving.", seq, values };
  if (formData.get("checked") !== "yes") {
    return { ok: false, message: "Confirm that boundary checks will be re-run for changed values.", seq, values };
  }
  const r = await post(`/api/admin/configurations/${id}/approve`, { reason }, seq, values);
  if (!r.ok) return r.state;
  return { ok: true, message: "Approved as the active version. Apply it to each hardhat by wired setup.", seq };
}
