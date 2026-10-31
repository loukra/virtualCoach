import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { apiDelete } from '../lib/api';
import { localDateString } from '../lib/dates';
import { EVENT_KINDS, eventSubtitle, planOutcomeText } from '../lib/events';
import { colors } from '../theme';

// Races, group rides and time off, each removable; a race journey's own race is shown but fixed.
// onChanged(note) gets a short line on what happened to the plans.
export default function EventList({ events, onChanged, empty }) {
  const today = localDateString(new Date());

  const remove = (event) => {
    Alert.alert(`Remove "${event.name}"?`, 'Plans covering it adapt from Monday on.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          try {
            const result = await apiDelete(`/events/${event.id}`);
            onChanged?.(planOutcomeText(`"${event.name}" removed`, result.journeys));
          } catch (e) {
            Alert.alert('Could not remove', e.message);
          }
        },
      },
    ]);
  };

  if (!events.length) return empty ? <Text style={styles.empty}>{empty}</Text> : null;
  return events.map((event) => {
    const kind = EVENT_KINDS[event.kind];
    const past = event.end_date < today;
    const main = event.kind === 'race' && event.priority === 'A';
    return (
      <View key={event.id} style={[styles.row, past && styles.past]}>
        <View style={[styles.icon, { backgroundColor: `${kind.color}33` }]}>
          <Ionicons name={main || event.kind !== 'race' ? kind.icon : 'flag-outline'} size={16} color={kind.color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.name}>{event.name}{event.goal ? '  ·  goal' : ''}</Text>
          <Text style={styles.sub}>{eventSubtitle(event)}</Text>
        </View>
        {!event.goal && !past && (
          <TouchableOpacity onPress={() => remove(event)} style={styles.remove} accessibilityLabel={`Remove ${event.name}`}>
            <Ionicons name="trash-outline" size={18} color={colors.textFaint} />
          </TouchableOpacity>
        )}
      </View>
    );
  });
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  past: { opacity: 0.45 },
  icon: { width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center' },
  name: { color: colors.text, fontSize: 15, fontWeight: '600' },
  sub: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  remove: { padding: 6 },
  empty: { color: colors.textMuted, fontSize: 14, lineHeight: 20 },
});
