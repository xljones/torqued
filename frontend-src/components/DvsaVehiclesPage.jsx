import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import RegPlate from './RegPlate.jsx';
import RelativeTime from './RelativeTime.jsx';
import { SkeletonRows } from './Skeleton.jsx';

export default function DvsaVehiclesPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);

  useEffect(() => {
    let active = true;
    setData(null);
    api.getDvsaVehicles(page).then(d => { if (active) setData(d); });
    return () => { active = false; };
  }, [page]);

  const items = data?.items ?? [];
  const pages = data?.pages ?? 0;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">DVSA vehicles</h1>
        {data && <span className="meta">{data.total} stored</span>}
      </div>

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Make / Model</th><th>Registration</th><th>Last updated</th></tr>
            </thead>
            <tbody>
              {data === null
                ? <SkeletonRows cols={['40%', '110px', '90px']} />
                : items.map(v => {
                  const makeModel = [v.make, v.model].filter(Boolean).join(' ') || '—';
                  return (
                    <tr key={v.id}>
                      <td>
                        {v.vehicle_id != null
                          ? <Link to={`/vehicles/${v.vehicle_id}`}>{makeModel}</Link>
                          : (
                            <>
                              {makeModel}
                              <span className="user-badge user-badge-readonly">vehicle deleted</span>
                            </>
                          )}
                      </td>
                      <td><RegPlate reg={v.registration} /></td>
                      <td className="meta"><RelativeTime value={v.fetched_at} /></td>
                    </tr>
                  );
                })}
              {data !== null && items.length === 0 && (
                <tr><td colSpan={3} className="empty">No DVSA vehicles stored yet</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {pages > 1 && (
          <div className="pagination">
            <button
              className="btn btn-secondary btn-sm"
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
            >
              ← Prev
            </button>
            <span className="meta">Page {data.page} of {pages}</span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page >= pages}
              onClick={() => setPage(p => p + 1)}
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
