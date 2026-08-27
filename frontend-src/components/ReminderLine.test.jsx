import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ReminderLine from './ReminderLine';

const base = {
  vehicle_id: 1, vehicle_name: 'Street Triple', vehicle_odometer_unit: 'mi',
  next_due_km: null, km_remaining: null,
};

const renderLine = (reminder, unit) =>
  render(<div className="reminder-row"><ReminderLine reminder={reminder} unit={unit} /></div>);

describe('ReminderLine', () => {
  it('renders a service reminder from its anchoring log', () => {
    renderLine({
      ...base, type: 'service', id: 7, title: 'Annual service', category: 'Service',
      date: '2025-04-05', status: 'upcoming', next_due_date: '2027-04-05',
    });
    expect(screen.getByText('Service')).toBeInTheDocument();
    expect(screen.getByText(/After “Annual service” \(2025-04-05\) — due 2027-04-05/)).toBeInTheDocument();
    expect(screen.getByText('Upcoming')).toBeInTheDocument();
  });

  it('falls back to the title when a reminder has no category', () => {
    renderLine({
      ...base, type: 'schedule', id: 3, title: 'Minor service', category: null,
      date: '2024-06-15', status: 'upcoming', next_due_date: '2027-06-15',
    });
    expect(screen.getByText('Minor service')).toBeInTheDocument();
  });

  it('shows the distance still to run, in the given unit', () => {
    renderLine({
      ...base, type: 'service', id: 7, title: 'Oil change', category: 'Oil change',
      date: '2025-04-05', status: 'due_soon', next_due_date: null,
      next_due_km: 3218.688, km_remaining: 160.9344,
    }, 'mi');
    expect(screen.getByText(/due at 2,000 mi \(100 mi to go\)/)).toBeInTheDocument();
    expect(screen.getByText('Due soon')).toBeInTheDocument();
  });

  it('renders MOT and tax reminders as expiry lines', () => {
    const { unmount } = renderLine({
      ...base, type: 'mot', id: null, title: 'MOT', category: 'MOT', date: null,
      status: 'due_soon', next_due_date: '2026-07-15',
    });
    expect(screen.getByText('Expires 2026-07-15')).toBeInTheDocument();
    unmount();

    renderLine({
      ...base, type: 'tax', id: null, title: 'Road tax', category: 'Tax', date: null,
      status: 'overdue', next_due_date: '2020-08-01',
    });
    expect(screen.getByText('Expired 2020-08-01')).toBeInTheDocument();
  });

  it('appends how far past due an overdue reminder is', () => {
    renderLine({
      ...base, type: 'service', id: 7, title: 'Oil change', category: 'Oil change',
      date: '2020-01-01', status: 'overdue', next_due_date: null,
      next_due_km: 1000, km_remaining: -160.9344,
    }, 'mi');
    expect(screen.getByText(/100 mi overdue/)).toBeInTheDocument();
  });

  it('defaults the unit to the reminder’s own vehicle unit', () => {
    renderLine({
      ...base, vehicle_odometer_unit: 'km', type: 'service', id: 7, title: 'Oil change',
      category: 'Oil change', date: '2025-04-05', status: 'upcoming', next_due_date: null,
      next_due_km: 1000,
    });
    expect(screen.getByText(/due at 1,000 km/)).toBeInTheDocument();
  });
});
