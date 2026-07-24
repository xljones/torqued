import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useToast } from './Toast.jsx';
import RelativeTime from './RelativeTime.jsx';
import PhotoGallery from './PhotoGallery.jsx';
import { SkeletonPage } from './Skeleton.jsx';
import { fmtCost, fmtDistance, fmtDistanceBoth } from '../units.js';
import { scheduleTitle } from '../schedules.js';

export default function ServiceDetail() {
  const { roleFor } = useAuth();
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [log, setLog] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState(null);
  const [schedules, setSchedules] = useState([]);

  const refresh = useCallback(() => { api.getService(id).then(setLog); }, [id]);
  useEffect(refresh, [refresh]);
  useEffect(() => { api.getServiceHistory(id).then(setHistory); }, [id]);
  useEffect(() => {
    if (log?.service_schedule_id) api.getSchedules(log.vehicle_id).then(setSchedules).catch(() => {});
  }, [log?.service_schedule_id, log?.vehicle_id]);

  async function handleDelete() {
    if (!confirm('Delete this service log (and its photos)?')) return;
    const vehicleId = log.vehicle_id;
    await api.deleteService(id);
    toast('Service deleted');
    navigate(`/vehicles/${vehicleId}`);
  }

  async function handleRevert(versionId) {
    if (!confirm('Revert this service log to the selected version?')) return;
    await api.revertService(id, versionId);
    toast('Service reverted');
    refresh();
    api.getServiceHistory(id).then(setHistory);
  }

  if (!log) return <SkeletonPage />;

  const ro = roleFor(log.garage_id) === 'readonly';
  const unit = log.odometer_unit || log.vehicle_odometer_unit || 'mi';

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="back-link">
            <Link to={`/vehicles/${log.vehicle_id}`}>← {log.vehicle_name}</Link>
          </div>
          <h1 className="page-title">{log.title}</h1>
        </div>
        <div className="btn-group">
          {!ro && <Link to={`/services/${id}/edit`} className="btn btn-secondary">Edit</Link>}
          {!ro && <button className="btn btn-danger" onClick={handleDelete}>Delete</button>}
        </div>
      </div>

      <div className="card card-body mb-6">
        <div className="form-grid">
          <div className="field"><label>Date</label><span>{log.date}</span></div>
          <div className="field"><label>Category</label><span>{log.category || '—'}</span></div>
          <div className="field"><label>Done by</label><span>{log.performed_by || '—'}</span></div>
          <div className="field"><label>Cost</label><span>{log.cost != null ? fmtCost(log.cost) : '—'}</span></div>
          <div className="field">
            <label>Odometer</label>
            <span>{log.odometer_km != null ? fmtDistanceBoth(log.odometer_km, unit) : '—'}</span>
          </div>
          <div className="field"><label>Logged</label><span><RelativeTime value={log.created_at} /></span></div>
          {log.service_schedule_id && (() => {
            const s = schedules.find(x => x.id === log.service_schedule_id);
            return s ? (
              <div className="field"><label>Fulfils schedule</label><span>{scheduleTitle(s)}</span></div>
            ) : null;
          })()}
          {(log.next_due_date || log.next_due_km != null) && (
            <div className="field span-2">
              <label>Next due</label>
              <span>
                {[log.next_due_date, log.next_due_km != null ? `at ${fmtDistance(log.next_due_km, unit)}` : null]
                  .filter(Boolean).join(' or ')}
              </span>
            </div>
          )}
          {log.description && (
            <div className="field span-2"><label>What was done</label><span style={{ whiteSpace: 'pre-wrap' }}>{log.description}</span></div>
          )}
        </div>
      </div>

      {log.fault_codes?.length > 0 && (
        <div className="card card-body mb-6">
          <h3 className="card-title mb-3">Fault codes</h3>
          <div className="fault-code-detail">
            {log.fault_codes.map(fc => (
              <div key={fc.code} className="fault-code-detail-row">
                <span className="dtc-code dtc-code-sm">{fc.code}</span>
                <span>{fc.description ?? 'No description — check vehicle service manual'}</span>
                {fc.system && <span className="fault-code-system">{fc.system}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mb-6">
        <PhotoGallery photos={log.photos} vehicleId={log.vehicle_id} serviceLogId={log.id} ro={ro} onChange={refresh} />
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
                        {f('date', v.date, 'date')}
                        {f('title', v.title, 'title')}
                        {f('category', v.category || '—', 'category')}
                        {f('by', v.performed_by || '—', 'performed_by')}
                        {f('cost', v.cost ?? '—', 'cost')}
                        {f('odometer km', v.odometer_km != null ? Math.round(v.odometer_km) : '—', 'odometer_km')}
                        {f('description', v.description || '—', 'description')}
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
