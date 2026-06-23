import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import MotField from './MotField';
import { titleCase } from '../units.js';

// The backend resolves the effective value and its source; MotField just displays them.
const props = (value, fromBaseline, extra = {}) => ({
  label: 'Make', value, fromBaseline, ...extra,
});

describe('MotField', () => {
  it('shows the DVSA baseline with a badge when there is no override', () => {
    render(<MotField {...props('VOLKSWAGEN', true)} />);
    expect(screen.getByText('VOLKSWAGEN')).toBeInTheDocument();
    expect(screen.getByText('DVSA')).toBeInTheDocument();
  });

  it('shows the user override without a badge when an override is set', () => {
    render(<MotField {...props('Custom', false)} />);
    expect(screen.getByText('Custom')).toBeInTheDocument();
    expect(screen.queryByText('DVSA')).not.toBeInTheDocument();
  });

  it('does not show a DVSA badge when the value came from the override', () => {
    render(<MotField {...props('VOLKSWAGEN', false)} />);
    expect(screen.queryByText('DVSA')).not.toBeInTheDocument();
  });

  it('falls back to a dash when there is no value', () => {
    render(<MotField {...props(null, true)} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('applies a custom renderer to the effective value', () => {
    render(
      <MotField {...props('1896', true, {
        label: 'Engine size', render: v => `${v} cc`,
      })} />,
    );
    expect(screen.getByText('1896 cc')).toBeInTheDocument();
  });

  it('applies the format prop to a DVSA baseline value', () => {
    render(<MotField {...props('VOLKSWAGEN', true, { format: titleCase })} />);
    expect(screen.getByText('Volkswagen')).toBeInTheDocument();
    expect(screen.getByText('DVSA')).toBeInTheDocument();
  });

  it('never applies the format prop to a user override', () => {
    render(<MotField {...props('McLaren', false, { format: titleCase })} />);
    expect(screen.getByText('McLaren')).toBeInTheDocument();
    expect(screen.queryByText('Mclaren')).not.toBeInTheDocument();
  });
});
