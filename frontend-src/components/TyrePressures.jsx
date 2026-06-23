import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { fmtPressurePsiBar } from '../units.js';

export default function TyrePressures() {
  const { currentGarage } = useAuth();
  const [vehicles, setVehicles] = useState(null);

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

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Tyre pressures — {currentGarage.name}</h1>
      </div>

      {vehicles === null ? (
        <p className="text-muted">Loading…</p>
      ) : vehicles.length === 0 ? (
        <div className="card"><p className="card-message">No vehicles yet</p></div>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Vehicle</th><th>Front</th><th>Rear</th></tr></thead>
              <tbody>
                {vehicles.map(v => (
                  <tr key={v.id}>
                    <td><Link to={`/vehicles/${v.id}`}>{v.name}</Link></td>
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
