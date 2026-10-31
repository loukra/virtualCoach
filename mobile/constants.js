// mobile/constants.js
// Values come from mobile/.env (see .env.example). Expo inlines EXPO_PUBLIC_* at build time.

export const API_URL = process.env.EXPO_PUBLIC_API_URL;
export const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
// The anon/publishable key is meant to ship in the app; Row Level Security protects the data.
export const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
export const STRAVA_CLIENT_ID = process.env.EXPO_PUBLIC_STRAVA_CLIENT_ID;
