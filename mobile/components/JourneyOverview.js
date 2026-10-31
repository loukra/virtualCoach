import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet, TouchableOpacity, ScrollView, Alert, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Markdown from 'react-native-markdown-display';
import { apiDelete, apiGet, apiPost } from '../lib/api';
import { localDateString } from '../lib/dates';
import { colors } from '../theme';
import CheckInModal from './CheckInModal';

const TIME_OPTIONS = [30, 45, 60, 75, 90, 120, 150, 180];

// Closest offered duration to the planned one, so the picker starts on the coach's suggestion.
function snapToOption(minutes) {
  if (!minutes) return 60;
  return TIME_OPTIONS.reduce((best, t) => (Math.abs(t - minutes) < Math.abs(best - minutes) ? t : best));
}

// Mirrors forced_recovery_reason in backend/logic/coach.py, so the athlete knows before generating.
function recoveryHint(checkin, fitness) {
  if (checkin && (checkin.feel_score <= 2 || checkin.soreness_score <= 2)) {
    return 'You feel low today, so the coach will prescribe an easy recovery ride.';
  }
  if (fitness && fitness.tsb <= -30) return 'Your form is very low, so the coach will prescribe recovery.';
  return null;
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
  const [minutes, setMinutes] = useState(60);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingWorkout, setLoadingWorkout] = useState(false);
  const [showCheckInModal, setShowCheckInModal] = useState(false);

  const pollingRef = useRef(null);

  const loadToday = useCallback(async () => {
    try {
      const data = await apiGet(`/journeys/${journeyId}/today`);
      setToday(data);
      setMinutes(snapToOption(data.workout?.duration_min ?? data.planned?.planned_duration_min));
    } catch (e) {
      console.log('Error loading today:', e.message);
    }
  }, [journeyId]);

  const loadJourney = useCallback(async () => {
    try {
      const data = await apiGet(`/journeys/${journeyId}`);
      setJourney(data);
      if (data.status === 'creating') startPolling();
    } catch (e) {
      Alert.alert('Error', e.message);
    }
  }, [journeyId]);

  useEffect(() => {
    loadJourney();
    loadToday();
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [journeyId]);

  const startPolling = () => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      const data = await apiGet(`/journeys/${journeyId}`).catch(() => null);
      if (data && data.status !== 'creating') {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
        setJourney(data);
        loadToday();
      }
    }, 3000);
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([loadJourney(), loadToday()]);
    setRefreshing(false);
  };

  const handleGenerateWorkout = async (force) => {
    setLoadingWorkout(true);
    try {
      await apiPost('/generate-workout', { journey_id: journeyId, available_time: minutes, force });
      await loadToday();
    } catch (e) {
      Alert.alert('Workout not created', e.message);
    } finally {
      setLoadingWorkout(false);
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

  const header = (
    <View style={styles.navHeader}>
      <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn} accessibilityLabel="Back">
        <Ionicons name="arrow-back" size={24} color={colors.accent} />
      </TouchableOpacity>
      <View style={{ flex: 1, alignItems: 'center' }}>
        <Text style={styles.navTitle} numberOfLines={1}>{journey.name}</Text>
        <Text style={styles.navSub}>{countdownText(journey.race_date)}</Text>
      </View>
      <View style={{ width: 34 }} />
    </View>
  );

  if (journey.status === 'creating' || journey.status === 'failed') {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        {header}
        <View style={styles.center}>
          {journey.status === 'creating' ? (
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
        </View>
      </SafeAreaView>
    );
  }

  const { planned, checkin, workout, fitness } = today || {};
  const form = fitness ? formDescription(fitness.tsb) : null;
  const hint = recoveryHint(checkin, fitness);
  const isRestDay = planned && (planned.planned_workout_type === 'Rest' || !planned.planned_duration_min);

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

        {/* TODAY'S PLAN */}
        <Text style={styles.sectionLabel}>TODAY IN THE PLAN</Text>
        <View style={styles.card}>
          {planned ? (
            <>
              <View style={styles.planRow}>
                <Text style={styles.planType}>{planned.planned_workout_type}</Text>
                {planned.phase ? <Text style={styles.phase}>{planned.phase}</Text> : null}
              </View>
              {!isRestDay && (
                <Text style={styles.planMeta}>
                  {planned.planned_duration_min} min · {planned.planned_tss} TSS
                </Text>
              )}
              {planned.description ? <Text style={styles.planDesc}>{planned.description}</Text> : null}
            </>
          ) : (
            <Text style={styles.hint}>Nothing planned for today.</Text>
          )}
        </View>

        {/* CHECK-IN */}
        <Text style={styles.sectionLabel}>HOW DO YOU FEEL?</Text>
        {checkin ? (
          <View style={styles.row}>
            <CheckInTile label="MOOD" value={checkin.feel_score} onPress={() => setShowCheckInModal(true)} />
            <CheckInTile label="LEGS" value={checkin.soreness_score} onPress={() => setShowCheckInModal(true)} />
          </View>
        ) : (
          <TouchableOpacity style={[styles.card, styles.checkInPrompt]} onPress={() => setShowCheckInModal(true)}>
            <Ionicons name="happy-outline" size={22} color={colors.accent} />
            <Text style={styles.checkInPromptText}>Check in before you ride</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
          </TouchableOpacity>
        )}

        {hint && (
          <View style={[styles.recovery, { marginTop: 12, marginBottom: 0 }]}>
            <Ionicons name="information-circle-outline" size={16} color={colors.warn} />
            <Text style={styles.recoveryText}>{hint}</Text>
          </View>
        )}

        {/* WORKOUT */}
        <Text style={styles.sectionLabel}>YOUR WORKOUT</Text>
        <View style={styles.card}>
          <Text style={styles.timeLabel}>Time available</Text>
          <View style={styles.chips}>
            {TIME_OPTIONS.map((t) => (
              <TouchableOpacity
                key={t}
                onPress={() => setMinutes(t)}
                style={[styles.chip, minutes === t && styles.chipActive]}
                disabled={loadingWorkout}
              >
                <Text style={[styles.chipText, minutes === t && styles.chipTextActive]}>{t} min</Text>
              </TouchableOpacity>
            ))}
          </View>

          {!today || loadingWorkout ? (
            <View style={styles.loading}>
              <ActivityIndicator color={colors.accent} />
              <Text style={styles.hint}>{loadingWorkout ? 'Your coach is writing the workout…' : 'Loading…'}</Text>
            </View>
          ) : workout ? (
            <View style={{ marginTop: 15 }}>
              {hint && !workout.recovery_reason ? (
                <TouchableOpacity style={styles.recovery} onPress={() => handleGenerateWorkout(true)}>
                  <Ionicons name="refresh" size={16} color={colors.warn} />
                  <Text style={styles.recoveryText}>This workout was made before your check-in. Tap to update it.</Text>
                </TouchableOpacity>
              ) : null}
              {workout.recovery_reason ? (
                <View style={styles.recovery}>
                  <Ionicons name="bed-outline" size={16} color={colors.warn} />
                  <Text style={styles.recoveryText}>Recovery day: {workout.recovery_reason}</Text>
                </View>
              ) : null}
              <Markdown style={markdownStyles}>{workout.workout_text}</Markdown>
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
                <Text style={styles.generateText}>Create today's workout</Text>
              </TouchableOpacity>
              {!checkin && <Text style={[styles.hint, { marginTop: 10 }]}>Tip: check in first so the coach knows how you feel.</Text>}
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function countdownText(raceDate) {
  const days = daysUntil(raceDate);
  if (days > 1) return `${days} days to go`;
  if (days === 1) return 'Race is tomorrow';
  if (days === 0) return 'Race day';
  return 'Race done';
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

function CheckInTile({ label, value, onPress }) {
  const color = value >= 4 ? colors.good : value <= 2 ? colors.accent : colors.text;
  return (
    <TouchableOpacity style={styles.tile} onPress={onPress}>
      <Text style={styles.tileLabel}>{label}</Text>
      <Text style={[styles.tileValue, { color }]}>{value}/5</Text>
      <Text style={styles.tileSub}>tap to change</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 20, paddingBottom: 50 },
  center: { flex: 1, backgroundColor: colors.background, justifyContent: 'center', alignItems: 'center', padding: 30 },
  navHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  backBtn: { padding: 5 },
  navTitle: { color: colors.text, fontSize: 18, fontWeight: 'bold' },
  navSub: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  stateText: { color: colors.text, fontSize: 16, marginTop: 15, textAlign: 'center' },
  stateSub: { color: colors.textMuted, marginTop: 8, textAlign: 'center' },
  sectionLabel: { color: colors.textFaint, fontSize: 12, fontWeight: 'bold', marginBottom: 10, marginTop: 20, letterSpacing: 1 },
  hint: { color: colors.textMuted, fontSize: 14, lineHeight: 20 },
  row: { flexDirection: 'row', gap: 12 },
  tile: { flex: 1, backgroundColor: colors.card, padding: 14, borderRadius: 10, alignItems: 'center' },
  tileLabel: { color: colors.textMuted, fontSize: 10, fontWeight: 'bold', marginBottom: 4 },
  tileValue: { fontSize: 24, fontWeight: 'bold' },
  tileSub: { color: colors.textFaint, fontSize: 10, marginTop: 2 },
  card: { backgroundColor: colors.card, padding: 18, borderRadius: 12 },
  planRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  planType: { color: colors.text, fontSize: 20, fontWeight: 'bold' },
  phase: { color: colors.accent, fontSize: 11, fontWeight: 'bold', textTransform: 'uppercase' },
  planMeta: { color: colors.textMuted, marginTop: 4 },
  planDesc: { color: '#ddd', marginTop: 10, lineHeight: 21 },
  checkInPrompt: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  checkInPromptText: { color: colors.text, fontSize: 16, flex: 1 },
  timeLabel: { color: colors.textMuted, fontSize: 12, marginBottom: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 16, backgroundColor: colors.input },
  chipActive: { backgroundColor: colors.accent },
  chipText: { color: colors.textMuted, fontWeight: '600' },
  chipTextActive: { color: colors.text },
  loading: { padding: 20, alignItems: 'center', gap: 10 },
  recovery: { flexDirection: 'row', gap: 8, alignItems: 'center', backgroundColor: '#2a2210', padding: 10, borderRadius: 8, marginBottom: 10 },
  recoveryText: { color: colors.warn, flex: 1 },
  generateBtn: { backgroundColor: colors.accent, paddingVertical: 12, paddingHorizontal: 25, borderRadius: 30 },
  generateText: { color: colors.text, fontWeight: 'bold' },
  secondaryBtn: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 15, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border },
  secondaryText: { color: colors.textMuted, fontSize: 13 },
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
