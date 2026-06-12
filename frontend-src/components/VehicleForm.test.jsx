import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import VehicleForm from './VehicleForm';
import { FormMode } from '../constants.js';
import { api } from '../api.js';

vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));
vi.mock('../AuthContext.jsx', () => ({
  useAuth: () => ({ currentGarage: { id: 1, name: 'Home Garage' } }),
}));
vi.mock('../api.js', () => ({
  api: {
    getMotStatus: vi.fn(),
    lookupMot: vi.fn(),
    getVehicle: vi.fn(),
    createVehicle: vi.fn(),
    refreshMot: vi.fn(),
    updateVehicle: vi.fn(),
  },
}));

function renderCreate() {
  return render(
    <MemoryRouter initialEntries={['/vehicles/new']}>
      <Routes>
        <Route path="/vehicles/new" element={<VehicleForm mode={FormMode.CREATE} />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderEdit() {
  return render(
    <MemoryRouter initialEntries={['/vehicles/7/edit']}>
      <Routes>
        <Route path="/vehicles/:id/edit" element={<VehicleForm mode={FormMode.EDIT} />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('VehicleForm DVSA lookup', () => {
  it('puts the registration plate input first with a fetch button when configured', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    renderCreate();
    await waitFor(() => expect(screen.getByText('Fetch from DVSA')).toBeInTheDocument());
    const plate = screen.getByPlaceholderText('LR53 UHD');
    expect(plate).toHaveClass('reg-plate-input');
  });

  it('hides the fetch button when DVSA is not configured', async () => {
    api.getMotStatus.mockResolvedValue({ configured: false });
    renderCreate();
    await waitFor(() => expect(screen.getByPlaceholderText('LR53 UHD')).toBeInTheDocument());
    expect(screen.queryByText('Fetch from DVSA')).not.toBeInTheDocument();
  });

  it('fetches the DVSA baseline and surfaces it as a summary and field placeholders', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.lookupMot.mockResolvedValue({
      configured: true,
      mot_baseline: { make: 'VOLKSWAGEN', model: 'PASSAT', year: 2003, colour: 'Blue', engine_size: '1896' },
    });
    renderCreate();
    const plate = await screen.findByPlaceholderText('LR53 UHD');
    await userEvent.type(plate, 'LR53 UHD');
    await userEvent.click(screen.getByText('Fetch from DVSA'));
    await waitFor(() => {
      expect(api.lookupMot).toHaveBeenCalledWith('LR53 UHD');
      expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument();
    });
    // Identity fields now hint the DVSA value; leaving them blank uses the baseline
    expect(screen.getByPlaceholderText('DVSA: VOLKSWAGEN')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('DVSA: 1896')).toBeInTheDocument();
  });

  it('splits each identity field into an editable input and a fixed DVSA value when editing', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicle.mockResolvedValue({
      name: 'Daily', kind: 'car', odometer_unit: 'mi',
      // No identity overrides set — everything should fall back to the DVSA baseline.
      mot_baseline: {
        make: 'VOLKSWAGEN', model: 'PASSAT', year: 2003,
        colour: 'Blue', fuel_type: 'Diesel', engine_size: '1896',
        first_used_date: '2003-06-01', registration_date: '2003-05-20',
      },
    });
    const { container } = renderEdit();
    // The right-hand third shows the fixed DVSA value alongside the editable input.
    await waitFor(() => expect(screen.getByText('VOLKSWAGEN')).toBeInTheDocument());
    expect(screen.getByText('2003-06-01')).toBeInTheDocument();
    expect(screen.getByText('Diesel')).toBeInTheDocument();
    // One "DVSA" label per populated baseline field (8 grid fields here).
    expect(screen.getAllByText('DVSA')).toHaveLength(8);
    // No overrides set, so every split marks the DVSA fallback as the active value.
    expect(container.querySelectorAll('.dvsa-split.is-dvsa')).toHaveLength(8);
    expect(container.querySelectorAll('.dvsa-split.is-override')).toHaveLength(0);
  });

  it('moves the active (green) marker to the input once the user overrides a DVSA value', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicle.mockResolvedValue({
      name: 'Daily', kind: 'car', odometer_unit: 'mi',
      mot_baseline: { make: 'VOLKSWAGEN' },
    });
    const { container } = renderEdit();
    await waitFor(() => expect(container.querySelector('.dvsa-split')).toHaveClass('is-dvsa'));
    // Typing a custom make makes the override the active value.
    await userEvent.type(screen.getByPlaceholderText('e.g. Honda'), 'Lotus');
    expect(container.querySelector('.dvsa-split')).toHaveClass('is-override');
  });
});
