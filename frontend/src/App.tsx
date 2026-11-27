import React, { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { apiClient, syncAuthMe } from './api/client';
import { PermissionGuard, ProtectedRoute, PublicOnlyRoute } from './components/Guards';
import { Layout } from './components/Layout';
import { ChangePasswordPage } from './features/auth/ChangePasswordPage';
import { ForbiddenPage } from './features/auth/ForbiddenPage';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterShopPage } from './features/auth/RegisterShopPage';
import { InventoryPage } from './features/inventory/InventoryPage';
import { PosCheckoutPage } from './features/pos/PosCheckoutPage';
import { getDefaultHomeRoute, useAuthStore } from './stores/authStore';
import type { MeResponse, ShopProfile, UserProfile } from './types/erp';

const AuthFocusSync: React.FC = () => {
  const isAuthenticated = useAuthStore((s) => Boolean(s.accessToken && s.user));

  useQuery({
    queryKey: ['auth', 'me'],
    queryFn: syncAuthMe,
    enabled: isAuthenticated,
    refetchOnWindowFocus: true,
    staleTime: 60_000,
    retry: false,
  });

  return null;
};

const HomeRedirect: React.FC = () => {
  const user = useAuthStore((s) => s.user);
  return <Navigate to={getDefaultHomeRoute(user?.role)} replace />;
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

export const App: React.FC = () => {
  const { isInitialized, setAuth, clearAuth, setInitialized } = useAuthStore();

  useEffect(() => {
    // -------------------------------------------------------------------------
    // Silent Session Restore on Application Mount
    // -------------------------------------------------------------------------
    // Attempt to rotate tokens via the secure httpOnly cookie (modulr_refresh_token).
    // If a valid cookie exists, we obtain a fresh access token and load user/tenant profile
    // without ever storing credentials or JWTs in insecure localStorage.
    const restoreSession = async () => {
      try {
        const refreshResponse = await axios.post<{ access: string }>(
          `${BASE_URL}/auth/token/refresh/`,
          {},
          {
            withCredentials: true,
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
            },
          }
        );

        const newAccessToken = refreshResponse.data.access;

        // Fetch active user details and tenant profile
        const meResponse = await apiClient.get<MeResponse>('/auth/me/', {
          headers: {
            Authorization: `Bearer ${newAccessToken}`,
          },
        });

        const meData = meResponse.data;
        const shopData = meData.shop;

        const normalizedShop: ShopProfile | null = shopData
          ? {
              id: shopData.id,
              public_id: shopData.public_id,
              name: shopData.name,
              address: shopData.address,
              phone: shopData.phone,
              is_active: shopData.is_active,
              features: shopData.features || {
                enable_credit_module: !!shopData.enable_credit_module,
                enable_whatsapp_alerts: !!shopData.enable_whatsapp_alerts,
              },
            }
          : null;

        const userProfile: UserProfile = {
          id: meData.id,
          public_id: meData.public_id,
          username: meData.username,
          email: meData.email,
          first_name: meData.first_name,
          last_name: meData.last_name,
          role: meData.role,
          must_change_password: meData.must_change_password,
        };

        setAuth(
          userProfile,
          normalizedShop,
          newAccessToken,
          meData.permissions ?? [],
          Boolean(meData.must_change_password)
        );
      } catch {
        // No active or valid cookie; user starts in unauthenticated state
        clearAuth();
      } finally {
        setInitialized(true);
      }
    };

    restoreSession();
  }, [setAuth, clearAuth, setInitialized]);

  if (!isInitialized) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
          <p className="text-sm font-semibold text-slate-600">Initializing Modulr ERP...</p>
        </div>
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <AuthFocusSync />
      <BrowserRouter>
        <Routes>
          {/* Public Auth Routes */}
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterShopPage />} />
          </Route>

          {/* Protected Application Routes */}
          <Route element={<ProtectedRoute />}>
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route path="/forbidden" element={<ForbiddenPage />} />
            <Route element={<Layout />}>
              <Route element={<PermissionGuard permission="sales.pos_checkout" />}>
                <Route path="/pos" element={<PosCheckoutPage />} />
              </Route>
              <Route element={<PermissionGuard permission="inventory.view_products" />}>
                <Route path="/inventory" element={<InventoryPage />} />
              </Route>
              <Route path="/" element={<HomeRedirect />} />
            </Route>
          </Route>

          {/* Fallback Catch-all Route */}
          <Route path="*" element={<Navigate to="/pos" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
