import React, { useState, useEffect } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, SafeAreaView, FlatList, ActivityIndicator, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { supabase } from '../lib/supabase';
import { API_URL } from '../constants'; 
import CreateJourneyModal from '../components/CreateJourneyModal';
import JourneyOverview from '../components/JourneyOverview'; // 👈 Import the new component

export default function Dashboard() {
  const [journeys, setJourneys] = useState([]);
  const [selectedJourneyId, setSelectedJourneyId] = useState(null); // 👈 Controls Navigation
  const [headerTitle, setHeaderTitle] = useState(null); // Display name in top-right
  const [isSyncing, setIsSyncing] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);

  // 1. Initial Load
  useEffect(() => {
    fetchJourneys();
    // Start background sync silently
    const getSession = async () => {
        const { data: { session } } = await supabase.auth.getSession();
        if(session) triggerApiSync(session.user.id);
    };
    getSession();
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

  const triggerApiSync = async (userId) => {
    setIsSyncing(true);
    try { await fetch(`${API_URL}/sync`, { method: 'POST', body: JSON.stringify({ user_id: userId }) }); }
    catch (e) {} finally { setTimeout(() => setIsSyncing(false), 3000); }
  };

  // --- NAVIGATION HANDLERS ---
  const handleSelectJourney = (journey) => {
    setSelectedJourneyId(journey.id);
    setHeaderTitle(journey.name); // Set initial title
  };

  const handleBackToHome = () => {
    setSelectedJourneyId(null);
    setHeaderTitle(null);
    fetchJourneys(); // Refresh list to see status updates
  };

  const handleJourneyCreated = () => {
    fetchJourneys(); 
    // Optional: Auto-select the new journey?
    // For now, let's just refresh the list.
  };

  // --- MENU COMPONENT ---
  const SimpleMenu = () => (
    <Modal animationType="fade" transparent={true} visible={menuVisible} onRequestClose={() => setMenuVisible(false)}>
      <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setMenuVisible(false)}>
        <View style={styles.menuContainer}>
          <Text style={styles.menuHeader}>Menu</Text>
          <TouchableOpacity style={styles.menuItem} onPress={() => supabase.auth.signOut()}>
            <Ionicons name="log-out-outline" size={24} color="#ff4d4d" />
            <Text style={[styles.menuText, { color: '#ff4d4d' }]}>Sign Out</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    </Modal>
  );

  return (
    <SafeAreaView style={styles.container}>
      <SimpleMenu />
      <CreateJourneyModal visible={createModalVisible} onClose={() => setCreateModalVisible(false)} onJourneyCreated={handleJourneyCreated} />

      {/* --- HEADER --- */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => setMenuVisible(true)}>
          <Ionicons name="menu" size={32} color="#fff" />
        </TouchableOpacity>

        {/* TOP RIGHT LOGIC */}
        <View style={{alignItems: 'flex-end'}}>
            {isSyncing && <Text style={{color:'#666', fontSize: 10, marginBottom: 4}}>SYNCING...</Text>}
            
            {selectedJourneyId ? (
                // MODE A: INSIDE A JOURNEY (Click to go back)
                <TouchableOpacity onPress={handleBackToHome}>
                    <Text style={{color:'#888', fontSize:10, fontWeight:'bold', textAlign:'right'}}>CURRENT VIEW</Text>
                    <View style={{flexDirection:'row', alignItems:'center'}}>
                        <Ionicons name="arrow-back" size={14} color="#ff4d4d" style={{marginRight: 4}} />
                        <Text style={{color:'#ff4d4d', fontSize:16, fontWeight:'bold'}}>{headerTitle}</Text>
                    </View>
                </TouchableOpacity>
            ) : (
                // MODE B: HOME SCREEN
                <Text style={{color:'#fff', fontWeight:'bold', fontSize: 16}}>My Journeys</Text>
            )}
        </View>
      </View>

      {/* --- CONTENT AREA --- */}
      <View style={styles.content}>
        
        {selectedJourneyId ? (
            // SHOW OVERVIEW COMPONENT
            <JourneyOverview 
                journeyId={selectedJourneyId} 
                onStatusChange={(name) => setHeaderTitle(name)} 
            />
        ) : (
            // SHOW JOURNEY LIST
            <View style={{flex: 1, width:'100%', padding: 20}}>
                <FlatList
                    data={journeys}
                    keyExtractor={(item) => item.id}
                    contentContainerStyle={{ gap: 15 }}
                    renderItem={({ item }) => (
                        <TouchableOpacity style={styles.card} onPress={() => handleSelectJourney(item)}>
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
        )}

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

  // Menu
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', flexDirection: 'row' },
  menuContainer: { width: '70%', backgroundColor: '#1a1a1a', height: '100%', padding: 20, paddingTop: 60 },
  menuHeader: { color: '#666', fontSize: 12, fontWeight: 'bold', marginBottom: 30, letterSpacing: 1 },
  menuItem: { flexDirection: 'row', alignItems: 'center', marginBottom: 25 },
  menuText: { color: 'white', fontSize: 18, marginLeft: 15, fontWeight: '500' },
});