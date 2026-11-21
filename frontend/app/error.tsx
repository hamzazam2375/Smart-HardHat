"use client";

// Shown when a page cannot load, most often because the backend API is unreachable.
// Data that could not be loaded is never shown as zero or "safe".
import { useEffect } from "react";

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto max-w-xl px-4 py-16 md:px-8">
      <h1 className="text-2xl font-semibold">Status unavailable</h1>
      <p className="mt-2 text-sm text-slate-600">
        The dashboard could not load data from the server. Current worker status is unknown. This does
        not mean workers are safe. Hardhat alarms keep working without the server.
      </p>
      <button
        onClick={() => retry()}
        className="mt-6 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
      >
        Try again
      </button>
    </main>
  );
}
