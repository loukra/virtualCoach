import React, { useState, useEffect, useCallback } from 'react';
import { 
  StyleSheet, 
  View, 
  Text, 
  TouchableOpacity, 
  FlatList, 
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { APP_NAME } from '../theme';
import { apiGet, apiPost } from '../lib/api';
import CreateJourneyModal from '../components/CreateJourneyModal';
import AddEventModal from '../components/AddEventModal';
import EventList from '../components/EventList';
import Toast from '../components/Toast';
import AddMenu from '../components/AddMenu';
import { EVENT_KINDS, eventWhen, journeyEvents } from '../lib/events';
import { localDateString } from '../lib/dates';
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
  const [events, setEvents] = useState([]);
  const [eventKind, setEventKind] = useState(null); // the AddEventModal is open for this kind
  const [note, setNote] = useState(null);
  const onEventsChanged = (message) => {
    setNote(message);
    fetchJourneys();
  };

  // New Strava rides once per app start; the list reloads whenever the tab comes back into view.
  useEffect(() => {
    triggerApiSync();
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchJourneys();
    }, [])
  );

  // While a plan is being built or adapted, check every few seconds so the card updates on its own.
  const anyCreating = journeys.some((j) => j.status === 'creating' || j.replanning);
  useEffect(() => {
    if (!anyCreating) return undefined;
    const timer = setInterval(fetchJourneys, 4000);
    return () => clearInterval(timer);
  }, [anyCreating]);

  const fetchJourneys = async () => {
    try {
      const [js, evs] = await Promise.all([apiGet('/journeys'), apiGet('/events')]);
      setJourneys(js);
      setEvents(evs);
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

  // The plus adds a journey or something the plans work around.
  const ADD_OPTIONS = [
    { label: 'New journey', icon: 'trending-up', color: '#ff4d4d', run: () => setCreateModalVisible(true) },
    ...Object.entries(EVENT_KINDS).map(([kind, k]) => ({ label: k.label, icon: k.icon, color: k.color, run: () => setEventKind(kind) })),
  ];

  // Events no journey covers yet: a journey planned for those dates later takes them into account.
  const today = localDateString(new Date());
  const looseEvents = events.filter((e) => e.end_date >= today
    && !journeys.some((j) => e.start_date <= j.race_date && e.end_date >= j.start_date));

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <CreateJourneyModal visible={createModalVisible} onClose={() => setCreateModalVisible(false)} onJourneyCreated={handleJourneyCreated} />
      <AddEventModal visible={!!eventKind} kind={eventKind || 'race'} onClose={() => setEventKind(null)} onSaved={onEventsChanged} />

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
                              {item.replanning ? <Text style={styles.cardStatus}>Adapting plan to your events…</Text> : null}
                              <NextEvent journey={item} events={events} today={today} />
                              {item.status === 'scheduled' && (
                                <Text style={styles.cardStatus}>Starts {item.start_date} · plan built on that day</Text>
                              )}
                              {item.status === 'failed' && <Text style={[styles.cardStatus, {color:'#ff4d4d'}]}>Plan failed</Text>}
                          </View>
                          <View style={{alignItems:'flex-end'}}>
                              {item.status === 'creating' || item.replanning ? (
                                  <ActivityIndicator color="#ff4d4d" />
                              ) : (
                                  <Ionicons name="chevron-forward" size={24} color="#666" />
                              )}
                          </View>
                      </TouchableOpacity>
                  )}
                  ListFooterComponent={looseEvents.length > 0 ? (
                      <View style={styles.looseBox}>
                          <Text style={styles.looseTitle}>NOT IN A JOURNEY YET</Text>
                          <EventList events={looseEvents} onChanged={onEventsChanged} />
                          <Text style={styles.looseHint}>A journey covering these dates will plan around them.</Text>
                      </View>
                  ) : null}
                  ListEmptyComponent={
                      <Text style={{color:'#666', textAlign:'center', marginTop: 50, lineHeight: 22}}>No journeys yet.{'\n'}Tap + to plan your next goal, or add a race.</Text>
                  }
              />

          </View>
      </View>
      <Toast message={note} onHide={() => setNote(null)} bottom={104} />
      <AddMenu options={ADD_OPTIONS} />
    </SafeAreaView>
  );
}

// The journey's next race or break, so the list shows what is coming.
function NextEvent({ journey, events, today }) {
  const next = journeyEvents(journey, events).find((e) => e.end_date >= today && !e.goal);
  if (!next) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 6 }}>
      <Ionicons name={EVENT_KINDS[next.kind].icon} size={12} color={EVENT_KINDS[next.kind].color} />
      <Text style={{ color: '#aaa', fontSize: 12 }}>{next.name} · {eventWhen(next)}</Text>
    </View>
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
  
  looseBox: { marginTop: 25, marginBottom: 90 },
  looseTitle: { color: '#666', fontSize: 12, fontWeight: 'bold', letterSpacing: 1, marginBottom: 4 },
  looseHint: { color: '#666', fontSize: 12, marginTop: 8 },

});