// Administrator loaders (server-side): accounts and configuration review.
import { api } from "@/lib/api";
import type { AdminAccount, ConfigSnapshot } from "@/lib/admin-types";

export async function loadAccounts(token: string): Promise<AdminAccount[]> {
  return (await api<{ accounts: AdminAccount[] }>("/api/admin/accounts", { token })).accounts;
}

export function loadConfigurations(token: string): Promise<ConfigSnapshot> {
  return api<ConfigSnapshot>("/api/admin/configurations", { token });
}
