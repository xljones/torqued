import { useState, useRef, useEffect } from 'react';

export default function ExportDropdown({ label, disabled, options }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [open]);

  return (
    <div className="export-dropdown" ref={ref}>
      <button
        className="btn btn-secondary"
        disabled={disabled}
        onClick={() => setOpen(v => !v)}
      >
        {label}
        <span className="export-dropdown-chevron">▾</span>
      </button>
      {open && (
        <div className="export-dropdown-menu">
          {options.map((opt, i) => {
            if (opt.divider) return <hr key={i} className="export-dropdown-divider" />;
            if (opt.type === 'checkbox') return (
              <label key={opt.label} className="export-dropdown-checkbox">
                <input type="checkbox" checked={opt.checked} onChange={opt.onChange} />
                {opt.label}
              </label>
            );
            return (
              <button
                key={opt.label}
                className="export-dropdown-item"
                onClick={() => { opt.onClick(); setOpen(false); }}
              >
                {opt.label}
                {opt.note && <span className="export-dropdown-note">{opt.note}</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
