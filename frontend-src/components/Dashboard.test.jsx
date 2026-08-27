import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import { DisplayPrefsProvider } from '../DisplayPrefsContext.jsx';

// One stable object: Dashboard's fetch effect keys on `currentGarage`, so a fresh literal
// per call would re-fire it on every render and burn through the mockResolvedValueOnce queue.
const auth = {
  user: { username: 'x', is_admin: false, memberships: [{ garage_id: 1, garage_name: 'Home Garage', role: 'member' }] },
  currentGarage: { id: 1, name: 'Home Garage', role: 'member' },
  roleFor: () => 'member',
};

vi.mock('../AuthContext.jsx', () => ({ useAuth: () => auth }));

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
        type: 'service', id: 7, vehicle_id: 1, vehicle_name: 'Street Triple',
        title: 'Annual service', category: 'Service', date: '2025-04-05', status: 'overdue',
        next_due_date: '2026-04-05', next_due_km: null, km_remaining: null,
        vehicle_odometer_unit: 'mi',
      },
    ]),
  },
}));

const upcoming = {
  type: 'service', id: 8, vehicle_id: 1, vehicle_name: 'Street Triple',
  title: 'Brake fluid', category: 'Brake fluid', date: '2025-04-05', status: 'upcoming',
  next_due_date: '2027-04-05', next_due_km: null, km_remaining: null,
  vehicle_odometer_unit: 'mi',
};

beforeEach(() => {
  localStorage.clear();
});

function renderDashboard() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <DisplayPrefsProvider><Dashboard /></DisplayPrefsProvider>
    </MemoryRouter>,
  );
}

