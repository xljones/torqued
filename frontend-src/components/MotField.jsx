// A vehicle detail field sourced from the official records. Shows the user override when
// set, otherwise the DVSA MOT value, falling back to the DVLA VES value. Each shown
// baseline value is badged with the source(s) that back it — DVSA, DVLA, or both when the
// two agree (see torqued.ves.field_sources).
//
// Hovering a source badge shows a tooltip quoting that record's *verbatim* value and
// naming the record, e.g. `"VOLKSWAGEN" from the DVSA record`. The quoted value is the raw
// baseline (`dvsaVal` / `vesVal`), never the displayed value — so with "Tidy up vehicle
// names" on, the field reads "Volkswagen" while the tooltip still reveals the record's
// true "VOLKSWAGEN", matching the app's convention that records are verbatim and
// tidy-casing is display-only.
//
// `format`, when given, is applied to the baseline only (e.g. title-casing an all-caps
// make/model) — the user's own override is always shown exactly as typed. `fieldSources`
// is the per-field provenance map from the API; without it the field self-describes as
// DVSA when only a DVSA baseline is shown (keeps the component usable standalone).
const SOURCE_LABEL = { dvsa: 'DVSA', dvla: 'DVLA' };

export default function MotField({
  label, fieldKey, vehicle, baseline, vesBaseline, fieldSources, render, format,
}) {
  const override = vehicle[fieldKey];
  const hasOverride = override != null && override !== '';
  const dvsaVal = baseline?.[fieldKey] ?? null;
  const vesVal = vesBaseline?.[fieldKey] ?? null;
  const baseVal = dvsaVal ?? vesVal;
  const value = hasOverride ? override : (format ? format(baseVal) : baseVal);
  const shown = value != null && value !== '';

  let sources = [];
  if (!hasOverride && shown) {
    sources = fieldSources?.[fieldKey] ?? (dvsaVal != null ? ['dvsa'] : ['dvla']);
  }
  // The verbatim value behind each source, quoted in that badge's tooltip.
  const sourceValue = { dvsa: dvsaVal, dvla: vesVal };
  return (
    <div className="field">
      <label>{label}</label>
      <span>
        {shown ? (render ? render(value) : value) : '—'}
        {sources.map(s => (
          <span key={s} className={`field-source field-source-${s}`}
            title={`"${sourceValue[s]}" from the ${SOURCE_LABEL[s]} record`}>
            {SOURCE_LABEL[s]}
          </span>
        ))}
      </span>
    </div>
  );
}
