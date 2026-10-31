// mobile/lib/api.js
import { API_URL } from '../constants';
import { getToken } from './session';

// Workout generation can take a while; anything longer means the server is stuck.
const TIMEOUT_MS = 120000;

export class AuthError extends Error {}

/**
 * Calls the Python backend with the athlete's access token.
 * The backend reads the athlete from the token, so bodies never carry an id.
 * Throws an Error with the server's message when the request fails (AuthError on 401).
 */
async function request(method, path, body, token) {
  const authToken = token ?? (await getToken());
  if (!authToken) throw new AuthError('Not signed in.');

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authToken}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) throw new AuthError('This access token is not valid.');
    if (!res.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`);
    }
    return data;
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('The server took too long to answer.');
    if (e instanceof TypeError) throw new Error(`Cannot reach the server at ${API_URL}.`);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const apiGet = (path, token) => request('GET', path, undefined, token);
export const apiPost = (path, body = {}) => request('POST', path, body);
export const apiPut = (path, body = {}) => request('PUT', path, body);
export const apiDelete = (path) => request('DELETE', path);
