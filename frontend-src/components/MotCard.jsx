import { useState, useEffect, useCallback } from 'react';
import { api } from '../api.js';
import { useToast } from './Toast.jsx';
import RelativeTime from './RelativeTime.jsx';
import DvsaRecord from './DvsaRecord.jsx';
import { fmtDistanceBoth, formatReg, toKm } from '../units.js';
import { isPast, taxTone, motTone } from '../status.js';

// A summary tile takes its colour from the shared status tone (see status.js).
const tileClass = tone => (tone ? `pressure-tile--${tone}` : '');

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

function recallTileClass(value) {
  return String(value).toLowerCase() === 'yes'
    ? 'pressure-tile--danger'
    : 'pressure-tile--ok'; // No / Unknown / Unavailable → green
}

// Parse a stored timestamp — an ISO date or a "YYYY-MM-DD HH:MM:SS" UTC datetime — to a
// Date (or null). Used only to compare the MOT vs tax refresh times, not to display them.
function parseTs(value) {
  if (!value) return null;
  const iso = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? value + 'T00:00:00Z'
    : (value.endsWith('Z') ? value : value.replace(' ', 'T') + 'Z');
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
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

export default function MotCard({ vehicle, ro, onSynced }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [tax, setTax] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  // Only one raw record panel is open at a time — the DVSA record or the DVLA tax record.
  const [openRecord, setOpenRecord] = useState(null);  // 'dvsa' | 'tax' | null
  const toggleRecord = which => setOpenRecord(cur => (cur === which ? null : which));

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
  const taxStatusLc = (taxInfo?.tax_status || '').toLowerCase();
  const taxed = taxStatusLc === 'taxed';
  // When a vehicle is untaxed (but not deliberately SORN'd) and we happen to have a date,
  // it's the date the tax lapsed. Our gov.uk scrape doesn't provide this, but the VES API
  // would — so surface it when present, like the MOT "Expired <date>" line.
  const taxLapsedDate = taxInfo && !taxed && taxStatusLc !== 'sorn' ? taxInfo.tax_due_date : null;
  const failed = !!latest && (latest.test_result || '').toUpperCase() !== 'PASSED';
  const expired = !!expiry && isPast(expiry);
  const motValid = !!expiry && !expired && !failed;  // a current, passed MOT
  const motTileClass = tileClass(motTone(expiry, failed));
  const showRecall = String(mot?.has_outstanding_recall ?? 'Unknown').toLowerCase() !== 'unknown';
  const visible = showAll ? tests : tests.slice(0, 5);

  // Header refresh time. MOT and tax carry independent fetched_at stamps; they normally
  // refresh together, so collapse to one label when within 2 min of each other (or when
  // only one source is present) and split them out when they genuinely differ.
  const motFetchedAt = mot?.fetched_at;
  const taxFetchedAt = taxInfo?.fetched_at;
  const motTs = parseTs(motFetchedAt);
  const taxTs = parseTs(taxFetchedAt);
  const oneRefresh = !motTs || !taxTs || Math.abs(motTs - taxTs) < 120_000;
  const latestFetchedAt = motTs && (!taxTs || motTs >= taxTs) ? motFetchedAt : taxFetchedAt;

  return (
    <div className="card card-body mb-6">
      <div className="section-header">
        <div className="mot-header-left">
          <h2 className="section-title">MOT &amp; tax</h2>
          {(mot || taxInfo) && (
            <span className="mot-reauth text-muted text-sm">
              <span className="mot-reauth-dot" aria-hidden="true">•</span>{' '}
              {oneRefresh
                ? <>refreshed <RelativeTime value={latestFetchedAt} /></>
                : <>MOT refreshed <RelativeTime value={motFetchedAt} />, tax <RelativeTime value={taxFetchedAt} /></>}
            </span>
          )}
        </div>
        {!ro && (motConfigured || taxConfigured) && (
          <button className="btn btn-secondary btn-sm" onClick={handleRefresh} disabled={busy}>
            {busy ? 'Refreshing…' : (mot || taxInfo) ? 'Refresh from DVSA & DVLA' : 'Fetch from DVSA & DVLA'}
          </button>
        )}
      </div>

      {/* Core info: MOT (left) | tax (right), side by side */}
      {(mot || taxInfo) && (
        <div className="motax-primary">
          {mot && (
            <div className={`pressure-tile ${motTileClass}`}>
              <div className="pressure-label">MOT</div>
              <div className="pressure-value">
                {failed ? 'Failed'
                  : expired ? 'Expired'
                  : expiry ? <>Expires <RelativeTime value={expiry} /></>
                  : '—'}
              </div>
              <div className="pressure-alt">
                {motValid ? `Expires ${expiry}`
                  : expired ? `Expired ${expiry}`
                  : '—'}
              </div>
            </div>
          )}
          {taxInfo && (
            <div className={`pressure-tile ${tileClass(taxTone(taxInfo.tax_status))}`}>
              {/* When taxed, the label carries the status and the value shows how long is
                  left; otherwise the label is generic and the value is the status word. */}
              <div className="pressure-label">{taxed ? 'Taxed' : 'Tax status'}</div>
              <div className="pressure-value">
                {taxed
                  ? (taxInfo.tax_due_date ? <>Due <RelativeTime value={taxInfo.tax_due_date} /></> : 'Taxed')
                  : (taxInfo.tax_status || '—')}
              </div>
              <div className="pressure-alt">
                {taxed
                  ? (taxInfo.tax_due_date || '—')
                  : taxLapsedDate ? `Expired ${taxLapsedDate}` : '—'}
              </div>
            </div>
          )}
        </div>
      )}

      {/* DVLA tax record: the full official tax lookup, under the tax box, expandable.
          Mutually exclusive with the DVSA record below (tax OR MOT open, never both). */}
      {taxInfo && (
        <DvsaRecord
          label="DVLA tax record"
          className="mt-3"
          raw={taxInfo.raw}
          open={openRecord === 'tax'}
          onToggle={() => toggleRecord('tax')}
          summary={
            <>
              {taxInfo.tax_status || '—'}
              {taxInfo.tax_due_date ? ` · due ${taxInfo.tax_due_date}` : ''}
            </>
          }
        />
      )}

      {!mot && motConfigured && vehicle.registration && (
        <p className="text-muted text-sm">
          No MOT data yet — fetch the official test history for {formatReg(vehicle.registration)} from the DVSA.
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

          {/* DVSA record: the full official record, full row width, expandable.
              Mutually exclusive with the DVLA tax record above. */}
          <DvsaRecord
            label="DVSA record"
            className="mt-3"
            raw={mot.raw}
            open={openRecord === 'dvsa'}
            onToggle={() => toggleRecord('dvsa')}
            summary={
              <>
                {[mot.make, mot.model].filter(Boolean).join(' ') || '—'}
                {mot.primary_colour ? ` · ${mot.primary_colour}` : ''}
                {mot.engine_size ? ` · ${mot.engine_size} cc` : ''}
                {mot.fuel_type ? ` · ${mot.fuel_type}` : ''}
                {mot.first_used_date ? ` · first used ${mot.first_used_date}` : ''}
              </>
            }
          />

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
