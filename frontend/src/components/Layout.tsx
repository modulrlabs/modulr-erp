import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LogOut, Package, ShoppingCart, Store, User } from 'lucide-react';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';

export const Layout: React.FC = () => {
  const { user, shop, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = React.useState(false);

  const handleLogout = async () => {
    try {
      setIsLoggingOut(true);
      await apiClient.post(
        '/auth/logout/',
        {},
        {
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
          },
        }
      );
    } catch {
      // Proceed with frontend session teardown even if network/backend already wiped cookie
    } finally {
      clearAuth();
      setIsLoggingOut(false);
      navigate('/login');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      {/* Header Bar */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Logo & Navigation */}
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-md shadow-indigo-200">
                <Store className="h-5 w-5" />
              </div>
              <div>
                <span className="text-base font-bold tracking-tight text-slate-900">Modulr ERP</span>
                {shop && (
                  <span className="block text-xs font-medium text-slate-500 truncate max-w-[140px] sm:max-w-[200px]">
                    {shop.name}
                  </span>
                )}
              </div>
            </div>

            <nav className="flex items-center gap-1 sm:gap-2">
              <NavLink
                to="/pos"
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700 shadow-sm'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                <ShoppingCart className="h-4 w-4" />
                <span>POS Billing</span>
              </NavLink>

              <NavLink
                to="/inventory"
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700 shadow-sm'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                <Package className="h-4 w-4" />
                <span>Inventory</span>
              </NavLink>
            </nav>
          </div>

          {/* User Profile & Actions */}
          <div className="flex items-center gap-3">
            {user && (
              <div className="hidden sm:flex items-center gap-2.5 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-1.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-200 text-slate-700">
                  <User className="h-4 w-4" />
                </div>
                <div className="text-left">
                  <span className="block text-xs font-semibold text-slate-800 leading-none">
                    {user.username}
                  </span>
                  <span
                    className={`mt-0.5 inline-block text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.2 rounded ${
                      user.role === 'OWNER'
                        ? 'bg-purple-100 text-purple-700'
                        : 'bg-blue-100 text-blue-700'
                    }`}
                  >
                    {user.role}
                  </span>
                </div>
              </div>
            )}

            <button
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-red-50 hover:border-red-200 hover:text-red-600 transition-colors shadow-sm disabled:opacity-50"
              title="Sign out of Modulr ERP"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Page Content */}
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
};
