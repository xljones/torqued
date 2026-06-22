import { createContext, useContext, useState, useCallback } from 'react';
import { titleCase } from './units.js';

const DisplayPrefsCtx = createContext(null);
const TITLECASE_KEY = 'torqued.titleCaseNames';

// Default ON: vehicle identity data (make/model/colour/fuel) arrives from the DVSA in all-caps,
// so title case is the nicer default. A stored 'false' opts out; a missing value falls back to on.
function readStoredTitleCase() {
  const saved = localStorage.getItem(TITLECASE_KEY);
  return saved == null ? true : saved === 'true';
}

export function DisplayPrefsProvider({ children }) {
  const [titleCaseNames, setTitleCaseNamesState] = useState(readStoredTitleCase);

  const setTitleCaseNames = useCallback((next) => {
    const val = !!next;
    setTitleCaseNamesState(val);
    localStorage.setItem(TITLECASE_KEY, String(val));
  }, []);

  // Tidy a DVSA-sourced value for display when the setting is on, otherwise pass it through.
  // Call sites only ever feed it baseline (DVSA) values — never the user's own overrides.
  const formatName = useCallback(
    (str) => (titleCaseNames ? titleCase(str) : str),
    [titleCaseNames],
  );

  return (
    <DisplayPrefsCtx.Provider value={{ titleCaseNames, setTitleCaseNames, formatName }}>
      {children}
    </DisplayPrefsCtx.Provider>
  );
}

// Null-safe: components (and their unit tests) rendered without the provider degrade to a
// passthrough rather than crashing.
export function useDisplayPrefs() {
  return useContext(DisplayPrefsCtx) ?? { titleCaseNames: false, formatName: (s) => s };
}
