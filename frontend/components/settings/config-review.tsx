"use client";

// Configuration review (F26-113 §4.8.7; UC-20; FR-47, FR-48, FR-53). Administrator only.
// A browser draft is NOT an over-air update: approving records the reviewed version as active
// on the server, and each hardhat changes only through controlled wired setup. The table of
// reported versions shows what each hardhat actually runs.
import { useActionState } from "react";
import { approveConfig, createConfigDraft } from "@/app/actions/admin";
import { FormMessage, INPUT_CLS, SubmitButton } from "@/components/forms";
import { Badge, DateTime, type Tone } from "@/components/overview/badge";
import type { ConfigField, ConfigSnapshot, Configuration } from "@/lib/admin-types";
import { INITIAL_FORM_STATE } from "@/lib/form-state";

const STATE_BADGE: Record<Configuration["state"], { label: string; tone: Tone }> = {
  active: { label: "Active", tone: "ok" },
  draft: { label: "Draft, not reviewed", tone: "warning" },
  retired: { label: "Retired", tone: "muted" },
};

function fmt(v: number | undefined, f: ConfigField): string {
  if (v === undefined || v === null) return "not set";
  return `${v} ${f.unit}`;
}

function ValuesTable({ schema, config, compare }: { schema: ConfigSnapshot["schema"]; config: Configuration; compare?: Configuration }) {
  const groups: [string, ConfigField[], "thresholds" | "timings"][] = [
    ["Thresholds", schema.thresholds, "thresholds"],
    ["Timings", schema.timings, "timings"],
  ];
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {groups.map(([title, fields, key]) => (
        <div key={key}>
          <h4 className="text-xs font-medium tracking-wide text-slate-500 uppercase">{title}</h4>
          <dl className="mt-1 divide-y divide-slate-100">
            {fields.map((f) => {
              const v = config[key][f.key];
              const old = compare?.[key][f.key];
              const changed = compare !== undefined && old !== v;
              return (
                <div key={f.key} className={`flex items-baseline justify-between gap-2 py-1 text-sm ${changed ? "bg-amber-50" : ""}`}>
                  <dt className="text-slate-600">{f.label}</dt>
                  <dd className="text-right font-mono">
                    {fmt(v, f)}
                    {changed && (
                      <span className="block text-xs font-sans text-amber-900">
                        was {fmt(old, f)} · re-run its boundary check
                      </span>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      ))}
    </div>
  );
}

function ApproveForm({ draft }: { draft: Configuration }) {
  const [state, action, pending] = useActionState(approveConfig, INITIAL_FORM_STATE);
  return (
    <form key={state.seq} action={action} className="space-y-2 border-t border-slate-100 pt-3">
      <input type="hidden" name="configId" value={draft.id} />
      <label htmlFor={`reason-${draft.id}`} className="block text-sm font-medium text-slate-700">
        Review reason (required)
      </label>
      <textarea
        id={`reason-${draft.id}`}
        name="reason"
        rows={2}
        maxLength={500}
        required
        defaultValue={state.ok ? "" : (state.values?.reason ?? "")}
        placeholder="Why this change, what evidence was reviewed"
        className={INPUT_CLS}
      />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="checked" value="yes" className="mt-1" />
        <span>
          I understand this does not update any hardhat. Each hardhat must be set up by wire, and the boundary checks for
          every changed value must be re-run before the next trial.
        </span>
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <SubmitButton pending={pending} variant="brand">
          Approve {draft.version}
        </SubmitButton>
        <FormMessage state={state} />
      </div>
    </form>
  );
}

function DraftForm({ schema, base }: { schema: ConfigSnapshot["schema"]; base: Configuration | undefined }) {
  const [state, action, pending] = useActionState(createConfigDraft, INITIAL_FORM_STATE);
  const keep = state.ok ? undefined : state.values;
  const groups: [string, ConfigField[], "t" | "m", "thresholds" | "timings"][] = [
    ["Thresholds", schema.thresholds, "t", "thresholds"],
    ["Timings", schema.timings, "m", "timings"],
  ];
  return (
    <section aria-labelledby="draft-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 id="draft-heading" className="font-semibold">
        New draft
      </h2>
      <p className="mt-0.5 text-xs text-slate-500">
        {base ? `Starts from ${base.version}.` : "No active version to start from."} Values are checked against the allowed
        ranges and for contradictions (for example CO reset must be below CO urgent).
      </p>
      <form key={state.seq} action={action} className="mt-3 space-y-4">
        <div className="max-w-xs space-y-1">
          <label htmlFor="cfg-version" className="block text-sm font-medium text-slate-700">
            Version name
          </label>
          <input id="cfg-version" name="version" required maxLength={40} placeholder="cfg-1.2" defaultValue={keep?.version ?? ""} className={`${INPUT_CLS} font-mono`} />
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          {groups.map(([title, fields, prefix, key]) => (
            <fieldset key={key} className="space-y-2">
              <legend className="text-xs font-medium tracking-wide text-slate-500 uppercase">{title}</legend>
              {fields.map((f) => {
                const name = `${prefix}.${f.key}`;
                const def = keep?.[name] ?? (base?.[key][f.key] !== undefined ? String(base[key][f.key]) : "");
                return (
                  <div key={f.key} className="grid grid-cols-[1fr_7rem] items-center gap-2">
                    <label htmlFor={`cfg-${name}`} className="text-sm text-slate-700">
                      {f.label}
                      <span className="block text-xs text-slate-500">
                        {f.min}–{f.max} {f.unit}
                      </span>
                    </label>
                    <input
                      id={`cfg-${name}`}
                      name={name}
                      type="number"
                      required
                      min={f.min}
                      max={f.max}
                      step={f.integer ? 1 : "any"}
                      defaultValue={def}
                      className={`${INPUT_CLS} py-1 text-right font-mono`}
                    />
                  </div>
                );
              })}
            </fieldset>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <SubmitButton pending={pending}>Save draft</SubmitButton>
          <FormMessage state={state} />
        </div>
      </form>
    </section>
  );
}

export function ConfigReview({ snapshot }: { snapshot: ConfigSnapshot }) {
  const { schema, configurations, devices } = snapshot;
  const active = configurations.find((c) => c.state === "active");
  const drafts = configurations.filter((c) => c.state === "draft");
  const retired = configurations.filter((c) => c.state === "retired");

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 md:px-8">
      <header>
        <h1 className="text-2xl font-semibold">Configuration review</h1>
        <p className="text-sm text-slate-500">Versioned thresholds and timings for the prototype hardhats.</p>
      </header>

      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        Saving or approving here never updates a hardhat that a worker is wearing. Hardhat settings change only through
        controlled wired setup, then the stored version is verified on startup. These values are prototype review bounds,
        not certified alarm setpoints.
      </p>

      <section aria-labelledby="active-cfg-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="active-cfg-heading" className="font-semibold">
            Active version {active && <span className="font-mono">{active.version}</span>}
          </h2>
          {active ? <Badge tone="ok">Active</Badge> : <Badge tone="warning">None active</Badge>}
        </div>
        {active ? (
          <>
            <p className="mt-1 text-xs text-slate-600">
              Approved by {active.reviewer ?? "unknown"}
              {active.activatedAt && (
                <>
                  {" "}
                  on <DateTime iso={active.activatedAt} />
                </>
              )}
              {active.reviewReason && <> · “{active.reviewReason}”</>}
            </p>
            <p className="font-mono text-[11px] break-all text-slate-400">{active.checksum}</p>
            <div className="mt-3">
              <ValuesTable schema={schema} config={active} />
            </div>
          </>
        ) : (
          <p className="mt-2 text-sm text-slate-600">No configuration has been approved yet.</p>
        )}
      </section>

      <section aria-labelledby="devices-cfg-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 id="devices-cfg-heading" className="font-semibold">
          Version reported by each hardhat
        </h2>
        <ul className="mt-2 divide-y divide-slate-100">
          {devices.map((d) => {
            const match = active && d.reportedVersion === active.version;
            return (
              <li key={d.label} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span className="font-mono">
                  {d.label}
                  {d.state !== "registered" && <span className="ml-1 font-sans text-xs text-slate-500">({d.state})</span>}
                </span>
                <span className="flex items-center gap-2">
                  <span className="font-mono">{d.reportedVersion ?? "unknown"}</span>
                  {!d.reportedVersion ? (
                    <Badge tone="muted">Never reported</Badge>
                  ) : match ? (
                    <Badge tone="ok">Matches active</Badge>
                  ) : (
                    <Badge tone="warning">Needs wired setup</Badge>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="mt-1 text-xs text-slate-500">From each hardhat&apos;s latest accepted status, not from this page.</p>
      </section>

      {drafts.map((d) => (
        <section key={d.id} className="space-y-3 rounded-xl border border-amber-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">
              Draft <span className="font-mono">{d.version}</span>
            </h2>
            <Badge tone={STATE_BADGE.draft.tone}>{STATE_BADGE.draft.label}</Badge>
          </div>
          <p className="text-xs text-slate-500">
            Created <DateTime iso={d.createdAt} /> · changed values are highlighted against the active version
          </p>
          <ValuesTable schema={schema} config={d} compare={active} />
          <ApproveForm draft={d} />
        </section>
      ))}

      <DraftForm schema={schema} base={active} />

      {retired.length > 0 && (
        <details className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <summary className="cursor-pointer font-semibold">Earlier versions ({retired.length})</summary>
          <ul className="mt-2 divide-y divide-slate-100">
            {retired.map((c) => (
              <li key={c.id} className="py-2 text-sm">
                <span className="font-mono">{c.version}</span>{" "}
                <span className="text-xs text-slate-500">
                  approved by {c.reviewer ?? "unknown"}
                  {c.activatedAt && (
                    <>
                      {" "}
                      on <DateTime iso={c.activatedAt} />
                    </>
                  )}
                  {" · "}
                  {c.telemetryCount} status records reference it
                </span>
                {c.reviewReason && <p className="text-xs text-slate-600">“{c.reviewReason}”</p>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
