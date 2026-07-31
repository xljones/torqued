// Distances are stored canonically in km, tyre pressures in psi.
export const KM_PER_MILE = 1.609344;
export const PSI_PER_BAR = 14.503773773;

export const toKm = (value, unit) => (unit === 'mi' ? value * KM_PER_MILE : value);
export const fromKm = (km, unit) => (unit === 'mi' ? km / KM_PER_MILE : km);

export const psiToBar = (psi) => psi / PSI_PER_BAR;
export const barToPsi = (bar) => bar * PSI_PER_BAR;

const otherUnit = (unit) => (unit === 'mi' ? 'km' : 'mi');

/** "12,800 mi" in the given display unit. */
export function fmtDistance(km, unit) {
  if (km == null) return null;
  return `${Math.round(fromKm(km, unit)).toLocaleString()} ${unit}`;
}

/** "12,800 mi (20,600 km)" — primary unit with the conversion alongside. */
export function fmtDistanceBoth(km, unit) {
  if (km == null) return null;
  return `${fmtDistance(km, unit)} (${fmtDistance(km, otherUnit(unit))})`;
}

/** "+400 mi" / "−12 mi" / "±0 mi" — a signed odometer delta in the display unit. */
export function fmtDistanceDelta(deltaKm, unit) {
  if (deltaKm == null) return null;
  const v = Math.round(fromKm(deltaKm, unit));
  const sign = v > 0 ? '+' : v < 0 ? '−' : '±';
  return `${sign}${Math.abs(v).toLocaleString()} ${unit}`;
}

/**
 * Humanised interval length. Full: "<1 day", "7 days", "3 months", "1 year", "1.5 years".
 * Compact (for tight layouts): "<1d", "7d", "3mo", "1y", "1.5y".
 */
export function fmtInterval(days, { compact = false } = {}) {
  if (days == null) return null;
  const d = Math.round(days);
  if (d <= 0) return compact ? '<1d' : '<1 day'; // same-day (or same-value) neighbours
  if (d < 31) return compact ? `${d}d` : `${d} ${d === 1 ? 'day' : 'days'}`;
  if (d < 365) {
    const m = Math.max(1, Math.round(d / 30.44));
    return compact ? `${m}mo` : `${m} ${m === 1 ? 'month' : 'months'}`;
  }
  const y = Math.round((d / 365.25) * 10) / 10; // 1 dp
  const yv = Number.isInteger(y) ? y : y.toFixed(1);
  return compact ? `${yv}y` : `${yv} ${y === 1 ? 'year' : 'years'}`;
}

/** "36 psi / 2.48 bar" */
export function fmtPressure(psi) {
  if (psi == null) return null;
  const p = Number(psi);
  return `${+p.toFixed(1)} psi / ${psiToBar(p).toFixed(2)} bar`;
}

/** "36psi (2.5 bar)" — compact, psi rounded to a whole number, bar to 1 dp. */
export function fmtPressurePsiBar(psi) {
  if (psi == null) return null;
  const p = Number(psi);
  return `${Math.round(p)}psi (${psiToBar(p).toFixed(1)} bar)`;
}

export function fmtCost(cost) {
  if (cost == null) return null;
  return Number(cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** "VOLKSWAGEN PASSAT" → "Volkswagen Passat". Tidies the all-caps text the DVSA returns;
 *  imperfect for names that aren't plain words (BMW → "Bmw", McLaren → "Mclaren"). Preserves
 *  null/undefined so callers can pass values straight through. */
export function titleCase(str) {
  if (str == null) return str;
  return String(str)
    .toLowerCase()
    .replace(/(^|[\s\-/])([a-z])/g, (_, sep, ch) => sep + ch.toUpperCase());
}

// UK registration formats, most-specific first. Each `re` splits the (uppercased,
// spaceless) plate into exactly two groups so the canonical single space sits between
// them; `label` names the era for tooltips. Shared by formatReg and regPlateType.
const PLATE_FORMATS = [
  // Current (Sep 2001+):  AA00 AAA
  { label: 'Current style (2001–present)', re: /^([A-Z]{2}[0-9]{2})([A-Z]{3})$/ },
  // Prefix (1983-2001):   A000 AAA   (year letter + 1-3 digits, then 3 letters)
  { label: 'Prefix (1983–2001)', re: /^([A-Z][0-9]{1,3})([A-Z]{3})$/ },
  // Suffix (1963-1983):   AAA 000A   (3 letters, then 1-3 digits + year letter)
  { label: 'Suffix (1963–1983)', re: /^([A-Z]{3})([0-9]{1,3}[A-Z])$/ },
  // Dateless (pre-1963):  AAA 0000   (1-3 letters, then 1-4 digits) — covers NI (I/Z allowed)
  { label: 'Dateless (pre-1963)', re: /^([A-Z]{1,3})([0-9]{1,4})$/ },
  // Reverse dateless:     0000 AAA   (1-4 digits, then 1-3 letters)
  { label: 'Dateless (pre-1963)', re: /^([0-9]{1,4})([A-Z]{1,3})$/ },
];

const UNKNOWN_PLATE_LABEL = 'Personalised / unrecognised';

// Uppercase + strip whitespace — the canonical spaceless key both plate helpers match on.
const canonicalReg = (reg) => String(reg).toUpperCase().replace(/\s+/g, '');

/**
 * Format a UK registration for display: uppercase, strip any existing spaces, then
 * re-insert the canonical single space per the plate's era/format (checked most
 * specific first). If it matches no known UK pattern, return it uppercased with no
 * inserted space — today's behaviour — so personalised/foreign plates render as-is.
 * Display-only: the stored value is never touched.
 */
export function formatReg(reg) {
  if (!reg) return '';
  const s = canonicalReg(reg);
  for (const { re } of PLATE_FORMATS) {
    const m = s.match(re);
    if (m) return `${m[1]} ${m[2]}`;
  }
  return s; // Unknown format — uppercase, no inserted space (today's fallback).
}

/**
 * Classify a UK registration by era ("Current style", "Prefix", "Dateless", …) for
 * display hints such as tooltips. Returns 'Personalised / unrecognised' for anything
 * that matches no known pattern, or null for an empty value.
 */
export function regPlateType(reg) {
  if (!reg) return null;
  const s = canonicalReg(reg);
  for (const { label, re } of PLATE_FORMATS) {
    if (re.test(s)) return label;
  }
  return UNKNOWN_PLATE_LABEL;
}
