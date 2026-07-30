import { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useDisplayPrefs } from '../DisplayPrefsContext.jsx';
import { useToast } from './Toast.jsx';
import { SkeletonPage } from './Skeleton.jsx';
import { FormMode, KIND_LABELS } from '../constants.js';
import { barToPsi, psiToBar } from '../units.js';

// Identity fields whose DVSA baseline preview is tidied by the title-case setting.
const TIDY_KEYS = ['make', 'model', 'colour', 'fuel_type'];

const EMPTY = {
  name: '', kind: 'car', make: '', model: '', year: '', registration: '', vin: '',
  colour: '', fuel_type: '', engine_size: '', first_used_date: '', registration_date: '',
  odometer_unit: 'mi', purchase_date: '',
  tyre_size_front: '', tyre_size_rear: '',
  tyre_pressure_front: '', tyre_pressure_rear: '',
  notes: '',
};

export default function VehicleForm({ mode }) {
  const { id } = useParams();
  const location = useLocation();
  const { currentGarage } = useAuth();
  const { formatName } = useDisplayPrefs();
  const navigate = useNavigate();
  const toast = useToast();
  const isEdit = mode === FormMode.EDIT;
  // "+ Add to garage" from the DVSA vehicles page hands us a registration (and a suggested
  // name) to seed a create; the DVSA baseline is then fetched to auto-populate the fields.
  const prefill = !isEdit ? location.state?.prefill : null;
  const [form, setForm] = useState(
    prefill
      ? { ...EMPTY, name: prefill.name ?? '', registration: prefill.registration ?? '' }
      : EMPTY,
  );
  const [prefillFetched, setPrefillFetched] = useState(false);
  const [baseline, setBaseline] = useState(null);
  // Registration the stored DVSA record is for (edit mode). Unlike `baseline`, which a preview
  // overwrites, this stays fixed to what's persisted so Save can tell a preview from the
  // attached record and decide whether the record still applies to the plate being saved.
  const [attachedMotReg, setAttachedMotReg] = useState(null);
  const [pressureUnit, setPressureUnit] = useState('psi');
  const [archived, setArchived] = useState(false);
  const [saving, setSaving] = useState(false);
  const [motConfigured, setMotConfigured] = useState(false);
  const [fetching, setFetching] = useState(false);
  // Edit mode blocks on the vehicle load so the populated form (incl. the DVSA baseline)
  // renders all at once instead of fields popping in after first paint. Create has nothing
  // to load, so it renders immediately.
  const [loading, setLoading] = useState(isEdit);

  useEffect(() => {
    api.getMotStatus().then(s => setMotConfigured(s.configured)).catch(() => {});
  }, []);

  // With a prefilled plate (from "+ Add to garage"), fetch its DVSA baseline once the API
  // is known to be configured, so the identity fields populate without a manual fetch.
  useEffect(() => {
    if (isEdit || prefillFetched || !prefill?.registration || !motConfigured) return;
    setPrefillFetched(true);
    handleFetch(prefill.registration);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEdit, prefill, motConfigured, prefillFetched]);

  useEffect(() => {
    if (!isEdit || !id) return;
    api.getVehicle(id).then(v => {
      setArchived(!!v.archived);
      setBaseline(v.mot_baseline);
      setAttachedMotReg(v.mot_baseline?.registration ?? null);
      setForm({
        name: v.name, kind: v.kind, make: v.make ?? '', model: v.model ?? '',
        year: v.year ?? '', registration: v.registration ?? '', vin: v.vin ?? '',
        colour: v.colour ?? '', fuel_type: v.fuel_type ?? '',
        engine_size: v.engine_size ?? '', first_used_date: v.first_used_date ?? '',
        registration_date: v.registration_date ?? '',
        odometer_unit: v.odometer_unit, purchase_date: v.purchase_date ?? '',
        tyre_size_front: v.tyre_size_front ?? '', tyre_size_rear: v.tyre_size_rear ?? '',
        tyre_pressure_front: v.tyre_pressure_front_psi ?? '',
        tyre_pressure_rear: v.tyre_pressure_rear_psi ?? '',
        notes: v.notes ?? '',
      });
    }).finally(() => setLoading(false));
  }, [isEdit, id]);

  const KIND_HINTS = {
    car: {
      make: 'e.g. Honda', model: 'e.g. Civic', year: 'e.g. 2019',
      engine_size: 'e.g. 1000 cc', colour: 'e.g. Blue', fuel_type: 'e.g. Petrol',
    },
    motorcycle: {
      make: 'e.g. Triumph', model: 'e.g. Street Triple', year: 'e.g. 2021',
      engine_size: 'e.g. 765 cc', colour: 'e.g. Black', fuel_type: 'e.g. Petrol',
    },
  };
  const hint = (key) => KIND_HINTS[form.kind]?.[key] ?? '';
  // Split an identity field into a two-thirds editable override (left) and a one-third fixed
  // DVSA value (right). The baseline is the vehicle's stored mot_baseline when editing
  // (GET /api/vehicles/<id>) or the result of a create-mode DVSA lookup — either way the field
  // renders the same way. With no baseline value the input keeps the full width.
  const dvsaSplit = (key, input) => {
    const val = baseline?.[key];
    if (val == null || val === '') return input;
    // A green border marks the value that will actually be used: the user's override when set,
    // otherwise the DVSA baseline it falls back to.
    const overridden = form[key] != null && String(form[key]).trim() !== '';
    // The fixed column shows the DVSA value as it will display elsewhere (tidied per setting);
    // the editable input keeps the user's exact text.
    const shown = TIDY_KEYS.includes(key) ? formatName(val) : val;
    return (
      <div className={`dvsa-split ${overridden ? 'is-override' : 'is-dvsa'}`}>
        {input}
        <div className="dvsa-fixed" title="From the DVSA MOT record">
          <span className="dvsa-fixed-label">DVSA</span>
          <span className="dvsa-fixed-value">{shown}</span>
        </div>
      </div>
    );
  };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  // Look up the DVSA record for the entered plate and show it as the baseline. In create mode
  // the lookup is *persisted* (a standalone DVSA record) so it isn't lost if the vehicle is never
  // saved — and it relinks automatically if the vehicle is added later. In edit mode it's a
  // non-persisting preview against the plate currently typed (Save re-fetches to store).
  async function handleFetch(regArg) {
    const reg = (typeof regArg === 'string' ? regArg : form.registration).trim();
    if (!reg) { toast('Enter a registration plate first', 'error'); return; }
    setFetching(true);
    try {
      const res = isEdit ? await api.lookupMot(reg) : await api.lookupDvsaVehicle(reg);
      setBaseline(res.mot_baseline);
      toast(isEdit ? 'Found a DVSA record — save to apply' : 'Found and saved a DVSA record');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setFetching(false);
    }
  }

  // Enter in the registration field fetches DVSA data instead of submitting the form.
  function handleRegKeyDown(e) {
    if (e.key !== 'Enter' || !motConfigured) return;
    e.preventDefault();
    if (!fetching && form.registration.trim()) handleFetch();
  }

  function switchPressureUnit(unit) {
    if (unit === pressureUnit) return;
    const convert = v => {
      if (v === '' || v == null) return '';
      const n = Number(v);
      if (Number.isNaN(n)) return v;
      return unit === 'bar' ? +psiToBar(n).toFixed(2) : +barToPsi(n).toFixed(1);
    };
    setForm(f => ({
      ...f,
      tyre_pressure_front: convert(f.tyre_pressure_front),
      tyre_pressure_rear: convert(f.tyre_pressure_rear),
    }));
    setPressureUnit(unit);
  }

  // Tyre pressures are stored in psi regardless of which unit was typed.
  const toPsi = v => {
    if (v === '' || v == null) return null;
    const n = Number(v);
    return pressureUnit === 'bar' ? +barToPsi(n).toFixed(1) : n;
  };

  // Normalise plates the way the backend does before a DVSA lookup (strip spaces, uppercase).
  const normReg = r => (r ?? '').replace(/\s+/g, '').toUpperCase();

  async function handleSubmit(e) {
    e.preventDefault();

    // Reconcile the attached DVSA record against the plate being saved (edit mode only).
    const formReg = normReg(form.registration);
    const attached = attachedMotReg ? normReg(attachedMotReg) : null;
    const aligned = !!baseline && normReg(baseline.registration) === formReg;
    const shouldClear = isEdit && !!attached && attached !== formReg; // plate moved off the record
    const needRefresh = isEdit && aligned && attached !== formReg; // aligned data not yet stored
    if (isEdit && shouldClear && !aligned) {
      // Stale record with no aligned replacement — warn that it will be disconnected.
      const to = form.registration.trim() || '(blank)';
      if (!confirm(
        `The MOT history attached to this vehicle is for ${attachedMotReg}. Because the ` +
        `registration is now ${to}, that DVSA data will be disconnected. Continue?`
      )) return;
    }

    setSaving(true);
    try {
      const body = {
        ...form,
        year: form.year === '' ? null : Number(form.year),
        tyre_pressure_front_psi: toPsi(form.tyre_pressure_front),
        tyre_pressure_rear_psi: toPsi(form.tyre_pressure_rear),
        archived,
      };
      delete body.tyre_pressure_front;
      delete body.tyre_pressure_rear;
      if (isEdit) {
        // Drop the stale record in the same PUT; if aligned data was previewed, re-fetch it
        // against the now-saved plate so the detail page shows the new MOT and tax data.
        if (shouldClear) body.disconnect_mot = true;
        await api.updateVehicle(id, body);
        if (needRefresh) await Promise.allSettled([api.refreshMot(id), api.refreshTax(id)]);
        toast('Vehicle updated');
        navigate(`/vehicles/${id}`);
      } else {
        const v = await api.createVehicle({ ...body, garage_id: currentGarage.id });
        // Fetch + store MOT history and tax status for the new plate so the detail page is ready.
        if (form.registration.trim()) {
          await Promise.allSettled([api.refreshMot(v.id), api.refreshTax(v.id)]);
        }
        toast('Vehicle added');
        navigate(`/vehicles/${v.id}`);
      }
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  if (isEdit && loading) return <SkeletonPage />;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="back-link">
            {isEdit ? <Link to={`/vehicles/${id}`}>← Vehicle</Link> : <Link to="/vehicles">← Garage</Link>}
          </div>
          <h1 className="page-title">{isEdit ? 'Edit vehicle' : `Add vehicle to ${currentGarage?.name ?? ''}`}</h1>
        </div>
      </div>

      <div className="card card-body">
        <form onSubmit={handleSubmit}>
          <div className="reg-lookup mb-4">
            <div className="field reg-lookup-field">
              <label>Registration plate</label>
              <input
                className="reg-plate-input"
                value={form.registration}
                onChange={e => set('registration', e.target.value)}
                onKeyDown={handleRegKeyDown}
                placeholder="A1 XYZ"
                autoFocus={!isEdit}
              />
            </div>
            {motConfigured && (
              <button type="button" className="btn btn-secondary" onClick={handleFetch}
                disabled={fetching || !form.registration.trim()}>
                {fetching ? 'Fetching…' : 'Fetch from DVSA'}
              </button>
            )}
          </div>
          {baseline && (
            <p className="mot-found mb-4">
              Found via DVSA:{' '}
              <strong>{[formatName(baseline.make), formatName(baseline.model)].filter(Boolean).join(' ') || 'record'}</strong>
              {baseline.year ? `, ${baseline.year}` : ''}
              {baseline.colour ? `, ${formatName(baseline.colour)}` : ''}
              {baseline.engine_size ? `, ${baseline.engine_size} cc` : ''}. Leave a field blank to use the DVSA value.
            </p>
          )}

          <div className="form-grid mb-4">
            <div className="field">
              <label>Name *</label>
              <input value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Street Triple, Daily" />
            </div>
            <div className="field">
              <label>Type</label>
              <select value={form.kind} onChange={e => set('kind', e.target.value)}>
                {Object.entries(KIND_LABELS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Make</label>
              {dvsaSplit('make', <input value={form.make} onChange={e => set('make', e.target.value)} placeholder={hint('make')} />)}
            </div>
            <div className="field">
              <label>Model</label>
              {dvsaSplit('model', <input value={form.model} onChange={e => set('model', e.target.value)} placeholder={hint('model')} />)}
            </div>
            <div className="field">
              <label>Year</label>
              {dvsaSplit('year', <input type="number" value={form.year} onChange={e => set('year', e.target.value)} placeholder={hint('year')} />)}
            </div>
            <div className="field">
              <label>Engine size</label>
              {dvsaSplit('engine_size', <input value={form.engine_size} onChange={e => set('engine_size', e.target.value)} placeholder={hint('engine_size')} />)}
            </div>
            <div className="field">
              <label>VIN</label>
              <input value={form.vin} onChange={e => set('vin', e.target.value)} />
            </div>
            <div className="field">
              <label>Colour</label>
              {dvsaSplit('colour', <input value={form.colour} onChange={e => set('colour', e.target.value)} placeholder={hint('colour')} />)}
            </div>
            <div className="field">
              <label>Fuel type</label>
              {dvsaSplit('fuel_type', <input value={form.fuel_type} onChange={e => set('fuel_type', e.target.value)} placeholder={hint('fuel_type')} />)}
            </div>
            <div className="field">
              <label>First used date</label>
              {dvsaSplit('first_used_date', <input type="date" value={form.first_used_date} onChange={e => set('first_used_date', e.target.value)} placeholder="" />)}
            </div>
            <div className="field">
              <label>First registered date</label>
              {dvsaSplit('registration_date', <input type="date" value={form.registration_date} onChange={e => set('registration_date', e.target.value)} placeholder="" />)}
            </div>
            <div className="field">
              <label>Odometer display unit</label>
              <select value={form.odometer_unit} onChange={e => set('odometer_unit', e.target.value)}>
                <option value="mi">Miles</option>
                <option value="km">Kilometres</option>
              </select>
            </div>
            <div className="field">
              <label>Purchase date</label>
              <input type="date" value={form.purchase_date} onChange={e => set('purchase_date', e.target.value)} />
            </div>
          </div>

          <h2 className="section-title mb-3">Tyres</h2>
          <div className="form-grid mb-4">
            <div className="field">
              <label>Front tyre size</label>
              <input value={form.tyre_size_front} onChange={e => set('tyre_size_front', e.target.value)} placeholder="e.g. 120/70 ZR17" />
            </div>
            <div className="field">
              <label>Rear tyre size</label>
              <input value={form.tyre_size_rear} onChange={e => set('tyre_size_rear', e.target.value)} placeholder="e.g. 180/55 ZR17" />
            </div>
            <div className="field span-2">
              <label>Tyre pressure</label>
              <div className="pressure-entry">
                <input type="number" step="any" aria-label="Front tyre pressure" placeholder="Front"
                  value={form.tyre_pressure_front} onChange={e => set('tyre_pressure_front', e.target.value)} />
                <div className="unit-toggle" role="group" aria-label="Pressure unit">
                  {['psi', 'bar'].map(u => (
                    <button key={u} type="button" className={pressureUnit === u ? 'is-active' : ''}
                      aria-pressed={pressureUnit === u} onClick={() => switchPressureUnit(u)}>
                      {u}
                    </button>
                  ))}
                </div>
                <input type="number" step="any" aria-label="Rear tyre pressure" placeholder="Rear"
                  value={form.tyre_pressure_rear} onChange={e => set('tyre_pressure_rear', e.target.value)} />
              </div>
            </div>
          </div>

          <div className="form-grid mb-4">
            <div className="field span-2">
              <label>Notes</label>
              <textarea value={form.notes} onChange={e => set('notes', e.target.value)} placeholder="Mods, quirks, anything worth remembering…" />
            </div>
            {isEdit && (
              <div className="field">
                <label>Archived</label>
                <label className="text-sm">
                  <input type="checkbox" checked={archived} onChange={e => setArchived(e.target.checked)} />
                  {' '}Hide from the garage (sold / off the road)
                </label>
              </div>
            )}
          </div>

          <div className="form-actions">
            <button className="btn btn-success" disabled={saving || !form.name}>
              {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Add vehicle'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
