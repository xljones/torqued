import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import RegPlate from './RegPlate.jsx';
import RelativeTime from './RelativeTime.jsx';
import DvsaRecord from './DvsaRecord.jsx';
import { SkeletonRows } from './Skeleton.jsx';

const plural = (n, noun) => `${n} ${noun}${n === 1 ? '' : 's'}`;

// One vehicle row: a summary line that expands to reveal every stored DVSA record —
// each record being one entire lookup, newest first — browsable with the shared record
// viewer. The records are fetched lazily on first expand.
function DvsaRow({ v }) {
  const [open, setOpen] = useState(false);
  const [records, setRecords] = useState(null);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && records === null) {
      api.getDvsaVehicleRecords(v.id).then(setRecords);
    }
  }

  const makeModel = [v.make, v.model].filter(Boolean).join(' ') || '—';

  return (
    <>
      <tr
        className="dvsa-row"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={toggle}
        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), toggle())}
      >
        <td>
          <span className="dvsa-record-caret">{open ? '▼' : '▶'}</span>{' '}
          {v.vehicle_id != null
            ? <Link to={`/vehicles/${v.vehicle_id}`} onClick={e => e.stopPropagation()}>{makeModel}</Link>
            : (
              <>
                {makeModel}
                <span className="user-badge user-badge-readonly">vehicle deleted</span>
              </>
            )}
          <span className="meta"> · {plural(v.record_count, 'record')}</span>
        </td>
        <td><RegPlate reg={v.registration} /></td>
        <td className="meta"><RelativeTime value={v.fetched_at} /></td>
      </tr>
      {open && (
        <tr className="dvsa-records-row">
          <td colSpan={3}>
            {records === null
              ? <p className="meta">Loading records…</p>
              : (
                <div className="dvsa-records">
                  {records.records.map(r => (
                    <DvsaRecord
                      key={r.id}
                      label="DVSA record"
                      raw={r.raw}
                      summary={
                        <>
                          {[r.make, r.model].filter(Boolean).join(' ') || '—'}
                          {' · looked up '}<RelativeTime value={r.fetched_at} />
                        </>
                      }
                    />
                  ))}
                </div>
              )}
          </td>
        </tr>
      )}
    </>
  );
}

export default function DvsaVehiclesPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    let active = true;
    setData(null);
    api.getDvsaVehicles(page).then(d => { if (active) setData(d); });
    return () => { active = false; };
  }, [page]);

  const items = data?.items ?? [];
  const pages = data?.pages ?? 0;

  // Filter the rows already loaded on this page (make/model or registration).
  const q = filter.trim().toLowerCase();
  const visible = q
    ? items.filter(v =>
      [v.make, v.model].filter(Boolean).join(' ').toLowerCase().includes(q) ||
      (v.registration ?? '').toLowerCase().replace(/\s+/g, '').includes(q.replace(/\s+/g, '')))
    : items;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">DVSA vehicles</h1>
        {data && (
          <span className="meta">
            {plural(data.total, 'vehicle')}, {plural(data.total_records, 'record')}
          </span>
        )}
      </div>

      <div className="mb-4 inline-form-sm">
        <input
          type="search"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filter by make, model or registration…"
          className="search-input"
        />
      </div>

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Make / Model</th><th>Registration</th><th>Pulled from DVSA</th></tr>
            </thead>
            <tbody>
              {data === null
                ? <SkeletonRows cols={['40%', '110px', '110px']} />
                : visible.map(v => <DvsaRow key={v.id} v={v} />)}
              {data !== null && visible.length === 0 && (
                <tr>
                  <td colSpan={3} className="empty">
                    {items.length === 0 ? 'No DVSA vehicles stored yet' : 'No matches on this page'}
                  </td>
                </tr>
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
