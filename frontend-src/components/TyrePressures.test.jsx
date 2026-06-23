import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import TyrePressures from './TyrePressures';

const vehicles = [
  {
    id: 1, name: 'Street Triple',
    tyre_size_front: '120/70 ZR17', tyre_size_rear: '180/55 ZR17',
    tyre_pressure_front_psi: 36, tyre_pressure_rear_psi: 42,
  },
  {
    id: 2, name: 'Daily',
    tyre_size_front: null, tyre_size_rear: null,
    tyre_pressure_front_psi: null, tyre_pressure_rear_psi: null,
  },
];

vi.mock('../api.js', () => ({
  api: { getVehicles: vi.fn().mockResolvedValue([]) },
}));

import { api } from '../api.js';

vi.mock('../AuthContext.jsx', () => ({
  useAuth: () => ({
    currentGarage: { id: 1, name: 'Home Garage', role: 'member' },
  }),
}));

function renderPage() {
  return render(<MemoryRouter><TyrePressures /></MemoryRouter>);
}

describe('TyrePressures', () => {
  it('lists each vehicle with front/rear pressure (psi + bar) and tyre size', async () => {
    api.getVehicles.mockResolvedValue(vehicles);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Street Triple')).toBeInTheDocument();
      expect(screen.getByText('36psi (2.5 bar)')).toBeInTheDocument();
      expect(screen.getByText('42psi (2.9 bar)')).toBeInTheDocument();
      expect(screen.getByText('120/70 ZR17')).toBeInTheDocument();
      expect(screen.getByText('180/55 ZR17')).toBeInTheDocument();
    });
    // Missing tyre data falls back to an em dash.
    expect(screen.getByText('Daily')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('shows empty state when the garage has no vehicles', async () => {
    api.getVehicles.mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/No vehicles yet/)).toBeInTheDocument();
    });
  });
});
