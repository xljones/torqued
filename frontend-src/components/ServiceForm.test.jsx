import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ServiceForm from './ServiceForm';
import { FormMode } from '../constants.js';
import { api } from '../api.js';

vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));
vi.mock('../api.js', () => ({
  api: {
    getPerformers: vi.fn().mockResolvedValue([]),
    getVehicle: vi.fn().mockResolvedValue({ id: 1, name: 'Bike', odometer_unit: 'mi' }),
    getSchedules: vi.fn(),
    createSchedule: vi.fn(),
    createService: vi.fn(),
  },
}));

const routerFuture = { v7_startTransition: true, v7_relativeSplatPath: true };

function renderCreate() {
  return render(
    <MemoryRouter initialEntries={['/vehicles/1/services/new']} future={routerFuture}>
      <Routes>
        <Route path="/vehicles/:vehicleId/services/new" element={<ServiceForm mode={FormMode.CREATE} />} />
        <Route path="/services/:id" element={<div>service page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getPerformers.mockResolvedValue([]);
  api.getVehicle.mockResolvedValue({ id: 1, name: 'Bike', odometer_unit: 'mi' });
});

describe('ServiceForm — fulfils schedules', () => {
  it('shows an italic empty message when the vehicle has no schedules', async () => {
    api.getSchedules.mockResolvedValue([]);
    renderCreate();
    const empty = await screen.findByText('No scheduled services');
    expect(empty).toBeInTheDocument();
    expect(empty).toHaveClass('checkbox-empty');
  });

  it('lists schedules as checkbox rows in normal (non-uppercase) markup', async () => {
    api.getSchedules.mockResolvedValue([
      { id: 5, kind: 'minor', name: null, interval_months: 6, interval_km: null, enabled: 1 },
    ]);
    renderCreate();
    // The option text is rendered verbatim ("Minor service") — casing is CSS, not markup.
    const row = (await screen.findByText('Minor service')).closest('label');
    expect(row).toHaveClass('checkbox-row');
    expect(within(row).getByRole('checkbox')).toBeInTheDocument();
  });

  it('lets the user add a schedule from the form and auto-ticks it', async () => {
    const user = userEvent.setup();
    api.getSchedules.mockResolvedValueOnce([]); // initial: none
    api.createSchedule.mockResolvedValue({ id: 9, kind: 'minor', name: null, interval_months: 12 });
    api.getSchedules.mockResolvedValueOnce([ // after create
      { id: 9, kind: 'minor', name: null, interval_months: 12, interval_km: null, enabled: 1 },
    ]);
    renderCreate();

    await user.click(await screen.findByRole('button', { name: '+ Add schedule' }));
    // The shared schedule form appears; save it.
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(api.createSchedule).toHaveBeenCalledWith(1, expect.objectContaining({
      kind: 'minor', interval_unit: 'mi',
    })));
    // The new schedule now appears and is ticked.
    const row = (await screen.findByText('Minor service')).closest('label');
    expect(within(row).getByRole('checkbox')).toBeChecked();
  });
});
