import { useState } from 'react';
import { useAuth } from '../AuthContext.jsx';
import BuildInfo from './BuildInfo.jsx';

export default function LoginPage() {
  const { login, dbSwitcher } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [database, setDatabase] = useState('local');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password, dbSwitcher ? database : undefined);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="card card-body auth-card">
        <img src="/wrench-icon.svg" className="auth-logo" alt="Wrench icon" />
        <h1 className="auth-title">Torqued</h1>
        <p className="auth-tagline">All torque, no friction</p>
        <form onSubmit={handleSubmit}>
          <div className="form-grid full mb-4">
            <div className="field">
              <label>Username</label>
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
                required
              />
            </div>
            <div className="field">
              <label>Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
          </div>
          {dbSwitcher && (
            <div className="field mb-4">
              <label>Database</label>
              <div className="db-toggle">
                <span className={database === 'local' ? 'db-toggle-active' : ''}>Local</span>
                <span className={`db-switch${database === 'production' ? ' is-prod' : ''}`}>
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label="Database"
                    checked={database === 'production'}
                    onChange={e => setDatabase(e.target.checked ? 'production' : 'local')}
                  />
                  <span className="db-switch-knob" aria-hidden="true" />
                </span>
                <span className={database === 'production' ? 'db-toggle-active' : ''}>Production</span>
              </div>
              {database === 'production' && (
                <p className="login-db-warning">
                  ⚠ Signing in to the <strong>production</strong> database — changes are live.
                </p>
              )}
            </div>
          )}
          {error && <p className="form-error">{error}</p>}
          <button className="btn btn-primary btn-full" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
      <BuildInfo className="auth-version" />
    </div>
  );
}
