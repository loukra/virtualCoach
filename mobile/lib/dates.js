// mobile/lib/dates.js

// YYYY-MM-DD in the phone's timezone. toISOString() would use UTC and,
// shortly after midnight in Germany, return yesterday.
export function localDateString(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

// "2026-11-01" as a local date (new Date("2026-11-01") would be midnight UTC).
export function parseLocalDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function weekdayName(iso, style = 'long') {
  return parseLocalDate(iso).toLocaleDateString('en-GB', { weekday: style });
}
