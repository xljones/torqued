import { useState } from 'react';
import { fmtDistance } from '../units.js';

// Where each point on the chart came from, with its label and dot colour class.
const SOURCE_META = {
  manual: { label: 'Manual entry', cls: 'mileage-dot-manual' },
  service: { label: 'Service log', cls: 'mileage-dot-service' },
  mot: { label: 'MOT test', cls: 'mileage-dot-mot' },
};

const PAD = 4; // percent inset so edge points and their tooltips aren't clipped

/**
 * Merged odometer timeline (manual logs + service readings + MOT tests) as an
 * interactive line chart: hover any point for its mileage, date and source.
 */
export default function MileageChart({ series, unit }) {
  const [hover, setHover] = useState(null);
  if (!series || series.length < 2) return null;

  const xs = series.map(p => new Date(p.date).getTime());
  const ys = series.map(p => p.odometer_km);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const fx = t => (x1 === x0 ? 0.5 : (t - x0) / (x1 - x0));
  const fy = v => (y1 === y0 ? 0.5 : (v - y0) / (y1 - y0));

  // Map a 0–1 fraction into the padded plot area, in percent.
  const left = f => PAD + f * (100 - 2 * PAD);
  const bottom = f => PAD + f * (100 - 2 * PAD);

  const points = series.map(p => ({
    ...p,
    left: left(fx(new Date(p.date).getTime())),
    bottom: bottom(fy(p.odometer_km)),
  }));
  const polyline = points.map(p => `${p.left.toFixed(2)},${(100 - p.bottom).toFixed(2)}`).join(' ');

  // Vertical guide + label at each Jan 1 within the data's time span. UTC throughout to
  // match how point dates parse (`new Date('YYYY-MM-DD')` is UTC midnight).
  const startYear = new Date(x0).getUTCFullYear();
  const endYear = new Date(x1).getUTCFullYear();
  const yearMarks = [];
  for (let y = startYear + 1; y <= endYear; y++) {
    const t = Date.UTC(y, 0, 1);
    if (t >= x0 && t <= x1) yearMarks.push({ year: y, left: left(fx(t)) });
  }

  return (
    <div className="mileage-chart" onMouseLeave={() => setHover(null)}>
      <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none" role="img"
        aria-label={`Mileage from ${fmtDistance(y0, unit)} to ${fmtDistance(y1, unit)}`}>
        {yearMarks.map(m => (
          <line
            key={m.year}
            className="mileage-year-line"
            x1={m.left}
            x2={m.left}
            y1="0"
            y2="100"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <polyline points={polyline} vectorEffect="non-scaling-stroke" />
      </svg>
      {points.map((p, i) => {
        const meta = SOURCE_META[p.source] ?? SOURCE_META.manual;
        return (
          <button
            key={`${p.source}-${p.id}`}
            type="button"
            className={`mileage-dot ${meta.cls}${hover === i ? ' is-active' : ''}`}
            style={{ left: `${p.left}%`, bottom: `${p.bottom}%` }}
            onMouseEnter={() => setHover(i)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            aria-label={`${fmtDistance(p.odometer_km, unit)} on ${p.date}, ${meta.label}`}
          />
        );
      })}
      {yearMarks.map(m => (
        <span key={m.year} className="mileage-year-label" style={{ left: `${m.left}%` }}>
          {m.year}
        </span>
      ))}
      {hover !== null && (() => {
        const p = points[hover];
        const meta = SOURCE_META[p.source] ?? SOURCE_META.manual;
        const tx = p.left < 22 ? '0' : p.left > 78 ? '-100%' : '-50%';
        return (
          <div
            className="mileage-tooltip"
            style={{ left: `${p.left}%`, bottom: `calc(${p.bottom}% + 12px)`, transform: `translateX(${tx})` }}
          >
            <div className="mileage-tooltip-value">{fmtDistance(p.odometer_km, unit)}</div>
            <div className="mileage-tooltip-meta">
              <span className={`mileage-tooltip-dot ${meta.cls}`} />
              {meta.label} · {p.date}
            </div>
            {p.note && <div className="mileage-tooltip-note">{p.note}</div>}
          </div>
        );
      })()}
    </div>
  );
}
