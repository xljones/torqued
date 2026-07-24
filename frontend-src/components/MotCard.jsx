import { useState, useEffect, useCallback } from 'react';
import { api } from '../api.js';
import { useToast } from './Toast.jsx';
import RelativeTime from './RelativeTime.jsx';
import { fmtDistanceBoth, toKm } from '../units.js';

const DEFECT_ORDER = ['DANGEROUS', 'MAJOR', 'FAIL', 'MINOR', 'ADVISORY'];

function defectRank(type) {
  const i = DEFECT_ORDER.indexOf((type || '').toUpperCase());
  return i === -1 ? DEFECT_ORDER.length : i;
}

function defectClass(type) {
  const t = (type || '').toUpperCase();
  if (t === 'DANGEROUS' || t === 'MAJOR' || t === 'FAIL') return 'mot-defect-serious';
  if (t === 'ADVISORY') return 'mot-defect-advisory';
  return 'mot-defect-minor';
}

function expiryTileClass(expiry) {
  if (!expiry) return '';
  const date = new Date(expiry);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const inAMonth = new Date(now);
  inAMonth.setMonth(inAMonth.getMonth() + 1);
  if (date < now) return 'pressure-tile--danger';     // out of date
  if (date <= inAMonth) return 'pressure-tile--warn'; // ≤ 1 month to go
  return 'pressure-tile--ok';                          // all good
}

function recallTileClass(value) {
  return String(value).toLowerCase() === 'yes'
    ? 'pressure-tile--danger'
    : 'pressure-tile--ok'; // No / Unknown / Unavailable → green
}

function isPast(dateStr) {
  const d = new Date(dateStr);
  return !Number.isNaN(d.getTime()) && d < new Date();
}

function taxStatusTileClass(status) {
  const s = (status || '').toLowerCase();
  if (s === 'taxed') return 'pressure-tile--ok';       // green
  if (s === 'sorn') return 'pressure-tile--warn';      // amber — off the road on purpose
  if (!s) return '';
  return 'pressure-tile--danger';                       // Untaxed / not taxed for on-road use
}

