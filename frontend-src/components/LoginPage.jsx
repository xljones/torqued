import { useState } from 'react';
import { useAuth } from '../AuthContext.jsx';
import BuildInfo from './BuildInfo.jsx';

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
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
