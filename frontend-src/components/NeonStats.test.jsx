import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import NeonStats from './NeonStats';
import { api } from '../api.js';

vi.mock('../api.js', () => ({
  api: {
    getNeonStats: vi.fn(),
  },
}));

beforeEach(() => vi.clearAllMocks());

describe('NeonStats', () => {
  it('renders storage, compute and project once stats load', async () => {
    api.getNeonStats.mockResolvedValue({
      configured: true,
      project: { id: 'proj-abc', name: 'torqued-db', region: 'aws-eu-west-2', pg_version: 17 },
      storage_bytes: 268435456, // 256 MB
      cpu_seconds: 7200, // 2 compute-hours
      active_seconds: 3600, // 1 active-hour
      quota_reset_at: '2099-01-01T00:00:00Z',
      last_active_at: '2026-06-21T09:00:00Z',
    });
    render(<NeonStats />);
    await waitFor(() => {
      expect(screen.getByText('Storage')).toBeInTheDocument();
      expect(screen.getByText('256 MB')).toBeInTheDocument();
      expect(screen.getByText('2.00 compute-hours')).toBeInTheDocument();
      expect(screen.getByText(/torqued-db/)).toBeInTheDocument();
    });
  });

  it('shows the env-var hint when not configured', async () => {
    api.getNeonStats.mockResolvedValue({ configured: false });
    render(<NeonStats />);
    await waitFor(() => {
      expect(screen.getByText(/Stats unavailable/)).toBeInTheDocument();
      expect(screen.getByText('NEON_API_KEY')).toBeInTheDocument();
    });
  });

  it('surfaces a backend API error', async () => {
    api.getNeonStats.mockResolvedValue({ configured: true, error: 'Neon API error: 401 Unauthorized' });
    render(<NeonStats />);
    await waitFor(() => {
      expect(screen.getByText('Neon API error: 401 Unauthorized')).toBeInTheDocument();
    });
  });
});
