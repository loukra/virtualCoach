import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export function ActivitiesScreen() {
  return (
    <View style={styles.center}>
      <Text style={styles.text}>🚴 Activities Log</Text>
    </View>
  );
}

export function SettingsScreen({ navigation }) {
  // Example of using navigation inside a screen
  return (
    <View style={styles.center}>
      <Text style={styles.text}>⚙️ App Settings</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: '#111', justifyContent: 'center', alignItems: 'center' },
  text: { color: '#fff', fontSize: 20 }
});