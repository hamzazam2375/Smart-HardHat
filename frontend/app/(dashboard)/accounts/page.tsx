// Account administration (UC-19). Administrator roles only (Table 4.34); enforced by the backend.
import type { Metadata } from "next";
import { Suspense } from "react";
import { AccountsPage } from "@/components/accounts/accounts-page";
import { AdminOnly, PageSkeleton } from "@/components/layout/supervisor-only";
import { canAdminister } from "@/lib/accounts";
import { loadAccounts } from "@/lib/admin";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Accounts" };

async function AccountsContent() {
  const { account, token } = await requireSession();
  if (!canAdminister(account.role)) return <AdminOnly name={account.displayName} />;
  const accounts = await loadAccounts(token);
  return <AccountsPage accounts={accounts} selfId={account.id} />;
}

export default function AccountsRoute() {
  return (
    <Suspense fallback={<PageSkeleton label="Loading accounts…" />}>
      <AccountsContent />
    </Suspense>
  );
}
