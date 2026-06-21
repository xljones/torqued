import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ThemeProvider, useTheme } from './ThemeContext.jsx';

// Controllable prefers-color-scheme mock. `darkMatches` is the current OS preference;
// `setSystemDark` flips it and notifies registered listeners (what an OS sundown does).
let darkMatches;
let changeListeners;

function setSystemDark(matches) {
  darkMatches = matches;
  changeListeners.forEach((cb) => cb({ matches }));
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  darkMatches = false;
  changeListeners = new Set();
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    get matches() { return darkMatches; },
    media: query,
    addEventListener: (_evt, cb) => changeListeners.add(cb),
    removeEventListener: (_evt, cb) => changeListeners.delete(cb),
    dispatchEvent: () => false,
  }));
});

function Probe() {
  const { mode, resolved, setMode, cycle } = useTheme();
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="resolved">{resolved}</span>
      <button onClick={() => setMode('light')}>set-light</button>
      <button onClick={() => setMode('dark')}>set-dark</button>
      <button onClick={() => setMode('system')}>set-system</button>
      <button onClick={cycle}>cycle</button>
    </div>
  );
}

const renderTheme = () => render(<ThemeProvider><Probe /></ThemeProvider>);
const docTheme = () => document.documentElement.getAttribute('data-theme');

describe('ThemeContext', () => {
  it('defaults to system and resolves via prefers-color-scheme', () => {
    renderTheme();
    expect(screen.getByTestId('mode')).toHaveTextContent('system');
    expect(screen.getByTestId('resolved')).toHaveTextContent('light');
    expect(docTheme()).toBe('light');
  });

  it('resolves system to dark when the OS prefers dark', () => {
    darkMatches = true;
    renderTheme();
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark');
    expect(docTheme()).toBe('dark');
  });

  it('reads a persisted mode from localStorage', () => {
    localStorage.setItem('torqued.theme', 'dark');
    renderTheme();
    expect(screen.getByTestId('mode')).toHaveTextContent('dark');
    expect(docTheme()).toBe('dark');
  });

  it('setMode persists the choice and applies it to the DOM', () => {
    renderTheme();
    fireEvent.click(screen.getByText('set-dark'));
    expect(screen.getByTestId('mode')).toHaveTextContent('dark');
    expect(localStorage.getItem('torqued.theme')).toBe('dark');
    expect(docTheme()).toBe('dark');

    fireEvent.click(screen.getByText('set-light'));
    expect(docTheme()).toBe('light');
    expect(localStorage.getItem('torqued.theme')).toBe('light');
  });

  it('cycle advances light → dark → system → light', () => {
    localStorage.setItem('torqued.theme', 'light');
    renderTheme();
    expect(screen.getByTestId('mode')).toHaveTextContent('light');

    fireEvent.click(screen.getByText('cycle'));
    expect(screen.getByTestId('mode')).toHaveTextContent('dark');
    fireEvent.click(screen.getByText('cycle'));
    expect(screen.getByTestId('mode')).toHaveTextContent('system');
    fireEvent.click(screen.getByText('cycle'));
    expect(screen.getByTestId('mode')).toHaveTextContent('light');
  });

  it('updates live when the OS flips while following the system', () => {
    renderTheme(); // mode = system, OS = light
    expect(docTheme()).toBe('light');

    act(() => setSystemDark(true)); // OS auto-switches at sundown
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark');
    expect(docTheme()).toBe('dark');
  });

  it('stops following the OS once a fixed mode is chosen', () => {
    renderTheme();
    fireEvent.click(screen.getByText('set-light'));
    expect(docTheme()).toBe('light');

    act(() => setSystemDark(true)); // OS flips, but we are pinned to light
    expect(screen.getByTestId('resolved')).toHaveTextContent('light');
    expect(docTheme()).toBe('light');
  });
});
