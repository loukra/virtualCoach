// Parses a typed number ("75,5" or "75.5"). Returns null for anything that is not one plain number
// inside [min, max], so "75,575,5" from repeated pastes is rejected instead of silently stored.
export function parseNumber(text, { min, max, integer = false } = {}) {
  const cleaned = String(text ?? '').trim().replace(',', '.');
  const pattern = integer ? /^\d+$/ : /^\d+(\.\d+)?$/;
  if (!pattern.test(cleaned)) return null;
  const value = Number(cleaned);
  if (min !== undefined && value < min) return null;
  if (max !== undefined && value > max) return null;
  return value;
}

// Same limits as backend/models.py.
export const LIMITS = {
  ftp: { min: 50, max: 600, integer: true, label: 'FTP', unit: 'W' },
  max_heart_rate: { min: 120, max: 230, integer: true, label: 'Max heart rate', unit: 'bpm' },
  weight: { min: 30, max: 200, label: 'Weight', unit: 'kg' },
};

export function rangeMessage(key) {
  const l = LIMITS[key];
  return `${l.label} must be a number between ${l.min} and ${l.max} ${l.unit}.`;
}
