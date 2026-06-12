import { useState, useEffect, useCallback } from 'react';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useToast } from './Toast.jsx';
import { ROLE_LABELS } from '../constants.js';

export default function MembersPage() {
  const { user: me, currentGarage, refreshGarages } = useAuth();
  const toast = useToast();
  const [members, setMembers] = useState(null);
  const [form, setForm] = useState({ username: '', role: 'member' });

  const refresh = useCallback(() => {
    if (currentGarage) api.getMembers(currentGarage.id).then(setMembers);
  }, [currentGarage]);
  useEffect(refresh, [refresh]);

  if (!currentGarage) return <p className="text-muted">No garage selected.</p>;
  const isOwner = currentGarage.role === 'owner';

  async function handleAdd(e) {
    e.preventDefault();
    try {
      await api.addMember(currentGarage.id, form.username.trim(), form.role);
      setForm({ username: '', role: 'member' });
      toast('Member added');
      refresh();
      refreshGarages();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleRoleChange(m, role) {
    try {
      await api.setMemberRole(currentGarage.id, m.user_id, role);
      toast(`${m.username} is now ${ROLE_LABELS[role].toLowerCase()}`);
      refresh();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleRemove(m) {
    if (!confirm(`Remove ${m.username} from ${currentGarage.name}?`)) return;
    try {
      await api.removeMember(currentGarage.id, m.user_id);
      toast('Member removed');
      refresh();
      refreshGarages();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Members — {currentGarage.name}</h1>
      </div>

      {isOwner && (
        <form onSubmit={handleAdd} className="inline-form-sm mb-4">
          <input
            value={form.username}
            onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            placeholder="Username to add…"
          />
          <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
            {Object.entries(ROLE_LABELS).map(([r, label]) => <option key={r} value={r}>{label}</option>)}
          </select>
          <button className="btn btn-primary" disabled={!form.username.trim()}>+ Add member</button>
        </form>
      )}

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Username</th><th>Role</th>{isOwner && <th></th>}</tr></thead>
            <tbody>
              {members === null && <tr><td colSpan={3} className="empty">Loading…</td></tr>}
              {members?.map(m => (
                <tr key={m.user_id}>
                  <td>
                    {m.username}
                    {m.user_id === me?.id && <span className="tag-you">(you)</span>}
                  </td>
                  <td>
                    {isOwner && m.user_id !== me?.id ? (
                      <select value={m.role} onChange={e => handleRoleChange(m, e.target.value)}>
                        {Object.entries(ROLE_LABELS).map(([r, label]) => <option key={r} value={r}>{label}</option>)}
                      </select>
                    ) : (
                      <span className={`user-badge user-badge-${m.role === 'owner' ? 'admin' : m.role === 'readonly' ? 'readonly' : 'normal'}`}>
                        {ROLE_LABELS[m.role]}
                      </span>
                    )}
                  </td>
                  {isOwner && (
                    <td className="col-shrink">
                      {m.user_id !== me?.id && (
                        <button className="btn btn-danger btn-sm" onClick={() => handleRemove(m)}>Remove</button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {members?.length === 0 && <tr><td colSpan={3} className="empty">No members</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {!isOwner && (
        <p className="text-muted text-sm mt-4">Only garage owners can manage members.</p>
      )}
    </div>
  );
}
