import { useState } from 'react';

// A collapsible viewer for a single DVSA record (the vehicle snapshot or one MOT test).
// Shared between the vehicle-detail MOT card and the admin DVSA-vehicles page so both
// analyse the raw official payload the same way: a clickable tile that expands into a
// Formatted (interactive tree) / Raw (pretty-printed JSON) panel.

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

export function JsonTree({ data }) {
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

export default function DvsaRecord({ label, summary, raw, className = '' }) {
  const [open, setOpen] = useState(false);
  const [jsonFmt, setJsonFmt] = useState('formatted');
  const toggle = () => setOpen(v => !v);

  return (
    <>
      <div
        className={`pressure-tile dvsa-record-tile${className ? ` ${className}` : ''}${open ? ' dvsa-record-tile--open' : ''}`}
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), toggle())}
      >
        <div className="pressure-label">
          {label} <span className="dvsa-record-caret">{open ? '▲' : '▼'}</span>
        </div>
        {/* The DVSA record shows the official data verbatim (all-caps as DVSA returns it) —
            never tidied — so it matches the raw JSON panel below. */}
        {summary != null && <div className="pressure-size">{summary}</div>}
      </div>

      {open && (
        <div className="dvsa-json-panel mt-2">
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
            ? <JsonTree data={raw} />
            : <pre className="dvsa-raw-json mt-2">{JSON.stringify(raw, null, 2)}</pre>}
        </div>
      )}
    </>
  );
}
