// Small form helpers shared by the dashboard pages.
import type { FormState } from "@/lib/form-state";

export const INPUT_CLS =
  "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-brand-dark focus:ring-2 focus:ring-brand/40 disabled:bg-slate-100";

const BUTTON_CLS = {
  primary: "bg-slate-900 text-white hover:bg-slate-800",
  brand: "bg-brand text-slate-900 hover:bg-amber-400",
  secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
  danger: "border border-red-300 bg-white text-red-700 hover:bg-red-50",
};

export function SubmitButton({
  children,
  pending,
  variant = "primary",
  disabled = false,
}: {
  children: React.ReactNode;
  pending: boolean;
  variant?: keyof typeof BUTTON_CLS;
  disabled?: boolean;
}) {
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      aria-disabled={pending || disabled}
      className={`rounded-lg px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_CLS[variant]}`}
    >
      {pending ? "Saving…" : children}
    </button>
  );
}

/** Result line under a form. Errors are announced to screen readers. */
export function FormMessage({ state }: { state: FormState }) {
  if (!state.message) return null;
  if (!state.ok && state.errors?.length) {
    return (
      <div role="alert" className="text-sm text-red-700">
        <p>▲ {state.message}</p>
        <ul className="mt-1 list-disc pl-5">
          {state.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      </div>
    );
  }
  return state.ok ? (
    <p role="status" className="text-sm text-emerald-700">
      ✓ {state.message}
    </p>
  ) : (
    <p role="alert" className="text-sm text-red-700">
      ▲ {state.message}
    </p>
  );
}
