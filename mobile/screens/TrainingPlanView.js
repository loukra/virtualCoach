import React, { useState, useCallback } from 'react';
import { 
  View, 
  Text, 
  FlatList, 
  StyleSheet, 
  ActivityIndicator, 
  TouchableOpacity, 
  Dimensions, 
  Modal 
} from 'react-native';
import { supabase } from '../lib/supabase';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native'; 
import { useJourney } from '../context/JourneyContext'; 

const SCREEN_WIDTH = Dimensions.get('window').width;
const TILE_SIZE = (SCREEN_WIDTH - 40) / 3; 

export default function TrainingPlanView() {
  const { activeJourneyId, setActiveJourneyId } = useJourney();
  
  const [loading, setLoading] = useState(true);
  const [journey, setJourney] = useState(null);
  const [gridData, setGridData] = useState([]);
  
  const [allJourneys, setAllJourneys] = useState([]);
  const [showSelector, setShowSelector] = useState(false);

  // DEBUG STATE
  const [debugStats, setDebugStats] = useState({ activities: 0, planItems: 0, matches: 0 });

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [activeJourneyId]) 
  );

  const formatTime = (seconds) => {
      if (!seconds) return '';
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;

      // 1. Fetch Journeys
      const { data: userJourneys } = await supabase
        .from('journeys')
        .select('id, name')
        .eq('user_id', session.user.id)
        .in('status', ['active', 'creating']) 
        .order('created_at', { ascending: false });
      
      setAllJourneys(userJourneys || []);

      let targetJourney = null;
      if (activeJourneyId) {
          targetJourney = userJourneys?.find(j => j.id === activeJourneyId);
      } 
      if (!targetJourney && userJourneys?.length > 0) {
          targetJourney = userJourneys[0];
          setActiveJourneyId(targetJourney.id); 
      }
      setJourney(targetJourney);

      // 2. Fetch Recent Activities
      const { data: activities } = await supabase
        .from('activities')
        .select('*')
        .eq('user_id', session.user.id)
        .order('start_date', { ascending: false })
        .limit(60);

      let mergedList = [];
      let matchCount = 0;

      if (targetJourney) {
        // 3. Fetch Master Plan
        const { data: masterPlan } = await supabase
            .from('master_plan')
            .select('*')
            .eq('journey_id', targetJourney.id)
            .order('date', { ascending: true });

        if (masterPlan) {
            mergedList = masterPlan.map(planItem => {
                // ROBUST DATE MATCHING: Compare YYYY-MM-DD only
                const planDate = planItem.date; 
                
                const matchedActivity = activities?.find(act => {
                    // Safety check: sometimes Strava sends dates differently
                    if (!act.start_date) return false;
                    const actDate = act.start_date.split('T')[0]; // Extract YYYY-MM-DD
                    return actDate === planDate;
                });

                if (matchedActivity) matchCount++;

                return {
                    id: planItem.id,
                    date: planItem.date,
                    // If matched, we force status to completed
                    status: matchedActivity ? 'completed' : 'planned',
                    planDetail: planItem,           
                    activityDetail: matchedActivity
                };
            });
            
            // Update Debug Stats
            setDebugStats({
                activities: activities?.length || 0,
                planItems: masterPlan.length,
                matches: matchCount
            });
        }
      } 
      
      // Sort Oldest -> Newest
      mergedList.sort((a, b) => new Date(a.date) - new Date(b.date));
      setGridData(mergedList);

    } catch (e) {
      console.log('Error fetching plan:', e);
    } finally {
      setLoading(false);
    }
  };

  const renderTile = ({ item }) => {
    const isRest = item.planDetail?.planned_workout_type === 'Rest';
    const isCompleted = item.status === 'completed';

    // 1. SHOW DONE (Green Tile) - Prioritize this!
    if (isCompleted) {
        return (
            <View style={[styles.tile, styles.completedTile]}>
                <Text style={[styles.dateLabel, {color:'rgba(0,0,0,0.5)'}]}>{item.date.slice(5)}</Text>
                
                <View style={{flex:1, justifyContent:'center'}}>
                    <View style={{flexDirection:'row', alignItems:'center', marginBottom:2}}>
                        <Ionicons name="checkmark-circle" size={14} color="black" style={{marginRight:2}}/>
                        <Text style={styles.doneLabel}>DONE</Text>
                    </View>
                    <Text style={styles.doneText} numberOfLines={2}>
                        {item.activityDetail.name}
                    </Text>
                    <Text style={styles.doneStats}>
                        {formatTime(item.activityDetail.moving_time)}
                    </Text>
                </View>
            </View>
        );
    }

    // 2. SHOW REST (Simple Dark Tile)
    if (isRest) {
        return (
            <View style={[styles.tile, styles.restTile]}>
                <Text style={styles.dateLabel}>{item.date.slice(5)}</Text>
                <View style={styles.centerContent}>
                    <Text style={{color:'#666', fontWeight:'bold', fontSize:12}}>REST</Text>
                </View>
            </View>
        );
    }

    // 3. SHOW PLANNED (Standard Tile)
    return (
        <View style={styles.tile}>
            <Text style={styles.dateLabel}>{item.date.slice(5)}</Text>
            <View style={styles.centerContent}>
                <Text style={styles.planLabel}>PLANNED</Text>
                <Text style={styles.planText} numberOfLines={2}>
                    {item.planDetail.planned_workout_type}
                </Text>
                <View style={styles.pill}>
                    <Text style={styles.pillText}>{item.planDetail.planned_duration_min} min</Text>
                </View>
            </View>
        </View>
    );
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color="#ff4d4d"/></View>;

  return (
    <View style={styles.container}>
      {/* HEADER */}
      <View style={styles.header}>
        <Text style={styles.title}>Training Calendar</Text>
        <TouchableOpacity onPress={() => setShowSelector(true)} style={styles.selectorBtn}>
            <Text style={styles.subtitle}>
                {journey ? `GOAL: ${journey.name}` : "SELECT A GOAL"}
            </Text>
            <Ionicons name="chevron-down" size={12} color="#ff4d4d" style={{marginLeft: 4}} />
        </TouchableOpacity>
        
        {/* 👇 DEBUG BAR: Shows if data is actually loading */}
        <Text style={styles.debugText}>
            Debug: Found {debugStats.activities} activities, {debugStats.planItems} planned days. Matched: {debugStats.matches}
        </Text>
      </View>

      {/* GRID */}
      <FlatList
        data={gridData}
        keyExtractor={(item) => item.id.toString()}
        renderItem={renderTile}
        numColumns={3}
        columnWrapperStyle={{ gap: 10 }}
        contentContainerStyle={{ padding: 20, gap: 10 }}
        ListEmptyComponent={
            <Text style={{color:'#666', textAlign:'center', marginTop:50}}>No data found.</Text>
        }
      />

      {/* SELECTOR MODAL */}
      <Modal visible={showSelector} transparent animationType="fade" onRequestClose={() => setShowSelector(false)}>
         <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setShowSelector(false)}>
            <View style={styles.modalContent}>
                <Text style={styles.modalTitle}>Select Active Journey</Text>
                {allJourneys.map(j => (
                    <TouchableOpacity 
                        key={j.id} 
                        style={[styles.modalItem, activeJourneyId === j.id && styles.modalItemSelected]}
                        onPress={() => {
                            setActiveJourneyId(j.id);
                            setShowSelector(false);
                        }}
                    >
                        <Text style={[styles.modalItemText, activeJourneyId === j.id && {color:'#ff4d4d'}]}>{j.name}</Text>
                        {activeJourneyId === j.id && <Ionicons name="checkmark" size={18} color="#ff4d4d" />}
                    </TouchableOpacity>
                ))}
            </View>
         </TouchableOpacity>
      </Modal>

    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111', paddingTop: 40 },
  center: { flex: 1, backgroundColor: '#111', justifyContent:'center', alignItems:'center' },
  header: { paddingHorizontal: 20, paddingBottom: 15, borderBottomWidth: 1, borderBottomColor: '#222' },
  title: { color: 'white', fontSize: 24, fontWeight: 'bold' },
  selectorBtn: { flexDirection:'row', alignItems:'center', marginTop: 5 },
  subtitle: { color: '#ff4d4d', fontSize: 10, fontWeight: 'bold', letterSpacing: 1, textTransform: 'uppercase' },
  debugText: { color: '#444', fontSize: 10, marginTop: 5 }, // Debug style

  // --- TILE BASE ---
  tile: { 
      width: TILE_SIZE, 
      height: TILE_SIZE, 
      backgroundColor: '#1a1a1a', 
      borderRadius: 8, 
      padding: 8, 
      justifyContent: 'space-between'
  },
  restTile: { backgroundColor: '#000', borderWidth: 1, borderColor: '#222', opacity: 0.7 },
  completedTile: { backgroundColor: '#4dff4d' }, 

  dateLabel: { color: '#666', fontSize: 9, fontWeight: 'bold', textAlign: 'right', marginBottom: 4 },
  centerContent: { flex: 1, justifyContent:'center' },

  // --- PLANNED STYLES ---
  planLabel: { color: '#ff4d4d', fontSize: 8, fontWeight:'bold', marginBottom: 2 },
  planText: { color: 'white', fontSize: 12, fontWeight: 'bold', marginBottom: 6 },
  pill: { backgroundColor: '#333', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, alignSelf: 'flex-start' },
  pillText: { color: '#ddd', fontSize: 10, fontWeight:'bold' },

  // --- COMPLETED STYLES ---
  doneLabel: { color: 'black', fontSize: 8, fontWeight:'bold' },
  doneText: { color: 'black', fontSize: 11, fontWeight: 'bold', lineHeight: 12 },
  doneStats: { color: 'rgba(0,0,0,0.7)', fontSize: 10, marginTop: 2, fontWeight:'600' },

  // --- MODAL ---
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center' },
  modalContent: { width: '80%', backgroundColor: '#222', borderRadius: 12, padding: 20 },
  modalTitle: { color: 'white', fontSize: 16, fontWeight: 'bold', marginBottom: 15, textAlign:'center' },
  modalItem: { paddingVertical: 15, borderBottomWidth: 1, borderBottomColor: '#333', flexDirection:'row', justifyContent:'space-between' },
  modalItemSelected: { backgroundColor: '#2a2a2a' },
  modalItemText: { color: '#ddd', fontSize: 14, fontWeight:'bold' },
});