import { useRef, useState } from 'react';
import { api } from '../api.js';
import { useAuth } from '../AuthContext.jsx';
import { useToast } from './Toast.jsx';

/**
 * Photo grid with upload, lightbox, caption editing, and delete.
 * Pass serviceLogId to scope uploads to a service log.
 */
export default function PhotoGallery({ photos, vehicleId, serviceLogId, onChange }) {
  const { user } = useAuth();
  const ro = user?.is_readonly;
  const toast = useToast();
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [openPhoto, setOpenPhoto] = useState(null);
  const [editingCaption, setEditingCaption] = useState(false);
  const [caption, setCaption] = useState('');

  async function handleFiles(e) {
    const files = [...e.target.files];
    e.target.value = '';
    if (!files.length) return;
    setUploading(true);
    try {
      for (const file of files) {
        await api.uploadPhoto(vehicleId, file, { serviceLogId });
      }
      toast(`${files.length} photo${files.length !== 1 ? 's' : ''} uploaded`);
      onChange?.();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(photo) {
    if (!confirm('Delete this photo?')) return;
    await api.deletePhoto(photo.id);
    setOpenPhoto(null);
    toast('Photo deleted');
    onChange?.();
  }

  async function handleSaveCaption(photo) {
    const updated = await api.updatePhoto(photo.id, caption.trim() || null);
    setOpenPhoto(p => ({ ...p, caption: updated.caption }));
    setEditingCaption(false);
    toast('Caption saved');
    onChange?.();
  }

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Photos ({photos?.length ?? 0})</h2>
        {!ro && (
          <>
            <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={handleFiles} />
            <button className="btn btn-primary btn-sm" disabled={uploading} onClick={() => fileRef.current?.click()}>
              {uploading ? 'Uploading…' : '+ Add photos'}
            </button>
          </>
        )}
      </div>

      {(photos?.length ?? 0) === 0
        ? <div className="card"><p className="card-message">No photos yet</p></div>
        : (
          <div className="photo-grid">
            {photos.map(p => (
              <button key={p.id} type="button" className="photo-thumb" onClick={() => { setOpenPhoto(p); setEditingCaption(false); }}>
                <img src={api.photoUrl(p.id)} alt={p.caption || p.original_name || 'Vehicle photo'} loading="lazy" />
                {(p.caption || p.service_title) && (
                  <span className="photo-thumb-caption">{p.caption || p.service_title}</span>
                )}
              </button>
            ))}
          </div>
        )}

      {openPhoto && (
        <div className="lightbox" onClick={e => { if (e.target === e.currentTarget) setOpenPhoto(null); }}>
          <img src={api.photoUrl(openPhoto.id)} alt={openPhoto.caption || 'Vehicle photo'} />
          <div className="lightbox-bar">
            {editingCaption ? (
              <>
                <input
                  className="lightbox-caption-input"
                  value={caption}
                  onChange={e => setCaption(e.target.value)}
                  placeholder="Caption…"
                  autoFocus
                />
                <button className="btn btn-success btn-sm" onClick={() => handleSaveCaption(openPhoto)}>Save</button>
                <button className="btn btn-secondary btn-sm" onClick={() => setEditingCaption(false)}>Cancel</button>
              </>
            ) : (
              <>
                <span>{openPhoto.caption || openPhoto.original_name}</span>
                {!ro && (
                  <button className="btn btn-secondary btn-sm" onClick={() => { setCaption(openPhoto.caption ?? ''); setEditingCaption(true); }}>
                    Edit caption
                  </button>
                )}
                {!ro && <button className="btn btn-danger btn-sm" onClick={() => handleDelete(openPhoto)}>Delete</button>}
                <button className="btn btn-secondary btn-sm" onClick={() => setOpenPhoto(null)}>Close</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
