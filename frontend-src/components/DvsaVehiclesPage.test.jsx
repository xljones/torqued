import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import DvsaVehiclesPage from './DvsaVehiclesPage';

// Renders nothing but reports the router location it was navigated to, so a test can
// assert what "+ Add to garage" passed to the new-vehicle route.
function LocationProbe({ onLocation }) {
  onLocation(useLocation());
  return null;
}

vi.mock('../api.js', () => ({
  api: {
    getDvsaVehicles: vi.fn(),
    getDvsaVehicleRecords: vi.fn(),
    getMotStatus: vi.fn(),
    lookupDvsaVehicle: vi.fn(),
  },
}));
vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));

import { api } from '../api.js';

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <DvsaVehiclesPage />
    </MemoryRouter>,
  );
}

describe('DvsaVehiclesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getMotStatus.mockResolvedValue({ configured: false });
  });

  it('shows make/model plain with a "(View … in …)" link when tied to a garage vehicle', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [{
        id: 1, vehicle_id: 7, vehicle_name: 'Daily', garage_name: 'Home Garage',
        registration: 'a1xyz',
        make: 'VOLKSWAGEN', model: 'PASSAT', fetched_at: '2024-01-01 00:00:00',
        record_count: 3,
      }],
      total: 1, total_records: 3, page: 1, per_page: 25, pages: 1,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());
    expect(api.getDvsaVehicles).toHaveBeenCalledWith(1);
    expect(screen.getByText('A1XYZ')).toBeInTheDocument();  // RegPlate forces uppercase
    expect(screen.getByText('1 vehicle, 3 records')).toBeInTheDocument();
    expect(screen.getByText('· 3 records')).toBeInTheDocument();
    // Make/model is plain text; the vehicle link is a separate "(View … in …)" affordance.
    expect(screen.getByText('VOLKSWAGEN PASSAT').tagName).not.toBe('A');
    const link = screen.getByRole('link', { name: '(View Daily in Home Garage)' });
    expect(link).toHaveAttribute('href', '/vehicles/7');
  });

  it('expands a row to browse each lookup record, newest first, with the shared viewer', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [{
        id: 2, vehicle_id: 7, registration: 'A1XYZ',
        make: 'VOLKSWAGEN', model: 'PASSAT', fetched_at: '2024-06-01 00:00:00',
        record_count: 2,
      }],
      total: 1, total_records: 2, page: 1, per_page: 25, pages: 1,
    });
    api.getDvsaVehicleRecords.mockResolvedValue({
      registration: 'A1XYZ',
      records: [
        {
          id: 2, vehicle_id: 7, registration: 'A1XYZ', make: 'VOLKSWAGEN', model: 'PASSAT',
          fetched_at: '2024-06-01 00:00:00',
          raw: { registration: 'A1XYZ', make: 'VOLKSWAGEN', motTests: [{ testResult: 'PASSED' }] },
        },
        {
          id: 1, vehicle_id: null, registration: 'A1XYZ', make: 'VOLKSWAGEN', model: 'PASSAT',
          fetched_at: '2023-01-01 00:00:00',
          raw: { registration: 'A1XYZ', make: 'VOLKSWAGEN', motTests: [] },
        },
      ],
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());

    // Records load lazily on first expand; one viewer per whole lookup.
    expect(api.getDvsaVehicleRecords).not.toHaveBeenCalled();
    await userEvent.click(screen.getByText('VOLKSWAGEN PASSAT').closest('tr'));

    await waitFor(() => expect(screen.getAllByText('DVSA record')).toHaveLength(2));
    expect(api.getDvsaVehicleRecords).toHaveBeenCalledWith(2);

    // The shared viewer expands a lookup into its raw fields (the whole payload).
    await userEvent.click(screen.getAllByText('DVSA record')[0]);
    expect(screen.getByText('motTests')).toBeInTheDocument();
  });

  it('does not toggle the row when the vehicle link is clicked', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [{
        id: 1, vehicle_id: 7, vehicle_name: 'Daily', garage_name: 'Home Garage',
        registration: 'A1XYZ',
        make: 'VOLKSWAGEN', model: 'PASSAT', fetched_at: '2024-01-01 00:00:00',
        record_count: 1,
      }],
      total: 1, total_records: 1, page: 1, per_page: 25, pages: 1,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('link', { name: '(View Daily in Home Garage)' }));
    expect(api.getDvsaVehicleRecords).not.toHaveBeenCalled();
  });

  it('filters the loaded rows by make/model or registration', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [
        {
          id: 1, vehicle_id: 7, registration: 'A1 XYZ',
          make: 'VOLKSWAGEN', model: 'PASSAT', fetched_at: '2024-01-01 00:00:00',
          record_count: 1,
        },
        {
          id: 2, vehicle_id: 8, registration: 'FD09 ABC',
          make: 'FORD', model: 'FOCUS', fetched_at: '2024-01-01 00:00:00',
          record_count: 1,
        },
      ],
      total: 2, total_records: 2, page: 1, per_page: 25, pages: 1,
    });
    renderPage();
    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());

    const box = screen.getByPlaceholderText(/Filter by make, model or registration/);

    // Match on make/model
    await userEvent.type(box, 'focus');
    expect(screen.getByText('FORD FOCUS')).toBeInTheDocument();
    expect(screen.queryByText('VOLKSWAGEN PASSAT')).not.toBeInTheDocument();

    // Match on registration, ignoring spacing
    await userEvent.clear(box);
    await userEvent.type(box, 'a1xyz');
    expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument();
    expect(screen.queryByText('FORD FOCUS')).not.toBeInTheDocument();

    // No matches on this page
    await userEvent.clear(box);
    await userEvent.type(box, 'zzz');
    expect(screen.getByText('No matches on this page')).toBeInTheDocument();
  });

  it('shows a detached record (not tied to a garage vehicle) with no view link', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [{
        id: 2, vehicle_id: null, vehicle_name: null, garage_name: null,
        registration: 'OLD123',
        make: 'FORD', model: 'FOCUS', fetched_at: '2024-01-01 00:00:00',
        record_count: 1,
      }],
      total: 1, total_records: 1, page: 1, per_page: 25, pages: 1,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('FORD FOCUS')).toBeInTheDocument());
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('looks up a registration and saves it, then reloads the list', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getDvsaVehicles.mockResolvedValue({
      items: [], total: 0, total_records: 0, page: 1, per_page: 25, pages: 0,
    });
    api.lookupDvsaVehicle.mockResolvedValue({ registration: 'A1XYZ', make: 'VOLKSWAGEN', model: 'PASSAT' });
    renderPage();

    const box = await screen.findByLabelText('Registration to look up');
    await userEvent.type(box, 'a1 xyz');
    await userEvent.click(screen.getByRole('button', { name: /Look up & save/ }));

    await waitFor(() => expect(api.lookupDvsaVehicle).toHaveBeenCalledWith('a1 xyz'));
    // The list is re-fetched after a successful lookup (initial load + reload).
    await waitFor(() => expect(api.getDvsaVehicles).toHaveBeenCalledTimes(2));
  });

  it('hides the lookup form when the DVSA API is not configured', async () => {
    api.getMotStatus.mockResolvedValue({ configured: false });
    api.getDvsaVehicles.mockResolvedValue({
      items: [], total: 0, total_records: 0, page: 1, per_page: 25, pages: 0,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText(/No DVSA vehicles stored yet/)).toBeInTheDocument());
    expect(screen.queryByLabelText('Registration to look up')).not.toBeInTheDocument();
  });

  it('offers "+ Add to garage" on an unlinked row, prefilling the new-vehicle form', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [{
        id: 5, vehicle_id: null, vehicle_name: null, garage_name: null,
        registration: 'A1 XYZ',
        make: 'VOLKSWAGEN', model: 'PASSAT', fetched_at: '2024-01-01 00:00:00',
        record_count: 1,
      }],
      total: 1, total_records: 1, page: 1, per_page: 25, pages: 1,
    });
    let captured = null;
    render(
      <MemoryRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        initialEntries={['/dvsa']}
      >
        <Routes>
          <Route path="/dvsa" element={<DvsaVehiclesPage />} />
          <Route
            path="/vehicles/new"
            element={<LocationProbe onLocation={l => { captured = l; }} />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole('button', { name: '+ Add to garage' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured.state.prefill).toEqual({ registration: 'A1 XYZ', name: 'VOLKSWAGEN PASSAT' });
  });

  it('pages through results with Prev/Next', async () => {
    api.getDvsaVehicles.mockImplementation(page => Promise.resolve({
      items: [{
        id: page, vehicle_id: page, registration: `REG${page}`,
        make: 'M', model: `Model${page}`, fetched_at: '2024-01-01 00:00:00',
        record_count: 1,
      }],
      total: 30, total_records: 30, page, per_page: 25, pages: 2,
    }));
    renderPage();

    await waitFor(() => expect(screen.getByText('Page 1 of 2')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /Prev/ })).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: /Next/ }));
    await waitFor(() => expect(screen.getByText('Page 2 of 2')).toBeInTheDocument());
    expect(api.getDvsaVehicles).toHaveBeenLastCalledWith(2);
    expect(screen.getByRole('button', { name: /Next/ })).toBeDisabled();
  });

  it('shows an empty state', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [], total: 0, total_records: 0, page: 1, per_page: 25, pages: 0,
    });
    renderPage();
    await waitFor(() => expect(screen.getByText(/No DVSA vehicles stored yet/)).toBeInTheDocument());
  });
});
