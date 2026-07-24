import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../api.js';
import { useToast } from './Toast.jsx';
import SuggestInput from './SuggestInput.jsx';
import FaultCodeInput from './FaultCodeInput.jsx';
import { FormMode, SERVICE_CATEGORIES, ScheduleKind } from '../constants.js';
import { fromKm } from '../units.js';
import { scheduleTitle, scheduleInterval } from '../schedules.js';

const EMPTY = {
  date: new Date().toISOString().slice(0, 10),
  title: '', category: '', description: '', performed_by: '', cost: '',
  odometer: '', odometer_unit: 'mi', next_due_date: '', next_due_distance: '',
  service_schedule_ids: [], fault_codes: [],
};

export default function ServiceForm({ mode }) {
  // CREATE mounts at /vehicles/:vehicleId/services/new, EDIT at /services/:id/edit
  const { vehicleId, id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const isEdit = mode === FormMode.EDIT;
  const [form, setForm] = useState(EMPTY);
  const [vehicle, setVehicle] = useState(null);
  const [performers, setPerformers] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.getPerformers().then(setPerformers).catch(() => {}); }, []);
  useEffect(() => {
    if (vehicle) api.getSchedules(vehicle.id).then(setSchedules).catch(() => {});
  }, [vehicle]);

  useEffect(() => {
    if (isEdit && id) {
      api.getService(id).then(s => {
        const unit = s.odometer_unit || s.vehicle_odometer_unit || 'mi';
        setForm({
          date: s.date, title: s.title, category: s.category ?? '',
          description: s.description ?? '', performed_by: s.performed_by ?? '',
          cost: s.cost ?? '',
          odometer: s.odometer_km != null ? +fromKm(s.odometer_km, unit).toFixed(0) : '',
          odometer_unit: unit,
          next_due_date: s.next_due_date ?? '',
          next_due_distance: s.next_due_km != null ? +fromKm(s.next_due_km, unit).toFixed(0) : '',
          service_schedule_ids: s.service_schedule_ids ?? [],
          fault_codes: (s.fault_codes || []).map(fc => fc.code),
        });
        api.getVehicle(s.vehicle_id).then(setVehicle);
      });
    } else if (vehicleId) {
      api.getVehicle(vehicleId).then(v => {
        setVehicle(v);
        setForm(f => ({ ...f, odometer_unit: v.odometer_unit }));
      });
    }
  }, [isEdit, id, vehicleId]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  // Toggle a schedule link. A major service includes the minor, so ticking a major
  // auto-ticks the minor schedule(s) too (still individually removable).
  function toggleSchedule(schedule, checked) {
    setForm(f => {
      const ids = new Set(f.service_schedule_ids);
      if (checked) {
        ids.add(schedule.id);
        if (schedule.kind === ScheduleKind.MAJOR) {
          schedules.filter(s => s.kind === ScheduleKind.MINOR).forEach(s => ids.add(s.id));
        }
      } else {
        ids.delete(schedule.id);
      }
      return { ...f, service_schedule_ids: [...ids] };
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEdit) {
        await api.updateService(id, form);
        toast('Service updated');
        navigate(`/services/${id}`);
      } else {
        const s = await api.createService(vehicleId, form);
        toast('Service logged');
        navigate(`/services/${s.id}`);
      }
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  const backTo = isEdit ? `/services/${id}` : `/vehicles/${vehicleId}`;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="back-link">
            <Link to={backTo}>← {vehicle ? vehicle.name : 'Back'}</Link>
          </div>
          <h1 className="page-title">{isEdit ? 'Edit service' : 'Log service'}</h1>
        </div>
      </div>

      <div className="card card-body">
        <form onSubmit={handleSubmit}>
          <div className="form-grid mb-4">
            <div className="field">
              <label>Date *</label>
              <input type="date" value={form.date} onChange={e => set('date', e.target.value)} required />
            </div>
            <div className="field">
              <label>Title *</label>
              <input value={form.title} onChange={e => set('title', e.target.value)} placeholder="e.g. Annual service, New rear tyre" autoFocus={!isEdit} />
            </div>
            <div className="field">
              <label>Category</label>
              <SuggestInput
                value={form.category}
                onChange={v => set('category', v)}
                options={SERVICE_CATEGORIES}
                placeholder="e.g. Oil change"
              />
            </div>
            <div className="field">
              <label>Done by</label>
              <SuggestInput
                value={form.performed_by}
                onChange={v => set('performed_by', v)}
                options={performers}
                placeholder="Me, garage name…"
              />
            </div>
            <div className="field">
              <label>Cost</label>
              <input type="number" step="any" min="0" value={form.cost} onChange={e => set('cost', e.target.value)} placeholder="0.00" />
            </div>
            <div className="field">
              <label>Odometer</label>
              <div className="inline-form-sm">
                <input type="number" step="any" min="0" value={form.odometer} onChange={e => set('odometer', e.target.value)} placeholder="Reading" />
                <select value={form.odometer_unit} onChange={e => set('odometer_unit', e.target.value)}>
                  <option value="mi">mi</option>
                  <option value="km">km</option>
                </select>
              </div>
            </div>
            <div className="field span-2">
              <label>What was done</label>
              <textarea value={form.description} onChange={e => set('description', e.target.value)} placeholder="Parts used, torque values, anything future-you will want to know…" />
            </div>
            <div className="field span-2">
              <label>Fault codes observed</label>
              <FaultCodeInput codes={form.fault_codes} onChange={v => set('fault_codes', v)} />
              <p className="form-hint muted">Type a code (e.g. P0016) or search by keyword. Press Enter to add.</p>
            </div>
            <div className="field">
              <label>Next due (date)</label>
              <input type="date" value={form.next_due_date} onChange={e => set('next_due_date', e.target.value)} />
              <p className="form-hint muted">Sets a reminder for this category.</p>
            </div>
            <div className="field">
              <label>Next due (odometer, {form.odometer_unit})</label>
              <input type="number" step="any" min="0" value={form.next_due_distance} onChange={e => set('next_due_distance', e.target.value)} placeholder="Reading when next due" />
            </div>
            {schedules.length > 0 && (
              <div className="field span-2">
                <label>Fulfils schedules</label>
                <div className="checkbox-list">
                  {schedules.map(s => (
                    <label key={s.id} className="checkbox-row text-sm">
                      <input
                        type="checkbox"
                        checked={form.service_schedule_ids.includes(s.id)}
                        onChange={e => toggleSchedule(s, e.target.checked)}
                      />
                      {' '}{scheduleTitle(s)}{' '}
                      <span className="muted">({scheduleInterval(s, vehicle?.odometer_unit)})</span>
                    </label>
                  ))}
                </div>
                <p className="form-hint muted">Anchors each schedule’s next-due reminder to this service. Ticking a major service also ticks the minor.</p>
              </div>
            )}
          </div>

          <div className="form-actions">
            <button className="btn btn-success" disabled={saving || !form.title || !form.date}>
              {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Log service'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
