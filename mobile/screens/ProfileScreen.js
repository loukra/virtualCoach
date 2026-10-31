import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { View, Text, StyleSheet, TouchableOpacity, Alert, ActivityIndicator, Modal } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import SetupProfile from '../components/SetupProfile';
import { useSessionContext } from '../context/SessionContext';
import { Ionicons } from '@expo/vector-icons';
import { apiGet, apiPost } from '../lib/api';
import { APP_NAME } from '../theme';

export default function ProfileScreen() {
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [ftp, setFtp] = useState(null);
  const { me, signOut, refresh } = useSessionContext();

  useFocusEffect(useCallback(() => {
    refresh();
    apiGet('/ftp').then(setFtp).catch((e) => console.log('Could not load FTP:', e.message));
  }, [refresh]));

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

  const handleSignOut = () => {
    Alert.alert("Sign out?", "You will need your access token to sign in again.", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: signOut },
    ]);
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Modal visible={editing} animationType="slide" onRequestClose={() => setEditing(false)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: '#111' }}>
          <TouchableOpacity onPress={() => setEditing(false)} style={styles.modalClose} accessibilityLabel="Close">
            <Ionicons name="close" size={26} color="#888" />
          </TouchableOpacity>
          <SetupProfile me={me} onProfileComplete={async () => { await refresh(); setEditing(false); }} />
        </SafeAreaView>
      </Modal>

      {/* HEADER */}
      <View style={styles.header}>
        <Ionicons name="person-circle-outline" size={80} color="#666" />
        <Text style={styles.emailText}>{me?.name || 'Athlete'}</Text>
      </View>

      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>TRAINING PROFILE</Text>
          <TouchableOpacity onPress={() => setEditing(true)}>
            <Text style={styles.editText}>Edit</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.profileCard}>
          <ProfileRow label="Goal" value={me?.goal} />
          <ProfileRow label="FTP" value={me?.ftp && `${me.ftp} W`} />
          <ProfileRow label="Max heart rate" value={me?.max_heart_rate && `${me.max_heart_rate} bpm`} />
          <ProfileRow label="Weight" value={me?.weight_kg && `${me.weight_kg} kg`} last />
        </View>
      </View>

      {ftp && (ftp.tests.length > 0 || ftp.history.length > 1) && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>FTP PROGRESS</Text>
          <View style={styles.profileCard}>
            {ftp.tests.map((t, i) => (
              <ProfileRow
                key={`test-${t.id}`}
                label={`Test ${t.date}`}
                value={`${t.best_20min_watts} W for 20 min → FTP ${t.ftp_estimate} W`}
                last={i === ftp.tests.length - 1 && ftp.history.length < 2}
              />
            ))}
            {ftp.history.length > 1 && (
              <ProfileRow
                label="FTP set"
                value={ftp.history.slice(-4).map((h) => `${h.ftp}`).join(' → ') + ' W'}
                last
              />
            )}
          </View>
        </View>
      )}

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
      <Text style={styles.version}>{APP_NAME}</Text>
    </SafeAreaView>
  );
}

function ProfileRow({ label, value, last }) {
  return (
    <View style={[styles.profileRow, !last && styles.profileRowBorder]}>
      <Text style={styles.profileLabel}>{label}</Text>
      <Text style={styles.profileValue} numberOfLines={1}>{value || '–'}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111', paddingHorizontal: 20 },
  
  header: { alignItems: 'center', marginTop: 20, marginBottom: 30 },
  emailText: { color: 'white', fontSize: 18, marginTop: 10, fontWeight: 'bold' },

  section: { marginBottom: 30 },
  sectionTitle: { color: '#666', fontSize: 12, fontWeight: 'bold', marginBottom: 10, letterSpacing: 1 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between' },
  editText: { color: '#ff4d4d', fontWeight: 'bold' },
  profileCard: { backgroundColor: '#1a1a1a', borderRadius: 12, paddingHorizontal: 15 },
  profileRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 13, gap: 15 },
  profileRowBorder: { borderBottomWidth: 1, borderBottomColor: '#262626' },
  profileLabel: { color: '#888', fontSize: 15 },
  profileValue: { color: 'white', fontSize: 15, flexShrink: 1 },
  modalClose: { alignSelf: 'flex-end', padding: 15 },

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