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
    refreshTax: vi.fn(),
    updateVehicle: vi.fn(),
  },
}));

const routerFuture = { v7_startTransition: true, v7_relativeSplatPath: true };

function renderCreate() {
  return render(
    <MemoryRouter initialEntries={['/vehicles/new']} future={routerFuture}>
      <Routes>
        <Route path="/vehicles/new" element={<VehicleForm mode={FormMode.CREATE} />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderEdit() {
  return render(
    <MemoryRouter initialEntries={['/vehicles/7/edit']} future={routerFuture}>
      <Routes>
        <Route path="/vehicles/:id/edit" element={<VehicleForm mode={FormMode.EDIT} />} />
        <Route path="/vehicles/:id" element={<div>vehicle detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.refreshTax.mockResolvedValue({ configured: true, tax: null });
});

describe('VehicleForm DVSA lookup', () => {
  it('puts the registration plate input first with a fetch button when configured', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    renderCreate();
    await waitFor(() => expect(screen.getByText('Fetch from DVSA')).toBeInTheDocument());
    const plate = screen.getByPlaceholderText('A1 XYZ');
    expect(plate).toHaveClass('reg-plate-input');
  });

  it('hides the fetch button when DVSA is not configured', async () => {
    api.getMotStatus.mockResolvedValue({ configured: false });
    renderCreate();
    await waitFor(() => expect(screen.getByPlaceholderText('A1 XYZ')).toBeInTheDocument());
    expect(screen.queryByText('Fetch from DVSA')).not.toBeInTheDocument();
  });

  it('fetches the DVSA baseline and shows each identity field as an editable / fixed-DVSA split', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.lookupMot.mockResolvedValue({
      configured: true,
      mot_baseline: { make: 'VOLKSWAGEN', model: 'PASSAT', year: 2003, colour: 'Blue', engine_size: '1896' },
    });
    const { container } = renderCreate();
    const plate = await screen.findByPlaceholderText('A1 XYZ');
    await userEvent.type(plate, 'A1 XYZ');
    await userEvent.click(screen.getByText('Fetch from DVSA'));
    await waitFor(() => {
      expect(api.lookupMot).toHaveBeenCalledWith('A1 XYZ');
      expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument();
    });
    // Create mode now renders the same split as edit mode: a fixed DVSA value beside each input.
    expect(screen.getByText('VOLKSWAGEN')).toBeInTheDocument();
    expect(screen.getByText('1896')).toBeInTheDocument();
    // make, model, year, colour, engine_size each have a baseline value → 5 DVSA-active splits.
    expect(container.querySelectorAll('.dvsa-split.is-dvsa')).toHaveLength(5);
    expect(container.querySelectorAll('.dvsa-split.is-override')).toHaveLength(0);
  });

  it('fetches from the DVSA when Enter is pressed in the registration field', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.lookupMot.mockResolvedValue({ configured: true, mot_baseline: { make: 'VOLKSWAGEN' } });
    api.createVehicle.mockResolvedValue({ id: 1 });
    renderCreate();
    const plate = await screen.findByPlaceholderText('A1 XYZ');
    await userEvent.type(plate, 'A1 XYZ{Enter}');
    // Enter looks up the plate instead of submitting the half-filled form.
    await waitFor(() => expect(api.lookupMot).toHaveBeenCalledWith('A1 XYZ'));
    expect(api.createVehicle).not.toHaveBeenCalled();
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

  it('shows a loading skeleton in edit mode until the vehicle has loaded', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    let resolveVehicle;
    api.getVehicle.mockReturnValue(new Promise(r => { resolveVehicle = r; }));
    const { container } = renderEdit();
    // Until the vehicle resolves the form is replaced by the skeleton shimmer, so the
    // identity fields (incl. the DVSA baseline) can't pop in after first paint.
    expect(container.querySelector('.skeleton-line')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('AB12 CDE')).not.toBeInTheDocument();
    resolveVehicle({
      name: 'Daily', kind: 'car', odometer_unit: 'mi', registration: 'AB12 CDE', mot_baseline: null,
    });
    // Once loaded, the populated form replaces the skeleton in one step.
    await screen.findByDisplayValue('AB12 CDE');
    expect(container.querySelector('.skeleton-line')).not.toBeInTheDocument();
  });

  it('fetches and stores MOT + tax after creating a vehicle with a registration', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.createVehicle.mockResolvedValue({ id: 42 });
    api.refreshMot.mockResolvedValue({});
    renderCreate();
    const plate = await screen.findByPlaceholderText('A1 XYZ');
    await userEvent.type(plate, 'A1 XYZ');
    await userEvent.type(screen.getByPlaceholderText('e.g. Street Triple, Daily'), 'Daily');
    await userEvent.click(screen.getByRole('button', { name: 'Add vehicle' }));
    await waitFor(() => {
      expect(api.createVehicle).toHaveBeenCalled();
      expect(api.refreshMot).toHaveBeenCalledWith(42);
      expect(api.refreshTax).toHaveBeenCalledWith(42);
    });
  });
});

describe('VehicleForm save reconciliation', () => {
  // A vehicle whose attached DVSA record is for plate AB12CDE.
  const editVehicle = (overrides = {}) => ({
    name: 'Daily', kind: 'car', odometer_unit: 'mi', registration: 'AB12 CDE',
    mot_baseline: { registration: 'AB12CDE', make: 'VOLKSWAGEN', model: 'PASSAT' },
    ...overrides,
  });

  it('edit-mode fetch previews via lookupMot without persisting', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicle.mockResolvedValue(editVehicle());
    api.lookupMot.mockResolvedValue({ mot_baseline: { registration: 'XY34ZZZ', make: 'FORD', model: 'FOCUS' } });
    renderEdit();
    const plate = await screen.findByDisplayValue('AB12 CDE');
    await userEvent.clear(plate);
    await userEvent.type(plate, 'XY34 ZZZ');
    await userEvent.click(screen.getByText('Fetch from DVSA'));
    await waitFor(() => expect(screen.getByText('FORD FOCUS')).toBeInTheDocument());
    expect(api.lookupMot).toHaveBeenCalledWith('XY34 ZZZ');
    expect(api.refreshMot).not.toHaveBeenCalled();
  });

  it('prompts and disconnects when the plate changes with no aligned DVSA data', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicle.mockResolvedValue(editVehicle());
    api.updateVehicle.mockResolvedValue({});
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderEdit();
    const plate = await screen.findByDisplayValue('AB12 CDE');
    await userEvent.clear(plate);
    await userEvent.type(plate, 'XY34 ZZZ');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.updateVehicle).toHaveBeenCalled());
    expect(confirmSpy).toHaveBeenCalled();
    expect(api.updateVehicle.mock.calls[0][1]).toMatchObject({ disconnect_mot: true });
    expect(api.refreshMot).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('aborts the save when the disconnect prompt is cancelled', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicle.mockResolvedValue(editVehicle());
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderEdit();
    const plate = await screen.findByDisplayValue('AB12 CDE');
    await userEvent.clear(plate);
    await userEvent.type(plate, 'XY34 ZZZ');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(api.updateVehicle).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('re-fetches without prompting when an aligned record was previewed for the new plate', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicle.mockResolvedValue(editVehicle());
    api.lookupMot.mockResolvedValue({ mot_baseline: { registration: 'XY34ZZZ', make: 'FORD', model: 'FOCUS' } });
    api.updateVehicle.mockResolvedValue({});
    api.refreshMot.mockResolvedValue({});
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderEdit();
    const plate = await screen.findByDisplayValue('AB12 CDE');
    await userEvent.clear(plate);
    await userEvent.type(plate, 'XY34 ZZZ');
    await userEvent.click(screen.getByText('Fetch from DVSA'));
    await waitFor(() => expect(screen.getByText('FORD FOCUS')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.refreshMot).toHaveBeenCalledWith('7'));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(api.updateVehicle.mock.calls[0][1]).toMatchObject({ disconnect_mot: true });
    confirmSpy.mockRestore();
  });

  it('keeps MOT data and does not prompt when the plate is unchanged', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicle.mockResolvedValue(editVehicle());
    api.updateVehicle.mockResolvedValue({});
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderEdit();
    await screen.findByDisplayValue('AB12 CDE');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.updateVehicle).toHaveBeenCalled());
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(api.updateVehicle.mock.calls[0][1]).not.toHaveProperty('disconnect_mot');
    expect(api.refreshMot).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
