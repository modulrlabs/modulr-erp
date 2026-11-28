import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { normalizeShopProfile, useAuthStore } from '../stores/authStore';
import type { MeResponse } from '../types/erp';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // Enables sending and receiving httpOnly cookies
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest', // Protects against CSRF on state-changing cookie requests
  },
});

// Request interceptor: Injects memory-held Bearer token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken;
    if (token && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Single-flight refresh token queue to avoid race conditions when multiple API calls 401 simultaneously
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Single-flight background permission sync on 403 Forbidden
let isSyncingPermissions = false;

export async function syncAuthMe(): Promise<void> {
  const { accessToken, setAuth } = useAuthStore.getState();
  if (!accessToken || isSyncingPermissions) return;

  isSyncingPermissions = true;
  try {
    const meRes = await apiClient.get<MeResponse>('/auth/me/');
    const me = meRes.data;
    setAuth(
      {
        id: me.id,
        public_id: me.public_id,
        username: me.username,
        email: me.email,
        first_name: me.first_name,
        last_name: me.last_name,
        role: me.role,
        must_change_password: me.must_change_password,
      },
      normalizeShopProfile(me.shop),
      accessToken,
      me.permissions || [],
      Boolean(me.must_change_password)
    );
  } catch {
    // Ignore transient sync errors; 401 handler handles expired sessions
  } finally {
    isSyncingPermissions = false;
  }
}

// Response interceptor: Handles 401 token rotation and 403 password-change / permission sync
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (!originalRequest) {
      return Promise.reject(error);
    }

    const isAuthEndpoint =
      originalRequest.url?.includes('/auth/login/') ||
      originalRequest.url?.includes('/auth/register/') ||
      originalRequest.url?.includes('/auth/token/refresh/');

    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

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
        useAuthStore.getState().setAccessToken(newAccessToken);
        processQueue(null, newAccessToken);

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        useAuthStore.getState().clearAuth();
        if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
          window.location.assign('/login');
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // Handle 403 Forbidden: password_change_required redirect or live permissions sync
    if (error.response?.status === 403 && !originalRequest.url?.includes('/auth/login/')) {
      const data = error.response.data as { code?: string } | undefined;
      if (data?.code === 'password_change_required') {
        useAuthStore.getState().setMustChangePassword(true);
        if (window.location.pathname !== '/change-password') {
          window.location.assign('/change-password');
        }
      } else if (!originalRequest.url?.includes('/auth/me/')) {
        void syncAuthMe();
      }
    }

    return Promise.reject(error);
  }
);
