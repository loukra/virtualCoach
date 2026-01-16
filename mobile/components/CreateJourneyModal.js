import React, { useState, useEffect } from 'react';
import { 
  View, 
  Text, 
  Modal, 
  TextInput, 
  TouchableOpacity, 
  StyleSheet, 
  ActivityIndicator, 
  Alert, 
  Platform, 
  KeyboardAvoidingView, 
  TouchableWithoutFeedback, 
  Keyboard 
} from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { supabase } from '../lib/supabase';
import { API_URL } from '../constants';

export default function CreateJourneyModal({ visible, onClose, onJourneyCreated }) {
  const [name, setName] = useState('');
  const [ftp, setFtp] = useState('200');
  const [weight, setWeight] = useState('75');
  const [date, setDate] = useState(new Date());
  const [showPicker, setShowPicker] = useState(false);
  const [loading, setLoading] = useState(false);

  // Pre-fill FTP/Weight
  useEffect(() => {
    if (visible) fetchStats();
  }, [visible]);

  const fetchStats = async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    const { data } = await supabase.from('profiles').select('ftp, weight_kg').eq('id', session.user.id).single();
    if (data) {
        setFtp(data.ftp ? data.ftp.toString() : '200');
        setWeight(data.weight_kg ? data.weight_kg.toString() : '75');
    }
  };

  const handleCreate = async () => {
    if (!name) return Alert.alert("Missing Info", "Please enter a name for your goal.");
    
    setLoading(true);
    const { data: { session } } = await supabase.auth.getSession();
    
    try {
        const raceDateStr = date.toISOString().split('T')[0];

        const response = await fetch(`${API_URL}/create-journey`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: session.user.id,
                journey_name: name,
                race_date: raceDateStr,
                current_ftp: parseInt(ftp),
                current_weight: parseFloat(weight)
            })
        });

        const result = await response.json();

        if (response.ok) {
            Alert.alert("Success", "AI is building your plan in the background.");
            onJourneyCreated(); 
            onClose();
        } else {
            Alert.alert("Error", result.detail || "Failed to create journey");
        }

    } catch (e) {
        Alert.alert("Error", "Network error: " + e.message);
    } finally {
        setLoading(false);
    }
  };

  // --- Date Picker Handler ---
  const onDateChange = (event, selectedDate) => {
    if (Platform.OS === 'android') {
        setShowPicker(false); // Close immediately on Android
    }
    if (selectedDate) {
        setDate(selectedDate);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={true} onRequestClose={onClose}>
      {/* 1. KEYBOARD DISMISSAL WRAPPER */}
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <View style={styles.overlay}>
          
          {/* 2. KEYBOARD AVOIDING VIEW (Pushes content up) */}
          <KeyboardAvoidingView 
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardView}
          >
            <View style={styles.card}>
              <View style={styles.headerRow}>
                <Text style={styles.title}>New Journey 🎯</Text>
                <TouchableOpacity onPress={onClose} style={styles.closeIcon}>
                    <Text style={{color:'#666', fontSize: 20}}>✕</Text>
                </TouchableOpacity>
              </View>

              <Text style={styles.label}>Goal Name</Text>
              <TextInput 
                style={styles.input} 
                placeholder="e.g. Gran Fondo 2026" 
                placeholderTextColor="#666"
                value={name} onChangeText={setName} 
                returnKeyType="done"
              />

              <Text style={styles.label}>Race Date</Text>
              
              {/* --- DATE PICKER LOGIC --- */}
              {Platform.OS === 'ios' ? (
                  // iOS: Show Button -> On Click, Show Spinner in-place or toggle
                  <View>
                      <TouchableOpacity onPress={() => setShowPicker(!showPicker)} style={styles.dateButton}>
                        <Text style={{color:'white', fontWeight:'bold'}}>{date.toDateString()}</Text>
                      </TouchableOpacity>
                      
                      {showPicker && (
                        <View style={styles.iosPickerContainer}>
                            <DateTimePicker
                                value={date}
                                mode="date"
                                display="spinner" // 👈 FORCES WHEEL STYLE
                                minimumDate={new Date()}
                                onChange={onDateChange}
                                themeVariant="dark"
                                textColor="white"
                            />
                        </View>
                      )}
                  </View>
              ) : (
                  // ANDROID: Standard Button -> Popup
                  <>
                    <TouchableOpacity onPress={() => setShowPicker(true)} style={styles.dateButton}>
                        <Text style={{color:'white', fontWeight:'bold'}}>{date.toDateString()}</Text>
                    </TouchableOpacity>
                    {showPicker && (
                        <DateTimePicker
                            value={date}
                            mode="date"
                            display="default"
                            minimumDate={new Date()}
                            onChange={onDateChange}
                        />
                    )}
                  </>
              )}

              <View style={{flexDirection:'row', gap: 10, marginTop: 10}}>
                <View style={{flex:1}}>
                    <Text style={styles.label}>FTP (W)</Text>
                    <TextInput 
                        style={styles.input} 
                        keyboardType="numeric" 
                        value={ftp} 
                        onChangeText={setFtp} 
                        returnKeyType="done" // Adds "Done" on some keyboards
                    />
                </View>
                <View style={{flex:1}}>
                    <Text style={styles.label}>Weight (kg)</Text>
                    <TextInput 
                        style={styles.input} 
                        keyboardType="numeric" 
                        value={weight} 
                        onChangeText={setWeight} 
                        returnKeyType="done"
                    />
                </View>
              </View>

              {loading ? (
                <ActivityIndicator size="large" color="#ff4d4d" style={{marginTop: 30}} />
              ) : (
                <View style={styles.buttons}>
                    <TouchableOpacity onPress={onClose} style={styles.cancelBtn}>
                        <Text style={{color:'#888'}}>Cancel</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={handleCreate} style={styles.createBtn}>
                        <Text style={{color:'white', fontWeight:'bold'}}>Generate Plan</Text>
                    </TouchableOpacity>
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
  keyboardView: { width: '100%', alignItems: 'center' }, // Centers the card
  card: { backgroundColor: '#1a1a1a', padding: 20, borderRadius: 16, width: '100%', maxWidth: 400 },
  
  headerRow: { flexDirection:'row', justifyContent:'space-between', alignItems:'center', marginBottom: 20 },
  closeIcon: { padding: 5 },
  
  title: { color: 'white', fontSize: 22, fontWeight: 'bold' },
  label: { color: '#888', marginBottom: 6, marginTop: 12, fontSize: 12, fontWeight:'bold', letterSpacing: 0.5 },
  input: { backgroundColor: '#333', color: 'white', padding: 14, borderRadius: 8, fontSize: 16 },
  
  dateButton: { backgroundColor: '#333', padding: 14, borderRadius: 8, alignItems:'center' },
  iosPickerContainer: { backgroundColor: '#222', borderRadius: 8, marginTop: 5, overflow: 'hidden' },

  buttons: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 30, alignItems:'center' },
  cancelBtn: { padding: 15 },
  createBtn: { backgroundColor: '#ff4d4d', paddingVertical: 15, paddingHorizontal: 20, borderRadius: 8, flex: 1, alignItems: 'center', marginLeft: 15 }
});