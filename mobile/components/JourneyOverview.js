import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet, TouchableOpacity, ScrollView, Alert, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Markdown from 'react-native-markdown-display';
import { apiDelete, apiGet, apiPost, apiPut } from '../lib/api';
import { localDateString, parseLocalDate, weekdayName } from '../lib/dates';
import { journeyEvents } from '../lib/events';
import { shareWorkout } from '../lib/share';
import { colors, TYPE_COLORS } from '../theme';
import AddEventModal from './AddEventModal';
import CheckInModal from './CheckInModal';
import EventList from './EventList';
import Toast from './Toast';

const TIME_OPTIONS = [30, 45, 60, 75, 90, 120, 150, 180];
const FTP_TEST_MINUTES = 51; // logic.ftp.TEST_DURATION_MIN

// Closest offered duration to the planned one, so the picker starts on the coach's suggestion.
function snapToOption(minutes) {
  if (!minutes) return 60;
  return TIME_OPTIONS.reduce((best, t) => (Math.abs(t - minutes) < Math.abs(best - minutes) ? t : best));
}

function minutesFor(session) {
  if (!session) return 60;
  if (session.planned_workout_type === 'FTP Test') return 60;
  return snapToOption(session.planned_duration_min);
}

function formDescription(tsb) {
  if (tsb > 5) return { label: 'Fresh', color: colors.good };
  if (tsb >= -10) return { label: 'Neutral', color: colors.text };
  if (tsb >= -30) return { label: 'Building', color: colors.warn };
  return { label: 'Very tired', color: colors.accent };
}

function daysUntil(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number);
  const [ty, tm, td] = localDateString(new Date()).split('-').map(Number);
  return Math.round((Date.UTC(y, m - 1, d) - Date.UTC(ty, tm - 1, td)) / 86400000);
}

