import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import VehicleRecordsPage from './VehicleRecordsPage';

// Renders nothing but reports the router location it was navigated to, so a test can
// assert what "+ Add to garage" passed to the new-vehicle route.
function LocationProbe({ onLocation }) {
  onLocation(useLocation());
  return null;
}

vi.mock('../api.js', () => ({
  api: {
    getVehicleRecords: vi.fn(),
    getRecordsForPlate: vi.fn(),
    getMotStatus: vi.fn(),
    getTaxStatus: vi.fn(),
    lookupVehicleRecord: vi.fn(),
    refreshMot: vi.fn(),
    refreshTax: vi.fn(),
  },
}));
vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));

import { api } from '../api.js';

// Build a list item with sensible defaults; `ref` identifies the group's newest row.
function item(overrides = {}) {
  return {
    ref: { source: 'dvsa', id: 1 },
    vehicle_id: null, vehicle_name: null, garage_name: null,
    registration: 'A1XYZ', make: 'VOLKSWAGEN', model: 'PASSAT', year: 2003,
    tax_status: null, tax_due_date: null,
    fetched_at: '2024-01-01 00:00:00',
    record_count: 1, dvsa_count: 1, tax_count: 0,
    ...overrides,
  };
}

function page(items, extra = {}) {
  return {
    items,
    total: items.length,
    total_records: items.reduce((n, i) => n + i.record_count, 0),
    total_dvsa: items.reduce((n, i) => n + i.dvsa_count, 0),
    total_tax: items.reduce((n, i) => n + i.tax_count, 0),
    page: 1, per_page: 25, pages: 1,
    ...extra,
  };
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <VehicleRecordsPage />
    </MemoryRouter>,
  );
}

