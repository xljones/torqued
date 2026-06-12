import { useState, useEffect, useRef } from 'react';
import { api } from '../api.js';

const CODE_RE = /^[PBCUpbcu][0-9][0-9A-Fa-f]{3}$/;

export default function FaultCodeInput({ codes, onChange }) {
  const [input, setInput] = useState('');
  const [suggestions, setSuggestions] = useState(null);
  const [focusIdx, setFocusIdx] = useState(-1);
  const wrapRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const q = input.trim();
    if (!q || q.length < 2) { setSuggestions(null); return; }
    const timer = setTimeout(() => {
      if (CODE_RE.test(q)) {
        api.lookupCode(q).then(r => setSuggestions(r ? [r] : [])).catch(() => setSuggestions(null));
      } else {
        api.searchCodes(q).then(m => setSuggestions(m ?? [])).catch(() => setSuggestions(null));
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setSuggestions(null);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function addCode(code) {
    const upper = code.trim().toUpperCase();
    if (upper && !codes.includes(upper)) onChange([...codes, upper]);
    setInput('');
    setSuggestions(null);
    setFocusIdx(-1);
    inputRef.current?.focus();
  }

  function removeCode(code) {
    onChange(codes.filter(c => c !== code));
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (focusIdx >= 0 && suggestions?.[focusIdx]) {
        addCode(suggestions[focusIdx].code);
      } else if (input.trim()) {
        addCode(input);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (suggestions?.length) setFocusIdx(i => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (suggestions?.length) setFocusIdx(i => Math.max(i - 1, 0));
    } else if (e.key === 'Escape') {
      setSuggestions(null);
      setFocusIdx(-1);
    } else if (e.key === 'Backspace' && !input && codes.length) {
      removeCode(codes[codes.length - 1]);
    }
  }

  return (
    <div ref={wrapRef} className="fault-code-input">
      <div className="fault-code-tags">
        {codes.map(c => (
          <span key={c} className="fault-code-tag">
            <span className="dtc-code dtc-code-sm">{c}</span>
            <button type="button" className="fault-code-remove" onClick={() => removeCode(c)} aria-label={`Remove ${c}`}>&times;</button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => { setInput(e.target.value); setFocusIdx(-1); }}
          onKeyDown={handleKeyDown}
          placeholder={codes.length ? '' : 'P0016, U0100…'}
          className="fault-code-text"
          autoComplete="off"
        />
      </div>
      {suggestions && suggestions.length > 0 && (
        <ul className="fault-code-suggest">
          {suggestions.map((s, i) => (
            <li
              key={s.code}
              className={`fault-code-option${i === focusIdx ? ' is-focused' : ''}${codes.includes(s.code) ? ' is-added' : ''}`}
              onMouseDown={() => addCode(s.code)}
            >
              <span className="dtc-code dtc-code-sm">{s.code}</span>
              <span className="fault-code-desc">{s.description ?? 'Manufacturer-specific code'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
