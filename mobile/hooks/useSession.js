// mobile/hooks/useSession.js
import { useState, useEffect, useRef, useCallback } from 'react';
import { apiGet, AuthError } from '../lib/api';
import { saveToken, clearToken } from '../lib/session';

/**
 * Who is signed in and how far onboarding is. `me` is the backend's /me answer,
 * or null when no valid token is stored.
 */
export function useSession() {
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);
  const pollingRef = useRef(null);

  const stopPolling = () => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = null;
  };

  const refresh = useCallback(async () => {
    try {
      const data = await apiGet('/me');
      setMe(data);
      setError(null);
    } catch (e) {
      if (e instanceof AuthError) setMe(null);
      else setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    return stopPolling;
  }, [refresh]);

  // While the Strava history imports, check every few seconds until it is done.
  useEffect(() => {
    if (me?.sync_status === 'syncing' && !pollingRef.current) {
      pollingRef.current = setInterval(refresh, 3000);
    } else if (me?.sync_status !== 'syncing') {
      stopPolling();
    }
  }, [me?.sync_status, refresh]);

  const signIn = async (token) => {
    const data = await apiGet('/me', token.trim()); // throws if the token is wrong
    await saveToken(token.trim());
    setMe(data);
    setError(null);
  };

  const signOut = async () => {
    stopPolling();
    await clearToken();
    setMe(null);
  };

  return { loading, me, error, refresh, signIn, signOut };
}
