import { useState, useEffect, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useDisplayPrefs } from '../DisplayPrefsContext.jsx';
import { SkeletonRows } from './Skeleton.jsx';
import RegPlate from './RegPlate.jsx';
import ReminderLine from './ReminderLine.jsx';
import { REMINDER_LABELS } from '../constants.js';
import { fmtCost, fmtDistance } from '../units.js';

const statSkeleton = <span className="skeleton-line" style={{ width: 48, height: 34, display: 'inline-block' }} />;

const STATUS_RANK = { overdue: 0, due_soon: 1, upcoming: 2 };
const worstStatus = rs =>
  rs.reduce((worst, r) => (STATUS_RANK[r.status] < STATUS_RANK[worst] ? r.status : worst), 'upcoming');

function VehicleRow({ vehicle: v, reminders: rs, formatName, navigate }) {
  // Vehicles with something overdue or due soon start expanded: the dashboard exists to
  // surface what needs action, and the flat list this replaces showed everything at once,
  // so collapsing an overdue item by default would be a regression. `null` means "follow
  // that default" — computed at render, not seeded in an effect, because the reminders
  // arrive after the first paint and would otherwise freeze the wrong default. An explicit
  // click sticks.
  const [override, setOverride] = useState(null);
  const worst = rs.length ? worstStatus(rs) : null;
  const open = rs.length > 0 && (override ?? worst !== 'upcoming');
  const reg = v.registration || v.mot_baseline?.registration;

  return (
    <>
      <tr
        className="row-clickable"
        onClick={e => { if (!e.target.closest('a, button')) navigate(`/vehicles/${v.id}`); }}
      >
        <td><span className="vehicle-name-cell"><Link to={`/vehicles/${v.id}`}>{v.name}</Link><RegPlate reg={reg} /></span></td>
        <td className="col-mobile-hide">{[v.year ?? v.mot_baseline?.year, v.make ?? formatName(v.mot_baseline?.make), v.model ?? formatName(v.mot_baseline?.model)].filter(Boolean).join(' ') || '—'}</td>
        <td>{v.latest_odometer ? fmtDistance(v.latest_odometer.odometer_km, v.odometer_unit) : '—'}</td>
        <td className="col-mobile-hide">{v.service_count}</td>
        <td className="col-shrink">
          {rs.length === 0 ? <span className="text-muted">—</span> : (
            // A real <button>, so the row's own click handler (which skips 'a, button')
            // leaves it alone and it stays keyboard-operable.
            <button
              type="button"
              className="reminder-toggle"
              aria-expanded={open}
              aria-controls={`vehicle-reminders-${v.id}`}
              aria-label={`${rs.length} reminder${rs.length === 1 ? '' : 's'} for ${v.name}`}
              onClick={() => setOverride(!open)}
            >
              <span className={`badge badge-${worst}`}>
                {rs.length}
                <span className="col-mobile-hide">{REMINDER_LABELS[worst].toLowerCase()}</span>
              </span>
              <span className="dvsa-record-caret" aria-hidden="true">{open ? '▲' : '▼'}</span>
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="reminder-subrow">
          <td colSpan={5} id={`vehicle-reminders-${v.id}`}>
            <div className="reminder-sublist">
              {rs.map(r => (
                <button
                  key={r.id == null ? r.type : `${r.type}-${r.id}`}
                  type="button"
                  className="reminder-row reminder-row--button"
                  // Only service reminders have a service page; the rest open the vehicle.
                  onClick={() => navigate(r.type === 'service' ? `/services/${r.id}` : `/vehicles/${v.id}`)}
                >
                  <ReminderLine reminder={r} />
                </button>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Dashboard() {
  const { currentGarage } = useAuth();
  const { formatName, showUpcoming, setShowUpcoming } = useDisplayPrefs();
  const [vehicles, setVehicles] = useState(null);
  const [services, setServices] = useState(null);
  const [reminders, setReminders] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!currentGarage) return;
    api.getVehicles(currentGarage.id).then(setVehicles).catch(() => {});
    api.getServices(currentGarage.id).then(setServices).catch(() => {});
    api.getReminders(currentGarage.id).then(setReminders).catch(() => {});
  }, [currentGarage]);

  // Filtered once, here, so the per-vehicle badge count, its colour and the auto-expand
  // default all follow the low-priority toggle without re-deriving it.
  const remindersByVehicle = useMemo(() => {
    const byVehicle = new Map();
    for (const r of reminders ?? []) {
      if (!showUpcoming && r.status === 'upcoming') continue;
      if (!byVehicle.has(r.vehicle_id)) byVehicle.set(r.vehicle_id, []);
      byVehicle.get(r.vehicle_id).push(r);
    }
    return byVehicle;
  }, [reminders, showUpcoming]);

  if (!currentGarage) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Dashboard</h1></div>
        <div className="card"><p className="card-message">Create a garage in the admin panel to get started.</p></div>
      </div>
    );
  }

  const dueCount = reminders === null ? null : reminders.filter(r => r.status !== 'upcoming').length;
  const upcomingCount = reminders === null ? 0 : reminders.length - dueCount;
  const totalSpent = services === null ? null : services.reduce((sum, s) => sum + (s.cost ?? 0), 0);
  const unitFor = (vehicleId) => vehicles?.find(v => v.id === vehicleId)?.odometer_unit ?? 'mi';

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard — {currentGarage.name}</h1>
      </div>
      <div className="stat-grid">
        <Link to="/vehicles" className="stat-card">
          <div className="stat-value">{vehicles === null ? statSkeleton : vehicles.length}</div>
          <div className="stat-label">Vehicles</div>
        </Link>
        <Link to="/services" className="stat-card">
          <div className="stat-value">{services === null ? statSkeleton : services.length}</div>
          <div className="stat-label">Services logged</div>
        </Link>
        <Link to="/services" className="stat-card">
          <div className="stat-value">{totalSpent === null ? statSkeleton : fmtCost(totalSpent)}</div>
          <div className="stat-label">Total spent</div>
        </Link>
        <div className="stat-card">
          <div className="stat-value">{dueCount === null ? statSkeleton : dueCount}</div>
          <div className="stat-label">Maintenance due</div>
        </div>
      </div>

      <div className="section-header mb-3">
        <h2 className="section-title">The garage</h2>
        {upcomingCount > 0 && (
          <button className="btn btn-secondary btn-sm" onClick={() => setShowUpcoming(!showUpcoming)}>
            {showUpcoming ? 'Hide upcoming' : `Show ${upcomingCount} upcoming`}
          </button>
        )}
      </div>
      <div className="card mb-6">
        {reminders?.length === 0 && vehicles?.length > 0 && (
          <p className="card-message">Nothing on the horizon — ride on 🏁</p>
        )}
        <div className="table-wrap">
          <table>
            <thead><tr><th>Vehicle</th><th className="col-mobile-hide">Make / model</th><th>Odometer</th><th className="col-mobile-hide">Services</th><th className="col-shrink">Due</th></tr></thead>
            <tbody>
              {vehicles === null
                ? <SkeletonRows cols={['25%', '35%', '20%', '40px', '80px']} rows={3} />
                : vehicles.map(v => (
                  <VehicleRow
                    key={v.id}
                    vehicle={v}
                    reminders={remindersByVehicle.get(v.id) ?? []}
                    formatName={formatName}
                    navigate={navigate}
                  />
                ))
              }
              {vehicles !== null && vehicles.length === 0 && (
                <tr><td colSpan={5} className="empty">No vehicles yet — <Link to="/vehicles/new">add your first</Link></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <h2 className="section-title mb-3">Recent services</h2>
      <div className="card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Vehicle</th><th>Service</th><th className="col-mobile-hide">Odometer</th><th>Cost</th></tr></thead>
            <tbody>
              {services === null
                ? <SkeletonRows cols={['90px', '20%', '40%', '90px', '60px']} rows={3} />
                : services.slice(0, 8).map(s => (
                  <tr key={s.id} className="row-clickable" onClick={e => { if (!e.target.closest('a, button')) navigate(`/services/${s.id}`); }}>
                    <td>{s.date}</td>
                    <td><Link to={`/vehicles/${s.vehicle_id}`}>{s.vehicle_name}</Link></td>
                    <td><Link to={`/services/${s.id}`}>{s.title}</Link></td>
                    <td className="col-mobile-hide">{s.odometer_km != null ? fmtDistance(s.odometer_km, unitFor(s.vehicle_id)) : '—'}</td>
                    <td>{s.cost != null ? fmtCost(s.cost) : '—'}</td>
                  </tr>
                ))
              }
              {services !== null && services.length === 0 && <tr><td colSpan={5} className="empty">No services yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
