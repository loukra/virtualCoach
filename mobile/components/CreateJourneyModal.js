import React, { useState, useEffect } from 'react';
import { 
  View, Text, Modal, TextInput, TouchableOpacity, StyleSheet, 
  ActivityIndicator, Alert, Platform, KeyboardAvoidingView, 
  TouchableWithoutFeedback, Keyboard 
} from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { apiGet, apiPost } from '../lib/api';
import { localDateString } from '../lib/dates';
import { parseNumber, LIMITS, rangeMessage } from '../lib/numbers';

const DEFAULT_PLAN_WEEKS = 12;
const WEEK_OPTIONS = [8, 12, 16, 20];
const GOALS = [
  { key: 'build', label: 'Build fitness', hint: 'Raise your FTP over the coming weeks, with FTP tests to see it work.' },
  { key: 'race', label: 'Prepare for a race', hint: 'Peak and taper for an event on a fixed date.' },
];

function weeksFromNow(weeks) {
  const d = new Date();
  d.setDate(d.getDate() + weeks * 7);
  return d;
}

export default function CreateJourneyModal({ visible, onClose, onJourneyCreated }) {
  const [goalType, setGoalType] = useState('build');
  const [weeks, setWeeks] = useState(16);
  const [name, setName] = useState('');
  const [ftp, setFtp] = useState('200');
  const [weight, setWeight] = useState('75');
  
  const [raceDate, setRaceDate] = useState(() => weeksFromNow(DEFAULT_PLAN_WEEKS));
  const [startDate, setStartDate] = useState(new Date());
  
  // Controls which picker is open: 'race', 'start', or null
  const [activePicker, setActivePicker] = useState(null); 
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (visible) fetchStats();
  }, [visible]);

  const fetchStats = async () => {
    try {
        const me = await apiGet('/me');
        setFtp(me.ftp ? me.ftp.toString() : '200');
        setWeight(me.weight_kg ? me.weight_kg.toString() : '75');
    } catch (e) {
        console.log('Could not load profile:', e.message);
    }
  };

  const handleCreate = async () => {
    const isRace = goalType === 'race';
    const title = name.trim() || (isRace ? '' : `${weeks} weeks of fitness`);
    if (!title) return Alert.alert("Missing info", "Please enter the name of your race.");
    const days = Math.round((raceDate - startDate) / 86400000);
    if (isRace && days < 6) return Alert.alert("Check the dates", "The race date must be at least one week after the start date.");
    const ftpValue = parseNumber(ftp, LIMITS.ftp);
    if (ftpValue === null) return Alert.alert("Check the value", rangeMessage('ftp'));
    const weightValue = parseNumber(weight, LIMITS.weight);
    if (weightValue === null) return Alert.alert("Check the value", rangeMessage('weight'));

    setLoading(true);
    try {
        await apiPost('/create-journey', {
            journey_name: title,
            goal_type: goalType,
            ...(isRace ? { race_date: localDateString(raceDate) } : { weeks }),
            start_date: localDateString(startDate),
            current_ftp: ftpValue,
            current_weight: weightValue
        });
        Alert.alert("Plan on the way", "Your coach is building the plan. This takes a minute or two.");
        onJourneyCreated();
        onClose();
    } catch (e) {
        Alert.alert("Error", e.message);
    } finally {
        setLoading(false);
    }
  };

  const onDateChange = (event, selectedDate) => {
    if (Platform.OS === 'android') setActivePicker(null);
    
    if (selectedDate) {
        if (activePicker === 'race') setRaceDate(selectedDate);
        if (activePicker === 'start') setStartDate(selectedDate);
    }
  };

  // --- HELPER COMPONENT FOR DATE INPUTS ---
  const DateInput = ({ label, dateValue, pickerType }) => (
    <View style={{ marginBottom: 15 }}>
        <Text style={styles.label}>{label}</Text>
        {Platform.OS === 'ios' ? (
            <View>
                <TouchableOpacity 
                    onPress={() => setActivePicker(activePicker === pickerType ? null : pickerType)} 
                    style={[styles.dateButton, activePicker === pickerType && styles.activeInput]}
                >
                    <Text style={{color:'white', fontWeight:'bold'}}>{dateValue.toDateString()}</Text>
                </TouchableOpacity>
                
                {activePicker === pickerType && (
                    <View style={styles.iosPickerContainer}>
                        <DateTimePicker
                            value={dateValue}
                            mode="date"
                            display="spinner"
                            onChange={onDateChange}
                            themeVariant="dark"
                            textColor="white"
                        />
                    </View>
                )}
            </View>
        ) : (
            <>
                <TouchableOpacity onPress={() => setActivePicker(pickerType)} style={styles.dateButton}>
                    <Text style={{color:'white', fontWeight:'bold'}}>{dateValue.toDateString()}</Text>
                </TouchableOpacity>
                {activePicker === pickerType && (
                    <DateTimePicker
                        value={dateValue}
                        mode="date"
                        display="default"
                        onChange={onDateChange}
                    />
                )}
            </>
        )}
    </View>
  );

  return (
    <Modal visible={visible} animationType="slide" transparent={true} onRequestClose={onClose}>
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <View style={styles.overlay}>
          <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.keyboardView}>
            <View style={styles.card}>
              
              <View style={styles.headerRow}>
                <Text style={styles.title}>New Journey</Text>
                <TouchableOpacity onPress={onClose}><Text style={{color:'#666', fontSize: 20}}>✕</Text></TouchableOpacity>
              </View>

              <View style={styles.segment}>
                {GOALS.map((g) => (
                  <TouchableOpacity
                    key={g.key}
                    style={[styles.segmentBtn, goalType === g.key && styles.segmentActive]}
                    onPress={() => setGoalType(g.key)}
                  >
                    <Text style={[styles.segmentText, goalType === g.key && { color: 'white' }]}>{g.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.goalHint}>{GOALS.find((g) => g.key === goalType).hint}</Text>

              <Text style={styles.label}>{goalType === 'race' ? 'Race' : 'Name (optional)'}</Text>
              <TextInput 
                style={styles.input} 
                placeholder={goalType === 'race' ? 'e.g. Gran Fondo 2027' : `${weeks} weeks of fitness`}
                placeholderTextColor="#666"
                value={name} onChangeText={setName} 
                returnKeyType="done"
              />

              <DateInput 
                 label="Start" 
                 dateValue={startDate} 
                 pickerType="start" 
              />

              {goalType === 'race' ? (
                <DateInput 
                   label="Race date" 
                   dateValue={raceDate} 
                   pickerType="race" 
                />
              ) : (
                <View style={{ marginBottom: 15 }}>
                  <Text style={styles.label}>Weeks</Text>
                  <View style={styles.weekChips}>
                    {WEEK_OPTIONS.map((w) => (
                      <TouchableOpacity key={w} style={[styles.weekChip, weeks === w && styles.segmentActive]} onPress={() => setWeeks(w)}>
                        <Text style={[styles.segmentText, weeks === w && { color: 'white' }]}>{w}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  {startDate.getDay() !== 1 && (
                    <Text style={styles.goalHint}>
                      Week 1 runs from {startDate.toLocaleDateString('en-GB', { weekday: 'long' })} to Sunday;
                      every week after it runs Monday to Sunday.
                    </Text>
                  )}
                </View>
              )}

              <View style={{flexDirection:'row', gap: 10, marginTop: 5}}>
                <View style={{flex:1}}>
                    <Text style={styles.label}>FTP (W)</Text>
                    <TextInput style={styles.input} keyboardType="number-pad" value={ftp} onChangeText={setFtp} returnKeyType="done" />
                </View>
                <View style={{flex:1}}>
                    <Text style={styles.label}>Weight (kg)</Text>
                    <TextInput style={styles.input} keyboardType="decimal-pad" value={weight} onChangeText={setWeight} returnKeyType="done" />
                </View>
              </View>

              {loading ? (
                <ActivityIndicator size="large" color="#ff4d4d" style={{marginTop: 30}} />
              ) : (
                <View style={styles.buttons}>
                    <TouchableOpacity onPress={onClose} style={styles.cancelBtn}><Text style={{color:'#888'}}>Cancel</Text></TouchableOpacity>
                    <TouchableOpacity onPress={handleCreate} style={styles.createBtn}><Text style={{color:'white', fontWeight:'bold'}}>Generate Plan</Text></TouchableOpacity>
                </View>
              )}
            </View>
          </KeyboardAvoidingView>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', padding: 20 },
  keyboardView: { width: '100%', alignItems: 'center' },
  card: { backgroundColor: '#1a1a1a', padding: 20, borderRadius: 16, width: '100%', maxWidth: 400 },
  headerRow: { flexDirection:'row', justifyContent:'space-between', alignItems:'center', marginBottom: 15 },
  title: { color: 'white', fontSize: 22, fontWeight: 'bold' },
  label: { color: '#888', marginBottom: 6, marginTop: 10, fontSize: 12, fontWeight:'bold' },
  input: { backgroundColor: '#333', color: 'white', padding: 14, borderRadius: 8, fontSize: 16 },
  dateButton: { backgroundColor: '#333', padding: 14, borderRadius: 8, alignItems:'center' },
  activeInput: { borderWidth: 1, borderColor: '#ff4d4d' }, // Highlight active picker
  segment: { flexDirection: 'row', backgroundColor: '#333', borderRadius: 10, padding: 3 },
  segmentBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  segmentActive: { backgroundColor: '#ff4d4d' },
  segmentText: { color: '#aaa', fontWeight: 'bold' },
  goalHint: { color: '#888', fontSize: 12, marginTop: 8, lineHeight: 17 },
  weekChips: { flexDirection: 'row', gap: 8 },
  weekChip: { flex: 1, backgroundColor: '#333', paddingVertical: 12, borderRadius: 8, alignItems: 'center' },
  iosPickerContainer: { backgroundColor: '#222', borderRadius: 8, marginTop: 5, overflow: 'hidden' },
  buttons: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 25, alignItems:'center' },
  cancelBtn: { padding: 15 },
  createBtn: { backgroundColor: '#ff4d4d', paddingVertical: 15, paddingHorizontal: 20, borderRadius: 8, flex: 1, alignItems: 'center', marginLeft: 15 }
});