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

const SOURCE_LABEL = {
  dvsa: 'DVSA record',
  ves: 'DVLA record (VES)',
};

// One record's summary line in the expanded view — make/model for DVSA; tax + MOT status
// for the DVLA VES record.
function recordSummary(r) {
  let head;
  if (r.source === 'ves') {
    const bits = [r.tax_status, r.mot_expiry_date ? `MOT to ${r.mot_expiry_date}` : null].filter(Boolean);
    head = bits.join(' · ') || 'DVLA';
  } else {
    head = [r.make, r.model].filter(Boolean).join(' ') || '—';
  }
  return <>{head}{' · looked up '}<RelativeTime value={r.fetched_at} /></>;
}

// "N records" with a per-source split when the vehicle has more than one kind.
function recordCountLabel(v) {
  const parts = [
    [v.dvsa_count, 'DVSA'],
    [v.ves_count, 'DVLA'],
  ].filter(([n]) => n);
  const split = parts.length > 1 ? ` (${parts.map(([n, label]) => `${n} ${label}`).join(', ')})` : '';
  return `${plural(v.record_count, 'record')}${split}`;
}

// One vehicle row: a summary line that expands to reveal every stored DVLA + DVSA record
// for its plate — each record one entire lookup, newest first — browsable with the shared
// record viewer. Records are fetched lazily whenever the row is open (click or auto-expanded
// after a fresh lookup).
function RecordRow({ v, defaultOpen = false, onRefreshed }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [open, setOpen] = useState(defaultOpen);
  const [records, setRecords] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (open && records === null) {
      api.getRecordsForPlate(v.ref.source, v.ref.id).then(setRecords);
    }
  }, [open, records, v.ref.source, v.ref.id]);

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

  // Pull the latest DVLA + DVSA records for this plate, keeping the previous as history. A
  // linked vehicle refreshes its live snapshots; a standalone record stores fresh lookups.
  async function refreshRow(e) {
    e.stopPropagation();
    if (refreshing) return;
    setRefreshing(true);
    try {
      if (v.vehicle_id != null) {
        // Refresh both sources independently so one failing doesn't block the other.
        await Promise.allSettled([api.refreshMot(v.vehicle_id), api.refreshVes(v.vehicle_id)]);
      } else {
        await api.lookupVehicleRecord(v.registration);
      }
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
            <button type="button" className="btn btn-secondary btn-sm dvsa-view-btn" onClick={viewVehicle}>
              View in garage
            </button>
          ) : (
            <button type="button" className="btn btn-success btn-sm dvsa-add-btn" onClick={addToGarage}>
              + Add to garage
            </button>
          )}
          <span className="meta"> · {recordCountLabel(v)}</span>
        </td>
        <td><RegPlate reg={v.registration} /></td>
        <td className="meta">
          <RelativeTime value={v.fetched_at} />
          <button
            type="button"
            className="btn btn-secondary btn-sm dvsa-refresh-btn"
            onClick={refreshRow}
            disabled={refreshing}
            title="Pull the latest DVLA & DVSA records"
            aria-label="Refresh from DVLA & DVSA"
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
                      key={`${r.source}-${r.id}`}
                      label={SOURCE_LABEL[r.source]}
                      raw={r.raw}
                      summary={recordSummary(r)}
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

export default function VehicleRecordsPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState('');
  const [canLookup, setCanLookup] = useState(false);
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
    api.getVehicleRecords(page).then(d => {
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
    // The Find form appears when either source can be queried.
    Promise.all([
      api.getMotStatus().then(s => s.configured).catch(() => false),
      api.getVesStatus().then(s => s.configured).catch(() => false),
    ]).then(([mot, tax]) => setCanLookup(mot || tax));
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
      const v = await api.lookupVehicleRecord(reg);
      toast?.(`Saved records for ${[v.make, v.model].filter(Boolean).join(' ') || v.registration || reg}`);
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
        <h1 className="page-title">DVLA &amp; DVSA Records</h1>
        {data && (
          <span className="meta">
            {plural(data.total, 'vehicle')}, {plural(data.total_records, 'record')}
            {' '}({data.total_dvsa} DVSA, {data.total_ves} DVLA)
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
        {canLookup && (
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
                  <RecordRow
                    key={`${v.ref.source}-${v.ref.id}`}
                    v={v}
                    defaultOpen={!!expandReg && normReg(v.registration) === expandReg}
                    onRefreshed={reloadExpanding}
                  />
                ))}
              {data !== null && visible.length === 0 && (
                <tr>
                  <td colSpan={3} className="empty">
                    {items.length === 0 ? 'No records stored yet' : 'No matches on this page'}
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
