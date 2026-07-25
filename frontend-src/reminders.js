// Helpers for displaying maintenance reminders.
import { fmtDistance, fmtInterval } from './units.js';

// Whole days between two YYYY-MM-DD dates, parsed as UTC midnight to avoid DST drift.
const daysBetween = (a, b) =>
  Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);

/**
 * For an overdue reminder, how far past due it is — by time and/or by distance.
 * Returns a short human string ("3 months overdue", "250 mi overdue",
 * "3 months / 250 mi overdue") or null when the reminder isn't overdue (or there's
 * nothing measurable to report). `unit` is the vehicle's display unit ('mi'/'km').
 */
export function overdueBy(r, unit, todayIso = new Date().toISOString().slice(0, 10)) {
  if (r.status !== 'overdue') return null;
  const parts = [];
  if (r.next_due_date && r.next_due_date < todayIso) {
    parts.push(fmtInterval(daysBetween(r.next_due_date, todayIso)));
  }
  // km_remaining is next_due_km − current odometer, so a negative value is the overshoot.
  if (r.km_remaining != null && r.km_remaining < 0) {
    parts.push(fmtDistance(-r.km_remaining, unit));
  }
  return parts.length ? `${parts.join(' / ')} overdue` : null;
}
