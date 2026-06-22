import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { DisplayPrefsProvider, useDisplayPrefs } from './DisplayPrefsContext.jsx';

beforeEach(() => {
  localStorage.clear();
});

function Probe() {
  const { titleCaseNames, setTitleCaseNames, formatName } = useDisplayPrefs();
  return (
    <div>
      <span data-testid="flag">{String(titleCaseNames)}</span>
      <span data-testid="sample">{formatName('VOLKSWAGEN')}</span>
      <button onClick={() => setTitleCaseNames(true)}>on</button>
      <button onClick={() => setTitleCaseNames(false)}>off</button>
    </div>
  );
}

const renderProbe = () => render(<DisplayPrefsProvider><Probe /></DisplayPrefsProvider>);

describe('DisplayPrefsContext', () => {
  it('defaults to on and title-cases via formatName', () => {
    renderProbe();
    expect(screen.getByTestId('flag')).toHaveTextContent('true');
    expect(screen.getByTestId('sample')).toHaveTextContent('Volkswagen');
  });

  it('reads a persisted opt-out from localStorage', () => {
    localStorage.setItem('torqued.titleCaseNames', 'false');
    renderProbe();
    expect(screen.getByTestId('flag')).toHaveTextContent('false');
    expect(screen.getByTestId('sample')).toHaveTextContent('VOLKSWAGEN');
  });

  it('toggling persists the choice and updates formatName', () => {
    renderProbe();
    fireEvent.click(screen.getByText('off'));
    expect(screen.getByTestId('flag')).toHaveTextContent('false');
    expect(screen.getByTestId('sample')).toHaveTextContent('VOLKSWAGEN');
    expect(localStorage.getItem('torqued.titleCaseNames')).toBe('false');

    fireEvent.click(screen.getByText('on'));
    expect(screen.getByTestId('sample')).toHaveTextContent('Volkswagen');
    expect(localStorage.getItem('torqued.titleCaseNames')).toBe('true');
  });

  it('falls back to a passthrough when used without a provider', () => {
    render(<Probe />);
    expect(screen.getByTestId('flag')).toHaveTextContent('false');
    expect(screen.getByTestId('sample')).toHaveTextContent('VOLKSWAGEN');
  });
});
