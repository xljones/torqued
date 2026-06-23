import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import DvsaVehiclesPage from './DvsaVehiclesPage';

vi.mock('../api.js', () => ({
  api: { getDvsaVehicles: vi.fn() },
}));

import { api } from '../api.js';

function renderPage() {
  return render(<MemoryRouter><DvsaVehiclesPage /></MemoryRouter>);
}

describe('DvsaVehiclesPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders a row with an uppercase plate and a link to the vehicle', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [{
        id: 1, vehicle_id: 7, registration: 'a1xyz',
        make: 'VOLKSWAGEN', model: 'PASSAT', fetched_at: '2024-01-01 00:00:00',
      }],
      total: 1, page: 1, per_page: 25, pages: 1,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('VOLKSWAGEN PASSAT')).toBeInTheDocument());
    expect(api.getDvsaVehicles).toHaveBeenCalledWith(1);
    expect(screen.getByText('A1XYZ')).toBeInTheDocument();  // RegPlate forces uppercase
    expect(screen.getByText('1 stored')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'VOLKSWAGEN PASSAT' }))
      .toHaveAttribute('href', '/vehicles/7');
  });

  it('marks a detached record (deleted vehicle) with no link', async () => {
    api.getDvsaVehicles.mockResolvedValue({
      items: [{
        id: 2, vehicle_id: null, registration: 'OLD123',
        make: 'FORD', model: 'FOCUS', fetched_at: '2024-01-01 00:00:00',
      }],
      total: 1, page: 1, per_page: 25, pages: 1,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('vehicle deleted')).toBeInTheDocument());
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('pages through results with Prev/Next', async () => {
    api.getDvsaVehicles.mockImplementation(page => Promise.resolve({
      items: [{
        id: page, vehicle_id: page, registration: `REG${page}`,
        make: 'M', model: `Model${page}`, fetched_at: '2024-01-01 00:00:00',
      }],
      total: 30, page, per_page: 25, pages: 2,
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
    api.getDvsaVehicles.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 25, pages: 0 });
    renderPage();
    await waitFor(() => expect(screen.getByText(/No DVSA vehicles stored yet/)).toBeInTheDocument());
  });
});
