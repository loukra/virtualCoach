import React, { useState, useEffect, useCallback } from 'react';
import { 
  StyleSheet, 
  View, 
  Text, 
  TouchableOpacity, 
  FlatList, 
  ActivityIndicator 
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { APP_NAME } from '../theme';
import { apiGet, apiPost } from '../lib/api';
import CreateJourneyModal from '../components/CreateJourneyModal';
import { useJourney } from '../context/JourneyContext';
import { useSessionContext } from '../context/SessionContext';
// 👇 IMPORT NAVIGATION HOOK
import { useNavigation, useFocusEffect } from '@react-navigation/native';

export default function Dashboard() {
  const navigation = useNavigation();
  const { setActiveJourneyId } = useJourney();
  const { me, refresh } = useSessionContext();
  const [journeys, setJourneys] = useState([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);

  // New Strava rides once per app start; the list reloads whenever the tab comes back into view.
  useEffect(() => {
    triggerApiSync();
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchJourneys();
    }, [])
  );

  // While a plan is being built, check every few seconds so the card updates on its own.
  const anyCreating = journeys.some((j) => j.status === 'creating');
  useEffect(() => {
    if (!anyCreating) return undefined;
    const timer = setInterval(fetchJourneys, 4000);
    return () => clearInterval(timer);
  }, [anyCreating]);

  const fetchJourneys = async () => {
    try {
      setJourneys(await apiGet('/journeys'));
    } catch (e) {
      console.log('Could not load journeys:', e.message);
    }
  };

  const triggerApiSync = async () => {
    setIsSyncing(true);
    try {
        await apiPost('/sync', { days_back: 7 });
    }
    catch (e) {
        console.log(e);
    } finally {
        // The import runs in the background; read its outcome (and any error) a moment later.
        setTimeout(() => { setIsSyncing(false); refresh(); }, 4000);
    }
  };

  const handleJourneyCreated = () => {
    fetchJourneys(); 
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <CreateJourneyModal visible={createModalVisible} onClose={() => setCreateModalVisible(false)} onJourneyCreated={handleJourneyCreated} />

      {/* --- HEADER (Updated for Bottom Tabs) --- */}
      <View style={styles.header}>
        
        {/* Left Side: Brand Logo (Replaces Burger Menu) */}
        <View style={{flexDirection:'row', alignItems:'center'}}>
            <Ionicons name="bicycle" size={24} color="#ff4d4d" style={{marginRight: 10}}/>
            <Text style={{color:'#fff', fontWeight:'bold', fontSize: 18}}>{APP_NAME}</Text>
        </View>

        {/* Right Side: Sync Status */}
        <View style={{alignItems: 'flex-end'}}>
            {isSyncing && <Text style={{color:'#666', fontSize: 10, marginBottom: 4}}>SYNCING...</Text>}
            <Text style={{color:'#fff', fontWeight:'bold', fontSize: 16}}>My Journeys</Text>
        </View>
      </View>

      {me?.sync_status === 'failed' && (
        <View style={styles.syncError}>
          <Ionicons name="warning-outline" size={20} color="#ffb84d" />
          <View style={{ flex: 1 }}>
            <Text style={styles.syncErrorTitle}>Strava rides could not be imported</Text>
            <Text style={styles.syncErrorText}>{me.sync_error || 'Try again later.'}</Text>
          </View>
          <TouchableOpacity onPress={triggerApiSync} disabled={isSyncing} style={styles.syncRetry}>
            {isSyncing ? <ActivityIndicator color="#ffb84d" size="small" /> : <Text style={styles.syncRetryText}>Retry</Text>}
          </TouchableOpacity>
        </View>
      )}

      {/* --- CONTENT AREA --- */}
      <View style={styles.content}>
          <View style={{flex: 1, width:'100%', padding: 20}}>
              <FlatList
                  data={journeys}
                  keyExtractor={(item) => item.id}
                  contentContainerStyle={{ gap: 15 }}
                  renderItem={({ item }) => (
                      <TouchableOpacity 
                        style={styles.card} 
                        // 👇 Navigate to the Journey Detail screen
                        onPress={() => {
                    setActiveJourneyId(item.id); // 👈 UPDATE GLOBAL ID
                    navigation.navigate('JourneyDetail', { journeyId: item.id, name: item.name });
                }}
                      >
                          <View>
                              <Text style={styles.cardTitle}>{item.name}</Text>
                              <Text style={styles.cardDate}>
                                {item.goal_type === 'build' ? `Build fitness · until ${item.race_date}` : `Race: ${item.race_date}`}
                              </Text>
                              {item.status === 'creating' && <Text style={styles.cardStatus}>Building plan…</Text>}
                              {item.status === 'scheduled' && (
                                <Text style={styles.cardStatus}>Starts {item.start_date} · plan built on that day</Text>
                              )}
                              {item.status === 'failed' && <Text style={[styles.cardStatus, {color:'#ff4d4d'}]}>Plan failed</Text>}
                          </View>
                          <View style={{alignItems:'flex-end'}}>
                              {item.status === 'creating' ? (
                                  <ActivityIndicator color="#ff4d4d" />
                              ) : (
                                  <Ionicons name="chevron-forward" size={24} color="#666" />
                              )}
                          </View>
                      </TouchableOpacity>
                  )}
                  ListEmptyComponent={
                      <Text style={{color:'#666', textAlign:'center', marginTop: 50, lineHeight: 22}}>No journeys yet.{'\n'}Tap + to plan your next goal.</Text>
                  }
              />

              {/* FLOATING CREATE BUTTON */}
              <TouchableOpacity style={styles.fab} onPress={() => setCreateModalVisible(true)}>
                  <Ionicons name="add" size={30} color="white" />
              </TouchableOpacity>
          </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems:'center', padding: 20, borderBottomWidth: 1, borderBottomColor: '#222' },
  content: { flex: 1 },
  syncError: { flexDirection: 'row', gap: 10, alignItems: 'center', backgroundColor: '#2a2210', margin: 20, marginBottom: 0, padding: 14, borderRadius: 12 },
  syncErrorTitle: { color: '#ffb84d', fontWeight: 'bold', marginBottom: 2 },
  syncErrorText: { color: '#d9c49a', fontSize: 13, lineHeight: 18 },
  syncRetry: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: '#ffb84d' },
  syncRetryText: { color: '#ffb84d', fontWeight: 'bold' },
  
  // List Card Styles
  card: { backgroundColor: '#1a1a1a', padding: 20, borderRadius: 12, flexDirection:'row', justifyContent:'space-between', alignItems:'center' },
  cardTitle: { color: 'white', fontSize: 18, fontWeight: 'bold' },
  cardDate: { color: '#888', fontSize: 12, marginTop: 4 },
  cardStatus: { color: '#888', fontSize: 12, marginTop: 4, fontStyle: 'italic' },
  
  // FAB (Floating Action Button)
  fab: { position: 'absolute', bottom: 30, right: 20, backgroundColor: '#ff4d4d', width: 60, height: 60, borderRadius: 30, justifyContent: 'center', alignItems: 'center', elevation: 5, shadowColor:'#000', shadowOffset:{width:0,height:4}, shadowOpacity:0.3, shadowRadius:4 },
});