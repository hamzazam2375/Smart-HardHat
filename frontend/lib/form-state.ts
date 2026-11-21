/** Result of a dashboard form server action. */
export interface FormState {
  ok: boolean;
  message: string | null;
  /** Bumped on every result so a form can reset itself after a success. */
  seq: number;
  /** Submitted text echoed back on failure, so a refused form keeps what the user typed. */
  values?: Record<string, string>;
  /** One-time secret to show once (e.g. a temporary password). Never stored client-side. */
  secret?: string;
  /** Field-level validation messages from the backend. */
  errors?: string[];
}

export const INITIAL_FORM_STATE: FormState = { ok: false, message: null, seq: 0 };
