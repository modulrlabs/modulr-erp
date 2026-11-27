import { create } from 'zustand';
import type { MeResponse, ShopProfile, UserProfile, UserRole } from '../types/erp';

interface AuthState {
  // In-memory access token only: NEVER written to localStorage or sessionStorage
  // to protect against Cross-Site Scripting (XSS) token theft.
  accessToken: string | null;
  user: UserProfile | null;
  shop: ShopProfile | null;
  permissions: string[];
  mustChangePassword: boolean;
  isInitialized: boolean;

  setAuth: (
    user: UserProfile,
    shop: ShopProfile | null,
    accessToken: string,
    permissions?: string[],
    mustChangePassword?: boolean
  ) => void;
  setAccessToken: (accessToken: string | null) => void;
  setUser: (user: UserProfile | null) => void;
  setShop: (shop: ShopProfile | null) => void;
  setPermissions: (permissions: string[]) => void;
  setMustChangePassword: (mustChangePassword: boolean) => void;
  setInitialized: (isInitialized: boolean) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  shop: null,
  permissions: [],
  mustChangePassword: false,
  isInitialized: false,

  setAuth: (user, shop, accessToken, permissions = [], mustChangePassword = false) =>
    set({
      user,
      shop,
      accessToken,
      permissions,
      mustChangePassword,
      isInitialized: true,
    }),

  setAccessToken: (accessToken) => set({ accessToken }),
  setUser: (user) => set({ user }),
  setShop: (shop) => set({ shop }),
  setPermissions: (permissions) => set({ permissions }),
  setMustChangePassword: (mustChangePassword) => set({ mustChangePassword }),
  setInitialized: (isInitialized) => set({ isInitialized }),

  clearAuth: () =>
    set({
      accessToken: null,
      user: null,
      shop: null,
      permissions: [],
      mustChangePassword: false,
      isInitialized: true,
    }),
}));

export function normalizeShopProfile(shopData: MeResponse['shop'] | ShopProfile | null): ShopProfile | null {
  if (!shopData) return null;
  const raw = shopData as MeResponse['shop'] & { features?: ShopProfile['features'] };
  if (!raw) return null;
  return {
    id: raw.id,
    public_id: raw.public_id,
    name: raw.name,
    address: raw.address,
    phone: raw.phone,
    is_active: raw.is_active,
    features: raw.features || {
      enable_credit_module: Boolean(raw.enable_credit_module),
      enable_whatsapp_alerts: Boolean(raw.enable_whatsapp_alerts),
    },
  };
}

/**
 * Role-based default home route helper.
 * OWNER / MANAGER / ACCOUNTANT fall back to /pos until /dashboard is implemented in Step F2.
 */
export function getDefaultHomeRoute(role?: UserRole): string {
  switch (role) {
    case 'INVENTORY_MANAGER':
      return '/inventory';
    case 'CASHIER':
      return '/pos';
    case 'OWNER':
    case 'MANAGER':
    case 'ACCOUNTANT':
    default:
      return '/pos';
  }
}
