import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import RegPlate from './RegPlate';

describe('RegPlate', () => {
  it('renders the plate in uppercase regardless of stored case', () => {
    render(<RegPlate reg="lb21 xyz" />);
    expect(screen.getByText('LB21 XYZ')).toBeInTheDocument();
  });

  it('leaves an already-uppercase plate unchanged', () => {
    render(<RegPlate reg="AB12 CDE" />);
    expect(screen.getByText('AB12 CDE')).toBeInTheDocument();
  });

  it('inserts canonical UK spacing for an unspaced plate', () => {
    render(<RegPlate reg="ab12cde" />);
    expect(screen.getByText('AB12 CDE')).toBeInTheDocument();
  });

  it('renders nothing when empty', () => {
    const { container } = render(<RegPlate reg="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
