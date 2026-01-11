import React, { useState } from 'react';
import { StyleSheet, View, Text, TextInput, TouchableOpacity, Alert } from 'react-native';
import { supabase } from '../lib/supabase';

export default function SetupProfile({ session, onProfileComplete }) {
  const [step, setStep] = useState(0); // 0=Goal, 1=FTP, 2=HR, 3=Weight
  const [answers, setAnswers] = useState({
    goal: '',
    ftp: '',
    max_heart_rate: '',
    weight: ''
  });

  const questions = [
    { key: 'goal', label: 'What is your main cycling goal?', placeholder: 'e.g. Finish a Century, Get faster', type: 'default' },
    { key: 'ftp', label: 'What is your estimated FTP?', placeholder: 'e.g. 200 (Watts)', type: 'numeric' },
    { key: 'max_heart_rate', label: 'What is your Max Heart Rate?', placeholder: 'e.g. 190 (BPM)', type: 'numeric' },
    { key: 'weight', label: 'What is your weight (kg)?', placeholder: 'e.g. 75', type: 'numeric' }
  ];

  const handleNext = async () => {
    // Basic Validation
    if (!answers[questions[step].key]) {
      return Alert.alert("Required", "Please fill in the field.");
    }

    if (step < questions.length - 1) {
      setStep(step + 1);
    } else {
      await saveProfile();
    }
  };

  const saveProfile = async () => {
    const { error } = await supabase
      .from('profiles')
      .update({
        goal: answers.goal,
        ftp: parseInt(answers.ftp),
        max_heart_rate: parseInt(answers.max_heart_rate),
        weight: parseFloat(answers.weight),
        // Important: Mark profile as "filled" so we don't ask again
        has_completed_onboarding: true 
      })
      .eq('id', session.user.id);

    if (error) Alert.alert("Error", error.message);
    else onProfileComplete();
  };

  return (
    <View style={styles.container}>
      <Text style={styles.stepIndicator}>Step {step + 1} of 4</Text>
      
      <Text style={styles.question}>{questions[step].label}</Text>
      
      <TextInput
        style={styles.input}
        placeholder={questions[step].placeholder}
        placeholderTextColor="#666"
        keyboardType={questions[step].type}
        value={answers[questions[step].key]}
        onChangeText={(text) => setAnswers({ ...answers, [questions[step].key]: text })}
      />

      <TouchableOpacity style={styles.button} onPress={handleNext}>
        <Text style={styles.buttonText}>
          {step === questions.length - 1 ? "Finish & Sync" : "Next"}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 20, backgroundColor: '#111' },
  stepIndicator: { color: '#ff4d4d', fontSize: 14, marginBottom: 10, textAlign: 'center' },
  question: { color: '#fff', fontSize: 24, fontWeight: 'bold', marginBottom: 30, textAlign: 'center' },
  input: { backgroundColor: '#222', color: '#fff', padding: 20, borderRadius: 10, fontSize: 18, marginBottom: 30, borderWidth: 1, borderColor: '#333' },
  button: { backgroundColor: '#ff4d4d', padding: 15, borderRadius: 8, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 18 }
});