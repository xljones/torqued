import { describe, it, expect } from 'vitest';
import {
  toKm, fromKm, psiToBar, barToPsi,
  fmtDistance, fmtDistanceBoth, fmtDistanceDelta, fmtInterval,
  fmtPressure, fmtPressurePsiBar, fmtCost, titleCase, formatReg, regPlateType,
} from './units.js';

describe('units', () => {
  it('converts miles to km and back', () => {
    expect(toKm(100, 'mi')).toBeCloseTo(160.9344);
    expect(toKm(100, 'km')).toBe(100);
    expect(fromKm(160.9344, 'mi')).toBeCloseTo(100);
    expect(fromKm(42, 'km')).toBe(42);
  });

  it('converts psi and bar', () => {
    expect(psiToBar(14.503773773)).toBeCloseTo(1);
    expect(barToPsi(2)).toBeCloseTo(29.0075, 3);
  });

  it('formats distances', () => {
    expect(fmtDistance(160.9344, 'mi')).toBe('100 mi');
    expect(fmtDistance(1609.344, 'km')).toBe('1,609 km');
    expect(fmtDistance(null, 'mi')).toBeNull();
    expect(fmtDistanceBoth(160.9344, 'mi')).toBe('100 mi (161 km)');
  });

  it('formats signed distance deltas in the display unit', () => {
    expect(fmtDistanceDelta(643.7376, 'mi')).toBe('+400 mi'); // 400 mi in km
    expect(fmtDistanceDelta(16093.44, 'mi')).toBe('+10,000 mi');
    expect(fmtDistanceDelta(-19.312128, 'mi')).toBe('−12 mi'); // odometer went backwards
    expect(fmtDistanceDelta(0, 'mi')).toBe('±0 mi');
    expect(fmtDistanceDelta(400, 'km')).toBe('+400 km');
    expect(fmtDistanceDelta(null, 'mi')).toBeNull();
  });

  it('humanises intervals in days/months/years', () => {
    expect(fmtInterval(7)).toBe('7 days');
    expect(fmtInterval(365)).toBe('1 year');
    expect(fmtInterval(1)).toBe('1 day');
    expect(fmtInterval(31)).toBe('1 month');
    expect(fmtInterval(548)).toBe('1.5 years');
    expect(fmtInterval(0)).toBe('<1 day');
    expect(fmtInterval(-3)).toBe('<1 day');
    expect(fmtInterval(null)).toBeNull();
  });

  it('abbreviates intervals in compact mode', () => {
    expect(fmtInterval(7, { compact: true })).toBe('7d');
    expect(fmtInterval(1, { compact: true })).toBe('1d');
    expect(fmtInterval(90, { compact: true })).toBe('3mo');
    expect(fmtInterval(365, { compact: true })).toBe('1y');
    expect(fmtInterval(548, { compact: true })).toBe('1.5y');
    expect(fmtInterval(0, { compact: true })).toBe('<1d');
  });

  it('formats pressures in both units', () => {
    expect(fmtPressure(36)).toBe('36 psi / 2.48 bar');
    expect(fmtPressure(null)).toBeNull();
  });

  it('formats compact psi (bar) pressures', () => {
    expect(fmtPressurePsiBar(36)).toBe('36psi (2.5 bar)');
    expect(fmtPressurePsiBar(42)).toBe('42psi (2.9 bar)');
    expect(fmtPressurePsiBar(null)).toBeNull();
  });

  it('formats costs', () => {
    expect(fmtCost(342)).toBe('342.00');
    expect(fmtCost(null)).toBeNull();
  });

  it('title-cases DVSA all-caps text, leaving nullish and empty values untouched', () => {
    expect(titleCase('VOLKSWAGEN')).toBe('Volkswagen');
    expect(titleCase('LAND ROVER')).toBe('Land Rover');
    expect(titleCase('MERCEDES-BENZ')).toBe('Mercedes-Benz');
    expect(titleCase('')).toBe('');
    expect(titleCase(null)).toBeNull();
    expect(titleCase(undefined)).toBeUndefined();
    expect(titleCase('BMW')).toBe('Bmw'); // documented imperfection for acronym makes
  });

  it('formats UK plates with canonical spacing across eras', () => {
    // Current format (AA00 AAA) — regardless of input case/spacing
    expect(formatReg('ab12cde')).toBe('AB12 CDE');
    expect(formatReg('AB12 CDE')).toBe('AB12 CDE');
    expect(formatReg('AB12  CDE')).toBe('AB12 CDE');
    // Prefix (A000 AAA)
    expect(formatReg('v292ktx')).toBe('V292 KTX');
    expect(formatReg('a1xyz')).toBe('A1 XYZ');
    // Suffix (AAA 000A)
    expect(formatReg('abc123a')).toBe('ABC 123A');
    // Dateless / Northern Ireland (AAA 0000) — I/Z allowed
    expect(formatReg('aaz1234')).toBe('AAZ 1234');
    expect(formatReg('abc123')).toBe('ABC 123');
    // Reverse dateless (0000 AAA)
    expect(formatReg('1abc')).toBe('1 ABC');
  });

  it('leaves unrecognised plates uppercased with no inserted space', () => {
    expect(formatReg('qwerty')).toBe('QWERTY');
    expect(formatReg('abcdefghij')).toBe('ABCDEFGHIJ');
    expect(formatReg('  a b c ')).toBe('ABC'); // collapses stray whitespace
  });

  it('returns empty string for nullish/empty plates', () => {
    expect(formatReg('')).toBe('');
    expect(formatReg(null)).toBe('');
    expect(formatReg(undefined)).toBe('');
  });

  it('classifies plates by era, tolerant of input case/spacing', () => {
    expect(regPlateType('ab12 cde')).toBe('Current style (2001–present)');
    expect(regPlateType('v292ktx')).toBe('Prefix (1983–2001)');
    expect(regPlateType('abc123a')).toBe('Suffix (1963–1983)');
    expect(regPlateType('aaz1234')).toBe('Dateless (pre-1963)'); // NI, I/Z allowed
    expect(regPlateType('1abc')).toBe('Dateless (pre-1963)'); // reversed
    expect(regPlateType('qwerty')).toBe('Personalised / unrecognised');
  });

  it('returns null plate type for nullish/empty plates', () => {
    expect(regPlateType('')).toBeNull();
    expect(regPlateType(null)).toBeNull();
    expect(regPlateType(undefined)).toBeNull();
  });
});
