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
import { EVENT_KINDS, PRIORITIES, eventWhen, journeyEvents } from '../lib/events';
import { localDateString, parseLocalDate } from '../lib/dates';
import { useJourney } from '../context/JourneyContext';
import { useSessionContext } from '../context/SessionContext';
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- once per app start, by design

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

      <View style={styles.header}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Ionicons name="bicycle" size={24} color="#ff4d4d" style={{ marginRight: 10 }} />
          <Text style={styles.appName}>{APP_NAME}</Text>
        </View>
        {isSyncing && (
          <View style={styles.syncing}>
            <ActivityIndicator size="small" color="#666" />
            <Text style={styles.syncingText}>Strava</Text>
          </View>
        )}
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
                      <JourneyCard
                        journey={item}
                        events={events}
                        today={today}
                        onPress={() => {
                          setActiveJourneyId(item.id);
                          navigation.navigate('JourneyDetail', { journeyId: item.id, name: item.name });
                        }}
                      />
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

function shortDate(iso) {
  return parseLocalDate(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

// One journey: its type, dates, how far along it is, its state and the races and breaks to come.
function JourneyCard({ journey, events, today, onPress }) {
  const isRace = journey.goal_type === 'race';
  const total = (parseLocalDate(journey.race_date) - parseLocalDate(journey.start_date)) / 86400000 + 1;
  const done = Math.min(total, Math.max(0, (parseLocalDate(today) - parseLocalDate(journey.start_date)) / 86400000 + 1));
  const busy = journey.status === 'creating' || journey.replanning;
  const status = journey.status === 'creating' ? 'Building plan…'
    : journey.replanning ? 'Adapting plan to your events…'
    : journey.status === 'scheduled' ? `Starts ${shortDate(journey.start_date)} · plan built that day`
    : journey.status === 'failed' ? 'Plan failed' : null;
  return (
    <TouchableOpacity style={styles.card} onPress={onPress} accessibilityLabel={`Open ${journey.name}`}>
      <View style={styles.cardTop}>
        <View style={[styles.badge, { backgroundColor: isRace ? '#3a2547' : '#1f3346' }]}>
          <Ionicons name={isRace ? 'flag' : 'trending-up'} size={12} color={isRace ? '#d7a6f0' : '#8cc8f2'} />
          <Text style={[styles.badgeText, { color: isRace ? '#d7a6f0' : '#8cc8f2' }]}>{isRace ? 'RACE' : 'BUILD'}</Text>
        </View>
        {busy ? <ActivityIndicator color="#ff4d4d" /> : <Ionicons name="chevron-forward" size={20} color="#555" />}
      </View>
      <Text style={styles.cardTitle}>{journey.name}</Text>
      <Text style={styles.cardDate}>
        {shortDate(journey.start_date)} – {shortDate(journey.race_date)} · {Math.round(total / 7)} weeks
      </Text>
      {journey.status === 'active' && done > 0 && (
        <View style={styles.track}><View style={[styles.fill, { width: `${(100 * done) / total}%` }]} /></View>
      )}
      {status && <Text style={[styles.cardStatus, journey.status === 'failed' && { color: '#ff4d4d' }]}>{status}</Text>}
      <JourneyEvents journey={journey} events={events} today={today} />
    </TouchableOpacity>
  );
}

// The journey's coming races, rides and breaks (its own race is in the subtitle already).
const MAX_EVENTS_ON_CARD = 4;

function JourneyEvents({ journey, events, today }) {
  const coming = journeyEvents(journey, events).filter((e) => e.end_date >= today && !e.goal);
  if (!coming.length) return null;
  const shown = coming.slice(0, MAX_EVENTS_ON_CARD);
  return (
    <View style={styles.eventBox}>
      {shown.map((e) => {
        const k = EVENT_KINDS[e.kind];
        const label = e.kind === 'race' ? PRIORITIES[e.priority].label : k.label;
        return (
          <View key={e.id} style={styles.eventRow}>
            <Ionicons name={e.kind === 'race' && e.priority === 'B' ? 'flag-outline' : k.icon} size={13} color={k.color} />
            <Text style={styles.eventName} numberOfLines={1}>{e.name}</Text>
            <Text style={styles.eventMeta}>{label} · {eventWhen(e)}</Text>
          </View>
        );
      })}
      {coming.length > shown.length && (
        <Text style={styles.eventMore}>+{coming.length - shown.length} more</Text>
      )}
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
  
  appName: { color: '#fff', fontWeight: 'bold', fontSize: 18 },
  syncing: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  syncingText: { color: '#666', fontSize: 12 },
  sectionTitle: { color: '#666', fontSize: 12, fontWeight: 'bold', letterSpacing: 1 },

  card: { backgroundColor: '#1a1a1a', padding: 18, borderRadius: 14 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 3, paddingHorizontal: 8, borderRadius: 6 },
  badgeText: { fontSize: 11, fontWeight: 'bold', letterSpacing: 1 },
  cardTitle: { color: 'white', fontSize: 19, fontWeight: 'bold' },
  cardDate: { color: '#888', fontSize: 13, marginTop: 4 },
  track: { height: 4, borderRadius: 2, backgroundColor: '#2a2a2a', marginTop: 12, overflow: 'hidden' },
  fill: { height: 4, backgroundColor: '#ff4d4d' },
  cardStatus: { color: '#888', fontSize: 12, marginTop: 8, fontStyle: 'italic' },
  
  eventBox: { marginTop: 12, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#333', gap: 7 },
  eventRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  eventName: { color: '#ddd', fontSize: 13, fontWeight: '600', flexShrink: 1 },
  eventMeta: { color: '#777', fontSize: 12 },
  eventMore: { color: '#777', fontSize: 12 },
  looseBox: { marginTop: 25, marginBottom: 90 },
  looseTitle: { color: '#666', fontSize: 12, fontWeight: 'bold', letterSpacing: 1, marginBottom: 4 },
  looseHint: { color: '#666', fontSize: 12, marginTop: 8 },

});