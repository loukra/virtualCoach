import React, { useState, useCallback } from 'react';
import { 
  View, 
  Text, 
  FlatList, 
  StyleSheet, 
  ActivityIndicator, 
  TouchableOpacity, 
  Dimensions, 
  Modal,
  ScrollView
} from 'react-native';
import { supabase } from '../lib/supabase';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native'; 
import { useJourney } from '../context/JourneyContext'; 

const SCREEN_WIDTH = Dimensions.get('window').width;
// 7 Columns. Subtracting padding (20px total) to fit screen.
const TILE_SIZE = (SCREEN_WIDTH - 20) / 7; 

const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

export default function TrainingPlanView() {
  const { activeJourneyId, setActiveJourneyId } = useJourney();
  
  const [loading, setLoading] = useState(true);
  const [journey, setJourney] = useState(null);
  const [gridData, setGridData] = useState([]);
  
  const [allJourneys, setAllJourneys] = useState([]);
  const [showSelector, setShowSelector] = useState(false);
  const [selectedTile, setSelectedTile] = useState(null);

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [activeJourneyId]) 
  );

  const formatTime = (seconds) => {
      if (!seconds) return '0m';
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

      if (targetJourney) {
        // 3. Fetch Master Plan
        const { data: masterPlan } = await supabase
            .from('master_plan')
            .select('*')
            .eq('journey_id', targetJourney.id)
            .order('date', { ascending: true });

        if (masterPlan) {
            mergedList = masterPlan.map(planItem => {
                const planDate = planItem.date; 
                const matchedActivity = activities?.find(act => {
                    if (!act.start_date) return false;
                    const actDate = act.start_date.split('T')[0]; 
                    return actDate === planDate;
                });

                return {
                    id: planItem.id,
                    date: planItem.date,
                    status: matchedActivity ? 'completed' : 'planned',
                    planDetail: planItem,           
                    activityDetail: matchedActivity
                };
            });
        }
      } 
      
      mergedList.sort((a, b) => new Date(a.date) - new Date(b.date));

      // --- CALENDAR ALIGNMENT LOGIC ---
      // We need to insert empty "ghost" tiles at the start so Monday is Col 1.
      if (mergedList.length > 0) {
          const firstDate = new Date(mergedList[0].date);
          // getDay() returns 0 (Sun) to 6 (Sat). We want 0 (Mon) to 6 (Sun).
          let dayOfWeek = firstDate.getDay(); 
          // Convert to Monday-index (Mon=0, Tue=1, ... Sun=6)
          let mondayIndex = dayOfWeek === 0 ? 6 : dayOfWeek - 1;

          const padding = [];
          for (let i = 0; i < mondayIndex; i++) {
              padding.push({ id: `pad-${i}`, type: 'empty' });
          }
          mergedList = [...padding, ...mergedList];
      }

      setGridData(mergedList);

    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  const renderTile = ({ item }) => {
    // A. Empty Alignment Tile
    if (item.type === 'empty') {
        return <View style={styles.tileInvisible} />;
    }

    const isRest = item.planDetail?.planned_workout_type === 'Rest';
    const isCompleted = item.status === 'completed';
    const dateNum = item.date.split('-')[2]; // Get "20" from "2026-01-20"

    // B. COMPLETED (Green)
    if (isCompleted) {
        return (
            <TouchableOpacity style={[styles.tile, styles.completedTile]} onPress={() => setSelectedTile(item)}>
                <Text style={styles.miniDate}>{dateNum}</Text>
                <Ionicons name="checkmark" size={16} color="black" />
            </TouchableOpacity>
        );
    }

    // C. REST (Grey Outline)
    if (isRest) {
        return (
            <TouchableOpacity style={[styles.tile, styles.restTile]} onPress={() => setSelectedTile(item)}>
                <Text style={[styles.miniDate, {color:'#666'}]}>{dateNum}</Text>
                <View style={styles.dotRest} />
            </TouchableOpacity>
        );
    }

    // D. PLANNED (Red Dot)
    return (
        <TouchableOpacity style={styles.tile} onPress={() => setSelectedTile(item)}>
            <Text style={styles.miniDate}>{dateNum}</Text>
            {/* Visual Indicator of workout type */}
            <View style={styles.dotPlanned} />
        </TouchableOpacity>
    );
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color="#ff4d4d"/></View>;

  return (
    <View style={styles.container}>
      {/* HEADER */}
      <View style={styles.header}>
        <Text style={styles.title}>Calendar</Text>
        <TouchableOpacity onPress={() => setShowSelector(true)} style={styles.selectorBtn}>
            <Text style={styles.subtitle}>{journey ? journey.name : "SELECT GOAL"}</Text>
            <Ionicons name="chevron-down" size={12} color="#ff4d4d" style={{marginLeft: 4}} />
        </TouchableOpacity>
      </View>

      {/* DAYS HEADER (M T W T F S S) */}
      <View style={styles.daysHeader}>
          {DAY_LABELS.map((d, i) => (
              <Text key={i} style={styles.dayLabelText}>{d}</Text>
          ))}
      </View>

      {/* CALENDAR GRID */}
      <FlatList
        data={gridData}
        keyExtractor={(item) => item.id.toString()}
        renderItem={renderTile}
        numColumns={7} // 👈 7 Columns for the week
        contentContainerStyle={{ paddingHorizontal: 10, paddingBottom: 20 }}
        columnWrapperStyle={{ gap: 0 }} // Remove gap, handle via padding in tile
      />

      {/* --- SELECTOR MODAL --- */}
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

      {/* --- DETAIL POPUP --- */}
      <Modal visible={!!selectedTile} transparent animationType="slide" onRequestClose={() => setSelectedTile(null)}>
         <View style={styles.detailOverlay}>
            <View style={styles.detailContent}>
                <TouchableOpacity style={styles.closeBtn} onPress={() => setSelectedTile(null)}>
                    <Ionicons name="close" size={24} color="#ddd" />
                </TouchableOpacity>

                {selectedTile && (
                  <ScrollView>
                    <Text style={styles.detailDate}>{selectedTile.date}</Text>

                    {/* PLAN */}
                    <View style={styles.detailSection}>
                        <Text style={styles.sectionHeader}>📋 PLAN</Text>
                        {selectedTile.planDetail?.planned_workout_type === 'Rest' ? (
                             <Text style={{color:'#ccc'}}>Rest Day</Text>
                        ) : (
                            <View>
                                <Text style={styles.detailTitle}>{selectedTile.planDetail?.planned_workout_type}</Text>
                                <Text style={styles.detailSub}>{selectedTile.planDetail?.planned_duration_min} min target</Text>
                                <Text style={styles.detailBody}>{selectedTile.planDetail?.description}</Text>
                            </View>
                        )}
                    </View>

                    {/* ACTUAL */}
                    {selectedTile.activityDetail && (
                        <View style={[styles.detailSection, {borderTopWidth:1, borderTopColor:'#333', marginTop:20, paddingTop:20}]}>
                            <Text style={[styles.sectionHeader, {color:'#4dff4d'}]}>✅ DONE</Text>
                            <Text style={styles.detailTitle}>{selectedTile.activityDetail.name}</Text>
                            <View style={styles.statsGrid}>
                                <View style={styles.statBox}><Text style={styles.statLabel}>TIME</Text><Text style={styles.statValue}>{formatTime(selectedTile.activityDetail.moving_time)}</Text></View>
                                <View style={styles.statBox}><Text style={styles.statLabel}>TSS</Text><Text style={styles.statValue}>{selectedTile.activityDetail.tss || '-'}</Text></View>
                            </View>
                        </View>
                    )}
                  </ScrollView>
                )}
            </View>
         </View>
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

  // --- DAYS HEADER ---
  daysHeader: { flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#222', paddingHorizontal: 10 },
  dayLabelText: { width: TILE_SIZE, textAlign: 'center', color: '#666', fontSize: 10, fontWeight: 'bold' },

  // --- MINIMAL TILES ---
  tile: { 
      width: TILE_SIZE, 
      height: TILE_SIZE, // Square
      justifyContent: 'center', 
      alignItems: 'center',
      borderWidth: 1,
      borderColor: '#222', // Subtle grid lines
      backgroundColor: '#151515'
  },
  tileInvisible: { width: TILE_SIZE, height: TILE_SIZE, backgroundColor: 'transparent' }, // For padding
  
completedTile: { 
      backgroundColor: '#A7F3D0', // Darker, natural green
      borderColor: '#1b5e20'     // Subtle border
  },
  restTile: { backgroundColor: '#000' },
  
  miniDate: { fontSize: 10, fontWeight: 'bold', color: '#888', position: 'absolute', top: 4, right: 4 },
  
  dotPlanned: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#ff4d4d' },
  dotRest: { width: 4, height: 4, borderRadius: 2, backgroundColor: '#333' },

  // --- MODAL / DETAILS ---
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center' },
  modalContent: { width: '80%', backgroundColor: '#222', borderRadius: 12, padding: 20 },
  modalTitle: { color: 'white', fontSize: 16, fontWeight: 'bold', marginBottom: 15, textAlign:'center' },
  modalItem: { paddingVertical: 15, borderBottomWidth: 1, borderBottomColor: '#333', flexDirection:'row', justifyContent:'space-between' },
  modalItemSelected: { backgroundColor: '#2a2a2a' },
  modalItemText: { color: '#ddd', fontSize: 14, fontWeight:'bold' },
  detailOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.9)', justifyContent: 'flex-end' },
  detailContent: { backgroundColor: '#1a1a1a', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 25, height: '60%' },
  closeBtn: { alignSelf: 'flex-end', padding: 5 },
  detailDate: { color: 'white', fontSize: 22, fontWeight: 'bold', marginBottom: 20 },
  sectionHeader: { color: '#ff4d4d', fontSize: 12, fontWeight: 'bold', letterSpacing: 1, marginBottom: 10 },
  detailTitle: { color: 'white', fontSize: 18, fontWeight: 'bold', marginBottom: 5 },
  detailSub: { color: '#888', fontSize: 14, marginBottom: 15 },
  detailBody: { color: '#ccc', fontSize: 14, lineHeight: 22 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 15 },
  statBox: { backgroundColor: '#222', width: '45%', padding: 15, borderRadius: 8 },
  statLabel: { color: '#666', fontSize: 10, fontWeight: 'bold' },
  statValue: { color: 'white', fontSize: 18, fontWeight: 'bold', marginTop: 5 },
});