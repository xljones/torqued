// Shared MOT / tax status → colour "tone" logic, used by both the vehicle-detail card
// tiles and the slimmed-down vehicle-list badges so their colours never drift apart.
// A tone is one of 'ok' | 'warn' | 'danger' | null, mapped to CSS by each consumer.

export function isPast(dateStr) {
  const d = new Date(dateStr);
  return !Number.isNaN(d.getTime()) && d < new Date();
}

// Tone for a date-driven expiry: green comfortably ahead, amber within a month, red once
// past. null when there's no (valid) date.
export function expiryTone(dateStr) {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return null;
  const inAMonth = new Date();
  inAMonth.setMonth(inAMonth.getMonth() + 1);
  if (date < new Date()) return 'danger';
  if (date <= inAMonth) return 'warn';
  return 'ok';
}

// Tax: Taxed green, SORN amber (off the road on purpose), anything else (Untaxed / not
// taxed for on-road use) red. null when unknown.
export function taxTone(status) {
  const s = (status || '').toLowerCase();
  if (s === 'taxed') return 'ok';
  if (s === 'sorn') return 'warn';
  if (!s) return null;
  return 'danger';
}

// MOT: a failed latest test is always red; otherwise colour by expiry.
export function motTone(expiry, failed) {
  return failed ? 'danger' : expiryTone(expiry);
}

// Compact magnitude of the gap between now and a date — "3d", "10mo", "2y" — to keep the
// vehicle-list status band tight. Direction (future/past) is conveyed by the caller's verb.
export function compactAge(dateStr) {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return '';
  const days = Math.round(Math.abs(Date.now() - d.getTime()) / 86_400_000);
  if (days < 30) return `${days}d`;
  const months = Math.round(days / 30.44);
  if (months < 12) return `${months}mo`;
  return `${Math.round(months / 12)}y`;
}
