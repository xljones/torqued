import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import CodeLookup from './CodeLookup';

vi.mock('../api.js', () => ({
  api: {
    lookupCode: vi.fn().mockResolvedValue({
      code: 'P0016',
      description: 'Crankshaft Position - Camshaft Position Correlation (Bank 1 Sensor A)',
      system: 'Powertrain (engine, transmission, emissions)',
      scope: 'generic',
      subsystem: null,
    }),
    searchCodes: vi.fn().mockResolvedValue([
      { code: 'P0300', description: 'Random/Multiple Cylinder Misfire Detected' },
    ]),
    listCodes: vi.fn().mockResolvedValue([
      { code: 'P0001', description: 'Fuel Volume Regulator Control Circuit/Open' },
      { code: 'P0002', description: 'Fuel Volume Regulator Control Circuit Range/Performance' },
    ]),
  },
}));

describe('CodeLookup', () => {
  it('shows the full code list before searching', async () => {
    render(<CodeLookup />);
    await waitFor(() => {
      expect(screen.getByText('Fuel Volume Regulator Control Circuit/Open')).toBeInTheDocument();
      expect(screen.getByText('P0002')).toBeInTheDocument();
    });
  });

  it('looks up a full code and shows its description', async () => {
    render(<CodeLookup />);
    await userEvent.type(screen.getByPlaceholderText(/P0016/), 'P0016');
    await waitFor(() => {
      expect(screen.getByText(/Crankshaft Position - Camshaft Position Correlation/)).toBeInTheDocument();
      expect(screen.getByText('Generic (SAE)')).toBeInTheDocument();
    });
  });

  it('falls back to keyword search for non-code input', async () => {
    render(<CodeLookup />);
    await userEvent.type(screen.getByPlaceholderText(/P0016/), 'misfire');
    await waitFor(() => {
      expect(screen.getByText('Random/Multiple Cylinder Misfire Detected')).toBeInTheDocument();
    });
  });
});
