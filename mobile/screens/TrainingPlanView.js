import React, { useState, useCallback } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, TouchableOpacity, Dimensions, Modal, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import Markdown from 'react-native-markdown-display';
import { apiGet } from '../lib/api';
import { localDateString } from '../lib/dates';
import { useJourney } from '../context/JourneyContext';
import { colors } from '../theme';

const GRID_PADDING = 16;
// Whole pixels, so seven tiles always fit in one row.
const TILE_SIZE = Math.floor((Dimensions.get('window').width - GRID_PADDING * 2) / 7);
const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

// One colour per intensity, easy to hard (types from backend/logic/schemas.py).
const TYPE_COLORS = {
  Rest: '#333',
  Recovery: '#a0a0a8',
  Endurance: '#5dade2',
  Tempo: '#58d68d',
  'Sweet Spot': '#f4d03f',
  Threshold: '#f5b041',
  'VO2 Max': '#ec7063',
  Anaerobic: '#c0392b',
  Race: '#af7ac5',
};
const LEGEND = ['Recovery', 'Endurance', 'Tempo', 'Sweet Spot', 'Threshold', 'VO2 Max'];

// "2026-11-01" as a local date (new Date("2026-11-01") would be midnight UTC).
function parseLocalDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function formatTime(seconds) {
  if (!seconds) return '0m';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// Plan days plus the rides done on them, grouped into months with leading blanks so Monday is column one.
function buildMonths(plan, activities) {
  const ridesByDay = {};
  activities.forEach((act) => {
    const day = act.start_date_local.slice(0, 10);
    (ridesByDay[day] = ridesByDay[day] || []).push(act);
  });

  const months = [];
  plan.forEach((planItem) => {
    const key = planItem.date.slice(0, 7);
    let month = months[months.length - 1];
    if (!month || month.key !== key) {
      const first = parseLocalDate(planItem.date);
      const blanks = (first.getDay() + 6) % 7;
      month = {
        key,
        title: first.toLocaleString('en-GB', { month: 'long', year: 'numeric' }).toUpperCase(),
        days: Array.from({ length: blanks }, (_, i) => ({ key: `pad-${key}-${i}`, empty: true })),
      };
      months.push(month);
    }
    month.days.push({ key: planItem.date, date: planItem.date, plan: planItem, rides: ridesByDay[planItem.date] || [] });
  });
  return months;
}

export default function TrainingPlanView() {
  const { activeJourneyId, setActiveJourneyId } = useJourney();
  const [loading, setLoading] = useState(true);
  const [journey, setJourney] = useState(null);
  const [months, setMonths] = useState([]);
  const [allJourneys, setAllJourneys] = useState([]);
  const [showSelector, setShowSelector] = useState(false);
  const [selectedDay, setSelectedDay] = useState(null);

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [activeJourneyId])
  );

  const fetchData = async () => {
    try {
      setLoading(true);
      const userJourneys = (await apiGet('/journeys')).filter((j) => j.status === 'active');
      setAllJourneys(userJourneys);

      let target = userJourneys.find((j) => j.id === activeJourneyId);
      if (!target && userJourneys.length > 0) {
        target = userJourneys[0];
        setActiveJourneyId(target.id);
      }
      setJourney(target || null);

      if (target) {
        const { plan, activities } = await apiGet(`/journeys/${target.id}/calendar`);
        setMonths(buildMonths(plan, activities));
      } else {
        setMonths([]);
      }
    } catch (e) {
      console.log('Could not load the calendar:', e.message);
    } finally {
      setLoading(false);
    }
  };

  const today = localDateString(new Date());

  const renderDay = (day) => {
    if (day.empty) return <View key={day.key} style={styles.tileEmpty} />;

    const type = day.plan.planned_workout_type;
    const done = day.rides.length > 0;
    const isToday = day.date === today;
    return (
      <TouchableOpacity
        key={day.key}
        style={[styles.tile, type === 'Rest' && styles.restTile, done && styles.doneTile, isToday && styles.todayTile]}
        onPress={() => setSelectedDay(day)}
        accessibilityLabel={`${day.date}: ${type}${done ? ', ride done' : ''}`}
      >
        <Text style={[styles.miniDate, isToday && { color: colors.accent }]}>{Number(day.date.slice(8))}</Text>
        {done ? (
          <Ionicons name="checkmark" size={16} color="#A7F3D0" />
        ) : type !== 'Rest' ? (
          <View style={[styles.dot, { backgroundColor: TYPE_COLORS[type] || colors.accent }]} />
        ) : null}
      </TouchableOpacity>
    );
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.accent} /></View>;

  const planned = selectedDay?.plan;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Calendar</Text>
        {journey && (
          <TouchableOpacity onPress={() => setShowSelector(true)} style={styles.selectorBtn} disabled={allJourneys.length < 2}>
            <Text style={styles.subtitle}>{journey.name}</Text>
            {allJourneys.length > 1 && <Ionicons name="chevron-down" size={12} color={colors.accent} style={{ marginLeft: 4 }} />}
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.daysHeader}>
        {DAY_LABELS.map((d, i) => <Text key={i} style={styles.dayLabelText}>{d}</Text>)}
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
        {months.length > 0 && (
          <View style={styles.legend}>
            {LEGEND.map((t) => (
              <View key={t} style={styles.legendItem}>
                <View style={[styles.dot, { backgroundColor: TYPE_COLORS[t] }]} />
                <Text style={styles.legendText}>{t}</Text>
              </View>
            ))}
          </View>
        )}
        {months.map((month) => (
          <View key={month.key} style={styles.monthContainer}>
            <Text style={styles.monthHeader}>{month.title}</Text>
            <View style={styles.monthGrid}>{month.days.map(renderDay)}</View>
          </View>
        ))}
        {months.length === 0 && (
          <Text style={styles.empty}>No plan yet. Create a journey on the Home tab.</Text>
        )}
      </ScrollView>

      <Modal visible={showSelector} transparent animationType="fade" onRequestClose={() => setShowSelector(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setShowSelector(false)}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Show journey</Text>
            {allJourneys.map((j) => (
              <TouchableOpacity
                key={j.id}
                style={[styles.modalItem, activeJourneyId === j.id && styles.modalItemSelected]}
                onPress={() => { setActiveJourneyId(j.id); setShowSelector(false); }}
              >
                <Text style={[styles.modalItemText, activeJourneyId === j.id && { color: colors.accent }]}>{j.name}</Text>
                {activeJourneyId === j.id && <Ionicons name="checkmark" size={18} color={colors.accent} />}
              </TouchableOpacity>
            ))}
          </View>
        </TouchableOpacity>
      </Modal>

      <Modal visible={!!selectedDay} transparent animationType="slide" onRequestClose={() => setSelectedDay(null)}>
        <View style={styles.detailOverlay}>
          <View style={styles.detailContent}>
            <TouchableOpacity style={styles.closeBtn} onPress={() => setSelectedDay(null)} accessibilityLabel="Close">
              <Ionicons name="close" size={24} color="#ddd" />
            </TouchableOpacity>
            {selectedDay && (
              <ScrollView>
                <Text style={styles.detailDate}>
                  {parseLocalDate(selectedDay.date).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}
                </Text>

                <Text style={styles.sectionHeader}>PLAN{planned.phase ? ` · ${planned.phase.toUpperCase()}` : ''}</Text>
                <View style={styles.planTitleRow}>
                  <View style={[styles.dot, { backgroundColor: TYPE_COLORS[planned.planned_workout_type] }]} />
                  <Text style={styles.detailTitle}>{planned.planned_workout_type}</Text>
                </View>
                {planned.planned_workout_type !== 'Rest' && (
                  <Text style={styles.detailSub}>{planned.planned_duration_min} min · {planned.planned_tss} TSS</Text>
                )}
                {planned.description ? <Text style={styles.detailBody}>{planned.description}</Text> : null}

                {planned.workout_text ? (
                  <View style={styles.divider}>
                    <Text style={styles.sectionHeader}>WORKOUT</Text>
                    <Markdown style={markdownStyles}>{planned.workout_text}</Markdown>
                  </View>
                ) : null}

                {selectedDay.rides.map((ride) => (
                  <View key={ride.id} style={styles.divider}>
                    <Text style={[styles.sectionHeader, { color: '#A7F3D0' }]}>DONE</Text>
                    <Text style={styles.detailTitle}>{ride.name}</Text>
                    <View style={styles.statsGrid}>
                      <View style={styles.statBox}><Text style={styles.statLabel}>TIME</Text><Text style={styles.statValue}>{formatTime(ride.moving_time)}</Text></View>
                      <View style={styles.statBox}><Text style={styles.statLabel}>TSS</Text><Text style={styles.statValue}>{ride.tss ?? '–'}</Text></View>
                    </View>
                  </View>
                ))}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, backgroundColor: colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { paddingHorizontal: 20, paddingTop: 10, paddingBottom: 15, borderBottomWidth: 1, borderBottomColor: '#222' },
  title: { color: colors.text, fontSize: 24, fontWeight: 'bold' },
  selectorBtn: { flexDirection: 'row', alignItems: 'center', marginTop: 5 },
  subtitle: { color: colors.accent, fontSize: 11, fontWeight: 'bold', letterSpacing: 1, textTransform: 'uppercase' },
  empty: { color: colors.textFaint, textAlign: 'center', marginTop: 50, paddingHorizontal: 30 },

  daysHeader: { flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#222', paddingHorizontal: GRID_PADDING },
  dayLabelText: { width: TILE_SIZE, textAlign: 'center', color: colors.textFaint, fontSize: 10, fontWeight: 'bold' },

  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, paddingHorizontal: GRID_PADDING, paddingTop: 12 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendText: { color: colors.textMuted, fontSize: 11 },

  monthContainer: { marginTop: 10, paddingHorizontal: GRID_PADDING },
  monthHeader: { color: colors.text, fontSize: 14, fontWeight: 'bold', marginVertical: 10, letterSpacing: 1 },
  monthGrid: { flexDirection: 'row', flexWrap: 'wrap', width: TILE_SIZE * 7 },

  tile: { width: TILE_SIZE, height: TILE_SIZE, justifyContent: 'center', alignItems: 'center', borderWidth: StyleSheet.hairlineWidth, borderColor: '#2a2a2a', backgroundColor: '#161616' },
  tileEmpty: { width: TILE_SIZE, height: TILE_SIZE },
  restTile: { backgroundColor: '#0c0c0c' },
  doneTile: { backgroundColor: '#1d3a2f' },
  todayTile: { borderWidth: 2, borderColor: colors.accent },
  miniDate: { fontSize: 10, fontWeight: 'bold', color: '#666', position: 'absolute', top: 4, right: 5 },
  dot: { width: 8, height: 8, borderRadius: 4 },

  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center' },
  modalContent: { width: '80%', backgroundColor: '#222', borderRadius: 12, padding: 20 },
  modalTitle: { color: colors.text, fontSize: 16, fontWeight: 'bold', marginBottom: 15, textAlign: 'center' },
  modalItem: { paddingVertical: 15, borderBottomWidth: 1, borderBottomColor: '#333', flexDirection: 'row', justifyContent: 'space-between' },
  modalItemSelected: { backgroundColor: '#2a2a2a' },
  modalItemText: { color: '#ddd', fontSize: 14, fontWeight: 'bold' },

  detailOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'flex-end' },
  detailContent: { backgroundColor: colors.card, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 25, maxHeight: '75%' },
  closeBtn: { alignSelf: 'flex-end', padding: 5 },
  detailDate: { color: colors.text, fontSize: 22, fontWeight: 'bold', marginBottom: 20 },
  sectionHeader: { color: colors.accent, fontSize: 12, fontWeight: 'bold', letterSpacing: 1, marginBottom: 10 },
  planTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  detailTitle: { color: colors.text, fontSize: 18, fontWeight: 'bold' },
  detailSub: { color: colors.textMuted, fontSize: 14, marginBottom: 12 },
  detailBody: { color: '#ccc', fontSize: 15, lineHeight: 22 },
  divider: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: 20, paddingTop: 20 },
  statsGrid: { flexDirection: 'row', gap: 10, marginTop: 15 },
  statBox: { backgroundColor: '#222', flex: 1, padding: 15, borderRadius: 8 },
  statLabel: { color: colors.textFaint, fontSize: 10, fontWeight: 'bold' },
  statValue: { color: colors.text, fontSize: 18, fontWeight: 'bold', marginTop: 5 },
});

const markdownStyles = {
  heading1: { color: colors.text, fontSize: 18, fontWeight: 'bold', marginBottom: 8 },
  heading2: { color: colors.accent, fontSize: 15, fontWeight: 'bold', marginTop: 12, marginBottom: 6 },
  body: { color: '#ddd', fontSize: 14, lineHeight: 21 },
  strong: { color: colors.text, fontWeight: 'bold' },
  bullet_list_icon: { color: colors.accent },
};
