import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import RegPlate from './RegPlate.jsx';
import { fmtPressurePsiBar } from '../units.js';

export default function TyrePressures() {
  const { currentGarage } = useAuth();
  const [vehicles, setVehicles] = useState(null);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    if (currentGarage) api.getVehicles(currentGarage.id).then(setVehicles);
  }, [currentGarage]);

  if (!currentGarage) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Tyre pressures</h1></div>
        <div className="card"><p className="card-message">Create a garage in the admin panel to get started.</p></div>
      </div>
    );
  }

  // Identity fields are resolved server-side (user override else DVSA baseline) into `effective`.
  const q = filter.toLowerCase();
  const visible = q
    ? (vehicles ?? []).filter(v =>
        v.name.toLowerCase().includes(q) ||
        String(v.effective?.make ?? '').toLowerCase().includes(q) ||
        String(v.effective?.model ?? '').toLowerCase().includes(q) ||
        String(v.effective?.registration ?? '').toLowerCase().includes(q)
      )
    : (vehicles ?? []);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Tyre pressures — {currentGarage.name}</h1>
      </div>

      <div className="mb-4 inline-form-sm">
        <input
          type="search"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filter by name, make, model, plate…"
          className="search-input"
        />
      </div>

      {vehicles === null ? (
        <p className="text-muted">Loading…</p>
      ) : vehicles.length === 0 ? (
        <div className="card"><p className="card-message">No vehicles yet</p></div>
      ) : visible.length === 0 ? (
        <div className="card"><p className="card-message">No matches</p></div>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Vehicle</th><th>Front</th><th>Rear</th></tr></thead>
              <tbody>
                {visible.map(v => (
                  <tr key={v.id}>
                    <td>
                      <span className="vehicle-name-cell">
                        <Link to={`/vehicles/${v.id}`}>{v.name}</Link>
                        {v.effective?.registration && <RegPlate reg={v.effective.registration} />}
                      </span>
                    </td>
                    <td>
                      <div>{fmtPressurePsiBar(v.tyre_pressure_front_psi) ?? '—'}</div>
                      <div className="text-sm text-muted">{v.tyre_size_front || '—'}</div>
                    </td>
                    <td>
                      <div>{fmtPressurePsiBar(v.tyre_pressure_rear_psi) ?? '—'}</div>
                      <div className="text-sm text-muted">{v.tyre_size_rear || '—'}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
