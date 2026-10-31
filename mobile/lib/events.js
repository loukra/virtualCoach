// Races, group rides and time off (backend/logic/events.py): shared labels, icons and messages.
import { parseLocalDate } from './dates';

export const EVENT_KINDS = {
  race: { label: 'Race', icon: 'flag', color: '#af7ac5' },
  ride: { label: 'Group ride', icon: 'people', color: '#5dade2' },
  off: { label: 'Time off', icon: 'airplane', color: '#8e8e9a' },
};

export const PRIORITIES = {
  A: { label: 'Main race', hint: 'Your coach tapers into it and lets you recover afterwards.' },
  B: { label: 'Secondary race', hint: 'Ridden from normal training: easy days around it, no taper.' },
};

function shortDate(iso) {
  return parseLocalDate(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
}

export function eventWhen(event) {
  if (event.end_date && event.end_date !== event.start_date) {
    return `${shortDate(event.start_date)} – ${shortDate(event.end_date)}`;
  }
  return shortDate(event.start_date);
}

export function eventSubtitle(event) {
  const parts = [eventWhen(event)];
  if (event.kind === 'race') parts.push(PRIORITIES[event.priority].label);
  if (event.kind === 'off') parts.push('no training');
  if (event.duration_min) parts.push(`about ${formatMinutes(event.duration_min)}`);
  return parts.join(' · ');
}

export function formatMinutes(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

// One short line on what happened to the plans covering the event (backend routers/events.py update_plans).
export function planOutcomeText(what, journeys) {
  if (!journeys.length) return `${what}. A journey for these dates will plan around it.`;
  const { name, plan } = journeys[0];
  if (plan === 'scheduled') return `${what}. "${name}" plans around it when it starts.`;
  if (plan === 'this_week') return `${what}. Today's suggestion takes it into account.`;
  return `${what}. Adapting "${name}" from Monday on.`;
}

// Events of a journey's date range, its own race first in time order with the others.
export function journeyEvents(journey, events) {
  const inside = events.filter((e) => e.start_date <= journey.race_date && e.end_date >= journey.start_date);
  if (journey.goal_type === 'race') {
    inside.push({ id: 'goal', kind: 'race', priority: 'A', name: journey.name, start_date: journey.race_date,
      end_date: journey.race_date, goal: true });
  }
  return inside.sort((a, b) => a.start_date.localeCompare(b.start_date));
}
