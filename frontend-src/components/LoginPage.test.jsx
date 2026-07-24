import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LoginPage from './LoginPage';

const mockLogin = vi.fn();
let mockAuth;

vi.mock('../AuthContext.jsx', () => ({
  useAuth: () => mockAuth,
}));

beforeEach(() => {
  mockLogin.mockReset();
  mockAuth = { login: mockLogin };
});

function fillForm(username, password) {
  fireEvent.change(screen.getAllByRole('textbox')[0], { target: { value: username } });
  fireEvent.change(document.querySelector('input[type="password"]'), { target: { value: password } });
}

describe('LoginPage', () => {
  it('renders username and password fields', () => {
    render(<LoginPage />);
    expect(screen.getByText('Username')).toBeInTheDocument();
    expect(screen.getByText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('calls login with entered credentials', async () => {
    mockLogin.mockResolvedValue(undefined);
    render(<LoginPage />);

    fillForm('alice', 'secret');
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('alice', 'secret'));
  });

  it('shows error message on failed login', async () => {
    mockLogin.mockRejectedValue(new Error('Invalid username or password'));
    render(<LoginPage />);

    fillForm('alice', 'wrongpass');
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText('Invalid username or password')).toBeInTheDocument()
    );
  });
});
