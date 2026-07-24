import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useDisplayPrefs } from '../DisplayPrefsContext.jsx';
import RegPlate from './RegPlate.jsx';
import { KIND_ICONS, KIND_LABELS, VehicleKind } from '../constants.js';
import { fmtDistanceBoth } from '../units.js';

export default function VehicleList() {
  const { currentGarage } = useAuth();
  const { formatName } = useDisplayPrefs();
  const ro = currentGarage?.role === 'readonly';
  const [vehicles, setVehicles] = useState(null);
  const [filter, setFilter] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    if (currentGarage) api.getVehicles(currentGarage.id, showArchived).then(setVehicles);
  }, [currentGarage, showArchived]);

  if (!currentGarage) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Vehicles</h1></div>
        <div className="card"><p className="card-message">Create a garage in the admin panel to get started.</p></div>
      </div>
    );
  }

  // Effective value = user override, else the DVSA MOT baseline (same rule as the detail panel).
  const eff = (v, key) => {
    const o = v[key];
    return o != null && o !== '' ? o : (v.mot_baseline?.[key] ?? null);
  };
  // Same, but tidies the DVSA baseline (make/model) per the title-case setting. The user's
  // own override is returned untouched; only the baseline fallback is formatted.
  const effName = (v, key) => {
    const o = v[key];
    return o != null && o !== '' ? o : formatName(v.mot_baseline?.[key] ?? null);
  };

  const q = filter.toLowerCase();
  const visible = q
    ? (vehicles ?? []).filter(v =>
        v.name.toLowerCase().includes(q) ||
        String(eff(v, 'make') ?? '').toLowerCase().includes(q) ||
        String(eff(v, 'model') ?? '').toLowerCase().includes(q) ||
        String(eff(v, 'registration') ?? '').toLowerCase().includes(q)
      )
    : (vehicles ?? []);

  const cars = visible.filter(v => v.kind === VehicleKind.CAR);
  const motorcycles = visible.filter(v => v.kind === VehicleKind.MOTORCYCLE);

  const renderCard = (v) => (
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
          {[eff(v, 'year'), effName(v, 'make'), effName(v, 'model')].filter(Boolean).join(' ') || '—'}
        </div>
        {eff(v, 'registration') && <div><RegPlate reg={eff(v, 'registration')} /></div>}
        <div className="vehicle-card-meta">
          <span>{v.latest_odometer ? fmtDistanceBoth(v.latest_odometer.odometer_km, v.odometer_unit) : 'No mileage yet'}</span>
          <span>{v.service_count} service{v.service_count !== 1 ? 's' : ''}</span>
        </div>
      </div>
    </Link>
  );

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{currentGarage.name}</h1>
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

      {cars.length > 0 && (
        <section className="vehicle-section">
          <h2 className="list-section-header">Cars</h2>
          <div className="vehicle-grid">{cars.map(renderCard)}</div>
        </section>
      )}

      {motorcycles.length > 0 && (
        <section className="vehicle-section">
          <h2 className="list-section-header">Motorcycles</h2>
          <div className="vehicle-grid">{motorcycles.map(renderCard)}</div>
        </section>
      )}

      {vehicles !== null && visible.length === 0 && (
        <div className="card"><p className="card-message">{filter ? 'No matches' : 'No vehicles yet — add your first one'}</p></div>
      )}
    </div>
  );
}
