export function HardhatIcon({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="currentColor">
      <path d="M12 4a7 7 0 0 0-7 7v2h14v-2a7 7 0 0 0-7-7Zm-1.5 1.2V10h3V5.2a6 6 0 0 1 1.5.5V10h1V6.4A6 6 0 0 1 18 11v1H6v-1a6 6 0 0 1 2-4.6V10h1V5.7a6 6 0 0 1 1.5-.5Z" />
      <rect x="2" y="14" width="20" height="3" rx="1.5" />
    </svg>
  );
}

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-slate-900">
        <HardhatIcon />
      </span>
      <div className="leading-tight">
        <p className={`text-sm font-semibold ${light ? "text-white" : "text-slate-900"}`}>Smart Hardhat</p>
        <p className={`text-xs ${light ? "text-slate-400" : "text-slate-500"}`}>Supervisor dashboard</p>
      </div>
    </div>
  );
}