// "Service" and the vehicle name also appear in the Recent services table below, so
// reminder assertions scope themselves to the nested sub-list.
const sublist = () => document.querySelector('.reminder-sublist');

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

  it('nests a reminder under its vehicle, with its status badge', async () => {
    const { container } = renderDashboard();
    await waitFor(() => expect(container.querySelector('.reminder-subrow')).toBeInTheDocument());
    // The old flat cross-vehicle list is gone; the vehicle row is the only heading.
    expect(screen.queryByText('Maintenance reminders')).toBeNull();
    // The sub-row no longer repeats the vehicle name — it's the parent row now.
    expect(sublist().textContent).toContain('Service');
    expect(sublist().textContent).not.toContain('Street Triple');
    expect(screen.getByText('Overdue')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '1 reminder for Street Triple' }))
      .toHaveAttribute('aria-expanded', 'true');
  });

  it('shows an MOT reminder with an expiry sub-line', async () => {
    const { api } = await import('../api.js');
    api.getReminders.mockResolvedValueOnce([{
      type: 'mot', id: null, vehicle_id: 1, vehicle_name: 'Street Triple',
      title: 'MOT', category: 'MOT', date: null, status: 'due_soon',
      next_due_date: '2026-07-15', next_due_km: null, km_remaining: null,
      vehicle_odometer_unit: 'mi',
    }]);
    renderDashboard();
    await waitFor(() => expect(screen.getByText('Expires 2026-07-15')).toBeInTheDocument());
    expect(sublist().textContent).toContain('MOT');
    expect(screen.getByText('Due soon')).toBeInTheDocument();
  });

  it('shows a road-tax reminder with a due sub-line', async () => {
    const { api } = await import('../api.js');
    api.getReminders.mockResolvedValueOnce([{
      type: 'tax', id: null, vehicle_id: 1, vehicle_name: 'Street Triple',
      title: 'Road tax', category: 'Tax', date: null, status: 'due_soon',
      next_due_date: '2026-08-01', next_due_km: null, km_remaining: null,
      vehicle_odometer_unit: 'mi',
    }]);
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Tax')).toBeInTheDocument();
      expect(screen.getByText('Due 2026-08-01')).toBeInTheDocument();
      expect(screen.getByText('Due soon')).toBeInTheDocument();
    });
  });

  it('shows a schedule reminder and links it to the vehicle', async () => {
    const { api } = await import('../api.js');
    api.getReminders.mockResolvedValueOnce([{
      type: 'schedule', id: 3, vehicle_id: 1, vehicle_name: 'Street Triple',
      title: 'Minor service', category: null, date: '2024-06-15', status: 'overdue',
      next_due_date: '2025-06-15', next_due_km: null, km_remaining: null,
      vehicle_odometer_unit: 'mi',
    }]);
    renderDashboard();
    await waitFor(() => {
      const row = screen.getByText('Minor service').closest('.reminder-row');
      expect(row).toBeInTheDocument();
      expect(screen.getByText(/After “Minor service” \(2024-06-15\)/)).toBeInTheDocument();
    });
  });

  it('converts odometer to the vehicle display unit', async () => {
    renderDashboard();
    // 160.9344 km == 100 mi
    await waitFor(() => {
      expect(screen.getAllByText('100 mi').length).toBeGreaterThan(0);
    });
  });

  it('starts collapsed when nothing is more urgent than upcoming', async () => {
    const { api } = await import('../api.js');
    api.getReminders.mockResolvedValueOnce([{ ...upcoming }]);
    localStorage.setItem('torqued.showUpcoming', 'true');
    renderDashboard();
    await waitFor(() => expect(screen.getByRole('button', { name: /1 reminder/ }))
      .toHaveAttribute('aria-expanded', 'false'));
    expect(screen.queryByText('Brake fluid')).toBeNull();
  });

  it('an explicit expand sticks, and toggling never navigates away', async () => {
    const { api } = await import('../api.js');
    api.getReminders.mockResolvedValueOnce([{ ...upcoming }]);
    localStorage.setItem('torqued.showUpcoming', 'true');
    renderDashboard();
    const toggle = await screen.findByRole('button', { name: /1 reminder/ });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Brake fluid')).toBeInTheDocument();
    // The row's own click-to-navigate handler skips 'a, button', so we're still here.
    expect(screen.getByText('Maintenance due')).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows no toggle for a vehicle with no reminders', async () => {
    const { api } = await import('../api.js');
    api.getReminders.mockResolvedValueOnce([]);
    const { container } = renderDashboard();
    await waitFor(() => expect(screen.getByText(/Nothing on the horizon/)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /reminder/ })).toBeNull();
    expect(container.querySelector('.reminder-subrow')).toBeNull();
  });

  it('hides upcoming reminders behind a toggle, always keeping the urgent ones', async () => {
    const { api } = await import('../api.js');
    api.getReminders.mockResolvedValueOnce([
      {
        type: 'service', id: 7, vehicle_id: 1, vehicle_name: 'Street Triple',
        title: 'Annual service', category: 'Service', date: '2025-04-05', status: 'overdue',
        next_due_date: '2026-04-05', next_due_km: null, km_remaining: null,
        vehicle_odometer_unit: 'mi',
      },
      { ...upcoming },
    ]);
    renderDashboard();
    // Hidden by default: only the overdue one is counted and listed.
    const toggle = await screen.findByRole('button', { name: 'Show 1 upcoming' });
    expect(screen.getByRole('button', { name: /1 reminder/ })).toBeInTheDocument();
    expect(sublist().textContent).not.toContain('Brake fluid');
    expect(sublist().textContent).toContain('Service');
    // The "Maintenance due" stat only ever counted the urgent ones, so it's unmoved.
    expect(screen.getByText('Maintenance due').previousSibling).toHaveTextContent('1');

    await userEvent.click(toggle);
    expect(sublist().textContent).toContain('Brake fluid');
    expect(sublist().textContent).toContain('Service');
    expect(screen.getByRole('button', { name: /2 reminders/ })).toBeInTheDocument();
    expect(localStorage.getItem('torqued.showUpcoming')).toBe('true');
    expect(screen.getByRole('button', { name: 'Hide upcoming' })).toBeInTheDocument();
  });

  it('falls back to mot_baseline for make/model/year when vehicle columns are null', async () => {
    const { api } = await import('../api.js');
    api.getVehicles.mockResolvedValueOnce([{
      id: 9, name: 'Passat', kind: 'car', make: null, model: null, year: null,
      odometer_unit: 'mi', service_count: 0, photo_count: 0, cover_photo_id: null,
      latest_odometer: null, mot_baseline: { make: 'VOLKSWAGEN', model: 'PASSAT', year: 2003 },
    }]);
    renderDashboard();
    // Title-cased because the display-prefs provider is now in the tree and tidy-up
    // names defaults on; the point here is that the baseline is used at all.
    await waitFor(() => {
      expect(screen.getByText('2003 Volkswagen Passat')).toBeInTheDocument();
    });
  });
});
