import React, { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios from 'axios';
import { apiClient } from './api/client';
import { ProtectedRoute, PublicOnlyRoute } from './components/Guards';
import { Layout } from './components/Layout';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterShopPage } from './features/auth/RegisterShopPage';
import { InventoryPage } from './features/inventory/InventoryPage';
import { PosCheckoutPage } from './features/pos/PosCheckoutPage';
import { useAuthStore } from './stores/authStore';
import type { ShopProfile, UserProfile } from './types/erp';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
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
        const meResponse = await apiClient.get<
          UserProfile & {
            shop: {
              id: number;
              public_id: string;
              name: string;
              address: string;
              phone: string;
              is_active?: boolean;
              enable_credit_module?: boolean;
              enable_whatsapp_alerts?: boolean;
              features?: {
                enable_credit_module: boolean;
                enable_whatsapp_alerts: boolean;
              };
            } | null;
          }
        >('/auth/me/', {
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
          username: meData.username,
          email: meData.email,
          first_name: meData.first_name,
          last_name: meData.last_name,
          role: meData.role,
        };

        setAuth(userProfile, normalizedShop, newAccessToken);
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
      <BrowserRouter>
        <Routes>
          {/* Public Auth Routes (Redirects to /pos if already authenticated) */}
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterShopPage />} />
          </Route>

          {/* Protected Application Routes */}
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/pos" element={<PosCheckoutPage />} />
              <Route path="/inventory" element={<InventoryPage />} />
              <Route path="/" element={<Navigate to="/pos" replace />} />
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
