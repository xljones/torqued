import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useDisplayPrefs } from '../DisplayPrefsContext.jsx';
import { SkeletonRows } from './Skeleton.jsx';
import RegPlate from './RegPlate.jsx';
import { REMINDER_LABELS } from '../constants.js';
import { fmtCost, fmtDistance } from '../units.js';

const statSkeleton = <span className="skeleton-line" style={{ width: 48, height: 34, display: 'inline-block' }} />;

export default function Dashboard() {
  const { currentGarage } = useAuth();
  const { formatName } = useDisplayPrefs();
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

  if (!currentGarage) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Dashboard</h1></div>
        <div className="card"><p className="card-message">Create a garage in the admin panel to get started.</p></div>
      </div>
    );
  }

  const dueCount = reminders === null ? null : reminders.filter(r => r.status !== 'upcoming').length;
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

      <h2 className="section-title mb-3">Maintenance reminders</h2>
      <div className="card mb-6">
        {reminders === null && <p className="card-message">Loading…</p>}
        {reminders?.length === 0 && <p className="card-message">Nothing on the horizon — ride on 🏁</p>}
        {reminders?.map(r => {
          const isMot = r.type === 'mot';
          const isTax = r.type === 'tax';
          const isExternal = isMot || isTax; // MOT/tax reminders link to the vehicle, not a service
          return (
            <div
              key={isExternal ? `${r.type}-${r.vehicle_id}` : r.id}
              className="reminder-row row-clickable"
              onClick={() => navigate(isExternal ? `/vehicles/${r.vehicle_id}` : `/services/${r.id}`)}
            >
              <div className="reminder-main">
                <span className="reminder-title">{r.vehicle_name} — {r.category || r.title}</span>
                <span className="reminder-sub">
                  {isMot
                    ? `${r.status === 'overdue' ? 'Expired' : 'Expires'} ${r.next_due_date}`
                    : isTax
                    ? `${r.status === 'overdue' ? 'Expired' : 'Due'} ${r.next_due_date}`
                    : <>
                        After “{r.title}” ({r.date})
                        {r.next_due_date && ` — due ${r.next_due_date}`}
                        {r.next_due_km != null && ` — due at ${fmtDistance(r.next_due_km, r.vehicle_odometer_unit)}`}
                      </>}
                </span>
              </div>
              <span className={`badge badge-${r.status}`}>{REMINDER_LABELS[r.status]}</span>
            </div>
          );
        })}
      </div>

      <h2 className="section-title mb-3">The garage</h2>
      <div className="card mb-6">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Vehicle</th><th className="col-mobile-hide">Make / model</th><th>Odometer</th><th>Services</th></tr></thead>
            <tbody>
              {vehicles === null
                ? <SkeletonRows cols={['25%', '35%', '20%', '40px']} rows={3} />
                : vehicles.map(v => {
                  const reg = v.registration || v.mot_baseline?.registration;
                  return (
                  <tr key={v.id} className="row-clickable" onClick={e => { if (!e.target.closest('a, button')) navigate(`/vehicles/${v.id}`); }}>
                    <td><span className="vehicle-name-cell"><Link to={`/vehicles/${v.id}`}>{v.name}</Link><RegPlate reg={reg} /></span></td>
                    <td className="col-mobile-hide">{[v.year ?? v.mot_baseline?.year, v.make ?? formatName(v.mot_baseline?.make), v.model ?? formatName(v.mot_baseline?.model)].filter(Boolean).join(' ') || '—'}</td>
                    <td>{v.latest_odometer ? fmtDistance(v.latest_odometer.odometer_km, v.odometer_unit) : '—'}</td>
                    <td>{v.service_count}</td>
                  </tr>
                  );
                })
              }
              {vehicles !== null && vehicles.length === 0 && (
                <tr><td colSpan={4} className="empty">No vehicles yet — <Link to="/vehicles/new">add your first</Link></td></tr>
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
