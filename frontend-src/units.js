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

/** Humanised interval length: "<1 day", "7 days", "3 months", "1 year", "1.5 years". */
export function fmtInterval(days) {
  if (days == null) return null;
  const d = Math.round(days);
  if (d <= 0) return '<1 day'; // same-day (or same-value) neighbours
  if (d < 31) return `${d} ${d === 1 ? 'day' : 'days'}`;
  if (d < 365) {
    const m = Math.max(1, Math.round(d / 30.44));
    return `${m} ${m === 1 ? 'month' : 'months'}`;
  }
  const y = Math.round((d / 365.25) * 10) / 10; // 1 dp
  return `${Number.isInteger(y) ? y : y.toFixed(1)} ${y === 1 ? 'year' : 'years'}`;
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
