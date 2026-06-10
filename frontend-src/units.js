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

/** "36 psi / 2.48 bar" */
export function fmtPressure(psi) {
  if (psi == null) return null;
  const p = Number(psi);
  return `${+p.toFixed(1)} psi / ${psiToBar(p).toFixed(2)} bar`;
}

export function fmtCost(cost) {
  if (cost == null) return null;
  return Number(cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
