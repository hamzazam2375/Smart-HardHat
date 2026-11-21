"use client";

// Administrator-only controls (UC-18; FR-29). The backend enforces the role; these are hidden
// for other roles only for clarity. No key material is entered or shown: only a key-slot reference.
import { useActionState, useState } from "react";
import { registerDevice, setDeviceState } from "@/app/actions/devices";
import { FormMessage, INPUT_CLS, SubmitButton } from "@/components/forms";
import type { DeviceHealth } from "@/lib/device-types";
import { INITIAL_FORM_STATE } from "@/lib/form-state";

const FIELDS = [
  { name: "label", label: "Label", placeholder: "HAT-004", mono: true },
  { name: "radioId", label: "Radio ID", placeholder: "4", mono: true },
  { name: "hardwareRevision", label: "Hardware revision", placeholder: "HH-A2", mono: false },
  { name: "firmwareVersion", label: "Firmware version", placeholder: "0.3.7", mono: false },
  { name: "keySlotReference", label: "Key slot reference", placeholder: "slot-4 (reference only, never the key)", mono: true },
] as const;

export function RegisterDeviceForm() {
  const [state, action, pending] = useActionState(registerDevice, INITIAL_FORM_STATE);
  const keep = state.ok ? undefined : state.values;
  return (
    <section aria-labelledby="register-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 id="register-heading" className="font-semibold">
        Register a hardhat <span className="text-xs font-normal text-slate-500">(administrator)</span>
      </h2>
      <form key={state.seq} action={action} className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {FIELDS.map((f) => (
          <div key={f.name} className="space-y-1">
            <label htmlFor={`reg-${f.name}`} className="block text-xs font-medium text-slate-700">
              {f.label}
            </label>
            <input
              id={`reg-${f.name}`}
              name={f.name}
              required
              maxLength={f.name === "keySlotReference" ? 64 : 32}
              inputMode={f.name === "radioId" ? "numeric" : undefined}
              placeholder={f.placeholder}
              defaultValue={keep?.[f.name] ?? ""}
              autoComplete="off"
              className={`${INPUT_CLS} ${f.mono ? "font-mono" : ""}`}
            />
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-5">
          <SubmitButton pending={pending}>Register hardhat</SubmitButton>
          <FormMessage state={state} />
        </div>
        <p className="text-xs text-slate-500 sm:col-span-2 lg:col-span-5">
          Keys are provisioned during wired setup. Enter only the reference to the key slot; never paste key material here.
        </p>
      </form>
    </section>
  );
}

export function DeviceStateControl({ device }: { device: DeviceHealth }) {
  const [state, action, pending] = useActionState(setDeviceState, INITIAL_FORM_STATE);
  const [confirm, setConfirm] = useState<"disabled" | "retired" | null>(null);

  if (device.state === "retired") {
    return <p className="text-xs text-slate-500">Retired devices cannot return to service. Kept for retained history.</p>;
  }

  if (confirm) {
    return (
      <form action={action} className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-2">
        <input type="hidden" name="deviceId" value={device.deviceId} />
        <input type="hidden" name="state" value={confirm} />
        <label htmlFor={`reason-${device.deviceId}`} className="block text-xs font-medium text-slate-700">
          Reason (optional)
        </label>
        <input id={`reason-${device.deviceId}`} name="reason" maxLength={200} className={`${INPUT_CLS} py-1 text-xs`} />
        {confirm === "retired" && (
          <p className="text-xs text-red-800">Retiring is permanent. The hardhat can no longer send operational data.</p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <SubmitButton pending={pending} variant="danger">
            {confirm === "retired" ? `Retire ${device.label}` : `Disable ${device.label}`}
          </SubmitButton>
          <button type="button" onClick={() => setConfirm(null)} className="text-xs text-slate-600 hover:underline">
            Cancel
          </button>
        </div>
        <FormMessage state={state} />
      </form>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-2">
        {device.state === "disabled" ? (
          <form action={action}>
            <input type="hidden" name="deviceId" value={device.deviceId} />
            <input type="hidden" name="state" value="registered" />
            <SubmitButton pending={pending} variant="secondary">
              Return to service
            </SubmitButton>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setConfirm("disabled")}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
          >
            Disable…
          </button>
        )}
        <button
          type="button"
          onClick={() => setConfirm("retired")}
          className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
        >
          Retire…
        </button>
      </div>
      <FormMessage state={state} />
    </div>
  );
}
