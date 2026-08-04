import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { useToast } from './Toast.jsx';

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

// frame = the crop box's actual rendered {w, h} in px (measured at runtime since CSS caps
// it at 90vw, so it isn't always the same size as the .cover-frame rule's base 480x270).
function geometry(natural, zoom, frame) {
  const baseScale = Math.max(frame.w / natural.w, frame.h / natural.h);
  const totalScale = baseScale * zoom;
  return { dispW: natural.w * totalScale, dispH: natural.h * totalScale };
}

function clampPan(pan, zoom, natural, frame) {
  if (!natural || !frame) return pan;
  const { dispW, dispH } = geometry(natural, zoom, frame);
  return { x: clamp(pan.x, frame.w - dispW, 0), y: clamp(pan.y, frame.h - dispH, 0) };
}

/** Fixed 16:9 frame (sized by CSS); the photo pans/zooms underneath it (avatar-cropper style). */
function CoverFramer({ photo, onSave, onCancel }) {
  const frameRef = useRef(null);
  const imgRef = useRef(null);
  const dragRef = useRef(null);
  const initializedRef = useRef(false);
  const [frameSize, setFrameSize] = useState(null);
  const [natural, setNatural] = useState(null);
  const [zoom, setZoom] = useState(photo.cover_zoom ?? 1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!frameRef.current) return;
    const rect = frameRef.current.getBoundingClientRect();
    setFrameSize({ w: rect.width, h: rect.height });
  }, []);

  // Reconstruct the pan offset implied by the photo's saved focal point/zoom, once both
  // the frame's rendered size and the image's natural size are known (order isn't
  // guaranteed - image load and the frame-size effect above race independently).
  useEffect(() => {
    if (!natural || !frameSize || initializedRef.current) return;
    initializedRef.current = true;
    const z = photo.cover_zoom ?? 1;
    const focalX = photo.cover_focal_x ?? 0.5;
    const focalY = photo.cover_focal_y ?? 0.5;
    const { dispW, dispH } = geometry(natural, z, frameSize);
    setZoom(z);
    setPan(clampPan(
      { x: frameSize.w / 2 - focalX * dispW, y: frameSize.h / 2 - focalY * dispH },
      z, natural, frameSize,
    ));
  }, [natural, frameSize, photo]);

  const ready = !!(natural && frameSize);

  function handleImgLoad() {
    setNatural({ w: imgRef.current.naturalWidth, h: imgRef.current.naturalHeight });
  }

  function handleZoomChange(e) {
    const z = Number(e.target.value);
    setZoom(z);
    setPan(p => clampPan(p, z, natural, frameSize));
  }

  function handlePointerDown(e) {
    if (!ready) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
  }
  function handlePointerMove(e) {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPan(clampPan({ x: dragRef.current.panX + dx, y: dragRef.current.panY + dy }, zoom, natural, frameSize));
  }
  function handlePointerUp() {
    dragRef.current = null;
  }

  async function handleSave() {
    if (!ready) return;
    const { dispW, dispH } = geometry(natural, zoom, frameSize);
    const focal_x = clamp((-pan.x + frameSize.w / 2) / dispW, 0, 1);
    const focal_y = clamp((-pan.y + frameSize.h / 2) / dispH, 0, 1);
    setSaving(true);
    try {
      await onSave({ focal_x, focal_y, zoom });
    } finally {
      setSaving(false);
    }
  }

  const imgStyle = ready ? (() => {
    const { dispW, dispH } = geometry(natural, zoom, frameSize);
    return { width: dispW, height: dispH, transform: `translate(${pan.x}px, ${pan.y}px)` };
  })() : undefined;

  return (
    <div className="cover-framer">
      <div
        ref={frameRef}
        className="cover-frame"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {!ready && <div className="cover-frame-loading">Loading…</div>}
        <img
          ref={imgRef}
          src={api.photoUrl(photo.id)}
          alt="Frame the cover crop"
          onLoad={handleImgLoad}
          style={imgStyle}
          draggable={false}
          onDragStart={e => e.preventDefault()}
        />
      </div>
      <div className="cover-frame-controls">
        <input type="range" min="1" max="4" step="0.01" value={zoom} disabled={!ready} onChange={handleZoomChange} />
        <button className="btn btn-success btn-sm" disabled={!ready || saving} onClick={handleSave}>Save</button>
        <button className="btn btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

/**
 * Photo grid with upload, lightbox, caption editing, cover framing, and delete.
 * Pass serviceLogId to scope uploads to a service log; ro disables editing.
 */
export default function PhotoGallery({ photos, vehicleId, serviceLogId, coverPhotoId, ro, onChange }) {
  const toast = useToast();
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [openIndex, setOpenIndex] = useState(null);
  const [editingCaption, setEditingCaption] = useState(false);
  const [caption, setCaption] = useState('');
  const [framingMode, setFramingMode] = useState(false);
  const [overrides, setOverrides] = useState(null);

  const basePhoto = openIndex != null ? photos[openIndex] : null;
  const openPhoto = basePhoto ? { ...basePhoto, ...overrides } : null;

  function openAt(i) {
    setOpenIndex(i);
    setEditingCaption(false);
    setFramingMode(false);
    setOverrides(null);
  }
  function showPrev() {
    setOpenIndex(i => (i - 1 + photos.length) % photos.length);
    setEditingCaption(false);
    setFramingMode(false);
    setOverrides(null);
  }
  function showNext() {
    setOpenIndex(i => (i + 1) % photos.length);
    setEditingCaption(false);
    setFramingMode(false);
    setOverrides(null);
  }

  useEffect(() => {
    if (openIndex == null) return;
    function onKeyDown(e) {
      if (e.key === 'Escape') {
        if (framingMode) { setFramingMode(false); return; }
        if (editingCaption) { setEditingCaption(false); return; }
        setOpenIndex(null);
        return;
      }
      if (framingMode || editingCaption) return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); showPrev(); }
      if (e.key === 'ArrowRight') { e.preventDefault(); showNext(); }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openIndex, framingMode, editingCaption, photos.length]);

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
    setOpenIndex(null);
    toast('Photo deleted');
    onChange?.();
  }

  async function handleSaveCaption(photo) {
    const updated = await api.updatePhoto(photo.id, caption.trim() || null);
    setOverrides(o => ({ ...o, caption: updated.caption }));
    setEditingCaption(false);
    toast('Caption saved');
    onChange?.();
  }

  async function handleSetCover(photo) {
    await api.setCover(photo.id);
    toast('Cover photo set');
    setOpenIndex(null);
    onChange?.();
  }

  async function handleSaveCoverFrame(photo, frame) {
    const updated = await api.updateCoverFrame(photo.id, frame);
    setOverrides(o => ({
      ...o,
      cover_focal_x: updated.cover_focal_x,
      cover_focal_y: updated.cover_focal_y,
      cover_zoom: updated.cover_zoom,
    }));
    setFramingMode(false);
    toast('Cover framing saved');
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
            {photos.map((p, i) => (
              <button key={p.id} type="button" className="photo-thumb" onClick={() => openAt(i)}>
                <img src={api.photoUrl(p.id)} alt={p.caption || p.original_name || 'Vehicle photo'} loading="lazy" />
                {p.id === coverPhotoId && (
                  <span className="photo-thumb-cover" title="Cover photo" aria-label="Cover photo">★</span>
                )}
                {(p.caption || p.service_title) && (
                  <span className="photo-thumb-caption">{p.caption || p.service_title}</span>
                )}
              </button>
            ))}
          </div>
        )}

      {openPhoto && (
        <div className="lightbox" onClick={e => { if (e.target === e.currentTarget) setOpenIndex(null); }}>
          {framingMode ? (
            <CoverFramer
              photo={openPhoto}
              onCancel={() => setFramingMode(false)}
              onSave={frame => handleSaveCoverFrame(openPhoto, frame)}
            />
          ) : (
            <>
              <div className="lightbox-counter">{openIndex + 1} / {photos.length}</div>
              <div className="lightbox-stage">
                {photos.length > 1 && (
                  <button type="button" className="lightbox-nav lightbox-nav--prev" aria-label="Previous photo" onClick={showPrev}>‹</button>
                )}
                <img src={api.photoUrl(openPhoto.id)} alt={openPhoto.caption || 'Vehicle photo'} />
                {photos.length > 1 && (
                  <button type="button" className="lightbox-nav lightbox-nav--next" aria-label="Next photo" onClick={showNext}>›</button>
                )}
              </div>
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
                    {!ro && (
                      openPhoto.id === coverPhotoId ? (
                        <button className="btn btn-secondary btn-sm" onClick={() => setFramingMode(true)}>
                          Edit cover <span className="cover-star">★</span>
                        </button>
                      ) : (
                        <button className="btn btn-secondary btn-sm" onClick={() => handleSetCover(openPhoto)}>
                          Set as cover
                        </button>
                      )
                    )}
                    {!ro && <button className="btn btn-danger btn-sm" onClick={() => handleDelete(openPhoto)}>Delete</button>}
                    <button className="btn btn-secondary btn-sm" onClick={() => setOpenIndex(null)}>Close</button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
