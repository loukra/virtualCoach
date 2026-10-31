import React, { useState, useCallback } from 'react';
import { 
  View, 
  Text, 
  StyleSheet, 
  ActivityIndicator, 
  TouchableOpacity, 
  Dimensions, 
  Modal,
  ScrollView,
  SectionList // 👈 We use SectionList now!
} from 'react-native';
import { supabase } from '../lib/supabase';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native'; 
import { useJourney } from '../context/JourneyContext'; 

const SCREEN_WIDTH = Dimensions.get('window').width;
// 7 Columns with a little margin
const TILE_SIZE = (SCREEN_WIDTH - 32) / 7; 
const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

export default function TrainingPlanView() {
  const { activeJourneyId, setActiveJourneyId } = useJourney();
  
  const [loading, setLoading] = useState(true);
  const [journey, setJourney] = useState(null);
  
  // Data is now an array of Sections: { title: "JANUARY", data: [ ...days ] }
  const [sections, setSections] = useState([]);
  
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
        .select('id, name, start_date')
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

      // 2. Fetch Activities (History)
      let query = supabase
        .from('activities')
        .select('*')
        .eq('user_id', session.user.id)
        .order('start_date_local', { ascending: false });

      if (targetJourney && targetJourney.start_date) {
           query = query.gte('start_date_local', targetJourney.start_date);
      } else {
           const ninetyDaysAgo = new Date();
           ninetyDaysAgo.setDate(ninetyDaysAgo.getDate() - 90);
           query = query.gte('start_date_local', ninetyDaysAgo.toISOString());
      }
      const { data: activities } = await query;

      // 3. Fetch Plan & Merge
      let mergedList = [];
      if (targetJourney) {
        const { data: masterPlan } = await supabase
            .from('master_plan')
            .select('*')
            .eq('journey_id', targetJourney.id)
            .order('date', { ascending: true });

        if (masterPlan) {
            mergedList = masterPlan.map(planItem => {
                const planDate = planItem.date; 
                const matchedActivity = activities?.find(act => 
                    act.start_date_local && act.start_date_local.split('T')[0] === planDate
                );
                return {
                    id: planItem.id,
                    date: planItem.date, // YYYY-MM-DD
                    status: matchedActivity ? 'completed' : 'planned',
                    planDetail: planItem,           
                    activityDetail: matchedActivity
                };
            });
        }
      }
      
      // Sort global list first
      mergedList.sort((a, b) => new Date(a.date) - new Date(b.date));

      // --- 4. GROUP BY MONTH (The Magic Step) ---
      const groupedData = {};

      mergedList.forEach(item => {
          // Extract "2026-01"
          const monthKey = item.date.substring(0, 7); 
          if (!groupedData[monthKey]) {
              groupedData[monthKey] = [];
          }
          groupedData[monthKey].push(item);
      });

      // Convert Group Object to SectionList Array
      const sectionArray = Object.keys(groupedData).sort().map(monthKey => {
          const daysInMonth = groupedData[monthKey];
          
          // Calculate Padding for this specific month
          const firstDayDate = new Date(daysInMonth[0].date);
          let dayOfWeek = firstDayDate.getDay(); // 0=Sun, 1=Mon...
          let mondayIndex = dayOfWeek === 0 ? 6 : dayOfWeek - 1; // Convert to Mon=0

          const padding = [];
          for (let i = 0; i < mondayIndex; i++) {
              padding.push({ id: `pad-${monthKey}-${i}`, type: 'empty' });
          }

          // Format Month Title (e.g., "JANUARY 2026")
          const monthTitle = firstDayDate.toLocaleString('default', { month: 'long', year: 'numeric' }).toUpperCase();

          return {
              title: monthTitle,
              data: [...padding, ...daysInMonth] // Add padding to the start of data
          };
      });

      setSections(sectionArray);

    } catch (e) {
      console.log(e);
    } finally {
      setLoading(false);
    }
  };

  // --- RENDER SINGLE TILE ---
  const renderTile = ({ item, index }) => {
    // We wrap tiles in a View to force the grid layout inside the SectionList
    // However, SectionList renders items in rows by default. 
    // Trick: We will actually render the GRID inside the Section Header, or just use flexWrap.
    
    // BETTER APPROACH FOR SECTION LIST GRID:
    // SectionList doesn't support 'numColumns'.
    // So we must simply render the tiles, but they will stack vertically unless we do the "Row of 7" trick.
    // BUT simpler: Use a FlatList of Months.
    return null; // See below for the actual render strategy
  };

  // --- ACTUAL RENDER STRATEGY: List of Months ---
  // We use a simple FlatList where each ITEM is a whole MONTH.
  const renderMonthBlock = ({ item }) => {
      return (
          <View style={styles.monthContainer}>
              <Text style={styles.monthHeader}>{item.title}</Text>
              
              <View style={styles.monthGrid}>
                  {item.data.map((dayItem, idx) => (
                      <View key={dayItem.id || idx}>
                          {renderDayContent(dayItem)}
                      </View>
                  ))}
              </View>
          </View>
      );
  };

  const renderDayContent = (item) => {
    if (item.type === 'empty') return <View style={styles.tileInvisible} />;

    const isRest = item.planDetail?.planned_workout_type === 'Rest';
    const isCompleted = item.status === 'completed';
    const dateNum = item.date.split('-')[2];

    if (isCompleted) {
        return (
            <TouchableOpacity style={[styles.tile, styles.completedTile]} onPress={() => setSelectedTile(item)}>
                <Text style={[styles.miniDate, styles.pastelText]}>{dateNum}</Text>
                <Ionicons name="checkmark" size={16} color="#1a1a1a" /> 
            </TouchableOpacity>
        );
    }
    if (isRest) {
        return (
            <TouchableOpacity style={[styles.tile, styles.restTile]} onPress={() => setSelectedTile(item)}>
                <Text style={[styles.miniDate, {color:'#444'}]}>{dateNum}</Text>
                <View style={styles.dotRest} />
            </TouchableOpacity>
        );
    }
    return (
        <TouchableOpacity style={styles.tile} onPress={() => setSelectedTile(item)}>
            <Text style={styles.miniDate}>{dateNum}</Text>
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

      {/* WEEK DAYS HEADER (Sticky) */}
      <View style={styles.daysHeader}>
          {DAY_LABELS.map((d, i) => (
              <Text key={i} style={styles.dayLabelText}>{d}</Text>
          ))}
      </View>

      {/* MONTHS LIST */}
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
          {sections.map((monthSection, index) => (
              renderMonthBlock({ item: monthSection, index })
          ))}
          {sections.length === 0 && (
              <Text style={{color:'#666', textAlign:'center', marginTop:50}}>No plan data found.</Text>
          )}
      </ScrollView>

      {/* MODALS (Keep existing ones exactly same) */}
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

      <Modal visible={!!selectedTile} transparent animationType="slide" onRequestClose={() => setSelectedTile(null)}>
         <View style={styles.detailOverlay}>
            <View style={styles.detailContent}>
                <TouchableOpacity style={styles.closeBtn} onPress={() => setSelectedTile(null)}>
                    <Ionicons name="close" size={24} color="#ddd" />
                </TouchableOpacity>

                {selectedTile && (
                  <ScrollView>
                    <Text style={styles.detailDate}>{selectedTile.date}</Text>
                    <View style={styles.detailSection}>
                        <Text style={styles.sectionHeader}>📋 PLAN</Text>
                        {selectedTile.planDetail?.planned_workout_type === 'Rest' ? (
                             <Text style={{color:'#ccc'}}>Rest Day</Text>
                        ) : (
                            <View>
                                <Text style={styles.detailTitle}>{selectedTile.planDetail?.planned_workout_type}</Text>
                                <Text style={styles.detailSub}>{selectedTile.planDetail?.planned_duration_min} min target</Text>
                                <Text style={styles.detailBody}>{selectedTile.planDetail?.workout_text}</Text>
                            </View>
                        )}
                    </View>
                    {selectedTile.activityDetail && (
                        <View style={[styles.detailSection, {borderTopWidth:1, borderTopColor:'#333', marginTop:20, paddingTop:20}]}>
                            <Text style={[styles.sectionHeader, {color:'#A7F3D0'}]}>✅ DONE</Text>
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
  daysHeader: { flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#222', paddingHorizontal: 16 }, // Matched padding
  dayLabelText: { width: TILE_SIZE, textAlign: 'center', color: '#666', fontSize: 10, fontWeight: 'bold' },

  // --- MONTH BLOCKS ---
  monthContainer: { marginBottom: 20, paddingHorizontal: 16 },
  monthHeader: { color: 'white', fontSize: 14, fontWeight: 'bold', marginBottom: 10, marginTop: 10, letterSpacing: 1 },
  monthGrid: { flexDirection: 'row', flexWrap: 'wrap' }, // 👈 This makes the grid work!

  // --- TILES ---
  tile: { 
      width: TILE_SIZE, 
      height: TILE_SIZE, 
      justifyContent: 'center', 
      alignItems: 'center',
      borderWidth: 1,
      borderColor: '#222', 
      backgroundColor: '#151515', 
      marginVertical: -0.5, 
      marginHorizontal: -0.5
  },
  tileInvisible: { width: TILE_SIZE, height: TILE_SIZE, backgroundColor: 'transparent' },
  
  // Pastel Look
  completedTile: { backgroundColor: '#A7F3D0', borderColor: '#A7F3D0', opacity: 0.9 },
  pastelText: { color: '#1a1a1a', opacity: 0.6 },
  restTile: { backgroundColor: '#0a0a0a', borderColor: '#111' },
  
  miniDate: { fontSize: 10, fontWeight: 'bold', color: '#555', position: 'absolute', top: 4, right: 4 },
  dotPlanned: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#FF8A80' }, 
  dotRest: { width: 4, height: 4, borderRadius: 2, backgroundColor: '#333' },

  // --- MODALS (Same) ---
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