export default function JourneyOverview({ route, navigation }) {
  const { journeyId } = route.params;

  const [journey, setJourney] = useState(null);
  const [today, setToday] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [minutes, setMinutes] = useState(60);
  const [choosing, setChoosing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingWorkout, setLoadingWorkout] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [showCheckInModal, setShowCheckInModal] = useState(false);
  const [events, setEvents] = useState([]);
  const [showAddEvent, setShowAddEvent] = useState(false);
  const [note, setNote] = useState(null);

  const pollingRef = useRef(null);

  const loadToday = useCallback(async () => {
    try {
      const data = await apiGet(`/journeys/${journeyId}/today`);
      setToday(data);
      // Today's workout decides the selection once it exists; before that, the suggestion.
      // A workout without a session was written for a day without one, so the suggestion fits it too.
      const chosenId = data.workout?.chosen_plan_id ?? data.suggestion.session?.id;
      const chosen = data.week.sessions.find((s) => s.id === chosenId) || null;
      setSelectedId(chosen ? chosen.id : null);
      setMinutes(data.workout ? snapToOption(data.workout.duration_min) : minutesFor(chosen));
    } catch (e) {
      console.log('Error loading today:', e.message);
    }
  }, [journeyId]);

  const loadJourney = useCallback(async () => {
    try {
      const data = await apiGet(`/journeys/${journeyId}`);
      setJourney(data);
      if (isBusy(data)) startPolling();
    } catch (e) {
      Alert.alert('Error', e.message);
    }
  }, [journeyId]);

  const loadEvents = useCallback(async () => {
    try {
      setEvents(await apiGet('/events'));
    } catch (e) {
      console.log('Error loading events:', e.message);
    }
  }, []);

  useEffect(() => {
    loadJourney();
    loadToday();
    loadEvents();
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [journeyId]);

  // While the plan is built or adapted to new events, check every few seconds.
  const startPolling = () => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      const data = await apiGet(`/journeys/${journeyId}`).catch(() => null);
      if (data && !isBusy(data)) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
        setJourney(data);
        loadToday();
      }
    }, 3000);
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([loadJourney(), loadToday(), loadEvents()]);
    setRefreshing(false);
  };

  const selectSession = (session) => {
    setSelectedId(session.id);
    setMinutes(minutesFor(session));
    setChoosing(false);
  };

  const handleGenerateWorkout = async (force) => {
    setLoadingWorkout(true);
    try {
      await apiPost('/generate-workout', {
        journey_id: journeyId, available_time: minutes, plan_id: selectedId, force,
      });
      await loadToday();
    } catch (e) {
      Alert.alert('Workout not created', e.message);
    } finally {
      setLoadingWorkout(false);
    }
  };

  const handleShare = async () => {
    setSharing(true);
    try {
      await shareWorkout(journeyId, today.date);
    } catch (e) {
      Alert.alert('Could not share the workout', e.message);
    } finally {
      setSharing(false);
    }
  };

  const handleFtp = async (value) => {
    try {
      await apiPut('/ftp', { ftp: value });
      await loadToday();
    } catch (e) {
      Alert.alert('FTP not saved', e.message);
    }
  };

  const onEventsChanged = (message) => {
    setNote(message);
    loadEvents();
    loadToday(); // a race or day off today changes today's suggestion
    loadJourney(); // a rebuild may have started
  };

  const handleRetryReplan = async () => {
    try {
      await apiPost(`/journeys/${journeyId}/replan`);
      loadJourney();
    } catch (e) {
      Alert.alert('Could not adapt the plan', e.message);
    }
  };

  const handleRemove = () => {
    Alert.alert('Remove journey?', 'It disappears from the app. You can create a new one at any time.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiDelete(`/journeys/${journeyId}`);
            navigation.goBack();
          } catch (e) {
            Alert.alert('Could not remove', e.message);
          }
        },
      },
    ]);
  };

  if (!journey) {
    return <View style={styles.center}><ActivityIndicator size="large" color={colors.accent} /></View>;
  }

  const isBuild = journey.goal_type === 'build';
  const eventsSection = (
    <>
      <AddEventModal
        visible={showAddEvent}
        onClose={() => setShowAddEvent(false)}
        onSaved={onEventsChanged}
        defaultDate={parseLocalDate(journey.start_date)}
      />
      <View style={styles.sectionRow}>
        <Text style={styles.sectionLabel}>RACES & EVENTS</Text>
        <TouchableOpacity onPress={() => setShowAddEvent(true)} style={styles.addLink} accessibilityLabel="Add race or event">
          <Ionicons name="add" size={16} color={colors.accent} />
          <Text style={styles.linkText}>Add</Text>
        </TouchableOpacity>
      </View>
      <View style={styles.card}>
        <EventList
          events={journeyEvents(journey, events)}
          onChanged={onEventsChanged}
          empty="No races or days off in this journey. Add them and your coach plans around them."
        />
      </View>
    </>
  );
  const header = (
    <View style={styles.navHeader}>
      <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn} accessibilityLabel="Back">
        <Ionicons name="arrow-back" size={24} color={colors.accent} />
      </TouchableOpacity>
      <View style={{ flex: 1, alignItems: 'center' }}>
        <Text style={styles.navTitle} numberOfLines={1}>{journey.name}</Text>
        <Text style={styles.navSub}>
          {today?.starts_on ? `Starts ${formatDay(today.starts_on)} · ${today.week.total} weeks` : ''}
          {today && !today.starts_on ? `Week ${today.week.number} of ${today.week.total}` : ''}
          {today && !isBuild ? ` · ${countdownText(journey.race_date)}` : ''}
        </Text>
      </View>
      <View style={{ width: 34 }} />
    </View>
  );

  if (journey.status === 'creating' || journey.status === 'failed' || journey.status === 'scheduled') {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        {header}
        <ScrollView contentContainerStyle={styles.stateScroll}>
          {journey.status === 'scheduled' ? (
            <>
              <Ionicons name="calendar-outline" size={40} color={colors.accent} />
              <Text style={styles.stateText}>Starts {formatDay(journey.start_date)}</Text>
              <Text style={styles.stateSub}>
                Your coach builds the plan on that day, from your fitness and FTP then.
              </Text>
              <TouchableOpacity style={styles.secondaryBtn} onPress={handleRemove}>
                <Text style={styles.secondaryText}>Remove journey</Text>
              </TouchableOpacity>
              <View style={{ alignSelf: 'stretch' }}>{eventsSection}</View>
            </>
          ) : journey.status === 'creating' ? (
            <>
              <ActivityIndicator color={colors.accent} />
              <Text style={styles.stateText}>Your coach is building the plan…</Text>
              <Text style={styles.stateSub}>This usually takes a minute or two.</Text>
            </>
          ) : (
            <>
              <Ionicons name="alert-circle-outline" size={40} color={colors.accent} />
              <Text style={styles.stateText}>The plan could not be created.</Text>
              <Text style={styles.stateSub}>{journey.error || 'Please create the journey again.'}</Text>
              <TouchableOpacity style={[styles.generateBtn, { marginTop: 25 }]} onPress={handleRemove}>
                <Text style={styles.generateText}>Remove journey</Text>
              </TouchableOpacity>
            </>
          )}
        </ScrollView>
        <Toast message={note} onHide={() => setNote(null)} />
      </SafeAreaView>
    );
  }

  if (!today) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        {header}
        <View style={styles.center}><ActivityIndicator color={colors.accent} /></View>
      </SafeAreaView>
    );
  }

  const { suggestion, week, checkin, workout, fitness, signals, ftp } = today;
  const sessions = week.sessions.filter((s) => s.state !== 'rest');
  const counted = sessions.filter((s) => s.state !== 'off'); // sessions on days off drop out
  const openSessions = sessions.filter((s) => s.state === 'open');
  const selected = sessions.find((s) => s.id === selectedId) || null;
  const workoutMatches = workout && workout.chosen_plan_id === selectedId;
  const form = fitness ? formDescription(fitness.tsb) : null;
  const isTest = selected?.planned_workout_type === 'FTP Test';
  const staleRecovery = workout && suggestion.mode === 'recovery' && !workout.recovery_reason;

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <CheckInModal
        visible={showCheckInModal}
        onClose={() => setShowCheckInModal(false)}
        currentValues={checkin}
        onSave={() => loadToday()}
      />
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
      >
        {header}

        {journey.replanning ? (
          <View style={[styles.banner, { marginTop: 10 }]}>
            <ActivityIndicator color={colors.warn} size="small" />
            <Text style={styles.bannerText}>Your coach is adapting the plan from Monday on to your events.</Text>
          </View>
        ) : journey.error ? (
          <TouchableOpacity style={[styles.banner, { marginTop: 10 }]} onPress={handleRetryReplan}>
            <Ionicons name="refresh" size={16} color={colors.warn} />
            <Text style={styles.bannerText}>{journey.error}</Text>
          </TouchableOpacity>
        ) : null}

        {signals.map((s) => (
          <View key={s.kind} style={[styles.banner, { marginTop: 10 }]}>
            <Ionicons name="warning-outline" size={16} color={colors.warn} />
            <Text style={styles.bannerText}>{s.message}</Text>
          </View>
        ))}

        {ftp && <FtpCard ftp={ftp} onAccept={() => handleFtp(ftp.suggested)} onKeep={() => handleFtp(ftp.current)} />}

        {/* TODAY */}
        <Text style={styles.sectionLabel}>TODAY</Text>
        <View style={styles.card}>
          {selected ? (
            <>
              <View style={styles.planRow}>
                <View style={styles.typeRow}>
                  <View style={[styles.dot, { backgroundColor: TYPE_COLORS[selected.planned_workout_type] }]} />
                  <Text style={styles.planType}>{selected.planned_workout_type}</Text>
                </View>
                {selected.phase ? <Text style={styles.phase}>{selected.phase}</Text> : null}
              </View>
              <Text style={styles.planMeta}>
                {isTest ? `${FTP_TEST_MINUTES} min · 20 min all out` : `${selected.planned_duration_min} min · ${selected.planned_tss} TSS`}
              </Text>
              {selected.description ? <Text style={styles.planDesc}>{selected.description}</Text> : null}
              {selected.id === suggestion.session?.id && suggestion.reason !== 'Planned for today.' ? (
                <Text style={styles.reason}>{suggestion.reason}</Text>
              ) : null}
              {selected.id !== suggestion.session?.id ? (
                <Text style={styles.reason}>You chose this one; planned for {weekdayName(selected.date)}.</Text>
              ) : null}
            </>
          ) : (
            <>
              <Text style={styles.planType}>
                {today.starts_on ? 'Not started yet'
                  : suggestion.mode === 'race' ? 'Race day'
                  : suggestion.mode === 'recovery' ? 'Easy recovery spin'
                  : suggestion.mode === 'done' ? 'Done for today' : 'Rest day'}
              </Text>
              <Text style={styles.planDesc}>{suggestion.reason}</Text>
            </>
          )}
          {openSessions.length > 0 && !today.starts_on && (
            <TouchableOpacity style={styles.linkRow} onPress={() => setChoosing(!choosing)}>
              <Text style={styles.linkText}>{choosing ? 'Close' : selected ? 'Ride another session' : 'Ride a session anyway'}</Text>
              <Ionicons name={choosing ? 'chevron-up' : 'chevron-down'} size={16} color={colors.accent} />
            </TouchableOpacity>
          )}
          {choosing && openSessions.map((s) => (
            <TouchableOpacity key={s.id} style={styles.choice} onPress={() => selectSession(s)}>
              <View style={[styles.dot, { backgroundColor: TYPE_COLORS[s.planned_workout_type] }]} />
              <Text style={styles.choiceText}>{s.planned_workout_type}</Text>
              <Text style={styles.choiceMeta}>{weekdayName(s.date, 'short')} · {s.planned_duration_min} min</Text>
              {s.id === selectedId && <Ionicons name="checkmark" size={16} color={colors.accent} />}
            </TouchableOpacity>
          ))}
        </View>

        {/* CHECK-IN */}
        <Text style={styles.sectionLabel}>HOW YOU FEEL</Text>
        {checkin ? (
          <TouchableOpacity style={styles.row} onPress={() => setShowCheckInModal(true)} accessibilityLabel="Update check-in">
            <CheckInTile label="ENERGY" value={checkin.feel_score} />
            <CheckInTile label="LEGS" value={checkin.soreness_score} />
            <CheckInTile label="MOTIVATION" value={checkin.motivation_score} />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={[styles.card, styles.checkInPrompt]} onPress={() => setShowCheckInModal(true)}>
            <Ionicons name="happy-outline" size={22} color={colors.accent} />
            <Text style={styles.checkInPromptText}>Check in before you ride</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
          </TouchableOpacity>
        )}
        {checkin && <Text style={styles.tapHint}>Tap to update whenever it changes.</Text>}

        {/* WORKOUT (none on race day: the race is the session) */}
        {suggestion.mode === 'race' && !selected ? null : (<>
        <Text style={styles.sectionLabel}>WORKOUT</Text>
        <View style={styles.card}>
          <Text style={styles.timeLabel}>Time available</Text>
          <View style={styles.chips}>
            {TIME_OPTIONS.map((t) => (
              <TouchableOpacity
                key={t}
                onPress={() => setMinutes(t)}
                style={[styles.chip, minutes === t && styles.chipActive, isTest && t < FTP_TEST_MINUTES && styles.chipDisabled]}
                disabled={loadingWorkout || (isTest && t < FTP_TEST_MINUTES)}
              >
                <Text style={[styles.chipText, minutes === t && styles.chipTextActive]}>{t} min</Text>
              </TouchableOpacity>
            ))}
          </View>

          {loadingWorkout ? (
            <View style={styles.loading}>
              <ActivityIndicator color={colors.accent} />
              <Text style={styles.hint}>{isTest ? 'Preparing your FTP test…' : 'Your coach is writing the workout…'}</Text>
            </View>
          ) : workoutMatches ? (
            <View style={{ marginTop: 15 }}>
              {staleRecovery ? (
                <TouchableOpacity style={styles.banner} onPress={() => handleGenerateWorkout(true)}>
                  <Ionicons name="refresh" size={16} color={colors.warn} />
                  <Text style={styles.bannerText}>This workout was made before your check-in. Tap to update it.</Text>
                </TouchableOpacity>
              ) : null}
              {workout.recovery_reason ? (
                <View style={styles.banner}>
                  <Ionicons name="bed-outline" size={16} color={colors.warn} />
                  <Text style={styles.bannerText}>Recovery: {workout.recovery_reason}</Text>
                </View>
              ) : null}
              <Markdown style={markdownStyles}>{workout.workout_text}</Markdown>
              <TouchableOpacity style={styles.shareBtn} onPress={handleShare} disabled={sharing}>
                {sharing ? <ActivityIndicator color={colors.text} /> : <Ionicons name="share-outline" size={18} color={colors.text} />}
                <Text style={styles.generateText}>Send to Zwift (.zwo)</Text>
              </TouchableOpacity>
              <Text style={styles.shareHint}>
                AirDrop it to your Mac, then move it into Documents › Zwift › Workouts › (your Zwift ID). It shows up under Custom Workouts.
              </Text>
              <TouchableOpacity
                style={styles.secondaryBtn}
                onPress={() => handleGenerateWorkout(workout.duration_min === minutes)}
              >
                <Ionicons name="refresh" size={16} color={colors.textMuted} />
                <Text style={styles.secondaryText}>
                  {workout.duration_min === minutes ? 'Create a new version' : `Redo for ${minutes} min`}
                </Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={{ marginTop: 15, alignItems: 'center' }}>
              <TouchableOpacity style={styles.generateBtn} onPress={() => handleGenerateWorkout(false)}>
                <Text style={styles.generateText}>
                  {isTest ? 'Get the FTP test' : selected ? `Create ${selected.planned_workout_type} workout` : 'Create an easy ride'}
                </Text>
              </TouchableOpacity>
              {workout && <Text style={[styles.hint, { marginTop: 10 }]}>This replaces today's earlier workout.</Text>}
              {!checkin && <Text style={[styles.hint, { marginTop: 10 }]}>Tip: check in first so the coach knows how you feel.</Text>}
            </View>
          )}
        </View>

        </>)}

        {/* THIS WEEK */}
        <Text style={styles.sectionLabel}>{today.starts_on ? 'FIRST WEEK' : 'THIS WEEK'}</Text>
        <View style={styles.card}>
          <View style={styles.progressRow}>
            <Text style={styles.hint}>{week.ridden_tss} of {week.planned_tss} TSS</Text>
            <Text style={styles.hint}>{counted.filter((s) => s.state === 'done').length}/{counted.length} sessions</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.min(100, (100 * week.ridden_tss) / Math.max(1, week.planned_tss))}%` }]} />
          </View>
          {sessions.map((s) => (
            <TouchableOpacity
              key={s.id}
              style={styles.weekRow}
              disabled={s.state !== 'open'}
              onPress={() => selectSession(s)}
              accessibilityLabel={`${s.planned_workout_type} ${s.state}`}
            >
              <Text style={styles.weekDay}>{weekdayName(s.date, 'short')}</Text>
              <View style={[styles.dot, { backgroundColor: TYPE_COLORS[s.planned_workout_type] }]} />
              <Text style={[styles.weekType, (s.state === 'done' || s.state === 'off') && styles.doneText]}>{s.planned_workout_type}</Text>
              <Text style={styles.weekMeta}>{s.planned_duration_min} min</Text>
              <SessionMark session={s} selected={s.id === selectedId} />
            </TouchableOpacity>
          ))}
          <Text style={[styles.hint, { marginTop: 10, fontSize: 12 }]}>
            Sessions can move within the week: whatever you ride counts for the session that fits it.
          </Text>
        </View>

        {eventsSection}

        {/* FITNESS */}
        <Text style={styles.sectionLabel}>TRAINING LOAD</Text>
        {fitness ? (
          <View style={styles.row}>
            <Metric label="FITNESS" sub="CTL" value={Math.round(fitness.ctl)} />
            <Metric label="FATIGUE" sub="ATL" value={Math.round(fitness.atl)} />
            <Metric label="FORM" sub={form.label} value={Math.round(fitness.tsb)} color={form.color} />
          </View>
        ) : (
          <Text style={styles.hint}>No rides synced yet. Fitness appears after your first Strava sync.</Text>
        )}
      </ScrollView>
      <Toast message={note} onHide={() => setNote(null)} />
    </SafeAreaView>
  );
}

function isBusy(journey) {
  return journey.status === 'creating' || !!journey.replanning;
}

function formatDay(iso) {
  return parseLocalDate(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
}

function countdownText(raceDate) {
  const days = daysUntil(raceDate);
  if (days > 1) return `${days} days to go`;
  if (days === 1) return 'race tomorrow';
  if (days === 0) return 'race day';
  return 'race done';
}

function FtpCard({ ftp, onAccept, onKeep }) {
  const up = ftp.suggested > ftp.current;
  const source = ftp.source === 'test'
    ? `Your FTP test on ${weekdayName(ftp.date)}`
    : `Your best 20 minutes on ${weekdayName(ftp.date)}`;
  return (
    <View style={[styles.card, styles.ftpCard]}>
      <View style={styles.typeRow}>
        <Ionicons name={up ? 'trending-up' : 'trending-down'} size={20} color={up ? colors.good : colors.warn} />
        <Text style={styles.ftpTitle}>New FTP: {ftp.suggested} W ({up ? '+' : ''}{ftp.change_pct} %)</Text>
      </View>
      <Text style={styles.planDesc}>{source} points to {ftp.suggested} W instead of {ftp.current} W. Workouts use FTP for every target.</Text>
      <View style={styles.ftpButtons}>
        <TouchableOpacity style={styles.generateBtn} onPress={onAccept}>
          <Text style={styles.generateText}>Use {ftp.suggested} W</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.keepBtn} onPress={onKeep}>
          <Text style={styles.secondaryText}>Keep {ftp.current} W</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function SessionMark({ session, selected }) {
  if (session.state === 'done') {
    const moved = session.done_on && session.done_on !== session.date;
    return <Text style={styles.markDone}>✓{moved ? ` ${weekdayName(session.done_on, 'short')}` : ''}</Text>;
  }
  if (session.state === 'missed') return <Text style={styles.markMissed}>missed</Text>;
  if (session.state === 'off') return <Text style={styles.markMissed}>time off</Text>;
  return selected ? <Ionicons name="radio-button-on" size={16} color={colors.accent} /> : <Ionicons name="radio-button-off" size={16} color={colors.textFaint} />;
}

function Metric({ label, sub, value, color = colors.text }) {
  return (
    <View style={styles.tile}>
      <Text style={styles.tileLabel}>{label}</Text>
      <Text style={[styles.tileValue, { color }]}>{value}</Text>
      <Text style={styles.tileSub}>{sub}</Text>
    </View>
  );
}

function CheckInTile({ label, value }) {
  const color = !value ? colors.textFaint : value >= 4 ? colors.good : value <= 2 ? colors.accent : colors.text;
  return (
    <View style={styles.tile}>
      <Text style={styles.tileLabel}>{label}</Text>
      <Text style={[styles.tileValue, { color }]}>{value ? `${value}/5` : '–'}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 20, paddingBottom: 50 },
  center: { flex: 1, backgroundColor: colors.background, justifyContent: 'center', alignItems: 'center', padding: 30 },
  navHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  backBtn: { padding: 5 },
  navTitle: { color: colors.text, fontSize: 18, fontWeight: 'bold' },
  navSub: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  stateScroll: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 20, paddingBottom: 50 },
  stateText: { color: colors.text, fontSize: 16, marginTop: 15, textAlign: 'center' },
  stateSub: { color: colors.textMuted, marginTop: 8, textAlign: 'center' },
  sectionLabel: { color: colors.textFaint, fontSize: 12, fontWeight: 'bold', marginBottom: 10, marginTop: 22, letterSpacing: 1 },
  sectionRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' },
  addLink: { flexDirection: 'row', alignItems: 'center', gap: 2, marginBottom: 10, padding: 2 },
  hint: { color: colors.textMuted, fontSize: 14, lineHeight: 20 },
  row: { flexDirection: 'row', gap: 12 },
  tile: { flex: 1, backgroundColor: colors.card, padding: 14, borderRadius: 10, alignItems: 'center' },
  tileLabel: { color: colors.textMuted, fontSize: 10, fontWeight: 'bold', marginBottom: 4 },
  tileValue: { fontSize: 22, fontWeight: 'bold' },
  tileSub: { color: colors.textFaint, fontSize: 10, marginTop: 2 },
  tapHint: { color: colors.textFaint, fontSize: 11, marginTop: 6, textAlign: 'center' },
  card: { backgroundColor: colors.card, padding: 18, borderRadius: 12 },
  planRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  typeRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  planType: { color: colors.text, fontSize: 20, fontWeight: 'bold' },
  phase: { color: colors.accent, fontSize: 11, fontWeight: 'bold', textTransform: 'uppercase' },
  planMeta: { color: colors.textMuted, marginTop: 4 },
  planDesc: { color: '#ddd', marginTop: 10, lineHeight: 21 },
  reason: { color: colors.warn, marginTop: 10, fontSize: 13, lineHeight: 19 },
  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border },
  linkText: { color: colors.accent, fontWeight: '600' },
  choice: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  choiceText: { color: colors.text, fontSize: 15, flex: 1 },
  choiceMeta: { color: colors.textMuted, fontSize: 13 },
  checkInPrompt: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  checkInPromptText: { color: colors.text, fontSize: 16, flex: 1 },
  timeLabel: { color: colors.textMuted, fontSize: 12, marginBottom: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 16, backgroundColor: colors.input },
  chipActive: { backgroundColor: colors.accent },
  chipDisabled: { opacity: 0.3 },
  chipText: { color: colors.textMuted, fontWeight: '600' },
  chipTextActive: { color: colors.text },
  loading: { padding: 20, alignItems: 'center', gap: 10 },
  banner: { flexDirection: 'row', gap: 8, alignItems: 'center', backgroundColor: '#2a2210', padding: 10, borderRadius: 8, marginBottom: 10 },
  bannerText: { color: colors.warn, flex: 1, lineHeight: 19 },
  generateBtn: { backgroundColor: colors.accent, paddingVertical: 12, paddingHorizontal: 25, borderRadius: 30, alignItems: 'center' },
  generateText: { color: colors.text, fontWeight: 'bold' },
  shareBtn: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, backgroundColor: colors.accent, paddingVertical: 12, borderRadius: 30, marginTop: 15 },
  shareHint: { color: colors.textFaint, fontSize: 12, lineHeight: 17, marginTop: 8, textAlign: 'center' },
  secondaryBtn: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 15, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border },
  secondaryText: { color: colors.textMuted, fontSize: 13 },
  progressRow: { flexDirection: 'row', justifyContent: 'space-between' },
  progressTrack: { height: 6, borderRadius: 3, backgroundColor: colors.input, marginTop: 8, marginBottom: 6, overflow: 'hidden' },
  progressFill: { height: 6, backgroundColor: colors.good },
  weekRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  weekDay: { color: colors.textMuted, width: 34, fontSize: 13 },
  weekType: { color: colors.text, flex: 1, fontSize: 15 },
  doneText: { color: colors.textMuted },
  weekMeta: { color: colors.textMuted, fontSize: 13 },
  markDone: { color: colors.good, fontWeight: 'bold', minWidth: 16, textAlign: 'right' },
  markMissed: { color: colors.textFaint, fontSize: 12 },
  ftpCard: { marginTop: 14, borderWidth: 1, borderColor: '#2f4a2f' },
  ftpTitle: { color: colors.text, fontSize: 17, fontWeight: 'bold' },
  ftpButtons: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 14 },
  keepBtn: { paddingVertical: 12, paddingHorizontal: 15 },
});

const markdownStyles = {
  heading1: { color: colors.text, fontSize: 22, fontWeight: 'bold', lineHeight: 30, marginBottom: 10 },
  body: { color: '#ddd', fontSize: 15, lineHeight: 22 },
  heading2: { color: colors.accent, fontSize: 17, fontWeight: 'bold', marginTop: 16, marginBottom: 8, borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: 4 },
  strong: { color: colors.text, fontWeight: 'bold' },
  bullet_list_icon: { color: colors.accent, fontSize: 18 },
  list_item: { marginBottom: 6 },
  em: { color: colors.textMuted, fontStyle: 'italic' },
};
