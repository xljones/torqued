import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MotCard from './MotCard';
import { DisplayPrefsProvider } from '../DisplayPrefsContext.jsx';
import { api } from '../api.js';

vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));

vi.mock('../api.js', () => ({
  api: {
    getMot: vi.fn(),
    refreshMot: vi.fn(),
    getTax: vi.fn(),
    refreshTax: vi.fn(),
  },
}));

const vehicle = { id: 1, registration: 'A1 XYZ', odometer_unit: 'mi' };

const mot = {
  registration: 'A1XYZ',
  make: 'VOLKSWAGEN',
  model: 'PASSAT',
  primary_colour: 'Blue',
  has_outstanding_recall: 'Unknown',
  fetched_at: '2026-06-11 12:00:00',
  raw: {
    registration: 'A1XYZ',
    make: 'VOLKSWAGEN',
    motTests: [{ completedDate: '2024.11.05 10:01:00', testResult: 'PASSED' }],
  },
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

const tax = {
  registration: 'A1XYZ', tax_status: 'Taxed', tax_due_date: '2026-12-01',
  fetched_at: '2026-06-11 12:00:00',
  raw: { registration: 'A1XYZ', tax_status: 'Taxed' },
};

beforeEach(() => {
  vi.clearAllMocks();
  // Default: tax enabled but nothing stored, so the MOT-only tests are unaffected.
  api.getTax.mockResolvedValue({ configured: true, tax: null });
  api.refreshTax.mockResolvedValue({ configured: true, tax: null });
});

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
      expect(screen.getByText('Fetch from DVSA & DVLA')).toBeInTheDocument();
    });
  });

  it('shows the dev env-var hint and hides the button when nothing is configured', async () => {
    api.getMot.mockResolvedValue({ configured: false, mot: null });
    api.getTax.mockResolvedValue({ configured: false, tax: null });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => {
      expect(screen.getByText(/credentials are not configured/)).toBeInTheDocument();
    });
    // No point offering a fetch that can never succeed without credentials
    expect(screen.queryByText('Fetch from DVSA & DVLA')).not.toBeInTheDocument();
  });

  it('shows a generic message in production when nothing is configured', async () => {
    vi.stubEnv('DEV', false);
    api.getMot.mockResolvedValue({ configured: false, mot: null });
    api.getTax.mockResolvedValue({ configured: false, tax: null });
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
      expect(screen.getByText('MOT')).toBeInTheDocument();
      expect(screen.getByText('Pass')).toBeInTheDocument();
      expect(screen.getByText('Fail')).toBeInTheDocument();
      expect(screen.getByText(/VOLKSWAGEN PASSAT/)).toBeInTheDocument();
    });
    // The fixture's latest test passed but its certificate has since lapsed → "Expired",
    // with the expiry date on the bottom line.
    const motTile = screen.getByText('MOT').closest('.pressure-tile');
    expect(motTile).toHaveTextContent('Expired');
    expect(motTile).toHaveTextContent('Expired 2025-11-04');
    await userEvent.click(screen.getByText('1 defect'));
    expect(screen.getByText('Tyre worn close to limit')).toBeInTheDocument();
  });

  it('shows the DVSA record verbatim even when name tidying is on', async () => {
    // The DVSA record reflects the official data as-is (all-caps as DVSA returns it);
    // the 'Tidy up vehicle names' setting must never touch it, unlike the vehicle
    // identity card. Rendered inside the provider (which defaults tidying ON).
    localStorage.setItem('torqued.titleCaseNames', 'true');
    api.getMot.mockResolvedValue({ configured: true, mot });
    render(
      <DisplayPrefsProvider>
        <MotCard vehicle={vehicle} ro={false} />
      </DisplayPrefsProvider>,
    );
    await waitFor(() => expect(screen.getByText(/VOLKSWAGEN PASSAT/)).toBeInTheDocument());
    // Not tidied to 'Volkswagen Passat'
    expect(screen.queryByText(/Volkswagen Passat/)).not.toBeInTheDocument();
    localStorage.removeItem('torqued.titleCaseNames');
  });

  it('colours the MOT tile by expiry and hides recall when unknown', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(screen.getByText('MOT')).toBeInTheDocument());

    // Fixture latest expiry (2025-11-04) is in the past → danger (red)
    expect(screen.getByText('MOT').closest('.pressure-tile'))
      .toHaveClass('pressure-tile--danger');
    // has_outstanding_recall: 'Unknown' → tile hidden entirely
    expect(screen.queryByText('Outstanding recall')).not.toBeInTheDocument();
  });

  it('shows a green recall tile when there is no outstanding recall', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot: { ...mot, has_outstanding_recall: 'No' } });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(screen.getByText('Outstanding recall')).toBeInTheDocument());
    expect(screen.getByText('Outstanding recall').closest('.pressure-tile'))
      .toHaveClass('pressure-tile--ok');
  });

  it('warns when the MOT expires within a month and flags an outstanding recall', async () => {
    const soon = new Date();
    soon.setDate(soon.getDate() + 14);
    const expiring = {
      ...mot,
      has_outstanding_recall: 'Yes',
      tests: [{ ...mot.tests[0], expiry_date: soon.toISOString().slice(0, 10) }],
    };
    api.getMot.mockResolvedValue({ configured: true, mot: expiring });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(screen.getByText('MOT')).toBeInTheDocument());

    expect(screen.getByText('MOT').closest('.pressure-tile'))
      .toHaveClass('pressure-tile--warn');
    expect(screen.getByText('Outstanding recall').closest('.pressure-tile'))
      .toHaveClass('pressure-tile--danger');
  });

  it('refreshes both MOT and tax and reports synced readings', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot });
    api.refreshMot.mockResolvedValue({ configured: true, mot });
    api.refreshTax.mockResolvedValue({ configured: true, tax });
    const onSynced = vi.fn();
    render(<MotCard vehicle={vehicle} ro={false} onSynced={onSynced} />);
    await waitFor(() => expect(screen.getByText('Refresh from DVSA & DVLA')).toBeInTheDocument());
    await userEvent.click(screen.getByText('Refresh from DVSA & DVLA'));
    await waitFor(() => {
      expect(api.refreshMot).toHaveBeenCalledWith(1);
      expect(api.refreshTax).toHaveBeenCalledWith(1);
      expect(onSynced).toHaveBeenCalled();
    });
  });

  it('shows one refreshed time when MOT and tax were refreshed together', async () => {
    // Fixture mot + tax share the same fetched_at → collapse to a single label.
    api.getMot.mockResolvedValue({ configured: true, mot });
    api.getTax.mockResolvedValue({ configured: true, tax });
    const { container } = render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(container.querySelector('.mot-reauth')).toBeInTheDocument());
    expect(container.querySelector('.mot-reauth').textContent).toMatch(/refreshed/);
    expect(container.querySelector('.mot-reauth').textContent).not.toMatch(/MOT refreshed/);
  });

  it('splits the refreshed times when MOT and tax differ', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot }); // fetched 2026-06-11
    api.getTax.mockResolvedValue({
      configured: true, tax: { ...tax, fetched_at: '2026-01-01 09:00:00' },
    });
    const { container } = render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(container.querySelector('.mot-reauth')).toBeInTheDocument());
    expect(container.querySelector('.mot-reauth').textContent).toMatch(/MOT refreshed/);
    expect(container.querySelector('.mot-reauth').textContent).toMatch(/tax/);
  });

  it('shows the refreshed time from tax alone when there is no MOT data', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot: null });
    api.getTax.mockResolvedValue({ configured: true, tax });
    const { container } = render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(container.querySelector('.mot-reauth')).toBeInTheDocument());
    expect(container.querySelector('.mot-reauth').textContent).toMatch(/refreshed/);
  });

  it('browses the raw DVSA record as an expandable tree, with nested arrays collapsed', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(screen.getByText('DVSA record')).toBeInTheDocument());

    // Open the JSON panel (defaults to the Formatted tree)
    await userEvent.click(screen.getByText('DVSA record'));

    // Top-level keys are visible; nested array starts collapsed
    expect(screen.getByText('motTests')).toBeInTheDocument();
    expect(screen.getByText('1 item')).toBeInTheDocument();
    expect(screen.queryByText('completedDate')).not.toBeInTheDocument();

    // Expanding the array reveals its (still-collapsed) element object
    await userEvent.click(screen.getByText('1 item'));
    expect(screen.getByText('2 keys')).toBeInTheDocument();
    expect(screen.queryByText('completedDate')).not.toBeInTheDocument();

    // Expanding that element reveals the leaf values
    await userEvent.click(screen.getByText('2 keys'));
    expect(screen.getByText('completedDate')).toBeInTheDocument();
  });

  it('hides the refresh button for readonly members', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot });
    render(<MotCard vehicle={vehicle} ro={true} />);
    await waitFor(() => expect(screen.getByText('MOT & tax')).toBeInTheDocument());
    expect(screen.queryByText('Refresh from DVSA & DVLA')).not.toBeInTheDocument();
  });

  // ── tax ────────────────────────────────────────────────────────────────────

  it('shows tax status and due date in one tile, green when taxed', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot: null });
    api.getTax.mockResolvedValue({ configured: true, tax });
    render(<MotCard vehicle={vehicle} ro={false} />);
    // When taxed the label carries the status; the value shows "Due <relative>" and the
    // exact due date sits on the bottom line.
    await waitFor(() => expect(screen.getByText('Taxed')).toBeInTheDocument());
    const taxTile = screen.getByText('Taxed').closest('.pressure-tile');
    expect(taxTile).toHaveTextContent('Due');
    expect(taxTile).toHaveTextContent('2026-12-01');
    expect(taxTile).toHaveClass('pressure-tile--ok');
  });

  it('colours a SORN vehicle amber with no due date', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot: null });
    api.getTax.mockResolvedValue({
      configured: true, tax: { ...tax, tax_status: 'SORN', tax_due_date: null },
    });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(screen.getByText('SORN')).toBeInTheDocument());
    const taxTile = screen.getByText('Tax status').closest('.pressure-tile');
    expect(taxTile).toHaveClass('pressure-tile--warn');
    // No due date → the third line falls back to an em dash.
    expect(taxTile).toHaveTextContent('—');
  });

  it('colours an untaxed vehicle red', async () => {
    api.getMot.mockResolvedValue({ configured: true, mot: null });
    api.getTax.mockResolvedValue({
      configured: true, tax: { ...tax, tax_status: 'Untaxed', tax_due_date: null },
    });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(screen.getByText('Untaxed')).toBeInTheDocument());
    expect(screen.getByText('Tax status').closest('.pressure-tile'))
      .toHaveClass('pressure-tile--danger');
  });

  it('shows when tax lapsed for an untaxed vehicle that carries a date', async () => {
    // The gov.uk scrape leaves this null, but the VES API would supply it — show it when present.
    api.getMot.mockResolvedValue({ configured: true, mot: null });
    api.getTax.mockResolvedValue({
      configured: true, tax: { ...tax, tax_status: 'Untaxed', tax_due_date: '2024-03-01' },
    });
    render(<MotCard vehicle={vehicle} ro={false} />);
    await waitFor(() => expect(screen.getByText('Untaxed')).toBeInTheDocument());
    expect(screen.getByText('Tax status').closest('.pressure-tile'))
      .toHaveTextContent('Expired 2024-03-01');
  });
});
