import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ExternalApis from './ExternalApis';
import { api } from '../api.js';

vi.mock('../api.js', () => ({
  api: {
    getExternalApis: vi.fn(),
  },
}));

beforeEach(() => vi.clearAllMocks());

describe('ExternalApis', () => {
  it('lists each external API with its effective URL, mode and token URL', async () => {
    api.getExternalApis.mockResolvedValue({
      apis: [
        { name: 'DVLA VES', purpose: 'Tax, MOT status & vehicle profile',
          mode: 'relay', url: 'https://torqued-ves.example.workers.dev' },
        { name: 'DVSA MOT', purpose: 'Full MOT test history', configured: true,
          url: 'https://history.mot.api.gov.uk/v1/trade/vehicles/registration/' },
      ],
    });
    render(<ExternalApis />);
    await waitFor(() => {
      expect(screen.getByText('DVLA VES')).toBeInTheDocument();
      expect(screen.getByText('https://torqued-ves.example.workers.dev')).toBeInTheDocument();
      expect(screen.getByText('relay')).toBeInTheDocument();
      expect(screen.getByText('DVSA MOT')).toBeInTheDocument();
    });
    // The OAuth token URL is never displayed.
    expect(screen.queryByText(/token:/)).not.toBeInTheDocument();
  });

  it('flags a source whose credentials are not configured', async () => {
    api.getExternalApis.mockResolvedValue({
      apis: [{ name: 'DVSA MOT', configured: false, url: 'https://history.mot.api.gov.uk/' }],
    });
    render(<ExternalApis />);
    await waitFor(() => expect(screen.getByText('not configured')).toBeInTheDocument());
  });

  it('surfaces a fetch error', async () => {
    api.getExternalApis.mockRejectedValue(new Error('Network down'));
    render(<ExternalApis />);
    await waitFor(() => expect(screen.getByText('Network down')).toBeInTheDocument());
  });
});
