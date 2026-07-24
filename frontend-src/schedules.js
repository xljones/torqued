// Helpers for displaying service schedules (minor / major / custom recurring services).
import { fmtDistance } from './units.js';

export const SCHEDULE_KIND_LABELS = Object.freeze({
  minor: 'Minor service',
  major: 'Major service',
  custom: 'Custom',
});

// A schedule's display title: its name if set, else a label for its kind.
export function scheduleTitle(s) {
  return (s.name && s.name.trim()) || SCHEDULE_KIND_LABELS[s.kind] || 'Service';
}

// A human summary of a schedule's interval, e.g. "every 12 months / every 5,000 mi".
export function scheduleInterval(s, unit) {
  const parts = [];
  if (s.interval_months) parts.push(`every ${s.interval_months} month${s.interval_months === 1 ? '' : 's'}`);
  if (s.interval_km != null) parts.push(`every ${fmtDistance(s.interval_km, unit)}`);
  return parts.join(' / ') || '—';
}
