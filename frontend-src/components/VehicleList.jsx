import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { KIND_ICONS, KIND_LABELS } from '../constants.js';
import { fmtDistanceBoth } from '../units.js';

export default function VehicleList() {
  const { user } = useAuth();
  const ro = user?.is_readonly;
  const [vehicles, setVehicles] = useState(null);
  const [filter, setFilter] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    api.getVehicles(showArchived).then(setVehicles);
  }, [showArchived]);

  const q = filter.toLowerCase();
  const visible = q
    ? (vehicles ?? []).filter(v =>
        v.name.toLowerCase().includes(q) ||
        (v.make ?? '').toLowerCase().includes(q) ||
        (v.model ?? '').toLowerCase().includes(q) ||
        (v.registration ?? '').toLowerCase().includes(q)
      )
    : (vehicles ?? []);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Garage</h1>
        <div className="btn-group">
          {!ro && <Link to="/vehicles/new" className="btn btn-primary">+ Add vehicle</Link>}
        </div>
      </div>

      <div className="mb-4 inline-form-sm">
        <input
          type="search"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filter by name, make, model, plate…"
          className="search-input"
        />
        <label className="text-sm text-muted" style={{ whiteSpace: 'nowrap' }}>
          <input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} />
          {' '}Show archived
        </label>
      </div>

      {vehicles === null && <p className="text-muted">Loading…</p>}

      <div className="vehicle-grid">
        {visible.map(v => (
          <Link key={v.id} to={`/vehicles/${v.id}`} className={`vehicle-card${v.archived ? ' archived' : ''}`}>
            <div className="vehicle-card-photo">
              {v.cover_photo_id
                ? <img src={api.photoUrl(v.cover_photo_id)} alt={v.name} loading="lazy" />
                : <span aria-hidden="true">{KIND_ICONS[v.kind]}</span>}
            </div>
            <div className="vehicle-card-body">
              <div className="vehicle-card-name">
                {v.name}
                <span className={`badge badge-${v.kind}`}>{KIND_LABELS[v.kind]}</span>
                {!!v.archived && <span className="badge">Archived</span>}
              </div>
              <div className="vehicle-card-sub">
                {[v.year, v.make, v.model].filter(Boolean).join(' ') || '—'}
              </div>
              {v.registration && <div><span className="reg-plate">{v.registration}</span></div>}
              <div className="vehicle-card-meta">
                <span>{v.latest_odometer ? fmtDistanceBoth(v.latest_odometer.odometer_km, v.odometer_unit) : 'No mileage yet'}</span>
                <span>{v.service_count} service{v.service_count !== 1 ? 's' : ''}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
      {vehicles !== null && visible.length === 0 && (
        <div className="card"><p className="card-message">{filter ? 'No matches' : 'No vehicles yet — add your first one'}</p></div>
      )}
    </div>
  );
}
