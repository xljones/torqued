import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
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

const vehicle = { id: 7, odometer_unit: 'mi', latest_odometer: null };

// A single manual reading: the chart needs ≥2 points to render, so the note text can only
// appear if the (otherwise-collapsed) entries table is open.
const withNote = [
  { id: 1, date: '2025-05-01', odometer_km: 21162.87, source: 'manual', unit: 'mi', note: 'Post-trip reading' },
];

beforeEach(() => vi.clearAllMocks());

describe('MileageCard note visibility', () => {
  it('opens the entries list on load when a manual reading carries a note', async () => {
    api.getMileage.mockResolvedValue(withNote);
    render(<MileageCard vehicle={vehicle} ro={false} />);
    // Visible without expanding the panel or hovering the chart.
    expect(await screen.findByText('Post-trip reading')).toBeInTheDocument();
  });

  it('stays collapsed on load when no reading has a note', async () => {
    api.getMileage.mockResolvedValue([{ ...withNote[0], note: null }]);
    render(<MileageCard vehicle={vehicle} ro={false} />);
    // The entries toggle appears, but the table (and its Note column) stays hidden.
    expect(await screen.findByRole('button', { name: /Entries/ })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Note' })).not.toBeInTheDocument();
  });

  it('reveals the just-logged reading and its note after submitting', async () => {
    api.getMileage.mockResolvedValueOnce([]); // initial load: nothing yet
    api.createOdometerLog.mockResolvedValue({ id: 2 });
    api.getMileage.mockResolvedValue([
      { id: 2, date: '2025-06-01', odometer_km: 1609.34, source: 'manual', unit: 'mi', note: 'Oil top-up' },
    ]); // refresh() after logging returns the new reading
    render(<MileageCard vehicle={vehicle} ro={false} />);
    await userEvent.type(screen.getByPlaceholderText('Odometer'), '1000');
    await userEvent.type(screen.getByPlaceholderText('Note (optional)'), 'Oil top-up');
    await userEvent.click(screen.getByRole('button', { name: 'Log' }));
    expect(await screen.findByText('Oil top-up')).toBeInTheDocument();
  });
});
