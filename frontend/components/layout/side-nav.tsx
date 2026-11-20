"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Role } from "@/lib/mock/accounts";

interface NavItem {
  label: string;
  href: string;
  roles: Role[];
  ready: boolean; // false = page not built yet
}

// Table 4.34 navigation and permission mapping.
const SUP: Role[] = ["supervisor", "admin_supervisor"];
const ADM: Role[] = ["admin", "admin_supervisor"];
const ALL: Role[] = ["supervisor", "admin", "admin_supervisor"];

const ITEMS: NavItem[] = [
  { label: "Overview", href: "/", roles: SUP, ready: true },
  { label: "Alerts", href: "/alerts", roles: SUP, ready: false },
  { label: "Workers", href: "/workers", roles: SUP, ready: false },
  { label: "Devices", href: "/devices", roles: ALL, ready: false },
  { label: "History", href: "/history", roles: SUP, ready: false },
  { label: "Accounts", href: "/accounts", roles: ADM, ready: false },
  { label: "Settings", href: "/settings", roles: ADM, ready: false },
];

export function SideNav({ role }: { role: Role }) {
  const pathname = usePathname();
  const items = ITEMS.filter((i) => i.roles.includes(role));

  return (
    <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto md:mx-0 md:flex-col md:overflow-visible">
      {items.map((item) => {
        const active = pathname === item.href;
        if (!item.ready) {
          return (
            <span
              key={item.href}
              aria-disabled="true"
              title="Not built yet"
              className="flex shrink-0 items-center justify-between gap-2 rounded-md px-3 py-2 text-sm text-slate-500"
            >
              {item.label}
              <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
                soon
              </span>
            </span>
          );
        }
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`shrink-0 rounded-md px-3 py-2 text-sm font-medium ${
              active ? "bg-brand text-slate-900" : "text-slate-200 hover:bg-slate-800"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
