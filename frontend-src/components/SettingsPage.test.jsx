import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPage from './SettingsPage';
import { ThemeProvider } from '../ThemeContext.jsx';
import { DisplayPrefsProvider } from '../DisplayPrefsContext.jsx';

vi.mock('../AuthContext.jsx', () => ({
  useAuth: () => ({ user: { username: 'alice', is_admin: false } }),
}));
vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));
vi.mock('../api.js', () => ({ api: { changePassword: vi.fn() } }));

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
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
    expect(screen.getByRole('heading', { name: 'Password' })).toBeInTheDocument();
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

  it('still exposes the change-password form', () => {
    renderSettings();
    expect(screen.getByText('Signed in as')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /change password/i })).toBeInTheDocument();
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
});
