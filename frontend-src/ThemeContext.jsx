import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const ThemeCtx = createContext(null);
const THEME_KEY = 'torqued.theme';
export const MODES = ['light', 'dark', 'system'];

const mql = () => window.matchMedia('(prefers-color-scheme: dark)');

// Resolution rule — kept behaviourally identical to the inline FOUC script in index.html.
function resolveTheme(mode) {
  if (mode === 'dark') return 'dark';
  if (mode === 'light') return 'light';
  return mql().matches ? 'dark' : 'light'; // 'system'
}

// The single DOM write. Same attribute the FOUC script sets, so React never has to "correct" it.
function applyTheme(resolved) {
  document.documentElement.setAttribute('data-theme', resolved);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', resolved === 'dark' ? '#1b1a17' : '#f5f4f0');
}

function readStoredMode() {
  const saved = localStorage.getItem(THEME_KEY);
  return MODES.includes(saved) ? saved : 'system';
}

export function ThemeProvider({ children }) {
  const [mode, setModeState] = useState(readStoredMode);
  const [resolved, setResolved] = useState(() => resolveTheme(readStoredMode()));

  // Recompute the resolved theme whenever the user changes mode.
  useEffect(() => {
    setResolved(resolveTheme(mode));
  }, [mode]);

  // Apply to the DOM on mount and whenever the resolved theme changes.
  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  // Live OS updates — only relevant while following the system. This is what delivers the
  // sundown/sunrise flip: when the OS auto-switches appearance, prefers-color-scheme fires.
  useEffect(() => {
    if (mode !== 'system') return undefined;
    const m = mql();
    const onChange = (e) => setResolved(e.matches ? 'dark' : 'light');
    m.addEventListener('change', onChange);
    return () => m.removeEventListener('change', onChange);
  }, [mode]);

  const setMode = useCallback((next) => {
    if (!MODES.includes(next)) return;
    setModeState(next);
    localStorage.setItem(THEME_KEY, next);
  }, []);

  // One-tap rotation for the nav button: light → dark → system → light.
  const cycle = useCallback(() => {
    setModeState((prev) => {
      const next = MODES[(MODES.indexOf(prev) + 1) % MODES.length];
      localStorage.setItem(THEME_KEY, next);
      return next;
    });
  }, []);

  return (
    <ThemeCtx.Provider value={{ mode, setMode, resolved, cycle, MODES }}>
      {children}
    </ThemeCtx.Provider>
  );
}

export const useTheme = () => useContext(ThemeCtx);
