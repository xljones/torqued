import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MileageCard } from './VehicleDetail';
import { api } from '../api.js';

vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));

vi.mock('../api.js', () => ({
  api: {
    getMileage: vi.fn(),
    createOdometerLog: vi.fn(),
    deleteOdometerLog: vi.fn(),
  },
}));

const KM_PER_MILE = 1.609344;
const mi = (m) => m * KM_PER_MILE; // build canonical-km fixtures from round mile values

// Oldest-first, as GET /api/vehicles/<id>/mileage returns it. Includes a same-day pair
// (service logged the same day as a manual reading) to exercise the "<1 day" interval.
const series = [
  { source: 'manual', id: 1, date: '2025-01-01', odometer_km: mi(10000), unit: 'mi', note: 'start' },
  { source: 'manual', id: 2, date: '2025-01-08', odometer_km: mi(10400), unit: 'mi', note: 'a week later' },
  { source: 'service', id: 3, date: '2025-01-08', odometer_km: mi(10410), unit: 'mi', note: 'same-day service' },
  { source: 'manual', id: 4, date: '2026-01-08', odometer_km: mi(20410), unit: 'mi', note: 'a year on' },
];

const vehicle = {
  id: 1,
  odometer_unit: 'mi',
  latest_odometer: { odometer_km: mi(20410), date: '2026-01-08' },
};

describe('MileageCard — "Since previous" column', () => {
  it('shows the distance and interval since the chronologically previous entry', async () => {
    api.getMileage.mockResolvedValue(series);
    render(<MileageCard vehicle={vehicle} ro />);

    await userEvent.click(await screen.findByRole('button', { name: /Entries \(4\)/ }));

    expect(screen.getByText('+400 mi in 7 days')).toBeInTheDocument();
    expect(screen.getByText('+10,000 mi in 1 year')).toBeInTheDocument();
    expect(screen.getByText('+10 mi in <1 day')).toBeInTheDocument(); // same-day pair
    expect(screen.getByText('—')).toBeInTheDocument(); // oldest row has no previous entry
  });

  it('uses compact interval labels when the viewport is narrow', async () => {
    const original = window.matchMedia;
    window.matchMedia = (query) => ({
      matches: true, // pretend we're below the mobile breakpoint
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    });
    try {
      api.getMileage.mockResolvedValue(series);
      render(<MileageCard vehicle={vehicle} ro />);

      await userEvent.click(await screen.findByRole('button', { name: /Entries \(4\)/ }));

      expect(screen.getByText('+400 mi in 7d')).toBeInTheDocument();
      expect(screen.getByText('+10,000 mi in 1y')).toBeInTheDocument();
      expect(screen.getByText('+10 mi in <1d')).toBeInTheDocument();
    } finally {
      window.matchMedia = original;
    }
  });
});
