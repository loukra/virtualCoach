import React, { useState, useEffect } from 'react';
import {
  View, Text, Modal, TouchableOpacity, StyleSheet, ActivityIndicator, Alert, TextInput,
  KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { apiPost } from '../lib/api';
import { colors } from '../theme';

// Check in as often as you like: a new check-in replaces today's, and the coach reads the
// last seven days to notice when you are running low.
export default function CheckInModal({ visible, onClose, currentValues, onSave }) {
  const [energy, setEnergy] = useState(3);
  const [legs, setLegs] = useState(3);
  const [motivation, setMotivation] = useState(3);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!visible) return;
    setEnergy(currentValues?.feel_score || 3);
    setLegs(currentValues?.soreness_score || 3);
    setMotivation(currentValues?.motivation_score || 3);
    setNotes(currentValues?.notes || '');
  }, [visible, currentValues]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const body = { feel_score: energy, soreness_score: legs, motivation_score: motivation, notes };
      await apiPost('/check-in', body);
      onSave(body);
      onClose();
    } catch (e) {
      Alert.alert('Check-in not saved', e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.overlay}>
        <View style={styles.card}>
          <ScrollView keyboardShouldPersistTaps="handled">
            <Text style={styles.title}>How are you right now?</Text>

            <Rating label="Energy" hint="1 = exhausted · 5 = great" value={energy} onChange={setEnergy} />
            <Rating label="Legs" hint="1 = very sore · 5 = fresh" value={legs} onChange={setLegs} />
            <Rating label="Motivation" hint="1 = no desire to ride · 5 = can't wait" value={motivation} onChange={setMotivation} />

            <Text style={styles.label}>Anything else?</Text>
            <TextInput
              style={styles.notes}
              value={notes}
              onChangeText={setNotes}
              placeholder="Slept badly, stressful week, a cold coming…"
              placeholderTextColor={colors.textFaint}
              multiline
              maxLength={500}
            />

            <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
              {saving ? <ActivityIndicator color="white" /> : <Text style={styles.saveText}>Save</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
              <Text style={{ color: colors.textFaint }}>Close</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function Rating({ label, hint, value, onChange }) {
  return (
    <View style={{ marginBottom: 18 }}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.hint}>{hint}</Text>
      <View style={styles.stars}>
        {[1, 2, 3, 4, 5].map((n) => (
          <TouchableOpacity
            key={n}
            onPress={() => onChange(n)}
            style={[styles.starBtn, value === n && styles.activeStar]}
            accessibilityLabel={`${label} ${n} of 5`}
          >
            <Text style={{ color: value === n ? 'white' : colors.textFaint, fontWeight: 'bold' }}>{n}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center' },
  card: { backgroundColor: colors.card, padding: 25, borderRadius: 15, width: '88%', maxHeight: '85%' },
  title: { color: colors.text, fontSize: 20, fontWeight: 'bold', marginBottom: 20, textAlign: 'center' },
  label: { color: '#ccc', fontSize: 16, fontWeight: 'bold' },
  hint: { color: '#777', fontSize: 12, marginTop: 2, marginBottom: 10 },
  stars: { flexDirection: 'row', justifyContent: 'space-between' },
  starBtn: { backgroundColor: colors.input, width: 40, height: 40, borderRadius: 20, justifyContent: 'center', alignItems: 'center' },
  activeStar: { backgroundColor: colors.accent },
  notes: { backgroundColor: colors.input, color: colors.text, borderRadius: 8, padding: 12, marginTop: 8, minHeight: 60, textAlignVertical: 'top' },
  saveBtn: { backgroundColor: colors.accent, padding: 15, borderRadius: 8, alignItems: 'center', marginTop: 20 },
  saveText: { color: colors.text, fontWeight: 'bold' },
  closeBtn: { alignItems: 'center', marginTop: 15 },
});
