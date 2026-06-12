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
});
