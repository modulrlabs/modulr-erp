import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { getDefaultHomeRoute, useAuthStore } from '../stores/authStore';
import type { ShopFeatures } from '../types/erp';

export const ProtectedRoute: React.FC = () => {
  const { user, mustChangePassword, isInitialized } = useAuthStore();
  const location = useLocation();

  if (!isInitialized) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
          <p className="text-sm font-medium text-slate-600">Restoring secure session...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (mustChangePassword && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  return <Outlet />;
};

export const PublicOnlyRoute: React.FC = () => {
  const { user, mustChangePassword, isInitialized } = useAuthStore();

  if (!isInitialized) {
    return null;
  }

  if (user) {
    return (
      <Navigate
        to={mustChangePassword ? '/change-password' : getDefaultHomeRoute(user.role)}
        replace
      />
    );
  }

  return <Outlet />;
};

interface PermissionGuardProps {
  permission?: string;
  anyOf?: string[];
  children?: React.ReactNode;
}

export const PermissionGuard: React.FC<PermissionGuardProps> = ({
  permission,
  anyOf,
  children,
}) => {
  const permissions = useAuthStore((s) => s.permissions);

  let allowed = false;
  if (permission) {
    allowed = permissions.includes(permission);
  } else if (anyOf && anyOf.length > 0) {
    allowed = anyOf.some((p) => permissions.includes(p));
  }

  if (!allowed) {
    return <Navigate to="/forbidden" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
};

interface FeatureGuardProps {
  feature: keyof ShopFeatures;
  children?: React.ReactNode;
}

export const FeatureGuard: React.FC<FeatureGuardProps> = ({ feature, children }) => {
  const shop = useAuthStore((s) => s.shop);

  if (!shop?.features?.[feature]) {
    return <Navigate to="/forbidden" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
};
