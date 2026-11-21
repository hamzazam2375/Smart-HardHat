// Account roles and permission helpers (Table 4.34). Accounts live in the backend DB.

export type Role = "supervisor" | "admin" | "admin_supervisor";

export interface Account {
  id: string;
  email: string;
  displayName: string;
  role: Role;
}

export const canSupervise = (role: Role) => role === "supervisor" || role === "admin_supervisor";
export const canAdminister = (role: Role) => role === "admin" || role === "admin_supervisor";

export const ROLE_LABEL: Record<Role, string> = {
  supervisor: "Supervisor",
  admin: "Administrator",
  admin_supervisor: "Administrator + supervisor",
};
