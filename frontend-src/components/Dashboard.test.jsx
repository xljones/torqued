import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';

vi.mock('../AuthContext.jsx', () => ({
  useAuth: () => ({
    user: { username: 'x', is_admin: false, memberships: [{ garage_id: 1, garage_name: 'Home Garage', role: 'member' }] },
    currentGarage: { id: 1, name: 'Home Garage', role: 'member' },
    roleFor: () => 'member',
  }),
}));

vi.mock('../api.js', () => ({
  api: {
    getVehicles: vi.fn().mockResolvedValue([
      {
        id: 1, name: 'Street Triple', kind: 'motorcycle', make: 'Triumph',
        model: 'Street Triple RS', year: 2021, odometer_unit: 'mi',
        service_count: 2, photo_count: 0, cover_photo_id: null,
        latest_odometer: { date: '2025-06-01', odometer_km: 160.9344 },
      },
    ]),
    getServices: vi.fn().mockResolvedValue([
      {
        id: 7, vehicle_id: 1, vehicle_name: 'Street Triple', date: '2025-04-05',
        title: 'Annual service', category: 'Service', cost: 342,
        odometer_km: 160.9344, photo_count: 0,
      },
    ]),
    getReminders: vi.fn().mockResolvedValue([
      {
        id: 7, vehicle_id: 1, vehicle_name: 'Street Triple', title: 'Annual service',
        category: 'Service', date: '2025-04-05', status: 'overdue',
        next_due_date: '2026-04-05', next_due_km: null, km_remaining: null,
        vehicle_odometer_unit: 'mi',
      },
    ]),
  },
}));

function renderDashboard() {
  return render(<MemoryRouter><Dashboard /></MemoryRouter>);
}

describe('Dashboard', () => {
  it('renders stat card labels', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Vehicles')).toBeInTheDocument();
      expect(screen.getByText('Services logged')).toBeInTheDocument();
      expect(screen.getByText('Total spent')).toBeInTheDocument();
      expect(screen.getByText('Maintenance due')).toBeInTheDocument();
    });
  });

  it('vehicles stat card links to /vehicles', async () => {
    renderDashboard();
    await waitFor(() => {
      const link = screen.getByText('Vehicles').closest('a');
      expect(link).toHaveAttribute('href', '/vehicles');
    });
  });

  it('shows a reminder with its status badge', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Street Triple — Service')).toBeInTheDocument();
      expect(screen.getByText('Overdue')).toBeInTheDocument();
    });
  });

  it('converts odometer to the vehicle display unit', async () => {
    renderDashboard();
    // 160.9344 km == 100 mi
    await waitFor(() => {
      expect(screen.getAllByText('100 mi').length).toBeGreaterThan(0);
    });
  });

  it('falls back to mot_baseline for make/model/year when vehicle columns are null', async () => {
    const { api } = await import('../api.js');
    api.getVehicles.mockResolvedValueOnce([{
      id: 9, name: 'Passat', kind: 'car', make: null, model: null, year: null,
      odometer_unit: 'mi', service_count: 0, photo_count: 0, cover_photo_id: null,
      latest_odometer: null, mot_baseline: { make: 'VOLKSWAGEN', model: 'PASSAT', year: 2003 },
    }]);
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('2003 VOLKSWAGEN PASSAT')).toBeInTheDocument();
    });
  });
});
