import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MotCard from './MotCard';
import { api } from '../api.js';

vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));

vi.mock('../api.js', () => ({
  api: {
    getMot: vi.fn(),
    refreshMot: vi.fn(),
  },
}));

const vehicle = { id: 1, registration: 'LR53 UHD', odometer_unit: 'mi' };

const mot = {
  registration: 'LR53UHD',
  make: 'VOLKSWAGEN',
  model: 'PASSAT',
  primary_colour: 'Blue',
  has_outstanding_recall: 'Unknown',
  fetched_at: '2026-06-11 12:00:00',
  tests: [
    {
      id: 11, completed_date: '2024-11-05T10:01:00.000Z', test_result: 'PASSED',
      expiry_date: '2025-11-04', odometer_value: 100, odometer_unit: 'mi',
      defects: [{ text: 'Tyre worn close to limit', type: 'ADVISORY', dangerous: false }],
    },
    {
      id: 12, completed_date: '2023-10-30T09:00:00.000Z', test_result: 'FAILED',
      expiry_date: null, odometer_value: null, odometer_unit: null,
      defects: [],
    },
  ],
};

beforeEach(() => vi.clearAllMocks());

describe('MotCard', () => {
  it('renders nothing without a registration or stored data', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot: null });
    const { container } = render(<MotCard vehicle={{ id: 1, odometer_unit: 'mi' }} ro={false} />);
    await waitFor(() => expect(api.getMot).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('prompts to fetch when configured but no data yet', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot: null });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => {
      expect(screen.getByText(/No MOT data yet/)).toBeInTheDocument();
      expect(screen.getByText('Fetch from DVSA')).toBeInTheDocument();
    });
  });

  it('shows the dev env-var hint and hides the button when credentials are missing', async () => {
    api.getMot.mockResolvedValue({ configured: false, mot: null });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => {
      expect(screen.getByText(/credentials are not configured/)).toBeInTheDocument();
    });
    // No point offering a fetch that can never succeed without credentials
    expect(screen.queryByText('Fetch from DVSA')).not.toBeInTheDocument();
  });

  it('shows a generic message in production when credentials are missing', async () => {
    vi.stubEnv('DEV', false);
    api.getMot.mockResolvedValue({ configured: false, mot: null });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => {
      expect(screen.getByText('MOT history is unavailable right now.')).toBeInTheDocument();
    });
    expect(screen.queryByText(/credentials are not configured/)).not.toBeInTheDocument();
    vi.unstubAllEnvs();
  });

  it('shows the stored test history with results, expiry and defects', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => {
      expect(screen.getByText('MOT expires')).toBeInTheDocument();
      expect(screen.getByText('2025-11-04')).toBeInTheDocument();
      expect(screen.getByText('Pass')).toBeInTheDocument();
      expect(screen.getByText('Fail')).toBeInTheDocument();
      expect(screen.getByText(/VOLKSWAGEN PASSAT/)).toBeInTheDocument();
    });
    await userEvent.click(screen.getByText('1 defect'));
    expect(screen.getByText('Tyre worn close to limit')).toBeInTheDocument();
  });

  it('refreshes from the DVSA and reports synced readings', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot });
    api.refreshMot.mockResolvedValue({ configured: true, mot });
    const onSynced = vi.fn();
    render(<MotCard vehicle={vehicle} ro={false} onSynced={onSynced} />);
    await waitFor(() => expect(screen.getByText('Refresh from DVSA')).toBeInTheDocument());
    await userEvent.click(screen.getByText('Refresh from DVSA'));
    await waitFor(() => {
      expect(api.refreshMot).toHaveBeenCalledWith(1);
      expect(onSynced).toHaveBeenCalled();
    });
  });

  it('hides the refresh button for readonly members', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot });
    render(<MotCard vehicle={vehicle} ro={true} />);
    await waitFor(() => expect(screen.getByText('MOT history')).toBeInTheDocument());
    expect(screen.queryByText('Refresh from DVSA')).not.toBeInTheDocument();
  });
});
