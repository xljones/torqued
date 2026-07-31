import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import MotField from './MotField';
import { titleCase } from '../units.js';

const props = (vehicle, baseline, extra = {}) => ({
  label: 'Make', fieldKey: 'make', vehicle, baseline, ...extra,
});

describe('MotField', () => {
  it('shows the DVSA baseline with a badge when there is no override', () => {
    render(<MotField {...props({ make: null }, { make: 'VOLKSWAGEN' })} />);
    expect(screen.getByText('VOLKSWAGEN')).toBeInTheDocument();
    expect(screen.getByText('DVSA')).toBeInTheDocument();
  });

  it('shows the user override without a badge when an override is set', () => {
    render(<MotField {...props({ make: 'Custom' }, { make: 'VOLKSWAGEN' })} />);
    expect(screen.getByText('Custom')).toBeInTheDocument();
    expect(screen.queryByText('DVSA')).not.toBeInTheDocument();
  });

  it('does not show a DVSA badge when the override equals the baseline', () => {
    render(<MotField {...props({ make: 'VOLKSWAGEN' }, { make: 'VOLKSWAGEN' })} />);
    expect(screen.queryByText('DVSA')).not.toBeInTheDocument();
  });

  it('falls back to a dash when neither override nor baseline is set', () => {
    render(<MotField {...props({ make: null }, null)} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('applies a custom renderer to the effective value', () => {
    render(
      <MotField {...props({ engine_size: null }, { engine_size: '1896' }, {
        label: 'Engine size', fieldKey: 'engine_size', render: v => `${v} cc`,
      })} />,
    );
    expect(screen.getByText('1896 cc')).toBeInTheDocument();
  });

  it('applies the format prop to a DVSA baseline value', () => {
    render(<MotField {...props({ make: null }, { make: 'VOLKSWAGEN' }, { format: titleCase })} />);
    expect(screen.getByText('Volkswagen')).toBeInTheDocument();
    expect(screen.getByText('DVSA')).toBeInTheDocument();
  });

  it('never applies the format prop to a user override', () => {
    render(<MotField {...props({ make: 'McLaren' }, { make: 'MCLAREN' }, { format: titleCase })} />);
    expect(screen.getByText('McLaren')).toBeInTheDocument();
    expect(screen.queryByText('Mclaren')).not.toBeInTheDocument();
  });

  it('tags both sources when field_sources says DVSA and DVLA agree', () => {
    render(<MotField {...props({ make: null }, { make: 'FORD' }, {
      vesBaseline: { make: 'FORD' }, fieldSources: { make: ['dvsa', 'dvla'] },
    })} />);
    expect(screen.getByText('DVSA')).toBeInTheDocument();
    expect(screen.getByText('DVLA')).toBeInTheDocument();
  });

  it('falls back to the DVLA value with a DVLA tag when DVSA lacks it', () => {
    render(<MotField {...props({ co2_emissions: undefined }, null, {
      label: 'CO₂', fieldKey: 'co2_emissions',
      vesBaseline: { co2_emissions: '204 g/km' }, fieldSources: { co2_emissions: ['dvla'] },
    })} />);
    expect(screen.getByText('204 g/km')).toBeInTheDocument();
    expect(screen.getByText('DVLA')).toBeInTheDocument();
    expect(screen.queryByText('DVSA')).not.toBeInTheDocument();
  });

  it('shows no source tag when an override overrides both baselines', () => {
    render(<MotField {...props({ make: 'Custom' }, { make: 'FORD' }, {
      vesBaseline: { make: 'FORD' }, fieldSources: { make: ['dvsa', 'dvla'] },
    })} />);
    expect(screen.queryByText('DVSA')).not.toBeInTheDocument();
    expect(screen.queryByText('DVLA')).not.toBeInTheDocument();
  });
});
