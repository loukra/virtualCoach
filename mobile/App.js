// mobile/App.js
import React from 'react';
import { StyleSheet, View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { supabase } from './lib/supabase';

// Components
import Auth from './components/Auth';
import ConnectStrava from './components/ConnectStrava';
import SetupProfile from './components/SetupProfile';
import Dashboard from './screens/Dashboard'; // New file

// Hooks
import { useUserOnboarding } from './hooks/useUserOnboarding'; // New file

export default function App() {
  // 1. All logic is now hidden inside this one line
  const { 
    session, 
    loading, 
    stravaConnected, 
    profileSetupDone, 
    syncCompleted, 
    refreshStatus 
  } = useUserOnboarding();

  // --- VIEW LOGIC (Routing) ---

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#ff4d4d"/>
      </View>
    );
  }

  if (!session) return <Auth />;

  // 1. Profile Setup First
  if (!profileSetupDone) {
    return <SetupProfile session={session} onProfileComplete={refreshStatus} />;
  }

  // 2. Connect Strava Second
  if (!stravaConnected) {
    return <ConnectStrava session={session} onSyncStarted={refreshStatus} />;
  }

  // 3. Wait for Sync
  if (!syncCompleted) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#ff4d4d" />
        <Text style={styles.waitText}>Finalizing your training plan...</Text>
        <Text style={styles.subText}>Calculating TSS based on your FTP...</Text>
        
        {/* Emergency Logout button */}
        <TouchableOpacity onPress={() => supabase.auth.signOut()} style={{ marginTop: 40 }}>
            <Text style={{ color: '#666' }}>Cancel & Logout</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // 4. Dashboard
  return <Dashboard />;
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: '#111', justifyContent: 'center', alignItems: 'center' },
  waitText: { color: '#fff', fontSize: 18, marginTop: 20 },
  subText: { color: '#666', marginTop: 10 },
});