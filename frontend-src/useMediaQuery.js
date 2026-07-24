import { useState, useEffect } from 'react';

/**
 * Track whether a CSS media query currently matches, updating live as the
 * viewport changes. Mirrors the matchMedia subscription used in ThemeContext.
 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = (e) => setMatches(e.matches);
    setMatches(m.matches); // resync in case the query changed between render and effect
    m.addEventListener('change', onChange);
    return () => m.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}
