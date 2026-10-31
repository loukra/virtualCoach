import React, { useEffect, useRef } from 'react';
import { Animated, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../theme';

const VISIBLE_MS = 3500;

// A short note at the bottom of the screen that fades out on its own; nothing to tap away.
export default function Toast({ message, onHide, bottom = 24 }) {
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!message) return undefined;
    opacity.setValue(0);
    Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }).start();
    const timer = setTimeout(() => {
      Animated.timing(opacity, { toValue: 0, duration: 300, useNativeDriver: true }).start(() => onHide());
    }, VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [message]);

  if (!message) return null;
  return (
    <Animated.View style={[styles.toast, { opacity, bottom }]} pointerEvents="none" accessibilityLiveRegion="polite">
      <Ionicons name="checkmark-circle" size={18} color={colors.good} />
      <Text style={styles.text}>{message}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute', left: 20, right: 20, flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#262626', borderWidth: 1, borderColor: '#3a3a3a', borderRadius: 12, paddingVertical: 12,
    paddingHorizontal: 14,
    shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 8, shadowOffset: { width: 0, height: 4 },
  },
  text: { color: colors.text, flex: 1, fontSize: 14, lineHeight: 19 },
});
