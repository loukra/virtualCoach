import React, { useState, useEffect } from 'react';
import { 
  StyleSheet, 
  View, 
  Text, 
  TouchableOpacity, 
  SafeAreaView, 
  FlatList, 
  ActivityIndicator 
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { supabase } from '../lib/supabase';
import { apiPost } from '../lib/api';
import CreateJourneyModal from '../components/CreateJourneyModal';
import { useJourney } from '../context/JourneyContext';
// 👇 IMPORT NAVIGATION HOOK
import { useNavigation } from '@react-navigation/native';

export default function Dashboard() {
  const navigation = useNavigation();
  const { setActiveJourneyId } = useJourney();
  const [journeys, setJourneys] = useState([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);

  // 1. Initial Load
  useEffect(() => {
    fetchJourneys();
    // Start background sync silently
    triggerApiSync();
  }, []);

  const fetchJourneys = async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;

    // Fetch ALL journeys
    const { data } = await supabase
      .from('journeys')
      .select('*')
      .eq('user_id', session.user.id)
      .order('created_at', { ascending: false });
    
    setJourneys(data || []);
  };

  const triggerApiSync = async () => {
    setIsSyncing(true);
    try {
        await apiPost('/sync', { days_back: 7 });
    }
    catch (e) {
        console.log(e);
    } finally { 
        setTimeout(() => setIsSyncing(false), 3000); 
    }
  };

  const handleJourneyCreated = () => {
    fetchJourneys(); 
  };

  return (
    <SafeAreaView style={styles.container}>
      <CreateJourneyModal visible={createModalVisible} onClose={() => setCreateModalVisible(false)} onJourneyCreated={handleJourneyCreated} />

      {/* --- HEADER (Updated for Bottom Tabs) --- */}
      <View style={styles.header}>
        
        {/* Left Side: Brand Logo (Replaces Burger Menu) */}
        <View style={{flexDirection:'row', alignItems:'center'}}>
            <Ionicons name="bicycle" size={24} color="#ff4d4d" style={{marginRight: 10}}/>
            <Text style={{color:'#fff', fontWeight:'bold', fontSize: 18}}>VELO AI</Text>
        </View>

        {/* Right Side: Sync Status */}
        <View style={{alignItems: 'flex-end'}}>
            {isSyncing && <Text style={{color:'#666', fontSize: 10, marginBottom: 4}}>SYNCING...</Text>}
            <Text style={{color:'#fff', fontWeight:'bold', fontSize: 16}}>My Journeys</Text>
        </View>
      </View>

      {/* --- CONTENT AREA --- */}
      <View style={styles.content}>
          <View style={{flex: 1, width:'100%', padding: 20}}>
              <FlatList
                  data={journeys}
                  keyExtractor={(item) => item.id}
                  contentContainerStyle={{ gap: 15 }}
                  renderItem={({ item }) => (
                      <TouchableOpacity 
                        style={styles.card} 
                        // 👇 Navigate to the Journey Detail screen
                        onPress={() => {
                    setActiveJourneyId(item.id); // 👈 UPDATE GLOBAL ID
                    navigation.navigate('JourneyDetail', { journeyId: item.id, name: item.name });
                }}
                      >
                          <View>
                              <Text style={styles.cardTitle}>{item.name}</Text>
                              <Text style={styles.cardDate}>Race: {item.race_date}</Text>
                          </View>
                          <View style={{alignItems:'flex-end'}}>
                              {item.status === 'creating' ? (
                                  <ActivityIndicator color="#ff4d4d" />
                              ) : (
                                  <Ionicons name="chevron-forward" size={24} color="#666" />
                              )}
                          </View>
                      </TouchableOpacity>
                  )}
                  ListEmptyComponent={
                      <Text style={{color:'#666', textAlign:'center', marginTop: 50}}>No journeys yet.</Text>
                  }
              />

              {/* FLOATING CREATE BUTTON */}
              <TouchableOpacity style={styles.fab} onPress={() => setCreateModalVisible(true)}>
                  <Ionicons name="add" size={30} color="white" />
              </TouchableOpacity>
          </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111', paddingTop: 40 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems:'center', padding: 20, borderBottomWidth: 1, borderBottomColor: '#222' },
  content: { flex: 1 },
  
  // List Card Styles
  card: { backgroundColor: '#1a1a1a', padding: 20, borderRadius: 12, flexDirection:'row', justifyContent:'space-between', alignItems:'center' },
  cardTitle: { color: 'white', fontSize: 18, fontWeight: 'bold' },
  cardDate: { color: '#888', fontSize: 12, marginTop: 4 },
  
  // FAB (Floating Action Button)
  fab: { position: 'absolute', bottom: 30, right: 20, backgroundColor: '#ff4d4d', width: 60, height: 60, borderRadius: 30, justifyContent: 'center', alignItems: 'center', elevation: 5, shadowColor:'#000', shadowOffset:{width:0,height:4}, shadowOpacity:0.3, shadowRadius:4 },
});