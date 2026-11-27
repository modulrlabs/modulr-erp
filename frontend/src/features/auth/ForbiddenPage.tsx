import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ShieldAlert } from 'lucide-react';
import { getDefaultHomeRoute, useAuthStore } from '../../stores/authStore';

export const ForbiddenPage: React.FC = () => {
  const user = useAuthStore((s) => s.user);
  const homeRoute = getDefaultHomeRoute(user?.role);

  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4 text-center">
      <div className="max-w-md rounded-2xl border border-red-200 bg-white p-8 shadow-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
          <ShieldAlert className="h-6 w-6" />
        </div>
        <h1 className="mt-4 text-xl font-bold text-slate-900">403 — Access Denied</h1>
        <p className="mt-2 text-sm text-slate-600">
          You do not have permission to view this page.
          {user ? ` Your current role is ${user.role}.` : ''}
        </p>
        <Link
          to={homeRoute}
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to Home</span>
        </Link>
      </div>
    </div>
  );
};
