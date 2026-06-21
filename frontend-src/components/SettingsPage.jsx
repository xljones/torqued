import { useState } from 'react';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useTheme } from '../ThemeContext.jsx';
import { useToast } from './Toast.jsx';

const THEME_LABELS = { light: 'Light', dark: 'Dark', system: 'System' };

export default function SettingsPage() {
  const { user } = useAuth();
  const { mode, setMode, MODES } = useTheme();
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
    <div className="settings-page">
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
      </div>

      <section className="settings-section">
        <h2 className="section-title mb-2">Account</h2>
        <div className="card card-body">
          <div className="meta">Signed in as</div>
          <div className="fw-600">{user?.username}</div>
          {user?.is_admin && <div className="meta">Site admin</div>}
        </div>
      </section>

      <section className="settings-section">
        <h2 className="section-title mb-2">Appearance</h2>
        <div className="card card-body">
          <div className="settings-field">
            <div>
              <div className="fw-600">Theme</div>
              <div className="meta">System follows your device&apos;s light/dark setting.</div>
            </div>
            <div className="btn-group" role="radiogroup" aria-label="Theme">
              {MODES.map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  className={`btn btn-secondary${mode === m ? ' btn-active' : ''}`}
                  onClick={() => setMode(m)}
                >
                  {THEME_LABELS[m]}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <h2 className="section-title mb-2">Password</h2>
        <div className="card card-body">
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
      </section>
    </div>
  );
}
