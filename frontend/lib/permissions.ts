import type { CurrentUser } from "@/types";

/** Superadmin pasa cualquier chequeo — mismo criterio que el backend
 * (require_permission en app/core/deps.py: is_superuser bypassea la lista). */
export function hasPermission(user: CurrentUser | null | undefined, permission: string): boolean {
  if (!user) return false;
  return user.is_superuser || user.permissions.includes(permission);
}
