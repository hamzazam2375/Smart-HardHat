// History and filters (F26-113 §4.8.5; UC-13). Supervisor roles only (Table 4.34).
import type { Metadata } from "next";
import { Suspense } from "react";
import { HistoryView } from "@/components/history/history-view";
import { PageSkeleton, SupervisorOnly } from "@/components/layout/supervisor-only";
import { canSupervise } from "@/lib/accounts";
import { loadHistory } from "@/lib/history";
import { HISTORY_PARAMS, type HistoryQuery } from "@/lib/history-types";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "History" };

type Search = Promise<Record<string, string | string[] | undefined>>;

async function HistoryContent({ searchParams }: { searchParams: Search }) {
  const { account, token } = await requireSession();
  if (!canSupervise(account.role)) return <SupervisorOnly name={account.displayName} />;
  const sp = await searchParams;
  const query: HistoryQuery = {};
  for (const k of HISTORY_PARAMS) {
    const v = sp[k];
    if (typeof v === "string" && v) query[k] = v;
  }
  const { page, error } = await loadHistory(token, query);
  return <HistoryView page={page} error={error} query={query} />;
}

export default function HistoryRoute(props: PageProps<"/history">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading history…" />}>
      <HistoryContent searchParams={props.searchParams} />
    </Suspense>
  );
}
