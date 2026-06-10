import { describe, it, expect } from 'vitest';
import {
  toKm, fromKm, psiToBar, barToPsi,
  fmtDistance, fmtDistanceBoth, fmtPressure, fmtCost,
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

  it('formats pressures in both units', () => {
    expect(fmtPressure(36)).toBe('36 psi / 2.48 bar');
    expect(fmtPressure(null)).toBeNull();
  });

  it('formats costs', () => {
    expect(fmtCost(342)).toBe('342.00');
    expect(fmtCost(null)).toBeNull();
  });
});
