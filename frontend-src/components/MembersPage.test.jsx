import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import MembersPage from './MembersPage';

vi.mock('../AuthContext.jsx', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'boss', is_admin: false },
    currentGarage: { id: 1, name: 'Home Garage', role: 'owner' },
    refreshGarages: vi.fn(),
  }),
}));

vi.mock('../api.js', () => ({
  api: {
    getMembers: vi.fn().mockResolvedValue([
      { user_id: 1, username: 'boss', role: 'owner' },
      { user_id: 2, username: 'rider', role: 'member' },
      { user_id: 3, username: 'viewer', role: 'readonly' },
    ]),
  },
}));

describe('MembersPage', () => {
  it('lists members of the current garage', async () => {
    render(<MembersPage />);
    await waitFor(() => {
      expect(screen.getByText('Members — Home Garage')).toBeInTheDocument();
      expect(screen.getByText('boss')).toBeInTheDocument();
      expect(screen.getByText('rider')).toBeInTheDocument();
      expect(screen.getByText('viewer')).toBeInTheDocument();
    });
  });

  it('shows the add-member form for garage owners', async () => {
    render(<MembersPage />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Username to add/)).toBeInTheDocument();
    });
  });
});
