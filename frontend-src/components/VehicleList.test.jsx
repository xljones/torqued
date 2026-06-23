import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import VehicleList from './VehicleList';

const vehicles = [
  {
    id: 1, name: 'Street Triple', kind: 'motorcycle',
    effective: { make: 'Triumph', model: 'Street Triple RS', year: 2021, registration: 'LB21 XYZ' },
    effective_source: { make: 'override', model: 'override', year: 'override', registration: 'override' },
    odometer_unit: 'mi', archived: 0, service_count: 4, photo_count: 0,
    cover_photo_id: null,
    latest_odometer: { date: '2025-06-01', odometer_km: 160.9344 },
  },
  {
    id: 2, name: 'Daily', kind: 'car',
    effective: { make: 'Honda', model: 'Civic', year: 2019, registration: null },
    effective_source: { make: 'override', model: 'override', year: 'override', registration: 'baseline' },
    odometer_unit: 'mi', archived: 0, service_count: 1,
    photo_count: 0, cover_photo_id: null, latest_odometer: null,
  },
];

vi.mock('../api.js', () => ({
  api: {
    getVehicles: vi.fn().mockResolvedValue([]),
    photoUrl: (id) => `/api/photos/${id}/file`,
  },
}));

import { api } from '../api.js';

vi.mock('../AuthContext.jsx', () => ({
  useAuth: () => ({
    user: { username: 'x', is_admin: false, memberships: [{ garage_id: 1, garage_name: 'Home Garage', role: 'member' }] },
    currentGarage: { id: 1, name: 'Home Garage', role: 'member' },
    roleFor: () => 'member',
  }),
}));

function renderList() {
  return render(<MemoryRouter><VehicleList /></MemoryRouter>);
}

describe('VehicleList', () => {
  it('renders vehicle cards with kind badges and odometer', async () => {
    api.getVehicles.mockResolvedValue(vehicles);
    renderList();
    await waitFor(() => {
      expect(screen.getByText('Street Triple')).toBeInTheDocument();
      expect(screen.getByText('Motorcycle')).toBeInTheDocument();
      expect(screen.getByText('Car')).toBeInTheDocument();
      expect(screen.getByText('100 mi (161 km)')).toBeInTheDocument();
      expect(screen.getByText('No mileage yet')).toBeInTheDocument();
    });
  });

  it('filters by name', async () => {
    api.getVehicles.mockResolvedValue(vehicles);
    renderList();
    await waitFor(() => expect(screen.getByText('Daily')).toBeInTheDocument());
    await userEvent.type(screen.getByPlaceholderText(/Filter by name/), 'Triple');
    expect(screen.queryByText('Daily')).not.toBeInTheDocument();
    expect(screen.getByText('Street Triple')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    api.getVehicles.mockResolvedValue([]);
    renderList();
    await waitFor(() => {
      expect(screen.getByText(/No vehicles yet/)).toBeInTheDocument();
    });
  });

  it('falls back to the MOT baseline for make/model/year/plate when not overridden', async () => {
    api.getVehicles.mockResolvedValue([{
      id: 3, name: 'Passat', kind: 'car',
      odometer_unit: 'mi', archived: 0, service_count: 0,
      photo_count: 0, cover_photo_id: null, latest_odometer: null,
      // The backend resolved every identity field from the DVSA baseline.
      effective: { make: 'VOLKSWAGEN', model: 'PASSAT', year: 2003, registration: 'A1XYZ' },
      effective_source: { make: 'baseline', model: 'baseline', year: 'baseline', registration: 'baseline' },
    }]);
    renderList();
    await waitFor(() => {
      expect(screen.getByText('2003 VOLKSWAGEN PASSAT')).toBeInTheDocument();
      expect(screen.getByText('A1XYZ')).toBeInTheDocument();
    });
    // Baseline values are searchable too
    await userEvent.type(screen.getByPlaceholderText(/Filter by name/), 'volkswagen');
    expect(screen.getByText('Passat')).toBeInTheDocument();
  });
});
