import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import ExportDropdown from './ExportDropdown.jsx';
import { SkeletonRows } from './Skeleton.jsx';
import { fmtCost, fmtDistance } from '../units.js';

export default function ServiceList() {
  const { currentGarage } = useAuth();
  const [services, setServices] = useState(null);
  const [filter, setFilter] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    if (currentGarage) api.getServices(currentGarage.id).then(setServices);
  }, [currentGarage]);

  if (!currentGarage) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Service log</h1></div>
        <div className="card"><p className="card-message">Create a garage in the admin panel to get started.</p></div>
      </div>
    );
  }

  const q = filter.toLowerCase();
  const visible = q
    ? (services ?? []).filter(s =>
        s.title.toLowerCase().includes(q) ||
        (s.category ?? '').toLowerCase().includes(q) ||
        (s.performed_by ?? '').toLowerCase().includes(q) ||
        s.vehicle_name.toLowerCase().includes(q)
      )
    : (services ?? []);

  const totalCost = visible.reduce((sum, s) => sum + (s.cost ?? 0), 0);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Service log — {currentGarage.name}</h1>
        <div className="btn-group">
          <ExportDropdown
            label="Export"
            disabled={visible.length === 0}
            options={[
              { label: 'Comma separated values (.csv)', onClick: () => { window.location.href = `/api/export/services?garage_id=${currentGarage.id}`; } },
              { label: 'Tab separated values (.tsv)', onClick: () => { window.location.href = `/api/export/services?garage_id=${currentGarage.id}&format=tsv`; } },
              { label: 'JSON (.json)', onClick: () => { window.location.href = `/api/export/services?garage_id=${currentGarage.id}&format=json`; } },
            ]}
          />
        </div>
      </div>

      <div className="mb-4">
        <input
          type="search"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filter by title, category, vehicle, garage…"
          className="search-input"
        />
      </div>

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Vehicle</th><th>Service</th><th>Category</th><th className="col-mobile-hide">Odometer</th><th className="col-mobile-hide">By</th><th>Cost</th></tr></thead>
            <tbody>
              {services === null
                ? <SkeletonRows cols={['90px', '15%', '30%', '15%', '90px', '15%', '60px']} />
                : visible.map(s => (
                  <tr key={s.id} className="row-clickable" onClick={e => { if (!e.target.closest('a, button')) navigate(`/services/${s.id}`); }}>
                    <td>{s.date}</td>
                    <td><Link to={`/vehicles/${s.vehicle_id}`}>{s.vehicle_name}</Link></td>
                    <td><Link to={`/services/${s.id}`}>{s.title}</Link>{s.photo_count > 0 && <span className="text-muted text-sm"> 📷{s.photo_count}</span>}</td>
                    <td>{s.category || '—'}</td>
                    <td className="col-mobile-hide">{s.odometer_km != null ? fmtDistance(s.odometer_km, s.vehicle_odometer_unit) : '—'}</td>
                    <td className="col-mobile-hide">{s.performed_by || '—'}</td>
                    <td>{s.cost != null ? fmtCost(s.cost) : '—'}</td>
                  </tr>
                ))
              }
              {services !== null && visible.length === 0 && <tr><td colSpan={7} className="empty">{filter ? 'No matches' : 'No services logged yet'}</td></tr>}
            </tbody>
            {visible.length > 0 && totalCost > 0 && (
              <tfoot>
                <tr>
                  <td colSpan={6} className="text-muted" style={{ textAlign: 'right' }}>Total</td>
                  <td className="fw-600">{fmtCost(totalCost)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}
