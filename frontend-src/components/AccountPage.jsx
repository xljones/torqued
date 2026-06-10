import { useState } from 'react';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useToast } from './Toast.jsx';

export default function AccountPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function handleSubmit(e) {
    e.preventDefault();
    if (form.new_password !== form.confirm_password) {
      toast('New passwords do not match', 'error');
      return;
    }
    setSaving(true);
    try {
      await api.changePassword(form.current_password, form.new_password);
      setForm({ current_password: '', new_password: '', confirm_password: '' });
      toast('Password changed');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Change Password</h1>
      </div>

      <div className="card card-body mw-sm">
        <div className="mb-4">
          <div className="meta">Signed in as</div>
          <div className="fw-600">{user?.username}</div>
          {user?.is_readonly && <div className="meta">Read-only account</div>}
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-grid mb-3">
            <div className="field span-2">
              <label>Current password</label>
              <input
                type="password"
                value={form.current_password}
                onChange={e => set('current_password', e.target.value)}
                autoComplete="current-password"
              />
            </div>
            <div className="field span-2">
              <label>New password</label>
              <input
                type="password"
                value={form.new_password}
                onChange={e => set('new_password', e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="field span-2">
              <label>Confirm new password</label>
              <input
                type="password"
                value={form.confirm_password}
                onChange={e => set('confirm_password', e.target.value)}
                autoComplete="new-password"
              />
            </div>
          </div>
          <div className="form-actions">
            <button
              className="btn btn-success"
              disabled={saving || !form.current_password || !form.new_password || !form.confirm_password}
            >
              {saving ? 'Saving…' : 'Change password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
