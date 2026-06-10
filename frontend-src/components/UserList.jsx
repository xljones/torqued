import { useState, useEffect } from 'react';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useToast } from './Toast.jsx';
import RelativeTime from './RelativeTime.jsx';
import PythonAnywhereStats from './PythonAnywhereStats.jsx';

function statusLabel(u) {
  if (!u.expires_at) return null;
  const exp = new Date(u.expires_at);
  return exp < new Date() ? 'expired' : `expires ${exp.toISOString().slice(0, 10)}`;
}

function userBadge(u) {
  if (u.is_admin) return { cls: 'user-badge-admin', label: 'Admin' };
  if (u.is_readonly) return { cls: 'user-badge-readonly', label: 'Read-only' };
  return { cls: 'user-badge-normal', label: 'Normal' };
}

export default function UserList() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', ttl_days: '', is_readonly: true });
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => { api.getUsers().then(setUsers); }, []);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function handleCreate(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const body = {
        username: form.username,
        password: form.password,
        is_readonly: form.is_readonly,
      };
      if (form.ttl_days) body.ttl_days = parseInt(form.ttl_days, 10);
      const created = await api.createUser(body);
      setUsers(us => [...us, created]);
      setForm({ username: '', password: '', ttl_days: '', is_readonly: true });
      setShowAdd(false);
      const kind = created.is_readonly ? 'Read-only' : 'Normal';
      toast(`${kind} user "${created.username}" created`);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(u) {
    if (!confirm(`Delete user "${u.username}"?`)) return;
    try {
      await api.deleteUser(u.id);
      setUsers(us => us.filter(x => x.id !== u.id));
      toast(`User "${u.username}" deleted`);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Deployment</h1>
      </div>
      <PythonAnywhereStats />
      <div className="page-header">
        <h1 className="page-title">Users</h1>
        <button className="btn btn-primary" onClick={() => setShowAdd(v => !v)}>+ New user</button>
      </div>

      {showAdd && (
        <div className="card card-body mb-6">
          <form onSubmit={handleCreate}>
            <div className="form-grid mb-3">
              <div className="field">
                <label>Username *</label>
                <input value={form.username} onChange={e => set('username', e.target.value)} autoFocus />
              </div>
              <div className="field">
                <label>Password *</label>
                <input type="password" value={form.password} onChange={e => set('password', e.target.value)} />
              </div>
              <div className="field">
                <label>User type</label>
                <select value={form.is_readonly ? 'readonly' : 'normal'} onChange={e => set('is_readonly', e.target.value === 'readonly')}>
                  <option value="readonly">Read-only</option>
                  <option value="normal">Normal</option>
                </select>
              </div>
              <div className="field">
                <label>Expires after (days)</label>
                <input
                  type="number" min="1" value={form.ttl_days}
                  onChange={e => set('ttl_days', e.target.value)}
                  placeholder="Leave blank for no expiry"
                />
              </div>
            </div>
            <div className="form-actions">
              <button className="btn btn-success" disabled={saving || !form.username || !form.password}>
                {saving ? 'Creating…' : 'Create user'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Username</th><th>Type</th><th>Status</th><th>Created (UTC)</th><th></th></tr>
            </thead>
            <tbody>
              {users.map(u => {
                const expiry = statusLabel(u);
                const isExpired = expiry === 'expired';
                const { cls, label } = userBadge(u);
                return (
                  <tr key={u.id}>
                    <td>
                      {u.username}
                      {u.id === me?.id && <span className="tag-you">(you)</span>}
                    </td>
                    <td>
                      <span className={`user-badge ${cls}`}>{label}</span>
                    </td>
                    <td className={isExpired ? 'text-danger text-sm' : 'text-muted text-sm'}>
                      {expiry || '—'}
                    </td>
                    <td className="meta"><RelativeTime value={u.created_at} /></td>
                    <td className="col-shrink">
                      {!u.is_admin && u.id !== me?.id && (
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(u)}>Delete</button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {users.length === 0 && <tr><td colSpan={5} className="empty">No users</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
