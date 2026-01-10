import React, { useState } from 'react';
import { Alert, StyleSheet, View, Text, TextInput, TouchableOpacity, ActivityIndicator } from 'react-native';
import { supabase } from '../lib/supabase';

export default function Auth() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [isLogin, setIsLogin] = useState(true); // Toggle between Login/Sign Up

  async function handleAuth() {
    setLoading(true);
    
    if (isLogin) {
      // --- LOG IN ---
      const { error } = await supabase.auth.signInWithPassword({
        email: email,
        password: password,
      });
      if (error) Alert.alert("Login Failed", error.message);
    } else {
      // --- REGISTER ---
      const { error } = await supabase.auth.signUp({
        email: email,
        password: password,
      });
      if (error) Alert.alert("Registration Error", error.message);
      else Alert.alert("Success!", "Account created. Please check your email (if verification is on).");
    }
    setLoading(false);
  }

  return (
    <View style={styles.container}>
      <Text style={styles.header}>🚴 AI Coach</Text>
      <Text style={styles.subHeader}>{isLogin ? "Welcome Back" : "Create Account"}</Text>

      <View style={styles.inputContainer}>
<TextInput
          style={styles.input}
          placeholder="email@address.com"
          placeholderTextColor="#888"
          onChangeText={(text) => setEmail(text)}
          value={email}
          autoCapitalize={'none'}
          keyboardType="email-address" // <--- 📧 ADD THIS LINE
        />
        <TextInput
          style={styles.input}
          placeholder="Password"
          placeholderTextColor="#888"
          onChangeText={(text) => setPassword(text)}
          value={password}
          secureTextEntry={true}  // <--- 🔒 ADD THIS LINE
          autoCapitalize={'none'}
        />
      </View>

      <TouchableOpacity 
        style={styles.button} 
        onPress={handleAuth} 
        disabled={loading}
      >
        {loading ? <ActivityIndicator color="#fff" /> : (
          <Text style={styles.buttonText}>{isLogin ? "Sign In" : "Sign Up"}</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity onPress={() => setIsLogin(!isLogin)}>
        <Text style={styles.switchText}>
          {isLogin ? "New here? Create an account" : "Already have an account? Sign in"}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 20, backgroundColor: '#111' },
  header: { fontSize: 32, fontWeight: 'bold', color: '#ff4d4d', textAlign: 'center', marginBottom: 10 },
  subHeader: { fontSize: 18, color: '#ccc', textAlign: 'center', marginBottom: 40 },
  inputContainer: { gap: 15, marginBottom: 30 },
  input: { backgroundColor: '#222', color: '#fff', padding: 15, borderRadius: 8, borderWidth: 1, borderColor: '#333' },
  button: { backgroundColor: '#ff4d4d', padding: 15, borderRadius: 8, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
  switchText: { color: '#888', textAlign: 'center', marginTop: 20, textDecorationLine: 'underline' }
});