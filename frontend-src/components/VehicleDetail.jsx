import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useDisplayPrefs } from '../DisplayPrefsContext.jsx';
import { useToast } from './Toast.jsx';
import RelativeTime from './RelativeTime.jsx';
import ExportDropdown from './ExportDropdown.jsx';
import PhotoGallery from './PhotoGallery.jsx';
import MotCard from './MotCard.jsx';
import RegPlate from './RegPlate.jsx';
import MileageChart from './MileageChart.jsx';
import MotField from './MotField.jsx';
import { SkeletonPage } from './Skeleton.jsx';
import { KIND_LABELS, REMINDER_LABELS, ScheduleKind } from '../constants.js';
import ScheduleForm, { EMPTY_SCHEDULE } from './ScheduleForm.jsx';
import { scheduleTitle, scheduleInterval } from '../schedules.js';
import { overdueBy } from '../reminders.js';
import { fmtCost, fmtDistance, fmtDistanceBoth, fmtDistanceDelta, fmtInterval, fmtPressure, fromKm, toKm } from '../units.js';
import { useMediaQuery } from '../useMediaQuery.js';

const SOURCE_LABEL = { manual: 'Manual', mot: 'MOT', service: 'Service' };

// Whole days between two YYYY-MM-DD dates, parsed as UTC midnight to avoid DST drift.
const daysBetween = (a, b) =>
  Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);

