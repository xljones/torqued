import { useState, useEffect } from 'react';
import { api } from '../api.js';

const fmt = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

function resetIn(isoString) {
  const ms = new Date(isoString) - Date.now();
  const mins = Math.round(ms / 60_000);
  if (Math.abs(mins) < 60) return fmt.format(mins, 'minute');
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return fmt.format(hours, 'hour');
  return fmt.format(Math.round(hours / 24), 'day');
}

function formatBytes(bytes) {
  if (!bytes) return '0 MB';
  const mb = bytes / 1024 / 1024;
  if (mb < 1024) return `${mb.toFixed(mb < 10 ? 2 : 0)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function formatHours(seconds) {
  const hours = (seconds || 0) / 3600;
  return hours < 10 ? hours.toFixed(2) : Math.round(hours).toLocaleString();
}

function SkeletonCard() {
  return (
    <div className="card card-body mb-6">
      <div className="form-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div>
          <div className="skeleton-line" style={{ width: 60, height: 11, marginBottom: 10 }} />
          <div className="skeleton-line" style={{ width: '80%', height: 14, marginBottom: 8 }} />
          <div className="skeleton-line" style={{ width: 120, height: 12 }} />
        </div>
        <div>
          <div className="skeleton-line" style={{ width: 60, height: 11, marginBottom: 10 }} />
          <div className="skeleton-line" style={{ width: '80%', height: 14, marginBottom: 8 }} />
          <div className="skeleton-line" style={{ width: '60%', height: 14 }} />
        </div>
      </div>
    </div>
  );
}

export default function NeonStats() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getNeonStats()
      .then(setStats)
      .catch(err => setError(err.message));
  }, []);

  if (error) {
    return (
      <div className="card card-body mb-6">
        <h2 className="section-title">Neon database</h2>
        <p className="text-sm text-danger">{error}</p>
      </div>
    );
  }

  if (!stats) return <SkeletonCard />;

  if (!stats.configured) {
    return (
      <div className="card card-body mb-6">
        <h2 className="section-title">Neon database</h2>
        <p className="text-sm text-muted">
          Stats unavailable — set <code>NEON_API_KEY</code> to enable.{' '}
          <code>NEON_PROJECT_ID</code> is optional (the first project is used when omitted).
        </p>
      </div>
    );
  }

  if (stats.error) {
    return (
      <div className="card card-body mb-6">
        <h2 className="section-title">Neon database</h2>
        <p className="text-sm text-danger">{stats.error}</p>
      </div>
    );
  }

  const { project, storage_bytes, cpu_seconds, active_seconds, quota_reset_at } = stats;

  return (
    <div className="card card-body mb-6">
      <h2 className="section-title mb-4">Neon database</h2>

      <div className="form-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div>
          <div className="scan-field-label mb-2">Storage</div>
          <div className="text-sm">{formatBytes(storage_bytes)}</div>
          <p className="text-sm text-muted mt-2">Logical + WAL, all branches</p>
        </div>

        <div>
          <div className="scan-field-label mb-2">Compute</div>
          <div className="text-sm">{formatHours(cpu_seconds)} compute-hours</div>
          <p className="text-sm text-muted mt-2">
            {formatHours(active_seconds)} active-hours this period
          </p>
        </div>
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <div className="scan-field-label mb-2">Project</div>
        <div className="text-sm">
          {project.name}
          {project.region && <span className="text-muted"> · {project.region}</span>}
          {project.pg_version && <span className="text-muted"> · Postgres {project.pg_version}</span>}
        </div>
        {quota_reset_at && (
          <p className="text-sm text-muted mt-2">Resets {resetIn(quota_reset_at)}</p>
        )}
      </div>
    </div>
  );
}
