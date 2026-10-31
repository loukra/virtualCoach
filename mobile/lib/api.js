// mobile/lib/api.js
import { supabase } from './supabase';
import { API_URL } from '../constants';

// Workout generation can take a while; anything longer means the server is stuck.
const TIMEOUT_MS = 120000;

/**
 * POSTs to the Python backend with the user's Supabase access token.
 * The backend reads the user from the token, so bodies never carry a user_id.
 * Throws an Error with the server's message when the request fails.
 */
export async function apiPost(path, body = {}) {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error('You are signed out. Please sign in again.');

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`);
    }
    return data;
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('The server took too long to answer.');
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
