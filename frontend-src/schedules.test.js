import { describe, it, expect } from 'vitest';
import { scheduleTitle, scheduleInterval } from './schedules.js';
import { SCHEDULE_KIND_LABELS } from './constants.js';

describe('scheduleTitle', () => {
  it('uses the name when set', () => {
    expect(scheduleTitle({ kind: 'custom', name: 'Valve check' })).toBe('Valve check');
  });

  it('falls back to a kind label when unnamed', () => {
    expect(scheduleTitle({ kind: 'minor', name: null })).toBe('Minor service');
    expect(scheduleTitle({ kind: 'major', name: '  ' })).toBe('Major service');
  });

  it('has a label for every kind', () => {
    expect(Object.keys(SCHEDULE_KIND_LABELS)).toEqual(['minor', 'major', 'custom']);
  });
});

describe('scheduleInterval', () => {
  it('formats a month interval', () => {
    expect(scheduleInterval({ interval_months: 12, interval_km: null }, 'mi')).toBe('every 12 months');
  });

  it('singularises one month', () => {
    expect(scheduleInterval({ interval_months: 1, interval_km: null }, 'mi')).toBe('every 1 month');
  });

  it('formats a distance interval in the vehicle unit', () => {
    // 8046.72 km == 5000 mi
    expect(scheduleInterval({ interval_months: null, interval_km: 8046.72 }, 'mi')).toBe('every 5,000 mi');
  });

  it('combines both intervals', () => {
    expect(scheduleInterval({ interval_months: 12, interval_km: 1000 }, 'km')).toBe('every 12 months / every 1,000 km');
  });

  it('renders a dash when nothing is set', () => {
    expect(scheduleInterval({ interval_months: null, interval_km: null }, 'mi')).toBe('—');
  });
});
