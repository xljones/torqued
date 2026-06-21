import '@testing-library/jest-dom';

// jsdom does not implement matchMedia; provide a minimal default so components that read
// prefers-color-scheme (ThemeProvider) can mount. Tests needing control over the query
// result install their own mock (see ThemeContext.test.jsx).
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}
