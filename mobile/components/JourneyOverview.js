import React, { useEffect, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet, TouchableOpacity, ScrollView, Alert } from 'react-native';
import { supabase } from '../lib/supabase';
import { Ionicons } from '@expo/vector-icons';
import { apiPost } from '../lib/api';
import { localDateString } from '../lib/dates';
import CheckInModal from './CheckInModal';
import Markdown from 'react-native-markdown-display';

export default function JourneyOverview({ route, navigation }) {
  const { journeyId } = route.params; 

  const [journey, setJourney] = useState(null);
  const [checkIn, setCheckIn] = useState(null);
  const [todaysWorkout, setTodaysWorkout] = useState(null);
  
  // 👇 1. NEW STATE: Tracks if we are fetching the initial data
  const [initializing, setInitializing] = useState(true);
  const [loadingWorkout, setLoadingWorkout] = useState(false);
  const [showCheckInModal, setShowCheckInModal] = useState(false);
  
  const pollingRef = useRef(null);

  useEffect(() => {
    loadJourney();
    loadTodayData();
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [journeyId]);

  const loadJourney = async () => {
    const { data } = await supabase.from('journeys').select('*').eq('id', journeyId).maybeSingle();
    if (data) {
        setJourney(data);
        if (data.status === 'creating') startPolling();
    }
  };

  const loadTodayData = async () => {
    try {
        const { data: { session } } = await supabase.auth.getSession();
        const today = localDateString();

        // A. Get Check-In
        const { data: checkData } = await supabase
            .from('daily_checkins')
            .select('*')
            .eq('user_id', session.user.id)
            .eq('date', today)
            .maybeSingle();
        setCheckIn(checkData || { feel_score: 3, soreness_score: 3 });

        // B. Get Prescription
        const { data: workData } = await supabase
            .from('daily_prescriptions')
            .select('workout_text')
            .eq('journey_id', journeyId)
            .eq('date', today)
            .maybeSingle();
        
        if (workData) setTodaysWorkout(workData.workout_text);
        else setTodaysWorkout(null);
        
    } catch (e) {
        console.log("Error loading today:", e);
    } finally {
        // 👇 2. CRITICAL: We are done checking, reveal the UI
        setInitializing(false);
    }
  };

  const startPolling = () => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      const { data } = await supabase.from('journeys').select('status, error').eq('id', journeyId).maybeSingle();
      if (data && data.status === 'active') {
         clearInterval(pollingRef.current);
         loadJourney();
      } else if (data && data.status === 'failed') {
         clearInterval(pollingRef.current);
         Alert.alert("Error", data.error || "Plan generation failed.");
         setJourney(prev => ({ ...prev, status: 'failed' }));
      }
    }, 3000);
  };

  const handleGenerateWorkout = async (isRedo = false) => {
    setLoadingWorkout(true);
    try {
        const data = await apiPost('/generate-workout', {
            journey_id: journeyId,
            available_time: 60,
            force: isRedo,
        });
        setTodaysWorkout(data.workout);
    } catch (e) {
        Alert.alert("Error", e.message);
    } finally {
        setLoadingWorkout(false);
    }
  };

  if (!journey) return <View style={styles.center}><ActivityIndicator size="large" color="#ff4d4d"/></View>;
  if (journey.status === 'creating') return <View style={styles.center}><ActivityIndicator color="#ff4d4d"/><Text style={{color:'white', marginTop:10}}>Creating Plan...</Text></View>;

  return (
    <ScrollView style={styles.container}>
        <CheckInModal 
            visible={showCheckInModal} 
            onClose={() => setShowCheckInModal(false)}
            userId={journey.user_id}
            currentValues={checkIn}
            onSave={(newValues) => setCheckIn(newValues)}
        />

        <View style={styles.navHeader}>
            <TouchableOpacity onPress={() => navigation.goBack()} style={{padding: 5}}>
                <Ionicons name="arrow-back" size={24} color="#ff4d4d" />
            </TouchableOpacity>
            <Text style={styles.navTitle}>{journey.name}</Text>
            <View style={{width: 30}} /> 
        </View>

        {/* --- SECTION 1: STATS --- */}
        <View style={styles.headerRow}>
            <Text style={styles.title}>Journey Stats</Text>
            <View style={styles.badge}><Text style={styles.badgeText}>{journey.status}</Text></View>
        </View>

        {/* --- SECTION 2: CHECK-IN TILES --- */}
        <Text style={styles.sectionLabel}>DAILY CHECK-IN</Text>
        <View style={styles.row}>
            <TouchableOpacity style={styles.tile} onPress={() => setShowCheckInModal(true)}>
                <Text style={styles.tileLabel}>MOOD</Text>
                <Text style={[styles.tileValue, {color: checkIn?.feel_score >= 4 ? '#4dff4d' : '#ff4d4d'}]}>
                    {checkIn?.feel_score || '-'}/5
                </Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.tile} onPress={() => setShowCheckInModal(true)}>
                <Text style={styles.tileLabel}>LEGS</Text>
                <Text style={[styles.tileValue, {color: checkIn?.soreness_score >= 4 ? '#4dff4d' : '#ff4d4d'}]}>
                    {checkIn?.soreness_score || '-'}/5
                </Text>
            </TouchableOpacity>
        </View>

        {/* --- SECTION 3: TODAY'S TRAINING --- */}
        <Text style={styles.sectionLabel}>TODAY'S TRAINING</Text>
        
        <View style={styles.workoutCard}>
            {/* 👇 3. UPDATED LOGIC: Show loader if Initializing OR Generating */}
            {(initializing || loadingWorkout) ? (
                <View style={{padding: 20, alignItems:'center'}}>
                    <ActivityIndicator color="#ff4d4d" />
                    <Text style={{color:'#666', marginTop: 10}}>
                        {loadingWorkout ? "Coach is thinking..." : "Loading today's plan..."}
                    </Text>
                </View>
            ) : todaysWorkout ? (
                <View>
                    <View style={{flexDirection:'row', justifyContent:'space-between', marginBottom: 10}}>
                        <Text style={{color:'#ff4d4d', fontWeight:'bold', fontSize: 12}}>RECOMMENDED</Text>
                        <TouchableOpacity onPress={() => handleGenerateWorkout(true)}>
                                <Ionicons name="refresh" size={20} color="#666" />
                        </TouchableOpacity>
                    </View>
                    
                    <Markdown style={markdownStyles}>
                        {todaysWorkout}
                    </Markdown>
                    
                    <TouchableOpacity style={styles.redoBtn} onPress={() => handleGenerateWorkout(true)}>
                        <Text style={styles.redoText}>Redo with current stats</Text>
                    </TouchableOpacity>
                </View>
            ) : (
                <View style={{alignItems:'center', padding: 10}}>
                    <Text style={{color:'#888', marginBottom: 15, textAlign:'center'}}>
                        No workout generated for today yet. 
                        Adjust your check-in above, then click generate.
                    </Text>
                    <TouchableOpacity style={styles.generateBtn} onPress={() => handleGenerateWorkout(false)}>
                        <Text style={styles.generateText}>Generate Training</Text>
                    </TouchableOpacity>
                </View>
            )}
        </View>

        <View style={{height: 50}} /> 
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111', padding: 20, paddingTop: 40 },
  center: { flex: 1, backgroundColor: '#111', justifyContent:'center', alignItems:'center' },
  navHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 },
  navTitle: { color: 'white', fontSize: 18, fontWeight: 'bold' },
  title: { color: 'white', fontSize: 24, fontWeight: 'bold' },
  headerRow: { flexDirection:'row', justifyContent:'space-between', alignItems:'center', marginBottom: 20 },
  badge: { backgroundColor:'#333', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },
  badgeText: { color:'#4dff4d', fontSize: 10, fontWeight:'bold', textTransform:'uppercase' },
  sectionLabel: { color: '#666', fontSize: 12, fontWeight: 'bold', marginBottom: 10, marginTop: 10, letterSpacing: 1 },
  row: { flexDirection: 'row', gap: 15, marginBottom: 20 },
  tile: { flex: 1, backgroundColor: '#1a1a1a', padding: 15, borderRadius: 10, alignItems:'center' },
  tileLabel: { color: '#888', fontSize: 10, fontWeight: 'bold', marginBottom: 5 },
  tileValue: { fontSize: 24, fontWeight: 'bold' },
  workoutCard: { backgroundColor: '#1a1a1a', padding: 20, borderRadius: 12, marginBottom: 20 },
  generateBtn: { backgroundColor: '#ff4d4d', paddingVertical: 12, paddingHorizontal: 25, borderRadius: 30 },
  generateText: { color: 'white', fontWeight: 'bold' },
  redoBtn: { marginTop: 15, padding: 10, alignItems:'center', borderTopWidth: 1, borderTopColor:'#333' },
  redoText: { color: '#666', fontSize: 12 }
});

const markdownStyles = {
  heading1: { color: 'white', fontSize: 26, fontWeight: 'bold', lineHeight: 36, paddingTop: 10, marginBottom: 15 },
  body: { color: '#ddd', fontSize: 16, lineHeight: 24 },
  heading2: { color: '#ff4d4d', fontSize: 20, fontWeight: 'bold', marginTop: 20, marginBottom: 10, borderBottomWidth: 1, borderBottomColor: '#333', paddingBottom: 5 },
  strong: { color: 'white', fontWeight: 'bold' },
  bullet_list_icon: { color: '#ff4d4d', fontSize: 20 },
  list_item: { marginBottom: 8 },
  em: { color: '#888', fontStyle: 'italic' },
};