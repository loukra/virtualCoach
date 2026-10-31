// mobile/App.js
import React from 'react';
import { StyleSheet, View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import 'react-native-gesture-handler';
// Components
import Auth from './components/Auth';
import ConnectStrava from './components/ConnectStrava';
import SetupProfile from './components/SetupProfile';
import AppNavigator from './navigation/AppNavigator';
// Hooks
import { useSession } from './hooks/useSession';
import { JourneyProvider } from './context/JourneyContext';
import { SessionProvider } from './context/SessionContext';

export default function App() {
  return (
    <SafeAreaProvider>
      <Root />
    </SafeAreaProvider>
  );
}

function Root() {
  const session = useSession();
  const { loading, me, error, refresh, signIn, signOut } = session;

  // --- VIEW LOGIC (Routing) ---

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#ff4d4d"/>
      </View>
    );
  }

  // Server unreachable: keep the stored token and let the user retry.
  if (error && !me) {
    return (
      <View style={styles.center}>
        <Text style={styles.waitText}>Can't reach your coach</Text>
        <Text style={styles.subText}>{error}</Text>
        <TouchableOpacity onPress={refresh} style={styles.retryBtn}>
          <Text style={styles.retryText}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (!me) return <Auth onSignIn={signIn} />;

  // 1. Profile Setup First
  if (!me.profile_complete) {
    return <SetupProfile me={me} onProfileComplete={refresh} />;
  }

  // 2. Wait for the Strava import
  if (me.sync_status === 'syncing') {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#ff4d4d" />
        <Text style={styles.waitText}>Importing your rides...</Text>
        <Text style={styles.subText}>Reading the last 90 days from Strava and calculating your fitness.</Text>
        <TouchableOpacity onPress={signOut} style={{ marginTop: 40 }}>
            <Text style={{ color: '#666' }}>Sign out</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // 3. Connect Strava
  if (!me.strava_connected) {
    return <ConnectStrava failed={me.sync_status === 'failed'} onSyncStarted={refresh} />;
  }

  return (
    <SessionProvider value={session}>
      <JourneyProvider>
        <NavigationContainer>
            <AppNavigator />
        </NavigationContainer>
      </JourneyProvider>
    </SessionProvider>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: '#111', justifyContent: 'center', alignItems: 'center', padding: 30 },
  waitText: { color: '#fff', fontSize: 18, marginTop: 20, textAlign: 'center' },
  subText: { color: '#666', marginTop: 10, textAlign: 'center' },
  retryBtn: { marginTop: 30, backgroundColor: '#ff4d4d', paddingVertical: 12, paddingHorizontal: 24, borderRadius: 8 },
  retryText: { color: '#fff', fontWeight: 'bold' },
});
