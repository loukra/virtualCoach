import React, { useState, useEffect } from 'react';
import { StyleSheet, View, Text, StatusBar } from 'react-native';
import { supabase } from './lib/supabase';
import Auth from './components/Auth';

export default function App() {
  const [session, setSession] = useState(null);

  useEffect(() => {
    // 1. Check if user is already logged in
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
    });

    // 2. Listen for login/logout events automatically
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });
    
    // Cleanup listener when app closes
    return () => subscription.unsubscribe();
  }, []);

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />
      
      {session && session.user ? (
        // --- 🟢 LOGGED IN VIEW ---
        // (This is where your Dashboard will go later)
        <View style={styles.dashboard}>
          <Text style={styles.text}>✅ You are logged in!</Text>
          <Text style={styles.subtext}>User: {session.user.email}</Text>
          <Text 
            style={styles.link} 
            onPress={() => supabase.auth.signOut()}
          >
            Sign Out
          </Text>
        </View>
      ) : (
        // --- 🔴 LOGGED OUT VIEW ---
        <Auth />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111' },
  dashboard: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  text: { color: '#fff', fontSize: 24, fontWeight: 'bold' },
  subtext: { color: '#888', marginTop: 10 },
  link: { color: '#ff4d4d', marginTop: 30, fontSize: 18 }
});