import React, { useState, useEffect } from 'react';
import { View, Text, Modal, TouchableOpacity, StyleSheet, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { apiPost } from '../lib/api';

export default function CheckInModal({ visible, onClose, currentValues, onSave }) {
  const [mood, setMood] = useState(3);
  const [legs, setLegs] = useState(3);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (visible && currentValues) {
        setMood(currentValues.feel_score || 3);
        setLegs(currentValues.soreness_score || 3);
    }
  }, [visible, currentValues]);

  const handleSave = async () => {
    setSaving(true);
    try {
        await apiPost('/check-in', { feel_score: mood, soreness_score: legs });
        onSave({ feel_score: mood, soreness_score: legs }); // Update parent state
        onClose();
    } catch (e) {
        Alert.alert("Check-in not saved", e.message);
    } finally {
        setSaving(false);
    }
  };

  const RatingRow = ({ label, hint, value, setValue }) => (
    <View style={{marginBottom: 20}}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.hint}>{hint}</Text>
        <View style={styles.stars}>
            {[1, 2, 3, 4, 5].map((n) => (
                <TouchableOpacity key={n} onPress={() => setValue(n)} style={[styles.starBtn, value === n && styles.activeStar]}>
                    <Text style={{color: value === n ? 'white' : '#666', fontWeight:'bold'}}>{n}</Text>
                </TouchableOpacity>
            ))}
        </View>
    </View>
  );

  return (
    <Modal visible={visible} transparent={true} animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.card}>
            <Text style={styles.title}>How do you feel today?</Text>
            
            <RatingRow label="Energy" hint="1 = exhausted · 5 = great" value={mood} setValue={setMood} />
            <RatingRow label="Legs" hint="1 = very sore · 5 = fresh" value={legs} setValue={setLegs} />

            <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
                {saving ? <ActivityIndicator color="white"/> : <Text style={styles.saveText}>Save</Text>}
            </TouchableOpacity>
            
            <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
                <Text style={{color:'#666'}}>Close</Text>
            </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center' },
  card: { backgroundColor: '#1a1a1a', padding: 25, borderRadius: 15, width: '85%' },
  title: { color: 'white', fontSize: 20, fontWeight: 'bold', marginBottom: 20, textAlign: 'center' },
  label: { color: '#ccc', fontSize: 16, fontWeight: 'bold' },
  hint: { color: '#777', fontSize: 12, marginTop: 2, marginBottom: 10 },
  stars: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  starBtn: { backgroundColor: '#333', width: 40, height: 40, borderRadius: 20, justifyContent: 'center', alignItems: 'center' },
  activeStar: { backgroundColor: '#ff4d4d' },
  saveBtn: { backgroundColor: '#ff4d4d', padding: 15, borderRadius: 8, alignItems: 'center', marginTop: 10 },
  saveText: { color: 'white', fontWeight: 'bold' },
  closeBtn: { alignItems: 'center', marginTop: 15 }
});