import React, { useState } from 'react';
import { Alert, StyleSheet, View, Text, TextInput, TouchableOpacity, ActivityIndicator } from 'react-native';

// Sign-in with the access token printed by `python -m manage add-athlete` on the server.
export default function Auth({ onSignIn }) {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSignIn() {
    if (!token.trim()) return Alert.alert("Access token", "Paste the token you got from the server.");
    setLoading(true);
    try {
      await onSignIn(token);
    } catch (e) {
      Alert.alert("Sign-in failed", e.message);
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.header}>🚴 Virtual Coach</Text>
      <Text style={styles.subHeader}>Paste your access token to sign in.</Text>
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          placeholder="Access token"
          placeholderTextColor="#888"
          onChangeText={setToken}
          value={token}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
        />
      </View>

      <TouchableOpacity
        style={styles.button}
        onPress={handleSignIn}
        disabled={loading}
      >
        {loading ? <ActivityIndicator color="#fff" /> : (
          <Text style={styles.buttonText}>Sign In</Text>
        )}
      </TouchableOpacity>

      <Text style={styles.hint}>
        No token yet? On the server run{'\n'}python -m manage add-athlete "Your name"
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 20, backgroundColor: '#111' },
  header: { fontSize: 32, fontWeight: 'bold', color: '#ff4d4d', textAlign: 'center', marginBottom: 10 },
  subHeader: { fontSize: 16, color: '#ccc', textAlign: 'center', marginBottom: 40 },
  inputContainer: { gap: 15, marginBottom: 30 },
  input: { backgroundColor: '#222', color: '#fff', padding: 15, borderRadius: 8, borderWidth: 1, borderColor: '#333' },
  button: { backgroundColor: '#ff4d4d', padding: 15, borderRadius: 8, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
  hint: { color: '#666', textAlign: 'center', marginTop: 30, fontSize: 12, lineHeight: 18 },
});
