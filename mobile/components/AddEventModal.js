import React, { useEffect, useState } from 'react';
import {
  View, Text, Modal, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator, Alert, Platform,
  KeyboardAvoidingView, ScrollView,
} from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { Ionicons } from '@expo/vector-icons';
import { apiPost } from '../lib/api';
import { localDateString, parseLocalDate } from '../lib/dates';
import { EVENT_KINDS, PRIORITIES, planOutcomeText } from '../lib/events';
import { colors } from '../theme';

const DURATIONS = [null, 60, 120, 180, 240, 300, 360]; // null: not known yet

const PLACEHOLDERS = {
  race: 'e.g. Spring Classic',
  ride: 'e.g. Club RTF',
  off: 'e.g. Ski trip, business trip, ill',
};

// Adds a race, a group ride or time off. The plans covering the date adapt (backend routers/events.py).
export default function AddEventModal({ visible, kind: initialKind = 'race', defaultDate, onClose, onSaved }) {
  const [kind, setKind] = useState(initialKind);
  const [name, setName] = useState('');
  const [priority, setPriority] = useState('B');
  const [duration, setDuration] = useState(null);
  const [startDate, setStartDate] = useState(new Date());
  const [endDate, setEndDate] = useState(new Date());
  const [picker, setPicker] = useState(null); // 'start' | 'end' | null
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!visible) return;
    const start = defaultDate && defaultDate > new Date() ? defaultDate : new Date();
    setKind(initialKind);
    setName('');
    setPriority('B');
    setDuration(null);
    setStartDate(start);
    setEndDate(start);
    setPicker(null);
  }, [visible, initialKind, defaultDate]);

  const onPick = (_, value) => {
    if (Platform.OS === 'android') setPicker(null);
    if (!value) return;
    if (picker === 'start') {
      setStartDate(value);
      if (endDate < value) setEndDate(value);
    } else {
      setEndDate(value);
    }
  };

  const handleSave = async () => {
    const title = name.trim() || (kind === 'off' ? 'Time off' : '');
    if (!title) return Alert.alert('Missing name', `Please name the ${kind === 'race' ? 'race' : 'ride'}.`);
    setSaving(true);
    try {
      const result = await apiPost('/events', {
        kind,
        name: title,
        start_date: localDateString(startDate),
        ...(kind === 'off' ? { end_date: localDateString(endDate) } : { duration_min: duration }),
        ...(kind === 'race' ? { priority } : {}),
      });
      onSaved?.(planOutcomeText(`${EVENT_KINDS[kind].label} added`, result.journeys));
      onClose();
    } catch (e) {
      Alert.alert('Not saved', e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.overlay}>
        <View style={styles.card}>
          <ScrollView keyboardShouldPersistTaps="handled">
            <View style={styles.headerRow}>
              <Text style={styles.title}>Add to your calendar</Text>
              <TouchableOpacity onPress={onClose} accessibilityLabel="Close">
                <Ionicons name="close" size={24} color={colors.textFaint} />
              </TouchableOpacity>
            </View>

            <View style={styles.segment}>
              {Object.entries(EVENT_KINDS).map(([key, k]) => (
                <TouchableOpacity
                  key={key}
                  style={[styles.segmentBtn, kind === key && styles.segmentActive]}
                  onPress={() => setKind(key)}
                >
                  <Ionicons name={k.icon} size={14} color={kind === key ? colors.text : '#aaa'} />
                  <Text style={[styles.segmentText, kind === key && { color: colors.text }]}>{k.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Name</Text>
            <TextInput
              style={styles.input}
              value={name}
              onChangeText={setName}
              placeholder={PLACEHOLDERS[kind]}
              placeholderTextColor={colors.textFaint}
              maxLength={100}
              returnKeyType="done"
            />

            <DateField
              label={kind === 'off' ? 'First day' : 'Date'}
              value={startDate}
              open={picker === 'start'}
              onToggle={() => setPicker(picker === 'start' ? null : 'start')}
              onChange={onPick}
            />
            {kind === 'off' && (
              <DateField
                label="Last day"
                value={endDate}
                minimumDate={startDate}
                open={picker === 'end'}
                onToggle={() => setPicker(picker === 'end' ? null : 'end')}
                onChange={onPick}
              />
            )}

            {kind === 'race' && (
              <>
                <Text style={styles.label}>Priority</Text>
                <View style={styles.segment}>
                  {Object.entries(PRIORITIES).map(([key, p]) => (
                    <TouchableOpacity
                      key={key}
                      style={[styles.segmentBtn, priority === key && styles.segmentActive]}
                      onPress={() => setPriority(key)}
                    >
                      <Text style={[styles.segmentText, priority === key && { color: colors.text }]}>{p.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.hint}>{PRIORITIES[priority].hint}</Text>
              </>
            )}

            {kind !== 'off' ? (
              <>
                <Text style={styles.label}>Expected duration</Text>
                <View style={styles.chips}>
                  {DURATIONS.map((d) => (
                    <TouchableOpacity
                      key={String(d)}
                      style={[styles.chip, duration === d && styles.segmentActive]}
                      onPress={() => setDuration(d)}
                    >
                      <Text style={[styles.segmentText, duration === d && { color: colors.text }]}>
                        {d ? `${d / 60} h` : 'Not sure'}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </>
            ) : (
              <Text style={styles.hint}>No training on these days. The weeks around them adapt to the break.</Text>
            )}

            <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
              {saving ? <ActivityIndicator color={colors.text} /> : <Text style={styles.saveText}>Add</Text>}
            </TouchableOpacity>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function DateField({ label, value, minimumDate, open, onToggle, onChange }) {
  const text = value.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TouchableOpacity onPress={onToggle} style={[styles.input, open && styles.activeInput]}>
        <Text style={styles.dateText}>{text}</Text>
      </TouchableOpacity>
      {open && (
        <View style={Platform.OS === 'ios' ? styles.pickerBox : null}>
          <DateTimePicker
            value={value}
            mode="date"
            display={Platform.OS === 'ios' ? 'spinner' : 'default'}
            minimumDate={minimumDate || parseLocalDate(localDateString(new Date()))}
            onChange={onChange}
            themeVariant="dark"
            textColor="white"
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center' },
  card: { backgroundColor: colors.card, padding: 20, borderRadius: 16, width: '92%', maxHeight: '88%' },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 },
  title: { color: colors.text, fontSize: 20, fontWeight: 'bold' },
  label: { color: colors.textMuted, marginBottom: 6, marginTop: 14, fontSize: 12, fontWeight: 'bold' },
  hint: { color: colors.textMuted, fontSize: 12, marginTop: 8, lineHeight: 17 },
  input: { backgroundColor: colors.input, color: colors.text, padding: 14, borderRadius: 8, fontSize: 16 },
  activeInput: { borderWidth: 1, borderColor: colors.accent },
  dateText: { color: colors.text, fontWeight: 'bold', textAlign: 'center' },
  pickerBox: { backgroundColor: '#222', borderRadius: 8, marginTop: 5, overflow: 'hidden' },
  segment: { flexDirection: 'row', backgroundColor: colors.input, borderRadius: 10, padding: 3 },
  segmentBtn: { flex: 1, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 5, paddingVertical: 10, borderRadius: 8 },
  segmentActive: { backgroundColor: colors.accent },
  segmentText: { color: '#aaa', fontWeight: 'bold', fontSize: 13 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { backgroundColor: colors.input, paddingVertical: 9, paddingHorizontal: 13, borderRadius: 16 },
  saveBtn: { backgroundColor: colors.accent, padding: 15, borderRadius: 8, alignItems: 'center', marginTop: 24 },
  saveText: { color: colors.text, fontWeight: 'bold' },
});
