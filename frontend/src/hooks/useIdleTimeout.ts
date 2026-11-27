import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { useAuthStore } from '../stores/authStore';

const DEFAULT_IDLE_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes

/**
 * Logs out the authenticated user after 15 minutes of inactivity,
 * clearing all Zustand auth state and redirecting to /login.
 */
export function useIdleTimeout(timeoutMs: number = DEFAULT_IDLE_TIMEOUT_MS): void {
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const navigate = useNavigate();

  useEffect(() => {
    if (!user) return;

    let timer: ReturnType<typeof setTimeout>;

    const handleTimeout = async () => {
      try {
        await apiClient.post('/auth/logout/', {});
      } catch {
        // Proceed with local teardown even if network request fails
      } finally {
        clearAuth();
        navigate('/login', { replace: true });
      }
    };

    const resetTimer = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        void handleTimeout();
      }, timeoutMs);
    };

    const activityEvents: Array<keyof WindowEventMap> = [
      'mousemove',
      'keydown',
      'mousedown',
      'touchstart',
      'scroll',
    ];

    activityEvents.forEach((evt) => window.addEventListener(evt, resetTimer, { passive: true }));
    resetTimer();

    return () => {
      clearTimeout(timer);
      activityEvents.forEach((evt) => window.removeEventListener(evt, resetTimer));
    };
  }, [user, clearAuth, navigate, timeoutMs]);
}