export function MileageCard({ vehicle, ro, onLogged }) {
  const toast = useToast();
  // Below the mobile breakpoint the entries table gets cramped — abbreviate the
  // interval ("7 days" → "7d") so the "Since previous" column stays on one line.
  const compactInterval = useMediaQuery('(max-width: 768px)');
  const [series, setSeries] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    odometer: '',
    unit: vehicle.odometer_unit,
    note: '',
  });

  const refresh = useCallback(() => {
    api.getMileage(vehicle.id).then(setSeries);
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

  // An odometer can't go backwards: the new reading must sit between the highest reading
  // recorded on or before its date and the lowest reading recorded on or after it.
  const enteredKm = form.odometer === '' ? null : toKm(Number(form.odometer), form.unit);
  let priorPeak = null; // highest reading dated on/before the entered date
  let laterFloor = null; // lowest reading dated on/after the entered date
  if (series && Number.isFinite(enteredKm)) {
    for (const p of series) {
      if (p.date <= form.date && (priorPeak === null || p.odometer_km > priorPeak.odometer_km)) {
        priorPeak = p;
      }
      if (p.date >= form.date && (laterFloor === null || p.odometer_km < laterFloor.odometer_km)) {
        laterFloor = p;
      }
    }
  }
  let readingWarning = null;
  if (priorPeak && enteredKm < priorPeak.odometer_km) {
    readingWarning = { peer: priorPeak, dir: 'lower' };
  } else if (laterFloor && enteredKm > laterFloor.odometer_km) {
    readingWarning = { peer: laterFloor, dir: 'higher' };
  }

  return (
    <div className="card card-body mb-6">
      <div className="section-header">
        <h2 className="section-title">Mileage</h2>
        {series?.length > 0 && (
          <button className="btn btn-secondary btn-sm" onClick={() => setShowLogs(v => !v)}>
            {showLogs ? 'Hide entries' : `Entries (${series.length})`}
          </button>
        )}
      </div>
      {vehicle.latest_odometer ? (
        <>
          <div className="odo-current">{fmtDistance(vehicle.latest_odometer.odometer_km, vehicle.odometer_unit)}</div>
          <div className="odo-current-alt">
            {fmtDistance(vehicle.latest_odometer.odometer_km, vehicle.odometer_unit === 'mi' ? 'km' : 'mi')}
            {' · '}last logged <RelativeTime value={vehicle.latest_odometer.date} />
          </div>
        </>
      ) : (
        <p className="text-muted text-sm">No readings yet — log one below.</p>
      )}
      <MileageChart series={series} unit={vehicle.odometer_unit} />

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
          <span className="inline-form-unit">{vehicle.odometer_unit}</span>
          <input placeholder="Note (optional)" value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))} />
          <button className="btn btn-primary btn-sm">Log</button>
        </form>
      )}
      {!ro && readingWarning && (
        <p className="form-warning mt-2">
          ⚠ This is {readingWarning.dir} than the
          {' '}{fmtDistance(readingWarning.peer.odometer_km, vehicle.odometer_unit)} reading
          {' '}on {readingWarning.peer.date} — odometers don&rsquo;t usually go backwards. Double-check the value.
        </p>
      )}

      {showLogs && series && (
        <div className="table-wrap mt-3">
          <table>
            <thead><tr><th>Date</th><th>Reading</th><th>Since previous</th><th>Source</th><th>Note</th><th></th></tr></thead>
            <tbody>
              {series
                .map((l, i) => ({ ...l, prev: i > 0 ? series[i - 1] : null }))
                .reverse()
                .map(l => (
                <tr key={`${l.source}-${l.id}`}>
                  <td>{l.date}</td>
                  <td>{fmtDistanceBoth(l.odometer_km, l.unit)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {l.prev
                      ? `${fmtDistanceDelta(l.odometer_km - l.prev.odometer_km, vehicle.odometer_unit)} in ${fmtInterval(daysBetween(l.prev.date, l.date), { compact: compactInterval })}`
                      : '—'}
                  </td>
                  <td><span className={`badge badge-source-${l.source}`}>{SOURCE_LABEL[l.source] ?? l.source}</span></td>
                  <td>{l.note || '—'}</td>
                  <td className="col-shrink">
                    {!ro && l.source === 'manual' && (
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(l.id)}>Delete</button>
                    )}
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

function SpecsCard({ vehicle, ro, onSaved }) {
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

function SchedulesCard({ vehicle, ro }) {
  const toast = useToast();
  const unit = vehicle.odometer_unit;
  const [schedules, setSchedules] = useState(null);
  const [editing, setEditing] = useState(null); // 'new' | schedule id | null
  const [form, setForm] = useState(EMPTY_SCHEDULE);

  const refresh = useCallback(() => { api.getSchedules(vehicle.id).then(setSchedules); }, [vehicle.id]);
  useEffect(refresh, [refresh]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  function startAdd() { setForm(EMPTY_SCHEDULE); setEditing('new'); }
  function startEdit(s) {
    setForm({
      kind: s.kind,
      name: s.name ?? '',
      interval_months: s.interval_months ?? '',
      interval_distance: s.interval_km != null ? +fromKm(s.interval_km, unit).toFixed(0) : '',
      enabled: !!s.enabled,
    });
    setEditing(s.id);
  }

  async function handleSave() {
    const body = {
      kind: form.kind,
      name: form.kind === ScheduleKind.CUSTOM ? form.name : null,
      interval_months: form.interval_months === '' ? null : Number(form.interval_months),
      interval_distance: form.interval_distance,
      interval_unit: unit,
      enabled: form.enabled,
    };
    try {
      if (editing === 'new') await api.createSchedule(vehicle.id, body);
      else await api.updateSchedule(editing, body);
      setEditing(null);
      toast('Schedule saved');
      refresh();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this schedule? Any services that fulfilled it are kept.')) return;
    await api.deleteSchedule(id);
    toast('Schedule deleted');
    refresh();
  }

  const cols = ro ? 2 : 3;

  return (
    <>
      <div className="section-header">
        <h2 className="section-title">Service schedules{schedules ? ` (${schedules.length})` : ''}</h2>
        {!ro && editing !== 'new' && (
          <button className="btn btn-primary btn-sm" onClick={startAdd}>+ Add schedule</button>
        )}
      </div>
      <div className="card mb-6">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Schedule</th><th>Interval</th>{!ro && <th></th>}</tr></thead>
            <tbody>
              {schedules === null && <tr><td colSpan={cols} className="empty">Loading…</td></tr>}
              {schedules?.map(s => editing === s.id ? (
                <tr key={s.id}>
                  <td colSpan={cols}>
                    <ScheduleForm form={form} set={set} unit={unit}
                      onSave={handleSave} onCancel={() => setEditing(null)} />
                  </td>
                </tr>
              ) : (
                <tr key={s.id}>
                  <td>{scheduleTitle(s)}{!s.enabled && <span className="badge"> Off</span>}</td>
                  <td>{scheduleInterval(s, unit)}</td>
                  {!ro && (
                    <td className="col-shrink">
                      <div className="btn-group">
                        <button className="btn btn-secondary btn-sm" onClick={() => startEdit(s)}>Edit</button>
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(s.id)}>✕</button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
              {editing === 'new' && (
                <tr>
                  <td colSpan={cols}>
                    <ScheduleForm form={form} set={set} unit={unit}
                      onSave={handleSave} onCancel={() => setEditing(null)} />
                  </td>
                </tr>
              )}
              {schedules?.length === 0 && editing !== 'new' && (
                <tr><td colSpan={cols} className="empty">No schedules yet — recurring services (minor, major, or your own) remind you from the last time you logged them.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export default function VehicleDetail() {
  const { roleFor } = useAuth();
  const { formatName } = useDisplayPrefs();
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [vehicle, setVehicle] = useState(null);
  const [services, setServices] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState(null);
  const [inclPhotos, setInclPhotos] = useState(false);

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

  const ro = roleFor(vehicle.garage_id) === 'readonly';
  const unit = vehicle.odometer_unit;
  const dueReminders = vehicle.reminders.filter(r => r.status !== 'upcoming');
  const fieldProps = { vehicle, baseline: vehicle.mot_baseline, ro };

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="back-link"><Link to="/vehicles">← Vehicles</Link></div>
          <h1 className="page-title">
            {vehicle.name}{' '}
            <span className={`badge badge-${vehicle.kind}`}>{KIND_LABELS[vehicle.kind]}</span>
            {!!vehicle.archived && <span className="badge"> Archived</span>}
          </h1>
        </div>
        <div className="btn-group">
          <ExportDropdown
            label="Export"
            options={[
              { label: 'Comma separated values (.csv)', onClick: () => { window.location.href = `/api/export/services?vehicle_id=${id}`; } },
              { label: 'Tab separated values (.tsv)', onClick: () => { window.location.href = `/api/export/services?vehicle_id=${id}&format=tsv`; } },
              { label: 'JSON (.json)', onClick: () => { window.location.href = `/api/export/services?vehicle_id=${id}&format=json`; } },
              { divider: true },
              { type: 'checkbox', label: 'Include photos', checked: inclPhotos, onChange: e => setInclPhotos(e.target.checked) },
              { label: 'Vehicle report (.pdf)', note: 'Full history', onClick: () => { window.location.href = `/api/export/vehicles/${id}/pdf${inclPhotos ? '?include_photos=1' : ''}`; } },
            ]}
          />
          {!ro && <Link to={`/vehicles/${id}/edit`} className="btn btn-secondary">Edit</Link>}
          {!ro && <button className="btn btn-danger" onClick={handleDelete}>Delete</button>}
        </div>
      </div>

      {dueReminders.length > 0 && (
        <div className="card mb-6">
          {dueReminders.map(r => (
            <div key={r.id == null ? r.type : `${r.type}-${r.id}`} className="reminder-row">
              <div className="reminder-main">
                <span className="reminder-title">{r.category || r.title}</span>
                <span className="reminder-sub">
                  {r.type === 'mot'
                    ? `${r.status === 'overdue' ? 'Expired' : 'Expires'} ${r.next_due_date}`
                    : r.type === 'tax'
                    ? `${r.status === 'overdue' ? 'Expired' : 'Due'} ${r.next_due_date}`
                    : <>
                        After “{r.title}” ({r.date})
                        {r.next_due_date && ` — due ${r.next_due_date}`}
                        {r.next_due_km != null && ` — due at ${fmtDistance(r.next_due_km, unit)}`}
                        {r.km_remaining != null && r.km_remaining > 0 && ` (${fmtDistance(r.km_remaining, unit)} to go)`}
                      </>}
                  {overdueBy(r, unit) && (
                    <span className="reminder-overdue"> — {overdueBy(r, unit)}</span>
                  )}
                </span>
              </div>
              <span className={`badge badge-${r.status}`}>{REMINDER_LABELS[r.status]}</span>
            </div>
          ))}
        </div>
      )}

      <div className="card card-body mb-6">
        <div className="form-grid">
          <MotField label="Make" fieldKey="make" {...fieldProps} format={formatName} />
          <MotField label="Model" fieldKey="model" {...fieldProps} format={formatName} />
          <MotField label="Year" fieldKey="year" {...fieldProps} />
          <MotField label="Registration" fieldKey="registration" {...fieldProps}
            render={v => <RegPlate reg={v} />} />
          <MotField label="Engine size" fieldKey="engine_size" {...fieldProps}
            render={v => (/^\d+$/.test(String(v)) ? `${v} cc` : v)} />
          <MotField label="Colour" fieldKey="colour" {...fieldProps} format={formatName} />
          <MotField label="Fuel" fieldKey="fuel_type" {...fieldProps} format={formatName} />
          <MotField label="First used" fieldKey="first_used_date" {...fieldProps} />
          <MotField label="First registered" fieldKey="registration_date" {...fieldProps} />
          <div className="field"><label>VIN</label><span>{vehicle.vin || '—'}</span></div>
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

      <SpecsCard vehicle={vehicle} ro={ro} onSaved={refresh} />
      <MileageCard vehicle={vehicle} ro={ro} onLogged={refresh} />
      <MotCard vehicle={vehicle} ro={ro} onSynced={refresh} />
      <SchedulesCard vehicle={vehicle} ro={ro} />

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
        <PhotoGallery photos={vehicle.photos} vehicleId={vehicle.id} coverPhotoId={vehicle.cover_photo_id} ro={ro} onChange={refresh} />
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
