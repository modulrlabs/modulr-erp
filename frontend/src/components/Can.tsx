import React from 'react';
import { useAuthStore } from '../stores/authStore';

interface CanProps {
  permission?: string;
  anyOf?: string[];
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

export const Can: React.FC<CanProps> = ({
  permission,
  anyOf,
  fallback = null,
  children,
}) => {
  const permissions = useAuthStore((s) => s.permissions);

  let allowed = false;
  if (permission) {
    allowed = permissions.includes(permission);
  } else if (anyOf && anyOf.length > 0) {
    allowed = anyOf.some((p) => permissions.includes(p));
  }

  return <>{allowed ? children : fallback}</>;
};
