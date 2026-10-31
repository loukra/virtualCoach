// mobile/lib/session.js
import * as SecureStore from 'expo-secure-store';

// The athlete's access token from `python -m manage add-athlete`, kept in the iOS Keychain /
// Android Keystore instead of the app bundle.
const KEY = 'virtualcoach.token';

export const getToken = () => SecureStore.getItemAsync(KEY);
export const saveToken = (token) => SecureStore.setItemAsync(KEY, token);
export const clearToken = () => SecureStore.deleteItemAsync(KEY);
