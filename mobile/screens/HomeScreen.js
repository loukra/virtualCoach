import React, { useEffect, useState } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { supabase } from '../lib/supabase';
// ADD THIS IMPORT:
import { useNavigation } from '@react-navigation/native';

export default function HomeScreen() { // Renamed from Dashboard to HomeScreen
  const navigation = useNavigation(); // Hook to control the drawer
  const [loading, setLoading] = useState(true);
  const [journey, setJourney] = useState(null);

  useEffect(() => {
    fetchJourneyStatus();
  }, []);

const fetchJourneyStatus = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;

      // 🔍 UPDATED QUERY:
      // We look directly in 'journeys' table for this user.
      // We sort by 'created_at' to find the NEWEST one.
      const { data: journeyData, error } = await supabase
        .from('journeys')
        .select('name, status') // Fetch name and status
        .eq('user_id', session.user.id)
        .order('created_at', { ascending: false }) // Latest first
        .limit(1)
        .maybeSingle();

      if (error) {
        console.log('Error fetching journey:', error.message);
      }
      
      // If we found a journey, show it. Otherwise, set to null.
      setJourney(journeyData);

    } catch (error) {
      console.log('Unexpected error:', error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateJourney = () => {
    Alert.alert("Coming Soon", "Journey Wizard");
  };

  // 👇 UPDATED FUNCTION
  const toggleMenu = () => {
    navigation.openDrawer(); // This opens the sidebar!
  };

  return (
    <View style={styles.container}>
      {/* ... (Keep your existing JSX exactly the same) ... */}
       <View style={styles.header}>
        <TouchableOpacity onPress={toggleMenu} style={styles.menuButton}>
          <Ionicons name="menu" size={32} color="#fff" />
        </TouchableOpacity>

        <View style={styles.journeyContainer}>
          {loading ? (
            <ActivityIndicator size="small" color="#888" />
          ) : journey ? (
            <View style={styles.journeyBadge}>
              <Text style={styles.journeyLabel}>CURRENT GOAL</Text>
              <Text style={styles.journeyName}>{journey.name}</Text>
            </View>
          ) : (
            <TouchableOpacity style={styles.createButton} onPress={handleCreateJourney}>
              <Text style={styles.createButtonText}>+ Create Journey</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      <View style={styles.content}>
        <Text style={styles.placeholderText}>Today's Training</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // ... (Keep your existing styles exactly the same) ...
  container: { flex: 1, backgroundColor: '#111', paddingTop: 50 },
  header: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 20, paddingBottom: 20, borderBottomWidth: 1, borderBottomColor: '#222' },
  journeyContainer: { alignItems: 'flex-end' },
  journeyBadge: { alignItems: 'flex-end' },
  journeyLabel: { color: '#666', fontSize: 10, fontWeight: 'bold', letterSpacing: 1 },
  journeyName: { color: '#ff4d4d', fontSize: 16, fontWeight: 'bold' },
  createButton: { backgroundColor: '#333', paddingVertical: 8, paddingHorizontal: 16, borderRadius: 20, borderWidth: 1, borderColor: '#444' },
  createButtonText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  content: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  placeholderText: { color: '#fff', fontSize: 20, fontWeight: 'bold' },
});