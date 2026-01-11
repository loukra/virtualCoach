import React, { useState, useEffect } from 'react';
import { StyleSheet, View, Text, StatusBar, ActivityIndicator } from 'react-native';
import { supabase } from './lib/supabase';
import Auth from './components/Auth';
import ConnectStrava from './components/ConnectStrava';
import SetupProfile from './components/SetupProfile';

export default function App() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // The 3 Phases of Onboarding
  const [stravaConnected, setStravaConnected] = useState(false);
  const [profileSetupDone, setProfileSetupDone] = useState(false);
  const [syncCompleted, setSyncCompleted] = useState(false);

  useEffect(() => {
    //supabase.auth.signOut();
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) checkUserStatus(session.user.id);
      else setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) checkUserStatus(session.user.id);
      else setLoading(false);
    });
    
    return () => subscription.unsubscribe();
  }, []);

  async function checkUserStatus(userId) {
    setLoading(true);
    
    // 1. Check Strava Connection
    const { data: stravaData } = await supabase.from('strava_connection').select('user_id').eq('user_id', userId).single();
    const isStravaConnected = !!stravaData;
    setStravaConnected(isStravaConnected);

    // 2. Check Profile Setup (Did they answer the questions?)
    const { data: profileData } = await supabase.from('profiles').select('goal, sync_status').eq('id', userId).single();
    
    // If 'goal' is filled, we assume they finished the setup
    const isProfileDone = profileData?.goal !== null && profileData?.goal !== undefined; 
    setProfileSetupDone(isProfileDone);

    // 3. Check Sync Status
    const isSyncDone = profileData?.sync_status === 'completed';
    setSyncCompleted(isSyncDone);

    setLoading(false);

    // If sync isn't done but everything else is, start polling
    if (isStravaConnected && isProfileDone && !isSyncDone) {
      pollSyncStatus(userId);
    }
  }

  // Poll DB until sync_status === 'completed'
  const pollSyncStatus = (userId) => {
    const interval = setInterval(async () => {
      const { data } = await supabase.from('profiles').select('sync_status').eq('id', userId).single();
      if (data?.sync_status === 'completed') {
        clearInterval(interval);
        setSyncCompleted(true);
      }
    }, 3000);
  };

  // --- VIEW LOGIC ---

  if (loading) return <View style={styles.center}><ActivityIndicator color="#ff4d4d"/></View>;

  if (!session) return <Auth />;

 if (!profileSetupDone) {
    return (
      <SetupProfile 
        session={session} 
        onProfileComplete={() => {
          setProfileSetupDone(true);
          // Now that FTP is saved, we check if they need to connect Strava
          checkUserStatus(session.user.id);
        }} 
      />
    );
  }

  // 2. Second: Connect Strava
  // Now when this triggers the backend sync, the FTP is already in the database!
  if (!stravaConnected) {
    return (
      <ConnectStrava 
        session={session} 
        onSyncStarted={() => {
          setStravaConnected(true); 
          pollSyncStatus(session.user.id);
        }} 
      />
    );
  }

  // 3. Third: Wait for Sync
  if (!syncCompleted) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#ff4d4d" />
        <Text style={styles.waitText}>Finalizing your training plan...</Text>
        <Text style={styles.subText}>Calculating TSS based on your FTP...</Text>
      </View>
    );
  }

  // 4. Finally: Dashboard
  return (
    <View style={styles.center}>
      <Text style={styles.text}>✅ Ready to Train!</Text>
      <Text style={styles.link} onPress={() => supabase.auth.signOut()}>Sign Out</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: '#111', justifyContent: 'center', alignItems: 'center' },
  text: { color: '#fff', fontSize: 24, fontWeight: 'bold' },
  waitText: { color: '#fff', fontSize: 18, marginTop: 20 },
  subText: { color: '#666', marginTop: 10 },
  link: { color: '#ff4d4d', marginTop: 30, fontSize: 18 }
});