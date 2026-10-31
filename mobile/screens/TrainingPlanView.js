import React, { useState, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, TouchableOpacity, Dimensions, Modal, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import Markdown from 'react-native-markdown-display';
import { apiGet } from '../lib/api';
import { localDateString, parseLocalDate, weekdayName } from '../lib/dates';
import { EVENT_KINDS, PRIORITIES, eventSubtitle } from '../lib/events';
import { colors, TYPE_COLORS } from '../theme';

const GRID_PADDING = 16;
// Whole pixels, so seven tiles always fit in one row.
const TILE_SIZE = Math.floor((Dimensions.get('window').width - GRID_PADDING * 2) / 7);
const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

const LEGEND = ['Recovery', 'Endurance', 'Tempo', 'Sweet Spot', 'Threshold', 'VO2 Max', 'FTP Test'];

function formatTime(seconds) {
  if (!seconds) return '0m';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function addDays(iso, n) {
  const d = parseLocalDate(iso);
  d.setDate(d.getDate() + n);
  return localDateString(d);
}

// Every day from the first journey to the last date anything is planned (journeys follow each
// other, so one timeline holds them all), grouped into months with leading blanks so Monday is
// column one. Each day carries its planned session, rides, events and the journey it belongs to.
function buildMonths({ first, last, journeys, plan, events, activities }) {
  const planByDay = Object.fromEntries(plan.map((p) => [p.date, p]));
  const ridesByDay = {};
  activities.forEach((act) => {
    const day = act.start_date_local.slice(0, 10);
    (ridesByDay[day] = ridesByDay[day] || []).push(act);
  });

  const months = [];
  for (let date = first; date <= last; date = addDays(date, 1)) {
    const key = date.slice(0, 7);
    let month = months[months.length - 1];
    if (!month || month.key !== key) {
      const day = parseLocalDate(date);
      const blanks = (day.getDay() + 6) % 7;
      month = {
        key,
        title: day.toLocaleString('en-GB', { month: 'long', year: 'numeric' }).toUpperCase(),
        starts: [],
        days: Array.from({ length: blanks }, (_, i) => ({ key: `pad-${key}-${i}`, empty: true })),
      };
      months.push(month);
    }
    const journey = journeys.find((j) => j.start_date <= date && date <= j.race_date);
    if (journey && journey.start_date === date) month.starts.push(journey);
    month.days.push({
      key: date,
      date,
      plan: planByDay[date] || null,
      rides: ridesByDay[date] || [],
      events: events.filter((e) => e.start_date <= date && date <= e.end_date),
      journey,
    });
  }
  return months;
}

export default function TrainingPlanView() {
  const [loading, setLoading] = useState(true);
  const [months, setMonths] = useState([]);
  const [selectedDay, setSelectedDay] = useState(null);
  const scrollRef = useRef(null);
  const scrolledToToday = useRef(false);

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [])
  );

  const fetchData = async () => {
    try {
      setLoading(true);
      scrolledToToday.current = false;
      const calendar = await apiGet('/calendar');
      setMonths(calendar.journeys.length || calendar.events.length ? buildMonths(calendar) : []);
    } catch (e) {
      console.log('Could not load the calendar:', e.message);
    } finally {
      setLoading(false);
    }
  };

  const today = localDateString(new Date());

  const renderDay = (day) => {
    if (day.empty) return <View key={day.key} style={styles.tileEmpty} />;

    const type = day.plan?.planned_workout_type;
    const state = day.plan?.state; // rest | done | open | missed (see backend session_state)
    const done = state === 'done';
    const isToday = day.date === today;
    const race = day.events.find((e) => e.kind === 'race') || (day.journey?.goal_type === 'race'
      && day.journey.race_date === day.date ? { kind: 'race', priority: 'A' } : null);
    const ride = day.events.find((e) => e.kind === 'ride');
    const off = day.events.some((e) => e.kind === 'off');
    const outside = !day.journey;
    return (
      <TouchableOpacity
        key={day.key}
        style={[styles.tile, outside && styles.outsideTile, (type === 'Rest' || off) && styles.restTile,
          done && styles.doneTile, isToday && styles.todayTile]}
        onPress={() => setSelectedDay(day)}
        accessibilityLabel={`${day.date}: ${type || 'nothing planned'}${state ? `, ${state}` : ''}`}
      >
        <Text style={[styles.miniDate, isToday && { color: colors.accent }]}>{Number(day.date.slice(8))}</Text>
        {race ? (
          <Ionicons name={race.priority === 'A' ? 'flag' : 'flag-outline'} size={15} color={done ? '#A7F3D0' : EVENT_KINDS.race.color} />
        ) : done ? (
          <Ionicons name="checkmark" size={16} color="#A7F3D0" />
        ) : off ? (
          <Ionicons name="airplane" size={12} color={EVENT_KINDS.off.color} />
        ) : ride ? (
          <Ionicons name="people" size={14} color={EVENT_KINDS.ride.color} />
        ) : type && type !== 'Rest' ? (
          <View style={[styles.dot, { backgroundColor: TYPE_COLORS[type] || colors.accent }, state === 'missed' && styles.missedDot]} />
        ) : null}
        {day.rides.length > 0 && !done && <View style={styles.rideMark} />}
      </TouchableOpacity>
    );
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.accent} /></View>;

  const planned = selectedDay?.plan;
  const pending = selectedDay?.journey && !planned; // a journey planned on its start day

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Calendar</Text>
        <Text style={styles.subtitle}>All journeys, races and time off</Text>
      </View>

      <View style={styles.daysHeader}>
        {DAY_LABELS.map((d, i) => <Text key={i} style={styles.dayLabelText}>{d}</Text>)}
      </View>

      <ScrollView ref={scrollRef} contentContainerStyle={{ paddingBottom: 40 }}>
        {months.length > 0 && (
          <View style={styles.legend}>
            {LEGEND.map((t) => (
              <View key={t} style={styles.legendItem}>
                <View style={[styles.dot, { backgroundColor: TYPE_COLORS[t] }]} />
                <Text style={styles.legendText}>{t}</Text>
              </View>
            ))}
            {Object.entries(EVENT_KINDS).map(([kind, k]) => (
              <View key={kind} style={styles.legendItem}>
                <Ionicons name={k.icon} size={11} color={k.color} />
                <Text style={styles.legendText}>{k.label}</Text>
              </View>
            ))}
          </View>
        )}
        {months.map((month) => (
          <View
            key={month.key}
            style={styles.monthContainer}
            onLayout={(e) => {
              // Open on the current month; earlier journeys stay a scroll away.
              if (month.key === today.slice(0, 7) && month !== months[0] && !scrolledToToday.current) {
                scrolledToToday.current = true;
                scrollRef.current?.scrollTo({ y: e.nativeEvent.layout.y, animated: false });
              }
            }}
          >
            <Text style={styles.monthHeader}>{month.title}</Text>
            {month.starts.map((j) => (
              <Text key={j.id} style={styles.journeyStart}>
                ▸ {j.name} starts {parseLocalDate(j.start_date).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}
                {j.status === 'scheduled' ? ' · plan built that day' : ''}
              </Text>
            ))}
            <View style={styles.monthGrid}>{month.days.map(renderDay)}</View>
          </View>
        ))}
        {months.length === 0 && (
          <Text style={styles.empty}>Nothing planned yet. Tap + on the Home tab to add a journey or a race.</Text>
        )}
      </ScrollView>

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

                {selectedDay.journey && <Text style={styles.journeyName}>{selectedDay.journey.name}</Text>}

                {selectedDay.events.map((e) => (
                  <View key={e.id} style={styles.eventRow}>
                    <Ionicons name={EVENT_KINDS[e.kind].icon} size={16} color={EVENT_KINDS[e.kind].color} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.detailTitle}>{e.name}</Text>
                      <Text style={styles.detailSub}>{e.kind === 'race' ? PRIORITIES[e.priority].label : EVENT_KINDS[e.kind].label} · {eventSubtitle(e)}</Text>
                    </View>
                  </View>
                ))}

                {planned ? (
                  <>
                    <Text style={styles.sectionHeader}>PLAN{planned.phase ? ` · ${planned.phase.toUpperCase()}` : ''}</Text>
                    <View style={styles.planTitleRow}>
                      <View style={[styles.dot, { backgroundColor: TYPE_COLORS[planned.planned_workout_type] }]} />
                      <Text style={styles.detailTitle}>{planned.planned_workout_type}</Text>
                    </View>
                    {planned.planned_workout_type !== 'Rest' && (
                      <Text style={styles.detailSub}>{planned.planned_duration_min} min · {planned.planned_tss} TSS</Text>
                    )}
                    {planned.description ? <Text style={styles.detailBody}>{planned.description}</Text> : null}
                    <SessionState plan={planned} />
                  </>
                ) : (
                  <Text style={styles.detailBody}>
                    {pending ? 'This journey gets its plan on its start day.' : 'No journey covers this day.'}
                  </Text>
                )}

                {planned?.workout_text ? (
                  <View style={styles.divider}>
                    <Text style={styles.sectionHeader}>WORKOUT</Text>
                    <Markdown style={markdownStyles}>{planned.workout_text}</Markdown>
                  </View>
                ) : null}

                {selectedDay.rides.map((ride) => (
                  <View key={ride.id} style={styles.divider}>
                    <Text style={[styles.sectionHeader, { color: '#A7F3D0' }]}>RIDDEN</Text>
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

function SessionState({ plan }) {
  if (plan.state === 'done') {
    const moved = plan.done_on && plan.done_on !== plan.date;
    return (
      <Text style={[styles.stateNote, { color: '#A7F3D0' }]}>
        ✓ Done{moved ? ` on ${weekdayName(plan.done_on)}` : ''}
      </Text>
    );
  }
  if (plan.state === 'missed') return <Text style={styles.stateNote}>Not ridden that week.</Text>;
  if (plan.state === 'off') return <Text style={styles.stateNote}>Time off: this session drops out.</Text>;
  return null;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, backgroundColor: colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { paddingHorizontal: 20, paddingTop: 10, paddingBottom: 15, borderBottomWidth: 1, borderBottomColor: '#222' },
  title: { color: colors.text, fontSize: 24, fontWeight: 'bold' },
  subtitle: { color: colors.textMuted, fontSize: 12, marginTop: 4 },
  journeyStart: { color: colors.accent, fontSize: 12, fontWeight: 'bold', marginBottom: 8 },
  journeyName: { color: colors.textMuted, fontSize: 12, fontWeight: 'bold', letterSpacing: 1, textTransform: 'uppercase', marginTop: -12, marginBottom: 16 },
  eventRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', marginBottom: 12 },
  outsideTile: { backgroundColor: '#0e0e0e', borderColor: '#1c1c1c' },
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
  missedDot: { opacity: 0.3 },
  rideMark: { position: 'absolute', bottom: 4, width: 4, height: 4, borderRadius: 2, backgroundColor: '#A7F3D0' },
  stateNote: { color: colors.textMuted, fontSize: 13, marginTop: 10 },

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
