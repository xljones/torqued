import { useState, useEffect } from 'react';
import { api } from '../api.js';

// Admin-only card showing which outbound URL each external vehicle-data lookup routes to
// (e.g. DVLA VES direct vs. via the relay, and the DVSA MOT API + its OAuth token URL).
// Never shows secrets — the backend only surfaces URLs.
function SkeletonCard() {
  return (
    <div className="card card-body mb-6">
      <div className="skeleton-line" style={{ width: 120, height: 14, marginBottom: 16 }} />
      <div className="skeleton-line" style={{ width: '70%', height: 12, marginBottom: 10 }} />
      <div className="skeleton-line" style={{ width: '80%', height: 12 }} />
    </div>
  );
}

export default function ExternalApis() {
  const [apis, setApis] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getExternalApis()
      .then(data => setApis(data.apis))
      .catch(err => setError(err.message));
  }, []);

  if (error) {
    return (
      <div className="card card-body mb-6">
        <h2 className="section-title">External APIs</h2>
        <p className="text-sm text-danger">{error}</p>
      </div>
    );
  }

  if (!apis) return <SkeletonCard />;

  return (
    <div className="card card-body mb-6">
      <h2 className="section-title mb-2">External APIs</h2>
      <p className="text-sm text-muted mb-4">Where each outbound vehicle-data lookup is routed.</p>

      <div className="form-grid" style={{ gap: '1.25rem' }}>
        {apis.map(a => (
          <div key={a.name}>
            <div className="scan-field-label mb-1">
              {a.name}
              {a.mode && <span className="field-source" title="Routing mode">{a.mode}</span>}
              {a.configured === false && (
                <span className="field-source" title="Credentials not set">not configured</span>
              )}
            </div>
            {a.purpose && <p className="text-sm text-muted" style={{ margin: '0 0 4px' }}>{a.purpose}</p>}
            <p className="text-sm" style={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{a.url}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
