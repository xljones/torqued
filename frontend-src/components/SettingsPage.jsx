import { useState, useEffect } from 'react';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useTheme } from '../ThemeContext.jsx';
import { useDisplayPrefs } from '../DisplayPrefsContext.jsx';
import { useToast } from './Toast.jsx';
import { fromKm, toKm } from '../units.js';

const THEME_LABELS = { light: 'Light', dark: 'Dark', system: 'System' };

// Mirrors the application defaults in the backend's torqued/reminders.py — shown as input
// placeholders so a blank field reads as "use the default" rather than "unset".
const WINDOW_DEFAULTS = { service_days: 30, service_distance: { mi: 2000, km: 3219 }, mot_days: 60, tax_days: 30 };

// The stored km value shown in the garage's chosen unit, rounded — these are coarse
// thresholds, so a fractional mile would be noise.
const distanceFor = (km, unit) => (km == null ? '' : String(Math.round(fromKm(km, unit))));

export default function SettingsPage() {
  const { user, currentGarage, roleFor, refreshGarages } = useAuth();
  const { mode, setMode, MODES } = useTheme();
  const { titleCaseNames, setTitleCaseNames } = useDisplayPrefs();
  const toast = useToast();
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [saving, setSaving] = useState(false);
  const [windows, setWindows] = useState(null);
  const [savingWindows, setSavingWindows] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const setWindow = (k, v) => setWindows(w => ({ ...w, [k]: v }));

  const canEditWindows = !!currentGarage && roleFor(currentGarage.id) === 'owner';
  const windowUnit = windows?.reminder_service_unit || 'mi';

  // Seed from the garage row, which GET /api/garages already returns whole.
  useEffect(() => {
    if (!currentGarage) return setWindows(null);
    const unit = currentGarage.reminder_service_unit || 'mi';
    setWindows({
      reminder_service_days: currentGarage.reminder_service_days ?? '',
      reminder_service_distance: distanceFor(currentGarage.reminder_service_km, unit),
      reminder_service_unit: unit,
      reminder_mot_days: currentGarage.reminder_mot_days ?? '',
      reminder_tax_days: currentGarage.reminder_tax_days ?? '',
    });
  }, [currentGarage]);

  // Convert the number as the unit flips, so 2,000 mi becomes 3,219 km rather than
  // silently turning into 2,000 km.
  const switchWindowUnit = (unit) => setWindows(w => {
    if (w.reminder_service_unit === unit) return w;
    return {
      ...w,
      reminder_service_unit: unit,
      reminder_service_distance: w.reminder_service_distance === ''
        ? ''
        : distanceFor(toKm(Number(w.reminder_service_distance), w.reminder_service_unit), unit),
    };
  });

  async function handleSaveWindows() {
    setSavingWindows(true);
    try {
      await api.updateGarageSettings(currentGarage.id, windows);
      await refreshGarages();
      toast('Reminder windows saved');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSavingWindows(false);
    }
  }

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
          <div className="settings-field">
            <div>
              <div className="fw-600">Tidy up vehicle names</div>
              <div className="meta">
                Official DVSA records come in capitals (e.g. “VOLKSWAGEN PASSAT”). With this on,
                makes, models, colours and fuel types from the DVSA show in title case
                (“Volkswagen Passat”). It only changes how they&apos;re displayed — the stored
                record is untouched, anything you type yourself shows exactly as entered, and a
                few names (BMW, McLaren) won&apos;t capitalise perfectly.
              </div>
            </div>
            <div className="btn-group" role="radiogroup" aria-label="Tidy up vehicle names">
              {[['On', true], ['Off', false]].map(([label, val]) => (
                <button
                  key={label}
                  type="button"
                  role="radio"
                  aria-checked={titleCaseNames === val}
                  className={`btn btn-secondary${titleCaseNames === val ? ' btn-active' : ''}`}
                  onClick={() => setTitleCaseNames(val)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {windows && (
        <section className="settings-section">
          <h2 className="section-title mb-2">Maintenance reminders</h2>
          <div className="card card-body">
            <p className="meta mb-3">
              How far ahead a reminder turns amber (“Due soon”) for{' '}
              <strong>{currentGarage.name}</strong>. This applies to the whole garage —
              every garage has its own. Leave a field blank to use the default.
            </p>
            <div className="form-grid mb-3">
              <div className="field">
                <label htmlFor="reminder-service-days">Service — days ahead</label>
                <input
                  id="reminder-service-days" type="number" min="1" max="3650" step="1"
                  placeholder={WINDOW_DEFAULTS.service_days} disabled={!canEditWindows}
                  value={windows.reminder_service_days}
                  onChange={e => setWindow('reminder_service_days', e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="reminder-service-distance">Service — distance ahead</label>
                <div className="pressure-entry">
                  <input
                    id="reminder-service-distance" type="number" min="1" step="1"
                    placeholder={WINDOW_DEFAULTS.service_distance[windowUnit]}
                    disabled={!canEditWindows}
                    value={windows.reminder_service_distance}
                    onChange={e => setWindow('reminder_service_distance', e.target.value)}
                  />
                  <div className="unit-toggle" role="group" aria-label="Distance unit">
                    {['mi', 'km'].map(u => (
                      <button
                        key={u} type="button" className={windowUnit === u ? 'is-active' : ''}
                        aria-pressed={windowUnit === u} disabled={!canEditWindows}
                        onClick={() => switchWindowUnit(u)}
                      >
                        {u}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="field">
                <label htmlFor="reminder-mot-days">MOT — days ahead</label>
                <input
                  id="reminder-mot-days" type="number" min="1" max="3650" step="1"
                  placeholder={WINDOW_DEFAULTS.mot_days} disabled={!canEditWindows}
                  value={windows.reminder_mot_days}
                  onChange={e => setWindow('reminder_mot_days', e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="reminder-tax-days">Road tax — days ahead</label>
                <input
                  id="reminder-tax-days" type="number" min="1" max="3650" step="1"
                  placeholder={WINDOW_DEFAULTS.tax_days} disabled={!canEditWindows}
                  value={windows.reminder_tax_days}
                  onChange={e => setWindow('reminder_tax_days', e.target.value)}
                />
              </div>
            </div>
            {canEditWindows ? (
              <div className="form-actions">
                <button
                  type="button" className="btn btn-success"
                  onClick={handleSaveWindows} disabled={savingWindows}
                >
                  {savingWindows ? 'Saving…' : 'Save reminders'}
                </button>
              </div>
            ) : (
              <p className="meta">Only a garage owner can change these.</p>
            )}
          </div>
        </section>
      )}

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