function TestRow({ test, unit }) {
  const [open, setOpen] = useState(false);
  const passed = (test.test_result || '').toUpperCase() === 'PASSED';
  const defects = [...test.defects].sort((a, b) => defectRank(a.type) - defectRank(b.type));
  return (
    <div className="mot-test">
      <div className="mot-test-row">
        <span className={`badge ${passed ? 'badge-passed' : 'badge-failed'}`}>
          {passed ? 'Pass' : 'Fail'}
        </span>
        <span className="mot-test-date">{test.completed_date?.slice(0, 10)}</span>
        <span className="mot-test-odo">
          {test.odometer_value != null && test.odometer_unit
            ? fmtDistanceBoth(toKm(test.odometer_value, test.odometer_unit), unit)
            : '—'}
        </span>
        <span className="mot-test-extra text-muted text-sm">
          {passed && test.expiry_date ? `expires ${test.expiry_date}` : ''}
        </span>
        {defects.length > 0 && (
          <button className="btn btn-secondary btn-sm" onClick={() => setOpen(v => !v)}>
            {open ? 'Hide' : `${defects.length} defect${defects.length === 1 ? '' : 's'}`}
          </button>
        )}
      </div>
      {open && (
        <ul className="mot-defects">
          {defects.map((d, i) => (
            <li key={i}>
              <span className={`mot-defect-type ${defectClass(d.type)}`}>{(d.type || 'NOTE').toLowerCase()}</span>
              {d.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function JsonLeaf({ value }) {
  if (value === null) return <span className="json-val json-val--null">null</span>;
  if (typeof value === 'boolean') return <span className="json-val json-val--bool">{String(value)}</span>;
  if (typeof value === 'number') return <span className="json-val json-val--num">{String(value)}</span>;
  if (typeof value === 'string') return <span className="json-val json-val--str">{value === '' ? '—' : value}</span>;
  return <span className="json-val">{String(value)}</span>;
}

function JsonNode({ name, value, depth }) {
  const [open, setOpen] = useState(depth === 0);
  const isBranch = value !== null && typeof value === 'object';

  if (!isBranch) {
    return (
      <div className="json-row json-row--leaf">
        <span className="json-caret" aria-hidden="true" />
        {name != null && <span className="json-key">{name}</span>}
        <JsonLeaf value={value} />
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value);
  const noun = isArray ? 'item' : 'key';
  const summary = `${entries.length} ${noun}${entries.length === 1 ? '' : 's'}`;
  const toggle = () => setOpen(v => !v);

  return (
    <div className="json-node">
      <div
        className="json-row json-row--branch"
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), toggle())}
      >
        <span className={`json-caret${open ? ' json-caret--open' : ''}`} aria-hidden="true">▶</span>
        {name != null && <span className="json-key">{name}</span>}
        <span className={`json-summary json-summary--${isArray ? 'array' : 'object'}`}>{summary}</span>
      </div>
      {open && (
        <div className="json-children">
          {entries.map(([k, v]) => (
            <JsonNode key={k} name={k} value={v} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function JsonTree({ data }) {
  const isContainer = data !== null && typeof data === 'object';
  const entries = Array.isArray(data) ? data.map((v, i) => [i, v]) : Object.entries(data ?? {});
  return (
    <div className="json-tree mt-2">
      {isContainer
        ? entries.map(([k, v]) => <JsonNode key={k} name={k} value={v} depth={1} />)
        : <JsonNode name={null} value={data} depth={1} />}
    </div>
  );
}

export default function MotCard({ vehicle, ro, onSynced }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [tax, setTax] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [jsonFmt, setJsonFmt] = useState('formatted');

  const load = useCallback(() => {
    api.getMot(vehicle.id).then(setData);
    api.getTax(vehicle.id).then(setTax);
  }, [vehicle.id]);
  useEffect(load, [load]);

  const motConfigured = data?.configured;
  const taxConfigured = tax?.configured;

  async function handleRefresh() {
    setBusy(true);
    try {
      // Refresh whichever sources are enabled, independently, so one failing (e.g. an
      // unknown plate at the DVLA) doesn't block the other.
      const jobs = [];
      if (motConfigured) jobs.push(api.refreshMot(vehicle.id).then(setData));
      if (taxConfigured) jobs.push(api.refreshTax(vehicle.id).then(setTax));
      const failure = (await Promise.allSettled(jobs)).find(r => r.status === 'rejected');
      toast(
        failure ? (failure.reason?.message ?? 'Refresh failed') : 'MOT & tax refreshed',
        failure ? 'error' : undefined,
      );
      onSynced?.();
    } finally {
      setBusy(false);
    }
  }

  const mot = data?.mot;
  const taxInfo = tax?.tax;
  if (!data && !tax) return null;
  if (!vehicle.registration && !mot && !taxInfo) return null;

  const tests = mot?.tests ?? [];
  const latest = tests[0];
  const expiry = latest?.expiry_date ?? mot?.mot_test_due_date;
  const motResult = latest ? ((latest.test_result || '').toUpperCase() === 'PASSED' ? 'Passed' : 'Failed') : '—';
  const expiryVerb = !latest ? 'Due' : (isPast(expiry) ? 'Expired' : 'Expires');
  const showRecall = String(mot?.has_outstanding_recall ?? 'Unknown').toLowerCase() !== 'unknown';
  const visible = showAll ? tests : tests.slice(0, 5);

  return (
    <div className="card card-body mb-6">
      <div className="section-header">
        <div className="mot-header-left">
          <h2 className="section-title">MOT &amp; tax</h2>
          {mot && (
            <span className="mot-reauth text-muted text-sm">
              <span className="mot-reauth-dot" aria-hidden="true">•</span>
              {' '}refreshed <RelativeTime value={mot.fetched_at} />
            </span>
          )}
        </div>
        {!ro && (motConfigured || taxConfigured) && (
          <button className="btn btn-secondary btn-sm" onClick={handleRefresh} disabled={busy}>
            {busy ? 'Refreshing…' : (mot || taxInfo) ? 'Refresh from DVSA & DVLA' : 'Fetch from DVSA & DVLA'}
          </button>
        )}
      </div>

      {/* Core info: tax | MOT side by side */}
      {(taxInfo || mot) && (
        <div className="motax-primary">
          {taxInfo && (
            <div className={`pressure-tile ${taxStatusTileClass(taxInfo.tax_status)}`}>
              <div className="pressure-label">Tax status</div>
              <div className="pressure-value">{taxInfo.tax_status || '—'}</div>
              <div className="pressure-alt">
                {taxInfo.tax_due_date
                  ? <>Due {taxInfo.tax_due_date} (<RelativeTime value={taxInfo.tax_due_date} />)</>
                  : '—'}
              </div>
            </div>
          )}
          {mot && (
            <div className={`pressure-tile ${expiryTileClass(expiry)}`}>
              <div className="pressure-label">MOT status</div>
              <div className="pressure-value">{motResult}</div>
              <div className="pressure-alt">
                {expiry
                  ? <>{expiryVerb} {expiry} (<RelativeTime value={expiry} />)</>
                  : '—'}
              </div>
            </div>
          )}
        </div>
      )}

      {!mot && motConfigured && vehicle.registration && (
        <p className="text-muted text-sm">
          No MOT data yet — fetch the official test history for {vehicle.registration} from the DVSA.
        </p>
      )}
      {!mot && motConfigured === false && (
        <p className="text-muted text-sm">
          {import.meta.env.DEV
            ? 'DVSA MOT API credentials are not configured (set MOT_CLIENT_ID, MOT_CLIENT_SECRET, MOT_TOKEN_URL and MOT_API_KEY).'
            : 'MOT history is unavailable right now.'}
        </p>
      )}

      {mot && (
        <>
          {/* Outstanding recall (when present) sits under the core tiles */}
          {showRecall && (
            <div className={`pressure-tile mt-3 ${recallTileClass(mot.has_outstanding_recall)}`}>
              <div className="pressure-label">Outstanding recall</div>
              <div className="pressure-value">{mot.has_outstanding_recall}</div>
            </div>
          )}

          {/* DVSA record: the full official record, full row width, expandable */}
          <div
            className={`pressure-tile dvsa-record-tile mt-3${showJson ? ' dvsa-record-tile--open' : ''}`}
            role="button"
            tabIndex={0}
            onClick={() => setShowJson(v => !v)}
            onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && setShowJson(v => !v)}
          >
            <div className="pressure-label">
              DVSA record <span className="dvsa-record-caret">{showJson ? '▲' : '▼'}</span>
            </div>
            {/* The DVSA record shows the official data verbatim (all-caps as DVSA
                returns it) — never tidied — so it matches the raw JSON panel below. */}
            <div className="pressure-size">
              {[mot.make, mot.model].filter(Boolean).join(' ') || '—'}
              {mot.primary_colour ? ` · ${mot.primary_colour}` : ''}
              {mot.engine_size ? ` · ${mot.engine_size} cc` : ''}
              {mot.fuel_type ? ` · ${mot.fuel_type}` : ''}
              {mot.first_used_date ? ` · first used ${mot.first_used_date}` : ''}
            </div>
          </div>

          {showJson && (
            <div className="dvsa-json-panel mt-3">
              <div className="dvsa-json-toolbar">
                <button
                  className={`btn btn-sm ${jsonFmt === 'formatted' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setJsonFmt('formatted')}
                >Formatted</button>
                <button
                  className={`btn btn-sm ${jsonFmt === 'raw' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setJsonFmt('raw')}
                >Raw</button>
              </div>
              {jsonFmt === 'formatted'
                ? <JsonTree data={mot.raw} />
                : <pre className="dvsa-raw-json mt-2">{JSON.stringify(mot.raw, null, 2)}</pre>
              }
            </div>
          )}

          {tests.length > 0 && (
            <div className="mt-3">
              {visible.map(t => <TestRow key={t.id} test={t} unit={vehicle.odometer_unit} />)}
              {tests.length > visible.length && (
                <button className="btn btn-secondary btn-sm mt-2" onClick={() => setShowAll(true)}>
                  Show all {tests.length} tests
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
