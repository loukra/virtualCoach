import React, { useEffect, useRef, useState } from 'react';
import { Animated, Pressable, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../theme';

// The plus button and the options that fan out of it: tapping the plus opens them above it
// (the plus turns into a close button), tapping an option or anywhere else closes them.
export default function AddMenu({ options }) {
  const [open, setOpen] = useState(false);
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(progress, { toValue: open ? 1 : 0, useNativeDriver: true, friction: 7, tension: 80 }).start();
  }, [open]);

  const choose = (option) => {
    setOpen(false);
    option.run();
  };

  const rotate = progress.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '45deg'] });
  return (
    <>
      {open && <Pressable style={StyleSheet.absoluteFill} onPress={() => setOpen(false)} accessibilityLabel="Close menu" />}
      <Animated.View pointerEvents="none" style={[styles.backdrop, { opacity: progress.interpolate({ inputRange: [0, 1], outputRange: [0, 0.6] }) }]} />
      <View style={styles.anchor} pointerEvents="box-none">
        {options.map((option, i) => {
          // Items rise from the plus, the nearest first, and fade in as they go.
          const distance = (options.length - i) * 14;
          return (
            <Animated.View
              key={option.label}
              pointerEvents={open ? 'auto' : 'none'}
              style={{
                opacity: progress,
                transform: [
                  { translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [distance, 0] }) },
                  { scale: progress.interpolate({ inputRange: [0, 1], outputRange: [0.8, 1] }) },
                ],
              }}
            >
              <TouchableOpacity style={styles.item} onPress={() => choose(option)} accessibilityLabel={option.label}>
                <Text style={styles.label}>{option.label}</Text>
                <View style={[styles.icon, { backgroundColor: option.color }]}>
                  <Ionicons name={option.icon} size={18} color={colors.text} />
                </View>
              </TouchableOpacity>
            </Animated.View>
          );
        })}
        <TouchableOpacity
          style={styles.fab}
          onPress={() => setOpen(!open)}
          accessibilityLabel={open ? 'Close menu' : 'Add journey, race or time off'}
        >
          <Animated.View style={{ transform: [{ rotate }] }}>
            <Ionicons name="add" size={30} color={colors.text} />
          </Animated.View>
        </TouchableOpacity>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: '#000' },
  anchor: { position: 'absolute', right: 20, bottom: 30, alignItems: 'flex-end', gap: 12 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingLeft: 6 },
  label: {
    color: colors.text, fontSize: 15, fontWeight: '600', backgroundColor: '#262626', paddingVertical: 8,
    paddingHorizontal: 12, borderRadius: 10, overflow: 'hidden',
  },
  icon: { width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center', marginRight: 8 },
  fab: {
    backgroundColor: colors.accent, width: 60, height: 60, borderRadius: 30, justifyContent: 'center', alignItems: 'center',
    elevation: 5, shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 4,
  },
});