describe('VehicleRecordsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getMotStatus.mockResolvedValue({ configured: false });
    api.getTaxStatus.mockResolvedValue({ configured: false });
  });

  it('shows year + make/model, a tax chip, source-split counts, and a green view button', async () => {
    api.getVehicleRecords.mockResolvedValue(page([item({
      ref: { source: 'dvsa', id: 2 }, vehicle_id: 7, vehicle_name: 'Daily', garage_name: 'Home Garage',
      registration: 'a1xyz', tax_status: 'Taxed', record_count: 2, dvsa_count: 1, tax_count: 1,
    })]));
    renderPage();

    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());
    expect(api.getVehicleRecords).toHaveBeenCalledWith(1);
    expect(screen.getByText('A1XYZ')).toBeInTheDocument();  // RegPlate forces uppercase
    expect(screen.getByText('2003')).toBeInTheDocument();
    expect(screen.getByText('Taxed')).toBeInTheDocument();  // tax status chip
    expect(screen.getByText('1 vehicle, 2 records (1 DVSA, 1 tax)')).toBeInTheDocument();
    expect(screen.getByText('· 2 records (1 DVSA, 1 tax)')).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: 'View Daily in Home Garage' });
    expect(btn).toHaveClass('btn-success');
  });

  it('expands a row to browse DVSA and tax records together, newest first', async () => {
    api.getVehicleRecords.mockResolvedValue(page([item({
      ref: { source: 'tax', id: 5 }, vehicle_id: 7, tax_status: 'Taxed',
      record_count: 2, dvsa_count: 1, tax_count: 1,
    })]));
    api.getRecordsForPlate.mockResolvedValue({
      registration: 'A1XYZ',
      records: [
        { source: 'tax', id: 5, vehicle_id: 7, registration: 'A1XYZ', tax_status: 'Taxed',
          fetched_at: '2024-06-01 00:00:00', raw: { tax_status: 'Taxed', tax_due_date: '2026-12-01' } },
        { source: 'dvsa', id: 2, vehicle_id: 7, registration: 'A1XYZ', make: 'VOLKSWAGEN',
          fetched_at: '2024-01-01 00:00:00', raw: { registration: 'A1XYZ', motTests: [] } },
      ],
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());
    expect(api.getRecordsForPlate).not.toHaveBeenCalled();
    await userEvent.click(screen.getByText('VOLKSWAGEN PASSAT').closest('tr'));

    // One viewer per lookup, each labelled by source.
    await waitFor(() => expect(screen.getByText('DVLA tax record')).toBeInTheDocument());
    expect(api.getRecordsForPlate).toHaveBeenCalledWith('tax', 5);
    expect(screen.getByText('DVSA record')).toBeInTheDocument();

    // The shared viewer expands a lookup into its raw fields.
    await userEvent.click(screen.getByText('DVLA tax record'));
    expect(screen.getByText('tax_due_date')).toBeInTheDocument();
  });

  it('does not toggle the row when the view button is clicked', async () => {
    api.getVehicleRecords.mockResolvedValue(page([item({
      vehicle_id: 7, vehicle_name: 'Daily', garage_name: 'Home Garage',
    })]));
    renderPage();

    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'View Daily in Home Garage' }));
    expect(api.getRecordsForPlate).not.toHaveBeenCalled();
  });

  it('filters the loaded rows by make/model or registration', async () => {
    api.getVehicleRecords.mockResolvedValue(page([
      item({ ref: { source: 'dvsa', id: 1 }, vehicle_id: 7, registration: 'A1 XYZ' }),
      item({ ref: { source: 'dvsa', id: 2 }, vehicle_id: 8, registration: 'FD09 ABC',
        make: 'FORD', model: 'FOCUS' }),
    ]));
    renderPage();
    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());

    const box = screen.getByPlaceholderText(/Filter by make, model or registration/);
    await userEvent.type(box, 'focus');
    expect(screen.getByText('FORD FOCUS')).toBeInTheDocument();
    expect(screen.queryByText('VOLKSWAGEN PASSAT')).not.toBeInTheDocument();

    await userEvent.clear(box);
    await userEvent.type(box, 'a1xyz');  // spacing-insensitive
    expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument();
    expect(screen.queryByText('FORD FOCUS')).not.toBeInTheDocument();

    await userEvent.clear(box);
    await userEvent.type(box, 'zzz');
    expect(screen.getByText('No matches on this page')).toBeInTheDocument();
  });

  it('shows a detached record (not tied to a garage vehicle) with no view link', async () => {
    api.getVehicleRecords.mockResolvedValue(page([item({
      registration: 'OLD123', make: 'FORD', model: 'FOCUS',
    })]));
    renderPage();

    await waitFor(() => expect(screen.getByText('FORD FOCUS')).toBeInTheDocument());
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Add to garage' })).toBeInTheDocument();
  });

  it('finds a registration (both sources), saves, reloads, and auto-expands the found row', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicleRecords
      .mockResolvedValueOnce(page([]))
      .mockResolvedValue(page([item({ ref: { source: 'dvsa', id: 9 } })]));
    api.lookupVehicleRecord.mockResolvedValue({ registration: 'A1XYZ', make: 'VOLKSWAGEN', model: 'PASSAT' });
    api.getRecordsForPlate.mockResolvedValue({
      registration: 'A1XYZ',
      records: [{ source: 'dvsa', id: 9, vehicle_id: null, make: 'VOLKSWAGEN', model: 'PASSAT',
        fetched_at: '2024-01-01 00:00:00', raw: { registration: 'A1XYZ' } }],
    });
    renderPage();

    const box = await screen.findByLabelText('Registration to look up');
    await userEvent.type(box, 'a1 xyz');
    await userEvent.click(screen.getByRole('button', { name: /^Find$/ }));

    await waitFor(() => expect(api.lookupVehicleRecord).toHaveBeenCalledWith('a1 xyz'));
    await waitFor(() => expect(api.getVehicleRecords).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(api.getRecordsForPlate).toHaveBeenCalledWith('dvsa', 9));
    expect(await screen.findByText('DVSA record')).toBeInTheDocument();
  });

  it('shows the Find form when only the tax API is configured', async () => {
    api.getMotStatus.mockResolvedValue({ configured: false });
    api.getTaxStatus.mockResolvedValue({ configured: true });
    api.getVehicleRecords.mockResolvedValue(page([]));
    renderPage();
    expect(await screen.findByLabelText('Registration to look up')).toBeInTheDocument();
  });

  it('refreshes a linked row via both sources, reloads, and re-expands', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicleRecords
      .mockResolvedValueOnce(page([item({
        ref: { source: 'dvsa', id: 3 }, vehicle_id: 7, vehicle_name: 'Daily', garage_name: 'Home Garage',
      })]))
      .mockResolvedValue(page([item({
        ref: { source: 'dvsa', id: 4 }, vehicle_id: 7, vehicle_name: 'Daily', garage_name: 'Home Garage',
        fetched_at: '2024-06-01 00:00:00', record_count: 2, dvsa_count: 2,
      })]));
    api.refreshMot.mockResolvedValue({});
    api.refreshTax.mockResolvedValue({});
    api.getRecordsForPlate.mockResolvedValue({
      registration: 'A1XYZ',
      records: [{ source: 'dvsa', id: 4, vehicle_id: 7, make: 'VOLKSWAGEN', model: 'PASSAT',
        fetched_at: '2024-06-01 00:00:00', raw: { registration: 'A1XYZ' } }],
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('· 1 record')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Refresh from DVLA & DVSA' }));

    // A linked row refreshes both sources via its vehicle.
    await waitFor(() => expect(api.refreshMot).toHaveBeenCalledWith(7));
    expect(api.refreshTax).toHaveBeenCalledWith(7);
    await waitFor(() => expect(screen.getByText('· 2 records')).toBeInTheDocument());
    await waitFor(() => expect(api.getRecordsForPlate).toHaveBeenCalledWith('dvsa', 4));
  });

  it('refreshes a standalone row via a fresh combined lookup', async () => {
    api.getMotStatus.mockResolvedValue({ configured: true });
    api.getVehicleRecords.mockResolvedValue(page([item({
      ref: { source: 'dvsa', id: 8 }, registration: 'OLD123', make: 'FORD', model: 'FOCUS',
    })]));
    api.lookupVehicleRecord.mockResolvedValue({ registration: 'OLD123', make: 'FORD', model: 'FOCUS' });
    api.getRecordsForPlate.mockResolvedValue({ registration: 'OLD123', records: [] });
    renderPage();

    await waitFor(() => expect(screen.getByText('FORD FOCUS')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Refresh from DVLA & DVSA' }));

    await waitFor(() => expect(api.lookupVehicleRecord).toHaveBeenCalledWith('OLD123'));
    expect(api.refreshMot).not.toHaveBeenCalled();
  });

  it('hides the Find form when neither source is configured', async () => {
    api.getVehicleRecords.mockResolvedValue(page([]));
    renderPage();

    await waitFor(() => expect(screen.getByText(/No records stored yet/)).toBeInTheDocument());
    expect(screen.queryByLabelText('Registration to look up')).not.toBeInTheDocument();
  });

  it('offers "+ Add to garage" on an unlinked row, prefilling the new-vehicle form', async () => {
    api.getVehicleRecords.mockResolvedValue(page([item({
      ref: { source: 'dvsa', id: 5 }, registration: 'A1 XYZ',
    })]));
    let captured = null;
    render(
      <MemoryRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        initialEntries={['/records']}
      >
        <Routes>
          <Route path="/records" element={<VehicleRecordsPage />} />
          <Route path="/vehicles/new" element={<LocationProbe onLocation={l => { captured = l; }} />} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole('button', { name: '+ Add to garage' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured.state.prefill).toEqual({ registration: 'A1 XYZ', name: 'VOLKSWAGEN PASSAT' });
  });

  it('pages through results with Prev/Next', async () => {
    api.getVehicleRecords.mockImplementation(p => Promise.resolve(page(
      [item({ ref: { source: 'dvsa', id: p }, vehicle_id: p, registration: `REG${p}`, model: `Model${p}` })],
      { total: 30, total_records: 30, page: p, pages: 2 },
    )));
    renderPage();

    await waitFor(() => expect(screen.getByText('Page 1 of 2')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /Prev/ })).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: /Next/ }));
    await waitFor(() => expect(screen.getByText('Page 2 of 2')).toBeInTheDocument());
    expect(api.getVehicleRecords).toHaveBeenLastCalledWith(2);
    expect(screen.getByRole('button', { name: /Next/ })).toBeDisabled();
  });

  it('shows an empty state', async () => {
    api.getVehicleRecords.mockResolvedValue(page([]));
    renderPage();
    await waitFor(() => expect(screen.getByText(/No records stored yet/)).toBeInTheDocument());
  });
});
