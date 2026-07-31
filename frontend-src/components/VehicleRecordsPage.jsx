import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import RegPlate from './RegPlate.jsx';
import RelativeTime from './RelativeTime.jsx';
import DvsaRecord from './DvsaRecord.jsx';
import { SkeletonRows } from './Skeleton.jsx';
import { useToast } from './Toast.jsx';

const plural = (n, noun) => `${n} ${noun}${n === 1 ? '' : 's'}`;
// Normalise a plate the way the backend groups them (strip spaces, case-insensitive).
const normReg = r => (r ?? '').replace(/\s+/g, '').toLowerCase();

// One vehicle row: a summary line that expands to reveal every stored DVSA record —
// each record being one entire lookup, newest first — browsable with the shared record
// viewer. Records are fetched lazily whenever the row is open (click or auto-expanded
// after a fresh lookup).
function DvsaRow({ v, defaultOpen = false, onRefreshed }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [open, setOpen] = useState(defaultOpen);
  const [records, setRecords] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (open && records === null) api.getDvsaVehicleRecords(v.id).then(setRecords);
  }, [open, records, v.id]);

  const makeModel = [v.make, v.model].filter(Boolean).join(' ') || '—';
  const toggle = () => setOpen(o => !o);

  function addToGarage(e) {
    e.stopPropagation();
    navigate('/vehicles/new', {
      state: { prefill: { registration: v.registration, name: [v.make, v.model].filter(Boolean).join(' ') } },
    });
  }

  function viewVehicle(e) {
    e.stopPropagation();
    navigate(`/vehicles/${v.vehicle_id}`);
  }

  // Pull the latest DVSA record for this plate, keeping the previous as history. A linked
  // vehicle refreshes its live snapshot; a standalone record stores a fresh lookup.
  async function refreshRow(e) {
    e.stopPropagation();
    if (refreshing) return;
    setRefreshing(true);
    try {
      if (v.vehicle_id != null) await api.refreshMot(v.vehicle_id);
      else await api.lookupDvsaVehicle(v.registration);
      const label = [v.year, v.make, v.model].filter(Boolean).join(' ') || v.registration;
      toast?.(`Refreshed ${label}`);
      onRefreshed?.(normReg(v.registration), { keepOrder: true });
    } catch (err) {
      toast?.(err.message ?? 'Refresh failed', 'error');
    } finally {
      setRefreshing(false);
    }
  }

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
          {v.year ? <span className="dvsa-year">{v.year} </span> : null}
          {makeModel}
          {v.vehicle_id != null ? (
            <button type="button" className="btn btn-success btn-sm dvsa-view-btn" onClick={viewVehicle}>
              View {v.vehicle_name}{v.garage_name ? ` in ${v.garage_name}` : ''}
            </button>
          ) : (
            <button type="button" className="btn btn-secondary btn-sm dvsa-add-btn" onClick={addToGarage}>
              + Add to garage
            </button>
          )}
          <span className="meta"> · {plural(v.record_count, 'record')}</span>
        </td>
        <td><RegPlate reg={v.registration} /></td>
        <td className="meta">
          <RelativeTime value={v.fetched_at} />
          <button
            type="button"
            className="btn btn-secondary btn-sm dvsa-refresh-btn"
            onClick={refreshRow}
            disabled={refreshing}
            title="Pull the latest DVSA record"
            aria-label="Refresh from DVSA"
          >
            <span className={refreshing ? 'dvsa-refresh-spin' : ''} aria-hidden="true">↻</span>
          </button>
        </td>
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
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState('');
  const [motConfigured, setMotConfigured] = useState(false);
  const [lookupReg, setLookupReg] = useState('');
  const [looking, setLooking] = useState(false);
  // Plate (normalised) of the most recent lookup, so its row auto-expands once reloaded.
  const [expandReg, setExpandReg] = useState(null);
  // When set, the next reload keeps this on-screen order (list of normalised plates) rather
  // than the server's newest-first order — so refreshing a row updates it in place. Cleared
  // after one reload, so a genuine page load re-sorts naturally.
  const keepOrderRef = useRef(null);

  useEffect(() => {
    let active = true;
    setData(null);
    api.getDvsaVehicles(page).then(d => {
      if (!active) return;
      const order = keepOrderRef.current;
      keepOrderRef.current = null;
      if (order) {
        const rank = r => (order.indexOf(normReg(r)) + 1 || Infinity);
        d = { ...d, items: [...d.items].sort((a, b) => rank(a.registration) - rank(b.registration)) };
      }
      setData(d);
    });
    return () => { active = false; };
  }, [page, reloadKey]);

  useEffect(() => {
    api.getMotStatus().then(s => setMotConfigured(s.configured)).catch(() => {});
  }, []);

  // Re-fetch the list and auto-expand the row for the given (normalised) plate. A standalone
  // lookup jumps to page 1 and lets the found row sort to the top; a row refresh keeps the
  // current order (keepOrder) so the row updates in place and only re-sorts on the next load.
  function reloadExpanding(reg, { keepOrder = false } = {}) {
    setExpandReg(reg);
    if (keepOrder) {
      if (data) keepOrderRef.current = data.items.map(i => normReg(i.registration));
    } else {
      setPage(1);
    }
    setReloadKey(k => k + 1);
  }

  async function handleLookup(e) {
    e.preventDefault();
    const reg = lookupReg.trim();
    if (!reg || looking) return;
    setLooking(true);
    try {
      const v = await api.lookupDvsaVehicle(reg);
      toast?.(`Saved DVSA record for ${[v.make, v.model].filter(Boolean).join(' ') || reg}`);
      setLookupReg('');
      reloadExpanding(normReg(v.registration ?? reg));
    } catch (err) {
      toast?.(err.message ?? 'Lookup failed', 'error');
    } finally {
      setLooking(false);
    }
  }

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
        <h1 className="page-title">DVSA Records</h1>
        {data && (
          <span className="meta">
            {plural(data.total, 'vehicle')}, {plural(data.total_records, 'record')}
          </span>
        )}
      </div>

      <div className="dvsa-toolbar mb-4">
        <input
          type="search"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filter by make, model or registration…"
          className="search-input"
        />
        {motConfigured && (
          <form className="dvsa-lookup" onSubmit={handleLookup}>
            <input
              className="reg-plate-input"
              value={lookupReg}
              onChange={e => setLookupReg(e.target.value)}
              placeholder="A1 XYZ"
              aria-label="Registration to look up"
            />
            <button className="btn btn-primary btn-sm" disabled={looking || !lookupReg.trim()}>
              {looking ? 'Finding…' : 'Find'}
            </button>
          </form>
        )}
      </div>

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Make / Model</th><th>Registration</th><th>Last updated</th></tr>
            </thead>
            <tbody>
              {data === null
                ? <SkeletonRows cols={['40%', '110px', '110px']} />
                : visible.map(v => (
                  <DvsaRow
                    key={v.id}
                    v={v}
                    defaultOpen={!!expandReg && normReg(v.registration) === expandReg}
                    onRefreshed={reloadExpanding}
                  />
                ))}
              {data !== null && visible.length === 0 && (
                <tr>
                  <td colSpan={3} className="empty">
                    {items.length === 0 ? 'No DVSA records stored yet' : 'No matches on this page'}
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
