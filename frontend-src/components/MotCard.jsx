import { useState, useEffect, useCallback } from 'react';
import { api } from '../api.js';
import { useToast } from './Toast.jsx';
import { useDisplayPrefs } from '../DisplayPrefsContext.jsx';
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

// MOT expiry status (expired / due_soon / ok) is decided server-side using the same
// threshold as the reminder list, so the tile and reminders always agree.
const EXPIRY_TILE_CLASS = {
  expired: 'pressure-tile--danger',
  due_soon: 'pressure-tile--warn',
  ok: 'pressure-tile--ok',
};

function recallTileClass(value) {
  return String(value).toLowerCase() === 'yes'
    ? 'pressure-tile--danger'
    : 'pressure-tile--ok'; // No / Unknown / Unavailable → green
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
  const { formatName } = useDisplayPrefs();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [jsonFmt, setJsonFmt] = useState('formatted');

  const load = useCallback(() => { api.getMot(vehicle.id).then(setData); }, [vehicle.id]);
  useEffect(load, [load]);

  async function handleRefresh() {
    setBusy(true);
    try {
      const result = await api.refreshMot(vehicle.id);
      setData(result);
      toast('MOT history refreshed');
      onSynced?.();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  if (!data || (!vehicle.registration && !data.mot)) return null;

  const mot = data.mot;
  const tests = mot?.tests ?? [];
  const latest = tests[0];
  const expiry = mot?.expiry?.expiry_date;
  const visible = showAll ? tests : tests.slice(0, 5);

  return (
    <div className="card card-body mb-6">
      <div className="section-header">
        <div className="mot-header-left">
          <h2 className="section-title">MOT history</h2>
          {mot && (
            <span className="mot-reauth text-muted text-sm">
              <span className="mot-reauth-dot" aria-hidden="true">•</span>
              {' '}refreshed <RelativeTime value={mot.fetched_at} />
            </span>
          )}
        </div>
        {!ro && data.configured && (
          <button className="btn btn-secondary btn-sm" onClick={handleRefresh} disabled={busy}>
            {busy ? 'Refreshing…' : mot ? 'Refresh from DVSA' : 'Fetch from DVSA'}
          </button>
        )}
      </div>

      {!mot && data.configured && (
        <p className="text-muted text-sm">
          No MOT data yet — fetch the official test history for {vehicle.registration} from the DVSA.
        </p>
      )}
      {!mot && !data.configured && (
        <p className="text-muted text-sm">
          {import.meta.env.DEV
            ? 'DVSA MOT API credentials are not configured (set MOT_CLIENT_ID, MOT_CLIENT_SECRET, MOT_TOKEN_URL and MOT_API_KEY).'
            : 'MOT history is unavailable right now.'}
        </p>
      )}

      {mot && (
        <>
          <div className="mot-summary">
            {expiry && (
              <div className={`pressure-tile ${EXPIRY_TILE_CLASS[mot.expiry?.status] ?? ''}`}>
                <div className="pressure-label">{latest ? 'MOT expires' : 'First MOT due'}</div>
                <div className="pressure-value">{expiry}</div>
                <div className="pressure-alt"><RelativeTime value={expiry} /></div>
              </div>
            )}
            {String(mot.has_outstanding_recall ?? 'Unknown').toLowerCase() !== 'unknown' && (
              <div className={`pressure-tile ${recallTileClass(mot.has_outstanding_recall)}`}>
                <div className="pressure-label">Outstanding recall</div>
                <div className="pressure-value">{mot.has_outstanding_recall}</div>
              </div>
            )}
            <div
              className={`pressure-tile dvsa-record-tile${showJson ? ' dvsa-record-tile--open' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => setShowJson(v => !v)}
              onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && setShowJson(v => !v)}
            >
              <div className="pressure-label">
                DVSA record <span className="dvsa-record-caret">{showJson ? '▲' : '▼'}</span>
              </div>
              <div className="pressure-size">
                {[formatName(mot.make), formatName(mot.model)].filter(Boolean).join(' ') || '—'}
                {mot.primary_colour ? ` · ${formatName(mot.primary_colour)}` : ''}
                {mot.engine_size ? ` · ${mot.engine_size} cc` : ''}
                {mot.fuel_type ? ` · ${formatName(mot.fuel_type)}` : ''}
                {mot.first_used_date ? ` · first used ${mot.first_used_date}` : ''}
              </div>
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
