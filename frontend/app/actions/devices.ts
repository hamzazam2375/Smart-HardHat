"use server";

// Device registration and state changes (UC-18; FR-29). Administrator only; the backend
// enforces the role (403) regardless of what the page shows. No key material is handled here:
// only a reference to the provisioned key slot.
import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiAuthError, ApiRequestError, refusalMessage } from "@/lib/api";
import type { FormState } from "@/lib/form-state";
import { requireSession } from "@/lib/session";

const UNREACHABLE = "The server is not reachable. Nothing was saved. Try again.";

async function send(path: string, body: unknown, seq: number, success: string, values?: Record<string, string>): Promise<FormState> {
  const { token } = await requireSession();
  try {
    await api(path, { method: "POST", token, body: JSON.stringify(body) });
  } catch (e) {
    if (e instanceof ApiAuthError) {
      if (e.status === 403) return { ok: false, message: "Administrator role required.", seq, values };
      redirect("/sign-in");
    }
    if (e instanceof ApiRequestError) {
      refresh();
      return { ok: false, message: refusalMessage(e, "The change was not saved."), seq, values };
    }
    return { ok: false, message: UNREACHABLE, seq, values };
  }
  refresh();
  return { ok: true, message: success, seq };
}

export async function registerDevice(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const values = {
    label: String(formData.get("label") ?? "").trim().toUpperCase(),
    radioId: String(formData.get("radioId") ?? "").trim(),
    hardwareRevision: String(formData.get("hardwareRevision") ?? "").trim(),
    firmwareVersion: String(formData.get("firmwareVersion") ?? "").trim(),
    keySlotReference: String(formData.get("keySlotReference") ?? "").trim(),
  };
  const radioId = Number(values.radioId);
  if (Object.values(values).some((v) => !v)) return { ok: false, message: "All fields are required.", seq, values };
  if (!Number.isInteger(radioId) || radioId <= 0) return { ok: false, message: "Radio ID must be a positive whole number.", seq, values };
  return send("/api/admin/devices", { ...values, radioId }, seq, `Hardhat ${values.label} registered.`, values);
}

const STATES = new Set(["registered", "disabled", "retired"]);

export async function setDeviceState(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const id = String(formData.get("deviceId") ?? "");
  const state = String(formData.get("state") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  if (!id || !STATES.has(state)) return { ok: false, message: "Invalid request. Reload the page.", seq };
  const done = { registered: "Returned to service.", disabled: "Disabled.", retired: "Retired." }[state];
  return send(`/api/admin/devices/${encodeURIComponent(id)}/state`, { state, reason: reason || null }, seq, done ?? "Saved.");
}
