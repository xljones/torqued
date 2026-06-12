import { useState, useEffect } from 'react';
import { api } from '../api.js';

const CODE_RE = /^[PBCUpbcu][0-9][0-9A-Fa-f]{3}$/;

export default function CodeLookup() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [matches, setMatches] = useState(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResult(null);
      api.listCodes().then(setMatches).catch(() => setMatches(null));
      return;
    }
    const timer = setTimeout(() => {
      if (CODE_RE.test(q)) {
        api.lookupCode(q).then(r => { setResult(r); setMatches(null); }).catch(() => setResult(null));
      } else {
        api.searchCodes(q).then(m => { setMatches(m); setResult(null); }).catch(() => setMatches(null));
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Fault codes</h1>
      </div>

      <p className="text-muted mb-4">
        Look up an OBD-II diagnostic trouble code (e.g. <button className="link-button" onClick={() => setQuery('P0016')}>P0016</button>),
        or search descriptions by keyword (e.g. <button className="link-button" onClick={() => setQuery('misfire')}>misfire</button>).
      </p>

      <div className="mb-4">
        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="P0016, U0100, misfire, camshaft…"
          className="search-input"
          autoFocus
        />
      </div>

      {result && (
        <div className="card card-body mb-6">
          <div className="dtc-header">
            <span className="dtc-code">{result.code}</span>
            <span className={`badge badge-${result.scope === 'generic' ? 'upcoming' : 'due_soon'}`}>
              {result.scope === 'generic' ? 'Generic (SAE)' : 'Manufacturer-specific'}
            </span>
          </div>
          <p className="dtc-description">
            {result.description
              ?? 'No description in the generic code database — this code\'s exact meaning depends on the manufacturer. Check your vehicle\'s service manual.'}
          </p>
          <div className="form-grid mt-3">
            <div className="field">
              <label>System</label>
              <span>{result.system}</span>
            </div>
            {result.subsystem && (
              <div className="field">
                <label>Subsystem</label>
                <span>{result.subsystem}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {matches && (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Code</th><th>Description</th></tr></thead>
              <tbody>
                {matches.map(m => (
                  <tr key={m.code} className="row-clickable" onClick={() => setQuery(m.code)}>
                    <td><span className="dtc-code dtc-code-sm">{m.code}</span></td>
                    <td>{m.description}</td>
                  </tr>
                ))}
                {matches.length === 0 && <tr><td colSpan={2} className="empty">No matching codes</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="text-muted text-sm mt-6">
        Generic powertrain code descriptions from the SAE J2012 set
        (via <a href="https://github.com/fabiovila/OBDIICodes" target="_blank" rel="noreferrer">OBDIICodes</a>, MIT).
        Manufacturer-specific codes (P1xxx, B/C/U 1–2xxx) vary by brand — always confirm against your vehicle&apos;s documentation.
      </p>
    </div>
  );
}
