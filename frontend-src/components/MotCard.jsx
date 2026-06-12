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

function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function jsonHighlight(data) {
  return esc(JSON.stringify(data, null, 2)).replace(
    /("(?:\\.|[^"\\])*"(?=\s*:))|("(?:\\.|[^"\\])*")|(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)|(true|false)|(null)/g,
    (_, key, str, num, bool, nul) => {
      if (key) return `<span class="jkey">${key}</span>`;
      if (str) return `<span class="jstr">${str}</span>`;
      if (num) return `<span class="jnum">${num}</span>`;
      if (bool) return `<span class="jbool">${bool}</span>`;
      if (nul) return `<span class="jnull">${nul}</span>`;
      return _;
    },
  );
}

export default function MotCard({ vehicle, ro, onSynced }) {
  const toast = useToast();
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
  const expiry = latest?.expiry_date ?? mot?.mot_test_due_date;
  const visible = showAll ? tests : tests.slice(0, 5);

  return (
    <div className="card card-body mb-6">
      <div className="section-header">
        <h2 className="section-title">MOT history</h2>
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
              <div className="pressure-tile">
                <div className="pressure-label">{latest ? 'MOT expires' : 'First MOT due'}</div>
                <div className="pressure-value">{expiry}</div>
              </div>
            )}
            <div className="pressure-tile">
              <div className="pressure-label">Outstanding recall</div>
              <div className="pressure-value">{mot.has_outstanding_recall ?? 'Unknown'}</div>
            </div>
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
                {[mot.make, mot.model].filter(Boolean).join(' ') || '—'}
                {mot.primary_colour ? ` · ${mot.primary_colour}` : ''}
                {mot.engine_size ? ` · ${mot.engine_size} cc` : ''}
                {mot.fuel_type ? ` · ${mot.fuel_type}` : ''}
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
                ? <pre className="dvsa-raw-json mt-2" dangerouslySetInnerHTML={{ __html: jsonHighlight(mot.raw) }} />
                : <pre className="dvsa-raw-json mt-2">{JSON.stringify(mot.raw)}</pre>
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

          <p className="text-muted text-sm mt-2">
            Source: DVSA MOT history · refreshed <RelativeTime value={mot.fetched_at} />
          </p>
        </>
      )}
    </div>
  );
}
