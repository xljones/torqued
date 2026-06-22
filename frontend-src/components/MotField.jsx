// A vehicle detail field whose baseline comes from the DVSA MOT record. Shows
// the user override when set, otherwise the DVSA value badged "DVSA".
// `format`, when given, is applied to the DVSA baseline only (e.g. title-casing the
// all-caps make/model) — the user's own override is always shown exactly as typed.
export default function MotField({ label, fieldKey, vehicle, baseline, render, format }) {
  const override = vehicle[fieldKey];
  const hasOverride = override != null && override !== '';
  const baseVal = baseline?.[fieldKey] ?? null;
  const value = hasOverride ? override : (format ? format(baseVal) : baseVal);
  const fromMot = !hasOverride && baseVal != null;
  return (
    <div className="field">
      <label>{label}</label>
      <span>
        {value != null && value !== '' ? (render ? render(value) : value) : '—'}
        {fromMot && <span className="field-source" title="From the DVSA MOT record">DVSA</span>}
      </span>
    </div>
  );
}
