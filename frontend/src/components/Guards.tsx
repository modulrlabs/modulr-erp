import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import type { UserRole } from '../types/erp';

interface ProtectedRouteProps {
  allowedRoles?: UserRole[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ allowedRoles }) => {
  const { user, isInitialized } = useAuthStore();
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

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <div className="flex h-[80vh] flex-col items-center justify-center text-center">
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 shadow-sm">
          <h2 className="text-xl font-bold text-red-700">Access Restricted</h2>
          <p className="mt-2 text-sm text-red-600">
            This screen is restricted to Shop Owners. Your current role is {user.role}.
          </p>
        </div>
      </div>
    );
  }

  return <Outlet />;
};

export const PublicOnlyRoute: React.FC = () => {
  const { user, isInitialized } = useAuthStore();

  if (!isInitialized) {
    return null;
  }

  if (user) {
    return <Navigate to="/pos" replace />;
  }

  return <Outlet />;
};
