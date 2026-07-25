import { describe, it, expect } from 'vitest';
import { overdueBy } from './reminders.js';

const TODAY = '2026-07-25';

describe('overdueBy', () => {
  it('returns null when not overdue', () => {
    expect(overdueBy({ status: 'due_soon', next_due_date: '2026-08-01' }, 'mi', TODAY)).toBeNull();
    expect(overdueBy({ status: 'upcoming', next_due_date: '2027-01-01' }, 'mi', TODAY)).toBeNull();
  });

  it('reports how long overdue by date', () => {
    // ~6 months before today
    expect(overdueBy({ status: 'overdue', next_due_date: '2026-01-25' }, 'mi', TODAY))
      .toBe('6 months overdue');
  });

  it('reports how far overdue by distance', () => {
    // km_remaining negative = overshoot; 804.672 km == 500 mi
    expect(overdueBy({ status: 'overdue', next_due_km: 1000, km_remaining: -804.672 }, 'mi', TODAY))
      .toBe('500 mi overdue');
  });

  it('combines date and distance when overdue on both', () => {
    expect(overdueBy(
      { status: 'overdue', next_due_date: '2026-07-14', km_remaining: -160.9344 }, 'mi', TODAY,
    )).toBe('11 days / 100 mi overdue');
  });

  it('ignores a future due date and a positive km_remaining', () => {
    // status overdue via km, but next_due_date is in the future and km_remaining positive
    expect(overdueBy(
      { status: 'overdue', next_due_date: '2027-01-01', km_remaining: 200 }, 'mi', TODAY,
    )).toBeNull();
  });

  it('works for a date-only reminder (e.g. MOT/tax)', () => {
    expect(overdueBy({ status: 'overdue', type: 'mot', next_due_date: '2026-07-15' }, 'mi', TODAY))
      .toBe('10 days overdue');
  });
});
