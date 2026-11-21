import Link from "next/link";

export default function AlertNotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-16 md:px-8">
      <h1 className="text-2xl font-semibold">Alert not found</h1>
      <p className="mt-2 text-sm text-slate-600">
        This alert does not exist or is no longer retained (identifiable records are kept for 30 days).
      </p>
      <Link href="/" className="mt-6 inline-block text-sm font-medium text-slate-900 underline">
        Back to Overview
      </Link>
    </div>
  );
}
