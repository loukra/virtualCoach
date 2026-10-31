import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert, ActivityIndicator } from 'react-native';
import { supabase } from '../lib/supabase';
import { Ionicons } from '@expo/vector-icons';
import { apiPost } from '../lib/api';

export default function ProfileScreen() {
  const [loading, setLoading] = useState(false);
  const [userEmail, setUserEmail] = useState('');

  useEffect(() => {
    // Get current user email for display
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) setUserEmail(session.user.email);
    });
  }, []);

  const handleSync = async () => {
    try {
      setLoading(true);
      await apiPost('/sync', { days_back: 90 });
      Alert.alert("Sync Started", "Your data is updating in the background. It may take a few seconds to appear.");
    } catch (e) {
      Alert.alert("Could not start sync", e.message);
    } finally {
      // Simulate a short loading state so the user knows something happened
      setTimeout(() => setLoading(false), 2000);
    }
  };

  const handleSignOut = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) Alert.alert("Error", error.message);
  };

  return (
    <View style={styles.container}>
      
      {/* HEADER */}
      <View style={styles.header}>
        <Ionicons name="person-circle-outline" size={80} color="#666" />
        <Text style={styles.emailText}>{userEmail || 'Athlete'}</Text>
      </View>

      {/* ACTIONS */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>DATA MANAGEMENT</Text>
        
        {/* SYNC BUTTON */}
        <TouchableOpacity 
            style={styles.actionButton} 
            onPress={handleSync} 
            disabled={loading}
        >
          <View style={{flexDirection:'row', alignItems:'center'}}>
            <View style={[styles.iconBox, {backgroundColor: '#e6f7ff'}]}>
                {loading ? <ActivityIndicator size="small" color="#007bff"/> : <Ionicons name="sync" size={20} color="#007bff" />}
            </View>
            <Text style={styles.actionText}>Sync Strava Data</Text>
          </View>
          {loading && <Text style={{color:'#666', fontSize:12}}>Starting...</Text>}
        </TouchableOpacity>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>ACCOUNT</Text>
        
        {/* LOGOUT BUTTON */}
        <TouchableOpacity style={styles.actionButton} onPress={handleSignOut}>
          <View style={{flexDirection:'row', alignItems:'center'}}>
            <View style={[styles.iconBox, {backgroundColor: '#ffe6e6'}]}>
                <Ionicons name="log-out-outline" size={20} color="#ff4d4d" />
            </View>
            <Text style={[styles.actionText, {color: '#ff4d4d'}]}>Sign Out</Text>
          </View>
        </TouchableOpacity>
      </View>

      <View style={{flex:1}} />
      <Text style={styles.version}>Velo AI v1.0.0</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111', padding: 20, paddingTop: 60 },
  
  header: { alignItems: 'center', marginBottom: 40 },
  emailText: { color: 'white', fontSize: 18, marginTop: 10, fontWeight: 'bold' },

  section: { marginBottom: 30 },
  sectionTitle: { color: '#666', fontSize: 12, fontWeight: 'bold', marginBottom: 10, letterSpacing: 1 },

  actionButton: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'space-between',
    backgroundColor: '#1a1a1a', 
    padding: 15, 
    borderRadius: 12, 
    marginBottom: 10 
  },
  iconBox: { width: 36, height: 36, borderRadius: 8, justifyContent:'center', alignItems:'center', marginRight: 15 },
  actionText: { color: 'white', fontSize: 16, fontWeight: '600' },
  
  version: { color: '#444', textAlign: 'center', fontSize: 12, marginBottom: 20 }
});