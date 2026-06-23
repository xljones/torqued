import { useState, useEffect } from 'react';
import { api } from '../api.js';
import RelativeTime from './RelativeTime.jsx';

function SkeletonCard() {
  return (
    <div className="card card-body mb-6">
      <div className="form-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div>
          <div className="skeleton-line" style={{ width: 60, height: 11, marginBottom: 10 }} />
          <div className="skeleton-line" style={{ width: '50%', height: 14, marginBottom: 14 }} />
          <div className="skeleton-line" style={{ width: 60, height: 11, marginBottom: 10 }} />
          <div className="skeleton-line" style={{ width: '70%', height: 14 }} />
        </div>
        <div>
          <div className="skeleton-line" style={{ width: 60, height: 11, marginBottom: 10 }} />
          <div className="skeleton-line" style={{ width: '40%', height: 14, marginBottom: 8 }} />
          <div className="skeleton-line" style={{ width: '90%', height: 14 }} />
        </div>
      </div>
    </div>
  );
}

export default function DeploymentInfo() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getDeploymentInfo()
      .then(setInfo)
      .catch(err => setError(err.message));
  }, []);

  if (error) {
    return (
      <div className="card card-body mb-6">
        <h2 className="section-title">Latest deployment</h2>
        <p className="text-sm text-danger">{error}</p>
      </div>
    );
  }

  if (!info) return <SkeletonCard />;

  if (!info.configured) {
    return (
      <div className="card card-body mb-6">
        <h2 className="section-title">Latest deployment</h2>
        <p className="text-sm text-muted">
          No build info yet — this card populates once a deploy writes <code>dist/build-info.json</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="card card-body mb-6">
      <h2 className="section-title mb-4">Latest deployment</h2>

      <div className="form-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div>
          <div className="scan-field-label mb-2">Version</div>
          <p className="text-sm">v{info.version}</p>

          <div className="scan-field-label mb-2 mt-4">Built</div>
          <p className="text-sm">
            {info.built_at ? <RelativeTime value={info.built_at} live={false} /> : '—'}
          </p>
        </div>

        <div>
          <div className="scan-field-label mb-2">Commit</div>
          <p className="text-sm" style={{ fontFamily: 'monospace' }}>{info.sha || '—'}</p>
          {info.msg && <p className="text-sm text-muted">{info.msg}</p>}
        </div>
      </div>
    </div>
  );
}
