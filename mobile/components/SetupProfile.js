import React, { useState } from 'react';
import { StyleSheet, View, Text, TextInput, TouchableOpacity, Alert } from 'react-native';
import { apiPut } from '../lib/api';
import { parseNumber, LIMITS, rangeMessage } from '../lib/numbers';

export default function SetupProfile({ me, onProfileComplete }) {
  const [step, setStep] = useState(0); // 0=Goal, 1=FTP, 2=HR, 3=Weight
  const [answers, setAnswers] = useState({
    goal: me?.goal || '',
    ftp: me?.ftp ? String(me.ftp) : '',
    max_heart_rate: me?.max_heart_rate ? String(me.max_heart_rate) : '',
    weight: me?.weight_kg ? String(me.weight_kg) : ''
  });

  const questions = [
    { key: 'goal', label: 'What is your main cycling goal?', placeholder: 'e.g. Finish a Century, Get faster', type: 'default' },
    { key: 'ftp', label: 'What is your estimated FTP?', placeholder: 'e.g. 200 (Watts)', type: 'number-pad' },
    { key: 'max_heart_rate', label: 'What is your Max Heart Rate?', placeholder: 'e.g. 190 (BPM)', type: 'number-pad' },
    { key: 'weight', label: 'What is your weight (kg)?', placeholder: 'e.g. 75', type: 'decimal-pad' }
  ];

  const handleNext = async () => {
    const { key } = questions[step];
    if (!answers[key].trim()) {
      return Alert.alert("Required", "Please fill in the field.");
    }
    if (LIMITS[key] && parseNumber(answers[key], LIMITS[key]) === null) {
      return Alert.alert("Check the value", rangeMessage(key));
    }

    if (step < questions.length - 1) {
      setStep(step + 1);
    } else {
      await saveProfile();
    }
  };

  const saveProfile = async () => {
    try {
      await apiPut('/profile', {
        goal: answers.goal.trim(),
        ftp: parseNumber(answers.ftp, LIMITS.ftp),
        max_heart_rate: parseNumber(answers.max_heart_rate, LIMITS.max_heart_rate),
        weight_kg: parseNumber(answers.weight, LIMITS.weight),
      });
      onProfileComplete();
    } catch (e) {
      Alert.alert("Could not save", e.message);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.stepIndicator}>Step {step + 1} of {questions.length}</Text>
      
      <Text style={styles.question}>{questions[step].label}</Text>
      
      <TextInput
        style={styles.input}
        placeholder={questions[step].placeholder}
        placeholderTextColor="#666"
        keyboardType={questions[step].type}
        value={answers[questions[step].key]}
        autoFocus
        returnKeyType="next"
        onSubmitEditing={handleNext}
        onChangeText={(text) => setAnswers({ ...answers, [questions[step].key]: text })}
      />

      <TouchableOpacity style={styles.button} onPress={handleNext}>
        <Text style={styles.buttonText}>
          {step === questions.length - 1 ? "Finish" : "Next"}
        </Text>
      </TouchableOpacity>
      {step > 0 && (
        <TouchableOpacity style={styles.backBtn} onPress={() => setStep(step - 1)}>
          <Text style={styles.backText}>Back</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 20, backgroundColor: '#111' },
  stepIndicator: { color: '#ff4d4d', fontSize: 14, marginBottom: 10, textAlign: 'center' },
  question: { color: '#fff', fontSize: 24, fontWeight: 'bold', marginBottom: 30, textAlign: 'center' },
  input: { backgroundColor: '#222', color: '#fff', padding: 20, borderRadius: 10, fontSize: 18, marginBottom: 30, borderWidth: 1, borderColor: '#333' },
  button: { backgroundColor: '#ff4d4d', padding: 15, borderRadius: 8, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 18 },
  backBtn: { alignItems: 'center', padding: 15, marginTop: 5 },
  backText: { color: '#888', fontSize: 16 }
});