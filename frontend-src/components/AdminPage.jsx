import { useState, useEffect } from 'react';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useToast } from './Toast.jsx';
import RelativeTime from './RelativeTime.jsx';
import DeploymentInfo from './DeploymentInfo.jsx';
import ExternalApis from './ExternalApis.jsx';
import PythonAnywhereStats from './PythonAnywhereStats.jsx';
import { ROLE_LABELS } from '../constants.js';

function statusLabel(u) {
  if (!u.expires_at) return null;
  const exp = new Date(u.expires_at);
  return exp < new Date() ? 'expired' : `expires ${exp.toISOString().slice(0, 10)}`;
}

function GaragesSection({ garages, onChanged }) {
  const toast = useToast();
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleCreate(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createGarage(name.trim());
      setName('');
      toast('Garage created');
      onChanged();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(g) {
    if (!confirm(`Delete garage "${g.name}" and ALL its vehicles, services, and photos?`)) return;
    try {
      await api.deleteGarage(g.id);
      toast(`Garage "${g.name}" deleted`);
      onChanged();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleRename(g) {
    const newName = prompt(`Rename garage "${g.name}" to:`, g.name);
    if (!newName || newName.trim() === g.name) return;
    try {
      await api.renameGarage(g.id, newName.trim());
      toast('Garage renamed');
      onChanged();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Garages</h1>
      </div>
      <form onSubmit={handleCreate} className="inline-form-sm mb-4">
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="New garage name…"
        />
        <button className="btn btn-primary" disabled={saving || !name.trim()}>+ Create garage</button>
      </form>
      <div className="card mb-6">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Vehicles</th><th>Members</th><th>Created (UTC)</th><th></th></tr></thead>
            <tbody>
              {(garages ?? []).map(g => (
                <tr key={g.id}>
                  <td>{g.name}</td>
                  <td>{g.vehicle_count}</td>
                  <td>{g.member_count}</td>
                  <td className="meta"><RelativeTime value={g.created_at} /></td>
                  <td className="col-shrink">
                    <div className="row-actions">
                      <button className="btn btn-secondary btn-sm" onClick={() => handleRename(g)}>Rename</button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(g)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
              {garages?.length === 0 && <tr><td colSpan={5} className="empty">No garages yet — create one above</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function UserEditor({ user, garages, onChanged }) {
  const toast = useToast();
  const [password, setPassword] = useState('');
  const [add, setAdd] = useState({ garage_id: '', role: 'member' });

  const memberGarageIds = new Set(user.memberships.map(m => m.garage_id));
  const joinable = (garages ?? []).filter(g => !memberGarageIds.has(g.id));

  async function handleResetPassword(e) {
    e.preventDefault();
    try {
      await api.resetUserPassword(user.id, password);
      setPassword('');
      toast(`Password reset for "${user.username}"`);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleAddMembership(e) {
    e.preventDefault();
    try {
      await api.addMember(Number(add.garage_id), user.username, add.role);
      setAdd({ garage_id: '', role: 'member' });
      toast(`Added to garage as ${ROLE_LABELS[add.role].toLowerCase()}`);
      onChanged();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleRoleChange(m, role) {
    try {
      await api.setMemberRole(m.garage_id, user.id, role);
      toast(`${user.username} is now ${ROLE_LABELS[role].toLowerCase()} of ${m.garage_name}`);
      onChanged();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleRemoveMembership(m) {
    if (!confirm(`Remove ${user.username} from ${m.garage_name}?`)) return;
    try {
      await api.removeMember(m.garage_id, user.id);
      toast(`Removed from ${m.garage_name}`);
      onChanged();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div className="user-editor">
      <div className="field mb-3">
        <label>Reset password</label>
        <form onSubmit={handleResetPassword} className="inline-form-sm">
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="New password (min 6 chars)"
            autoComplete="new-password"
          />
          <button className="btn btn-secondary btn-sm" disabled={password.length < 6}>Reset</button>
        </form>
      </div>

      <div className="field">
        <label>Garages</label>
        {user.memberships.length === 0 && <span className="text-muted text-sm">Not in any garage yet.</span>}
        {user.memberships.map(m => (
          <div key={m.garage_id} className="inline-form-sm mb-2">
            <span className="user-editor-garage">{m.garage_name}</span>
            <select value={m.role} onChange={e => handleRoleChange(m, e.target.value)}>
              {Object.entries(ROLE_LABELS).map(([r, label]) => <option key={r} value={r}>{label}</option>)}
            </select>
            <button type="button" className="btn btn-danger btn-sm" onClick={() => handleRemoveMembership(m)}>Remove</button>
          </div>
        ))}
        {joinable.length > 0 && (
          <form onSubmit={handleAddMembership} className="inline-form-sm">
            <select value={add.garage_id} onChange={e => setAdd(a => ({ ...a, garage_id: e.target.value }))}>
              <option value="">— Add to garage —</option>
              {joinable.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
            {add.garage_id && (
              <select value={add.role} onChange={e => setAdd(a => ({ ...a, role: e.target.value }))}>
                {Object.entries(ROLE_LABELS).map(([r, label]) => <option key={r} value={r}>{label}</option>)}
              </select>
            )}
            <button className="btn btn-primary btn-sm" disabled={!add.garage_id}>Add</button>
          </form>
        )}
      </div>
    </div>
  );
}

function UsersSection({ garages, onChanged }) {
  const { user: me } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [form, setForm] = useState({ username: '', password: '', ttl_days: '', garage_id: '', role: 'member' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.getUsers().then(setUsers); }, []);

  const refreshUsers = () => {
    api.getUsers().then(setUsers);
    onChanged();
  };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function handleCreate(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { username: form.username, password: form.password };
      if (form.ttl_days) body.ttl_days = parseInt(form.ttl_days, 10);
      if (form.garage_id) {
        body.garage_id = Number(form.garage_id);
        body.role = form.role;
      }
      const created = await api.createUser(body);
      setUsers(us => [...us, created]);
      setForm({ username: '', password: '', ttl_days: '', garage_id: '', role: 'member' });
      setShowAdd(false);
      toast(`User "${created.username}" created`);
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
    <>
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
                <label>Add to garage</label>
                <select value={form.garage_id} onChange={e => set('garage_id', e.target.value)}>
                  <option value="">— None yet —</option>
                  {(garages ?? []).map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              </div>
              {form.garage_id && (
                <div className="field">
                  <label>Role in garage</label>
                  <select value={form.role} onChange={e => set('role', e.target.value)}>
                    {Object.entries(ROLE_LABELS).map(([r, label]) => <option key={r} value={r}>{label}</option>)}
                  </select>
                </div>
              )}
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

      <div className="card mb-6">
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Username</th><th>Garages</th><th>Status</th><th>Created (UTC)</th><th></th></tr>
            </thead>
            <tbody>
              {users.map(u => {
                const expiry = statusLabel(u);
                const isExpired = expiry === 'expired';
                const manageable = !u.is_admin && u.id !== me?.id;
                const expanded = expandedId === u.id;
                return [
                  <tr key={u.id}>
                    <td>
                      {u.username}
                      {u.is_admin && <span className="user-badge user-badge-admin">Site admin</span>}
                      {u.id === me?.id && <span className="tag-you">(you)</span>}
                    </td>
                    <td className="text-sm">
                      {u.memberships?.length
                        ? u.memberships.map(m => (
                            <span key={m.garage_id} className="membership-chip">
                              {m.garage_name} <em>({ROLE_LABELS[m.role] ?? m.role})</em>
                            </span>
                          ))
                        : <span className="text-muted">—</span>}
                    </td>
                    <td className={isExpired ? 'text-danger text-sm' : 'text-muted text-sm'}>
                      {expiry || '—'}
                    </td>
                    <td className="meta"><RelativeTime value={u.created_at} /></td>
                    <td className="col-shrink">
                      {manageable && (
                        <div className="row-actions">
                          <button
                            className={`btn btn-secondary btn-sm${expanded ? ' btn-active' : ''}`}
                            onClick={() => setExpandedId(expanded ? null : u.id)}
                          >
                            {expanded ? 'Close' : 'Manage'}
                          </button>
                          <button className="btn btn-danger btn-sm" onClick={() => handleDelete(u)}>Delete</button>
                        </div>
                      )}
                    </td>
                  </tr>,
                  manageable && expanded && (
                    <tr key={`${u.id}-editor`}>
                      <td colSpan={5}>
                        <UserEditor user={u} garages={garages} onChanged={refreshUsers} />
                      </td>
                    </tr>
                  ),
                ];
              })}
              {users.length === 0 && <tr><td colSpan={5} className="empty">No users</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export default function AdminPage() {
  const { garages, refreshGarages } = useAuth();

  return (
    <div>
      <GaragesSection garages={garages} onChanged={refreshGarages} />
      <UsersSection garages={garages} onChanged={refreshGarages} />
      <div className="page-header">
        <h1 className="page-title">Deployment</h1>
      </div>
      <DeploymentInfo />
      <ExternalApis />
      <PythonAnywhereStats />
    </div>
  );
}
