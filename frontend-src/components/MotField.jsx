// A vehicle detail field whose value the backend has already resolved (user override
// else DVSA MOT baseline). `fromBaseline` says the value came from the DVSA record, so
// it gets the "DVSA" badge and — when `format` is given — title-casing; a user's own
// override is shown exactly as typed.
export default function MotField({ label, value, fromBaseline, render, format }) {
  const shown = fromBaseline && format ? format(value) : value;
  return (
    <div className="field">
      <label>{label}</label>
      <span>
        {shown != null && shown !== '' ? (render ? render(shown) : shown) : '—'}
        {fromBaseline && value != null && (
          <span className="field-source" title="From the DVSA MOT record">DVSA</span>
        )}
      </span>
    </div>
  );
}
