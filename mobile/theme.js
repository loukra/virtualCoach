// Shared colours so screens stop drifting apart.
export const colors = {
  background: '#111',
  card: '#1a1a1a',
  input: '#333',
  border: '#333',
  text: '#fff',
  textMuted: '#888',
  textFaint: '#666',
  accent: '#ff4d4d',
  good: '#4dff4d',
  warn: '#ffb84d',
};

export const APP_NAME = 'Virtual Coach';

// One colour per session type, easy to hard (types from backend/logic/schemas.py).
export const TYPE_COLORS = {
  Rest: '#333',
  Recovery: '#a0a0a8',
  Endurance: '#5dade2',
  Tempo: '#58d68d',
  'Sweet Spot': '#f4d03f',
  Threshold: '#f5b041',
  'VO2 Max': '#ec7063',
  Anaerobic: '#c0392b',
  'FTP Test': '#ffffff',
  Race: '#af7ac5',
};
