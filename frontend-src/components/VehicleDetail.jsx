import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useToast } from './Toast.jsx';
import RelativeTime from './RelativeTime.jsx';
import ExportDropdown from './ExportDropdown.jsx';
import PhotoGallery from './PhotoGallery.jsx';
import { SkeletonPage } from './Skeleton.jsx';
import { KIND_LABELS, REMINDER_LABELS } from '../constants.js';
import { fmtCost, fmtDistance, fmtDistanceBoth, fmtPressure } from '../units.js';

function Sparkline({ series, unit }) {
  if (!series || series.length < 2) return null;
  const xs = series.map(p => new Date(p.date).getTime());
  const ys = series.map(p => p.odometer_km);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const W = 600, H = 60, PAD = 4;
  const px = x => x1 === x0 ? W / 2 : PAD + ((x - x0) / (x1 - x0)) * (W - 2 * PAD);
  const py = y => y1 === y0 ? H / 2 : H - PAD - ((y - y0) / (y1 - y0)) * (H - 2 * PAD);
  const points = series.map(p => `${px(new Date(p.date).getTime()).toFixed(1)},${py(p.odometer_km).toFixed(1)}`).join(' ');
  return (
    <svg className="sparkline" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
      aria-label={`Mileage from ${fmtDistance(y0, unit)} to ${fmtDistance(y1, unit)}`}>
      <polyline points={points} />
    </svg>
  );
}

