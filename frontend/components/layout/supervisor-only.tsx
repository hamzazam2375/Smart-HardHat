// Table 4.34: worker names, readings, locations and assignments are for supervisor roles only.
// The backend enforces this too (403); this is just the friendly page.
export function SupervisorOnly({ name }: { name: string }) {
  return (
    <div className="mx-auto max-w-xl px-4 py-16 md:px-8">
      <h1 className="text-2xl font-semibold">Supervisor access required</h1>
      <p className="mt-2 text-sm text-slate-600">
        {name}, your account has administrator permissions only. This page shows worker information, which is
        available to supervisors.
      </p>
    </div>
  );
}

/** Table 4.34: accounts, device registration and configuration are administrator actions. */
export function AdminOnly({ name }: { name: string }) {
  return (
    <div className="mx-auto max-w-xl px-4 py-16 md:px-8">
      <h1 className="text-2xl font-semibold">Administrator access required</h1>
      <p className="mt-2 text-sm text-slate-600">
        {name}, this page is for administrators. The server refuses these actions for other roles.
      </p>
    </div>
  );
}

export function PageSkeleton({ label }: { label: string }) {
  return (
    <div className="mx-auto max-w-6xl animate-pulse space-y-6 px-4 py-6 md:px-8" aria-busy="true">
      <div className="h-8 w-48 rounded bg-slate-200" />
      <div className="h-24 rounded-xl bg-slate-200" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="h-64 rounded-xl bg-slate-200 lg:col-span-2" />
        <div className="h-64 rounded-xl bg-slate-200" />
      </div>
      <p className="text-sm text-slate-500">{label}</p>
    </div>
  );
}
