import { create } from 'zustand';
import type { ShopProfile, UserProfile } from '../types/erp';

interface AuthState {
  // In-memory access token only: NEVER written to localStorage or sessionStorage
  // to protect against Cross-Site Scripting (XSS) token theft.
  accessToken: string | null;
  user: UserProfile | null;
  shop: ShopProfile | null;
  isInitialized: boolean;

  setAuth: (user: UserProfile, shop: ShopProfile | null, accessToken: string) => void;
  setAccessToken: (accessToken: string | null) => void;
  setUser: (user: UserProfile | null) => void;
  setShop: (shop: ShopProfile | null) => void;
  setInitialized: (isInitialized: boolean) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  shop: null,
  isInitialized: false,

  setAuth: (user, shop, accessToken) =>
    set({
      user,
      shop,
      accessToken,
      isInitialized: true,
    }),

  setAccessToken: (accessToken) =>
    set({ accessToken }),

  setUser: (user) =>
    set({ user }),

  setShop: (shop) =>
    set({ shop }),

  setInitialized: (isInitialized) =>
    set({ isInitialized }),

  clearAuth: () =>
    set({
      accessToken: null,
      user: null,
      shop: null,
      isInitialized: true,
    }),
}));