function MileageCard({ vehicle, onLogged }) {
  const { user } = useAuth();
  const ro = user?.is_readonly;
  const toast = useToast();
  const [series, setSeries] = useState(null);
  const [logs, setLogs] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    odometer: '',
    unit: vehicle.odometer_unit,
    note: '',
  });

  const refresh = useCallback(() => {
    api.getMileage(vehicle.id).then(setSeries);
    api.getOdometerLogs(vehicle.id).then(setLogs);
  }, [vehicle.id]);
  useEffect(refresh, [refresh]);

  async function handleAdd(e) {
    e.preventDefault();
    try {
      await api.createOdometerLog(vehicle.id, form);
      setForm(f => ({ ...f, odometer: '', note: '' }));
      toast('Mileage logged');
      refresh();
      onLogged?.();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleDelete(logId) {
    if (!confirm('Delete this odometer entry?')) return;
    await api.deleteOdometerLog(logId);
    toast('Entry deleted');
    refresh();
    onLogged?.();
  }

  return (
    <div className="card card-body mb-6">
      <div className="section-header">
        <h2 className="section-title">Mileage</h2>
        {logs?.length > 0 && (
          <button className="btn btn-secondary btn-sm" onClick={() => setShowLogs(v => !v)}>
            {showLogs ? 'Hide entries' : `Entries (${logs.length})`}
          </button>
        )}
      </div>
      {vehicle.latest_odometer ? (
        <>
          <div className="odo-current">{fmtDistance(vehicle.latest_odometer.odometer_km, vehicle.odometer_unit)}</div>
          <div className="odo-current-alt">
            {fmtDistance(vehicle.latest_odometer.odometer_km, vehicle.odometer_unit === 'mi' ? 'km' : 'mi')}
            {' · '}last logged {vehicle.latest_odometer.date}
          </div>
        </>
      ) : (
        <p className="text-muted text-sm">No readings yet — log one below.</p>
      )}
      <Sparkline series={series} unit={vehicle.odometer_unit} />

      {!ro && (
        <form onSubmit={handleAdd} className="inline-form-sm mt-3" style={{ flexWrap: 'wrap' }}>
          <input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} required />
          <input
            type="number" step="any" min="0" placeholder="Odometer"
            value={form.odometer}
            onChange={e => setForm(f => ({ ...f, odometer: e.target.value }))}
            required
            style={{ width: 110 }}
          />
          <select value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))}>
            <option value="mi">mi</option>
            <option value="km">km</option>
          </select>
          <input placeholder="Note (optional)" value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))} />
          <button className="btn btn-primary btn-sm">Log</button>
        </form>
      )}

      {showLogs && logs && (
        <div className="table-wrap mt-3">
          <table>
            <thead><tr><th>Date</th><th>Reading</th><th>Note</th><th></th></tr></thead>
            <tbody>
              {logs.map(l => (
                <tr key={l.id}>
                  <td>{l.date}</td>
                  <td>{fmtDistanceBoth(l.odometer_km, l.unit)}</td>
                  <td>{l.note || '—'}</td>
                  <td className="col-shrink">
                    {!ro && <button className="btn btn-danger btn-sm" onClick={() => handleDelete(l.id)}>Delete</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SpecsCard({ vehicle, onSaved }) {
  const { user } = useAuth();
  const ro = user?.is_readonly;
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState([]);

  function startEdit() {
    setRows(vehicle.specs.map(s => ({ name: s.name, value: s.value })));
    setEditing(true);
  }

  async function handleSave() {
    try {
      await api.replaceSpecs(vehicle.id, rows.filter(r => r.name.trim()));
      setEditing(false);
      toast('Specs saved');
      onSaved?.();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const setRow = (i, k, v) => setRows(rs => rs.map((r, j) => j === i ? { ...r, [k]: v } : r));

  return (
    <div className="card card-body mb-6">
      <div className="section-header">
        <h2 className="section-title">Reference specs</h2>
        {!ro && !editing && <button className="btn btn-secondary btn-sm" onClick={startEdit}>Edit</button>}
        {editing && (
          <div className="btn-group">
            <button className="btn btn-success btn-sm" onClick={handleSave}>Save</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        )}
      </div>
      {editing ? (
        <div>
          {rows.map((r, i) => (
            <div key={i} className="inline-form-sm mb-2">
              <input value={r.name} onChange={e => setRow(i, 'name', e.target.value)} placeholder="Name (e.g. Engine oil)" />
              <input value={r.value} onChange={e => setRow(i, 'value', e.target.value)} placeholder="Value (e.g. 10W-40, 3.1 L)" />
              <button type="button" className="btn btn-danger btn-sm" onClick={() => setRows(rs => rs.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setRows(rs => [...rs, { name: '', value: '' }])}>
            + Add spec
          </button>
        </div>
      ) : vehicle.specs.length === 0 ? (
        <p className="text-muted text-sm">Things you always look up: oil grade, chain slack, torque values…</p>
      ) : (
        <div className="form-grid">
          {vehicle.specs.map(s => (
            <div key={s.id} className="field">
              <label>{s.name}</label>
              <span>{s.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function VehicleDetail() {
  const { user } = useAuth();
  const ro = user?.is_readonly;
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [vehicle, setVehicle] = useState(null);
  const [services, setServices] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState(null);

  const refresh = useCallback(() => {
    api.getVehicle(id).then(setVehicle);
    api.getVehicleServices(id).then(setServices);
  }, [id]);
  useEffect(refresh, [refresh]);
  useEffect(() => { api.getVehicleHistory(id).then(setHistory); }, [id]);

  async function handleDelete() {
    if (!confirm('Delete this vehicle and ALL its service history, mileage logs, and photos?')) return;
    await api.deleteVehicle(id);
    toast('Vehicle deleted');
    navigate('/vehicles');
  }

  async function handleRevert(versionId) {
    if (!confirm('Revert this vehicle to the selected version?')) return;
    await api.revertVehicle(id, versionId);
    toast('Vehicle reverted');
    refresh();
    api.getVehicleHistory(id).then(setHistory);
  }

  if (!vehicle) return <SkeletonPage />;

  const unit = vehicle.odometer_unit;
  const dueReminders = vehicle.reminders.filter(r => r.status !== 'upcoming');

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="back-link"><Link to="/vehicles">← Garage</Link></div>
          <h1 className="page-title">
            {vehicle.name}{' '}
            <span className={`badge badge-${vehicle.kind}`}>{KIND_LABELS[vehicle.kind]}</span>
            {!!vehicle.archived && <span className="badge"> Archived</span>}
          </h1>
        </div>
        <div className="btn-group">
          <ExportDropdown
            label="Export services"
            options={[
              { label: 'Comma separated values (.csv)', onClick: () => { window.location.href = `/api/export/services?vehicle_id=${id}`; } },
              { label: 'Tab separated values (.tsv)', onClick: () => { window.location.href = `/api/export/services?vehicle_id=${id}&format=tsv`; } },
              { label: 'JSON (.json)', onClick: () => { window.location.href = `/api/export/services?vehicle_id=${id}&format=json`; } },
            ]}
          />
          {!ro && <Link to={`/vehicles/${id}/edit`} className="btn btn-secondary">Edit</Link>}
          {!ro && <button className="btn btn-danger" onClick={handleDelete}>Delete</button>}
        </div>
      </div>

      {dueReminders.length > 0 && (
        <div className="card mb-6">
          {dueReminders.map(r => (
            <div key={r.id} className="reminder-row">
              <div className="reminder-main">
                <span className="reminder-title">{r.category || r.title}</span>
                <span className="reminder-sub">
                  After “{r.title}” ({r.date})
                  {r.next_due_date && ` — due ${r.next_due_date}`}
                  {r.next_due_km != null && ` — due at ${fmtDistance(r.next_due_km, unit)}`}
                  {r.km_remaining != null && r.km_remaining > 0 && ` (${fmtDistance(r.km_remaining, unit)} to go)`}
                </span>
              </div>
              <span className={`badge badge-${r.status}`}>{REMINDER_LABELS[r.status]}</span>
            </div>
          ))}
        </div>
      )}

      <div className="card card-body mb-6">
        <div className="form-grid">
          <div className="field"><label>Make / model</label><span>{[vehicle.make, vehicle.model].filter(Boolean).join(' ') || '—'}</span></div>
          <div className="field"><label>Year</label><span>{vehicle.year ?? '—'}</span></div>
          <div className="field"><label>Registration</label><span>{vehicle.registration ? <span className="reg-plate">{vehicle.registration}</span> : '—'}</span></div>
          <div className="field"><label>VIN</label><span>{vehicle.vin || '—'}</span></div>
          <div className="field"><label>Colour</label><span>{vehicle.colour || '—'}</span></div>
          <div className="field"><label>Fuel</label><span>{vehicle.fuel_type || '—'}</span></div>
          <div className="field"><label>Purchased</label><span>{vehicle.purchase_date || '—'}</span></div>
          <div className="field"><label>Updated</label><span><RelativeTime value={vehicle.updated_at} /></span></div>
          {vehicle.notes && <div className="field span-2"><label>Notes</label><span>{vehicle.notes}</span></div>}
        </div>
      </div>

      {(vehicle.tyre_pressure_front_psi != null || vehicle.tyre_pressure_rear_psi != null
        || vehicle.tyre_size_front || vehicle.tyre_size_rear) && (
        <div className="card card-body mb-6">
          <h2 className="section-title mb-3">Tyres</h2>
          <div className="pressure-grid">
            <div className="pressure-tile">
              <div className="pressure-label">Front</div>
              <div className="pressure-value">{vehicle.tyre_pressure_front_psi != null ? `${+vehicle.tyre_pressure_front_psi.toFixed(1)} psi` : '—'}</div>
              {vehicle.tyre_pressure_front_psi != null && <div className="pressure-alt">{fmtPressure(vehicle.tyre_pressure_front_psi).split(' / ')[1]}</div>}
              {vehicle.tyre_size_front && <div className="pressure-size">{vehicle.tyre_size_front}</div>}
            </div>
            <div className="pressure-tile">
              <div className="pressure-label">Rear</div>
              <div className="pressure-value">{vehicle.tyre_pressure_rear_psi != null ? `${+vehicle.tyre_pressure_rear_psi.toFixed(1)} psi` : '—'}</div>
              {vehicle.tyre_pressure_rear_psi != null && <div className="pressure-alt">{fmtPressure(vehicle.tyre_pressure_rear_psi).split(' / ')[1]}</div>}
              {vehicle.tyre_size_rear && <div className="pressure-size">{vehicle.tyre_size_rear}</div>}
            </div>
          </div>
        </div>
      )}

      <SpecsCard vehicle={vehicle} onSaved={refresh} />
      <MileageCard vehicle={vehicle} onLogged={refresh} />

      <div className="section-header">
        <h2 className="section-title">Service history ({services?.length ?? 0})</h2>
        {!ro && <Link to={`/vehicles/${id}/services/new`} className="btn btn-primary btn-sm">+ Log service</Link>}
      </div>
      <div className="card mb-6">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Service</th><th>Category</th><th className="col-mobile-hide">Odometer</th><th className="col-mobile-hide">By</th><th>Cost</th></tr></thead>
            <tbody>
              {services?.map(s => (
                <tr key={s.id} className="row-clickable" onClick={e => { if (!e.target.closest('a, button')) navigate(`/services/${s.id}`); }}>
                  <td>{s.date}</td>
                  <td><Link to={`/services/${s.id}`}>{s.title}</Link>{s.photo_count > 0 && <span className="text-muted text-sm"> 📷{s.photo_count}</span>}</td>
                  <td>{s.category || '—'}</td>
                  <td className="col-mobile-hide">{s.odometer_km != null ? fmtDistance(s.odometer_km, unit) : '—'}</td>
                  <td className="col-mobile-hide">{s.performed_by || '—'}</td>
                  <td>{s.cost != null ? fmtCost(s.cost) : '—'}</td>
                </tr>
              ))}
              {services !== null && services.length === 0 && <tr><td colSpan={6} className="empty">No services logged yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mb-6">
        <PhotoGallery photos={vehicle.photos} vehicleId={vehicle.id} onChange={refresh} />
      </div>

      <div className="mt-4">
        <button className="btn btn-secondary btn-sm" onClick={() => setShowHistory(v => !v)}>
          {showHistory ? '▼' : '▶'} Version history{history ? ` (${history.length})` : ''}
        </button>
        {showHistory && (
          <div className="card mt-2">
            {history === null && <p className="card-message">Loading…</p>}
            {history?.length === 0 && <p className="card-message">No history yet.</p>}
            {history?.map((v, i) => {
              const prev = history[i + 1];
              const diff = (key) => prev && String(v[key] ?? '') !== String(prev[key] ?? '');
              const f = (label, value, key) => (
                <span key={key}>
                  <em className={diff(key) ? 'diff' : ''}>{label}</em>{' '}
                  <span className={diff(key) ? 'diff-value' : ''}>{value}</span>
                </span>
              );
              return (
                <div key={v.id} className="history-entry">
                  <div className="history-row">
                    <div>
                      <div className="history-meta">
                        {v.changed_at} — <strong>{v.changed_by_username ?? 'unknown'}</strong>
                      </div>
                      <div className="history-fields">
                        {f('name', v.name, 'name')}
                        {f('make', v.make || '—', 'make')}
                        {f('model', v.model || '—', 'model')}
                        {f('year', v.year ?? '—', 'year')}
                        {f('plate', v.registration || '—', 'registration')}
                        {f('front psi', v.tyre_pressure_front_psi ?? '—', 'tyre_pressure_front_psi')}
                        {f('rear psi', v.tyre_pressure_rear_psi ?? '—', 'tyre_pressure_rear_psi')}
                        {f('notes', v.notes || '—', 'notes')}
                      </div>
                    </div>
                    {i > 0 && !ro && (
                      <button className="btn btn-secondary btn-sm flex-shrink-0" onClick={() => handleRevert(v.id)}>
                        Revert to this
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
