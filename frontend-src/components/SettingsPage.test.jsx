import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPage from './SettingsPage';
import { ThemeProvider } from '../ThemeContext.jsx';
import { DisplayPrefsProvider } from '../DisplayPrefsContext.jsx';
import { api } from '../api.js';

// Mutable so a test can swap in a different user, garage or role before rendering.
let currentUser = { username: 'alice', is_admin: false };
const auth = {
  currentGarage: { id: 3, name: 'Home Garage' },
  roleFor: () => 'owner',
  refreshGarages: vi.fn(),
};

vi.mock('../AuthContext.jsx', () => ({ useAuth: () => ({ ...auth, user: currentUser }) }));
vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));
vi.mock('../api.js', () => ({
  api: { changePassword: vi.fn(), updateGarageSettings: vi.fn() },
}));

beforeEach(() => {
  currentUser = { username: 'alice', is_admin: false };
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  vi.clearAllMocks();
  auth.currentGarage = { id: 3, name: 'Home Garage' };
  auth.roleFor = () => 'owner';
});

const renderSettings = () => render(
  <ThemeProvider><DisplayPrefsProvider><SettingsPage /></DisplayPrefsProvider></ThemeProvider>,
);

describe('SettingsPage', () => {
  it('renders the Settings title and section headings', () => {
    renderSettings();
    expect(screen.getByRole('heading', { name: 'Settings', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Account' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Appearance' })).toBeInTheDocument();
  });

  it('shows the three theme options with System selected by default', () => {
    renderSettings();
    expect(screen.getByRole('radio', { name: 'System' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Light' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'false');
  });

  it('selecting a theme updates the selection and persists it', () => {
    renderSettings();
    fireEvent.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(screen.getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'System' })).toHaveAttribute('aria-checked', 'false');
    expect(localStorage.getItem('torqued.theme')).toBe('dark');
  });

  it('keeps the password form collapsed inside the account card until asked for', () => {
    renderSettings();
    expect(screen.getByText('Signed in as')).toBeInTheDocument();
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.queryByText('Current password')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /change password/i }));
    expect(screen.getByText('Current password')).toBeInTheDocument();
    expect(screen.getByText('New password')).toBeInTheDocument();
    expect(screen.getByText('Confirm new password')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('Current password')).not.toBeInTheDocument();
  });

  it('shows the site-admin pill inline with the username, for admins only', () => {
    renderSettings();
    expect(screen.queryByText('Site admin')).not.toBeInTheDocument();

    currentUser = { username: 'root', is_admin: true };
    renderSettings();
    expect(screen.getByText('Site admin')).toHaveClass('user-badge-admin');
  });

  it('shows the tidy-names toggle on by default', () => {
    renderSettings();
    expect(screen.getByText('Tidy up vehicle names')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'On' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Off' })).toHaveAttribute('aria-checked', 'false');
  });

  it('turning tidy-names off updates the selection and persists it', () => {
    renderSettings();
    fireEvent.click(screen.getByRole('radio', { name: 'Off' }));
    expect(screen.getByRole('radio', { name: 'Off' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'On' })).toHaveAttribute('aria-checked', 'false');
    expect(localStorage.getItem('torqued.titleCaseNames')).toBe('false');
  });

  describe('maintenance reminder windows', () => {
    it('names the garage and shows the defaults as placeholders when unset', () => {
      renderSettings();
      expect(screen.getByRole('heading', { name: 'Maintenance reminders' })).toBeInTheDocument();
      expect(screen.getByText('Home Garage')).toBeInTheDocument();
      expect(screen.getByLabelText('Service — days ahead')).toHaveValue(null);
      expect(screen.getByLabelText('Service — days ahead')).toHaveAttribute('placeholder', '30');
      expect(screen.getByLabelText('Service — distance ahead')).toHaveAttribute('placeholder', '2000');
      expect(screen.getByLabelText('MOT — days ahead')).toHaveAttribute('placeholder', '60');
      expect(screen.getByLabelText('Road tax — days ahead')).toHaveAttribute('placeholder', '30');
    });

    it("shows the garage's overrides, with the distance back in the unit it was entered", () => {
      auth.currentGarage = {
        id: 3, name: 'Home Garage',
        reminder_service_days: 45, reminder_service_km: 3218.688, reminder_service_unit: 'mi',
        reminder_mot_days: 90, reminder_tax_days: 14,
      };
      renderSettings();
      expect(screen.getByLabelText('Service — days ahead')).toHaveValue(45);
      expect(screen.getByLabelText('Service — distance ahead')).toHaveValue(2000);
      expect(screen.getByRole('button', { name: 'mi' })).toHaveAttribute('aria-pressed', 'true');
    });

    it('converts the distance when the unit toggle flips', () => {
      renderSettings();
      fireEvent.change(screen.getByLabelText('Service — distance ahead'), { target: { value: '2000' } });
      fireEvent.click(screen.getByRole('button', { name: 'km' }));
      expect(screen.getByLabelText('Service — distance ahead')).toHaveValue(3219);
      fireEvent.click(screen.getByRole('button', { name: 'mi' }));
      expect(screen.getByLabelText('Service — distance ahead')).toHaveValue(2000);
    });

    it('saves the windows and refreshes the garages', async () => {
      api.updateGarageSettings.mockResolvedValue({});
      renderSettings();
      fireEvent.change(screen.getByLabelText('Service — days ahead'), { target: { value: '45' } });
      fireEvent.click(screen.getByRole('button', { name: 'Save reminders' }));
      await waitFor(() => expect(auth.refreshGarages).toHaveBeenCalled());
      expect(api.updateGarageSettings).toHaveBeenCalledWith(3, expect.objectContaining({
        reminder_service_days: '45', reminder_service_unit: 'mi',
      }));
    });

    it('is read-only for a member', () => {
      auth.roleFor = () => 'member';
      renderSettings();
      expect(screen.getByLabelText('Service — days ahead')).toBeDisabled();
      expect(screen.getByRole('button', { name: 'mi' })).toBeDisabled();
      expect(screen.queryByRole('button', { name: 'Save reminders' })).toBeNull();
      expect(screen.getByText('Only a garage owner can change these.')).toBeInTheDocument();
    });

    it('is hidden entirely when the user has no garage', () => {
      auth.currentGarage = null;
      renderSettings();
      expect(screen.queryByRole('heading', { name: 'Maintenance reminders' })).toBeNull();
    });
  });
});
