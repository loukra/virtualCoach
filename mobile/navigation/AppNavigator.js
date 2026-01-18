// mobile/navigation/AppNavigator.js
import React from 'react';
import { createDrawerNavigator } from '@react-navigation/drawer';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';

// Import your existing screens
import Dashboard from '../screens/Dashboard';
import JourneyOverview from '../components/JourneyOverview'; 

const Drawer = createDrawerNavigator();
const Stack = createNativeStackNavigator();

// 1. The Sidebar Menu (Drawer)
function MainDrawer() {
  return (
    <Drawer.Navigator
      screenOptions={{
        headerShown: false, // We hide the default header to keep your custom dark theme header
        drawerStyle: { backgroundColor: '#1a1a1a', width: '75%' },
        drawerActiveTintColor: '#ff4d4d',
        drawerInactiveTintColor: '#ddd',
        drawerType: 'front', // Slides over the content
      }}
    >
      <Drawer.Screen 
        name="Dashboard" 
        component={Dashboard} 
        options={{
          title: 'Home',
          drawerIcon: ({color}) => <Ionicons name="home-outline" size={22} color={color} />
        }}
      />
      {/* You can add "Settings" or "Profile" here later */}
    </Drawer.Navigator>
  );
}

// 2. The Main Stack (Handles transitions between screens)
export default function AppNavigator() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {/* The base of the app is the Drawer */}
      <Stack.Screen name="Main" component={MainDrawer} />
      
      {/* Detail screens go here (so they cover the drawer when opened) */}
      <Stack.Screen name="JourneyDetail" component={JourneyOverview} />
    </Stack.Navigator>
  );
}