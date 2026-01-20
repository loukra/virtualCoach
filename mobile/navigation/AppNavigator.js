// mobile/navigation/AppNavigator.js
import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { View, Text, TouchableOpacity } from 'react-native';
import { supabase } from '../lib/supabase';
import ProfileScreen from '../screens/ProfileScreen';
// Screens
import Dashboard from '../screens/Dashboard';
import TrainingPlanView from '../screens/TrainingPlanView'; 
import JourneyOverview from '../components/JourneyOverview'; 

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

// --- 1. THE HOME STACK (Allows navigation while keeping tabs) ---
function HomeStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Dashboard" component={Dashboard} />
      <Stack.Screen name="JourneyDetail" component={JourneyOverview} />
    </Stack.Navigator>
  );
}


// --- 3. THE MAIN TABS ---
export default function AppNavigator() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false, 
        tabBarStyle: { 
            backgroundColor: '#1a1a1a', 
            borderTopColor: '#333',
            height: 90, 
            paddingTop: 10,
        },
        tabBarActiveTintColor: '#ff4d4d',
        tabBarInactiveTintColor: '#666',
        tabBarIcon: ({ focused, color, size }) => {
            let iconName;
            if (route.name === 'HomeTab') iconName = focused ? 'home' : 'home-outline';
            else if (route.name === 'Plan') iconName = focused ? 'calendar' : 'calendar-outline';
            else if (route.name === 'Profile') iconName = focused ? 'person' : 'person-outline';
            return <Ionicons name={iconName} size={size} color={color} />;
        },
      })}
    >
      {/* We point the first tab to "HomeStack" instead of "Dashboard".
         This means when you click a Journey, you stay inside this tab!
      */}
      <Tab.Screen 
          name="HomeTab" 
          component={HomeStack} 
          options={{ title: 'Home' }}
      />
      <Tab.Screen name="Plan" component={TrainingPlanView} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}