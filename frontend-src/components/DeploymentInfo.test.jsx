import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DeploymentInfo from './DeploymentInfo';
import { api } from '../api.js';

vi.mock('../api.js', () => ({
  api: {
    getDeploymentInfo: vi.fn(),
  },
}));

beforeEach(() => vi.clearAllMocks());

describe('DeploymentInfo', () => {
  it('shows the version, commit and a relative build time once loaded', async () => {
    api.getDeploymentInfo.mockResolvedValue({
      configured: true,
      version: '0.0.1',
      sha: 'abc1234',
      msg: 'fix(admin): add deployment card',
      built_at: '2020-01-01T00:00:00Z', // firmly in the past → deterministic "… ago"
    });
    render(<DeploymentInfo />);
    await waitFor(() => {
      expect(screen.getByText('v0.0.1')).toBeInTheDocument();
      expect(screen.getByText('abc1234')).toBeInTheDocument();
      expect(screen.getByText('fix(admin): add deployment card')).toBeInTheDocument();
    });
    // built_at is rendered via the self-updating RelativeTime component.
    expect(screen.getByText(/ago/)).toBeInTheDocument();
  });

  it('shows a hint when no build info is available', async () => {
    api.getDeploymentInfo.mockResolvedValue({ configured: false });
    render(<DeploymentInfo />);
    await waitFor(() => {
      expect(screen.getByText(/No build info yet/)).toBeInTheDocument();
      expect(screen.getByText('dist/build-info.json')).toBeInTheDocument();
    });
  });

  it('surfaces a fetch error', async () => {
    api.getDeploymentInfo.mockRejectedValue(new Error('Network down'));
    render(<DeploymentInfo />);
    await waitFor(() => {
      expect(screen.getByText('Network down')).toBeInTheDocument();
    });
  });
});
