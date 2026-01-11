import React, { useState } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';

// 1. Configuration
// ⚠️ REPLACE WITH YOUR LOCAL IP (e.g., 192.168.178.XX)
const BACKEND_URL = 'http://192.168.178.39:8000'; 
const STRAVA_CLIENT_ID = '194995'; 
// This tells Strava to open your app after login
const REDIRECT_URI = Linking.createURL('/'); 

// Note: changed prop name to 'onSyncStarted' to match App.js
export default function ConnectStrava({ session, onSyncStarted }) {
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState("Connect your account to analyze your history.");

  // --- A. Handle the OAuth Flow ---
  const handleConnect = async () => {
    setLoading(true);
    setStatusText("Waiting for Strava...");

    try {
      // 1. Open Strava in a browser popup
      const authUrl = `https://www.strava.com/oauth/authorize?client_id=${STRAVA_CLIENT_ID}&response_type=code&redirect_uri=${REDIRECT_URI}&scope=activity:read_all`;
      
      const result = await WebBrowser.openAuthSessionAsync(authUrl, REDIRECT_URI);

      if (result.type === 'success' && result.url) {
        // 2. Extract the 'code' from the URL
        const params = Linking.parse(result.url);
        const code = params.queryParams.code;

        if (code) {
          setStatusText("Code received! Syncing data...");
          await sendCodeToBackend(code);
        } else {
          Alert.alert("Error", "Could not find authorization code.");
          setLoading(false);
        }
      } else {
        setLoading(false); // User cancelled
      }
    } catch (error) {
      Alert.alert("Error", error.message);
      setLoading(false);
    }
  };

  // --- B. Send Code to Python Backend ---
  const sendCodeToBackend = async (code) => {
    try {
      const response = await fetch(`${BACKEND_URL}/connect-strava`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: session.user.id,
          code: code
        })
      });

      const data = await response.json();

      if (data.status === 'processing') {
        setStatusText("✅ Connected! Starting background sync...");
        
        // 🚀 SUCCESS: We don't wait for the sync to finish anymore.
        // We immediately let the user go to the Setup Profile screen.
        setTimeout(() => {
            onSyncStarted(); 
        }, 1500); // Small delay just so user sees the "Connected" text
        
      } else {
        throw new Error("Backend rejected the request.");
      }
    } catch (e) {
      Alert.alert("Connection Failed", "Is your Python server running? " + e.message);
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.emoji}>🔗</Text>
      <Text style={styles.title}>Let's get your data</Text>
      <Text style={styles.subtitle}>{statusText}</Text>

      {loading ? (
        <ActivityIndicator size="large" color="#ff4d4d" style={{ marginTop: 20 }} />
      ) : (
        <TouchableOpacity style={styles.button} onPress={handleConnect}>
          <Text style={styles.buttonText}>Connect with Strava</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20, backgroundColor: '#111' },
  emoji: { fontSize: 60, marginBottom: 20 },
  title: { fontSize: 24, fontWeight: 'bold', color: '#fff', marginBottom: 10 },
  subtitle: { fontSize: 16, color: '#888', textAlign: 'center', marginBottom: 40 },
  button: { backgroundColor: '#FC4C02', paddingVertical: 15, paddingHorizontal: 30, borderRadius: 8 },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 18 }
});