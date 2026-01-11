import React, { useState, useEffect } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, Modal, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { supabase } from '../lib/supabase';

export default function Dashboard() {
  const [menuVisible, setMenuVisible] = useState(false);
  const [journeyName, setJourneyName] = useState(null);

  // Journey laden (wie vorher)
  useEffect(() => {
    async function loadJourney() {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;

      const { data } = await supabase
        .from('journeys')
        .select('name')
        .eq('user_id', session.user.id)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      
      setJourneyName(data?.name);
    }
    loadJourney();
  }, []);

  // --- DAS SICHERE MENÜ (Einfaches Modal) ---
  const SimpleMenu = () => (
    <Modal animationType="fade" transparent={true} visible={menuVisible} onRequestClose={() => setMenuVisible(false)}>
      <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setMenuVisible(false)}>
        <View style={styles.menuContainer}>
          <Text style={styles.menuHeader}>Menu</Text>
          
          <TouchableOpacity style={styles.menuItem} onPress={() => { setMenuVisible(false); console.log("Home"); }}>
            <Ionicons name="home-outline" size={24} color="white" />
            <Text style={styles.menuText}>Home</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.menuItem} onPress={() => { setMenuVisible(false); console.log("Activities"); }}>
            <Ionicons name="bicycle-outline" size={24} color="white" />
            <Text style={styles.menuText}>Activities</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.menuItem} onPress={() => { setMenuVisible(false); console.log("Settings"); }}>
            <Ionicons name="settings-outline" size={24} color="white" />
            <Text style={styles.menuText}>Settings</Text>
          </TouchableOpacity>

          <View style={styles.divider} />

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

      {/* HEADER */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => setMenuVisible(true)}>
          <Ionicons name="menu" size={32} color="#fff" />
        </TouchableOpacity>

        <View>
            {journeyName ? (
                <View style={{alignItems:'flex-end'}}>
                    <Text style={{color:'#888', fontSize:10, fontWeight:'bold'}}>CURRENT GOAL</Text>
                    <Text style={{color:'#ff4d4d', fontSize:16, fontWeight:'bold'}}>{journeyName}</Text>
                </View>
            ) : (
                <Text style={{color:'#ff4d4d', fontWeight:'bold'}}>+ Create Journey</Text>
            )}
        </View>
      </View>

      {/* CONTENT */}
      <View style={styles.content}>
        <Text style={{color:'white', fontSize: 20}}>Ready to Train! 🚴‍♂️</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111', paddingTop: 40 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems:'center', padding: 20, borderBottomWidth: 1, borderBottomColor: '#222' },
  content: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  
  // Menu Styles
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', flexDirection: 'row' },
  menuContainer: { width: '70%', backgroundColor: '#1a1a1a', height: '100%', padding: 20, paddingTop: 60 },
  menuHeader: { color: '#666', fontSize: 12, fontWeight: 'bold', marginBottom: 30, letterSpacing: 1 },
  menuItem: { flexDirection: 'row', alignItems: 'center', marginBottom: 25 },
  menuText: { color: 'white', fontSize: 18, marginLeft: 15, fontWeight: '500' },
  divider: { height: 1, backgroundColor: '#333', marginVertical: 20 },
});