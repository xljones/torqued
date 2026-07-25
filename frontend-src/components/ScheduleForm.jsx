import { ScheduleKind, SCHEDULE_KIND_LABELS } from '../constants.js';

// Blank state for the schedule add/edit form. `interval_distance` is in the vehicle's
// display unit; the caller converts to km via the API payload.
export const EMPTY_SCHEDULE = {
  kind: ScheduleKind.MINOR, name: '', interval_months: '', interval_distance: '', enabled: true,
};

// Controlled add/edit form for a service schedule. The parent owns the form state
// (`form` + `set`) and the save/cancel handlers, so it can create or update as needed.
export default function ScheduleForm({ form, set, unit, onSave, onCancel }) {
  return (
    <div className="schedule-edit mb-2">
      <div className="form-grid">
        <div className="field">
          <label>Type</label>
          <select value={form.kind} onChange={e => set('kind', e.target.value)}>
            {Object.entries(SCHEDULE_KIND_LABELS).map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </div>
        {form.kind === ScheduleKind.CUSTOM && (
          <div className="field">
            <label>Name</label>
            <input value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Valve clearance" />
          </div>
        )}
        <div className="field">
          <label>Every (months)</label>
          <input type="number" min="1" step="1" value={form.interval_months}
            onChange={e => set('interval_months', e.target.value)} placeholder="e.g. 12" />
        </div>
        <div className="field">
          <label>Every (distance, {unit})</label>
          <input type="number" min="1" step="any" value={form.interval_distance}
            onChange={e => set('interval_distance', e.target.value)} placeholder={`e.g. 6000`} />
        </div>
        <div className="field">
          <label>Active</label>
          <label className="text-sm">
            <input type="checkbox" checked={form.enabled} onChange={e => set('enabled', e.target.checked)} />
            {' '}Generate reminders
          </label>
        </div>
      </div>
      <p className="form-hint muted">Set a month interval, a distance interval, or both.</p>
      <div className="btn-group">
        <button type="button" className="btn btn-success btn-sm" onClick={onSave}>Save</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
