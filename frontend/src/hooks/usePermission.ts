import { useAuthStore } from '../stores/authStore';

export function usePermission(permission: string): boolean {
  const permissions = useAuthStore((s) => s.permissions);
  return permissions.includes(permission);
}

export function useAnyPermission(requiredPermissions: string[]): boolean {
  const permissions = useAuthStore((s) => s.permissions);
  return requiredPermissions.some((p) => permissions.includes(p));
}
