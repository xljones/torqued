import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import RelativeTime from './RelativeTime';

const NOW = new Date('2026-06-12T12:00:00Z');

describe('RelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders an em dash when no value is given', () => {
    const { container } = render(<RelativeTime value={null} />);
    expect(container.textContent).toBe('—');
  });

  it('renders a future date in human-friendly units, not raw seconds', () => {
    // ~36 days ahead (a typical MOT expiry) — regression for "in 3,043,741 seconds"
    const { container } = render(<RelativeTime value="2026-07-18" />);
    expect(container.textContent).not.toMatch(/second/);
    expect(container.textContent).toMatch(/next month/);
  });

  it('renders a near-future datetime in hours', () => {
    const { container } = render(<RelativeTime value="2026-06-12T17:00:00Z" />);
    expect(container.textContent).toMatch(/in \d+ hours?/);
  });

  it('still renders past dates in the past tense', () => {
    const { container } = render(<RelativeTime value="2026-05-01T12:00:00Z" />);
    expect(container.textContent).toMatch(/last month/);
  });

  it('renders a several-days-past date as "N days ago"', () => {
    const { container } = render(<RelativeTime value="2026-06-08T12:00:00Z" />);
    expect(container.textContent).toMatch(/\d+ days ago/);
  });

  it('exposes the absolute UTC time as a tooltip', () => {
    const { container } = render(<RelativeTime value="2026-07-18" />);
    expect(container.querySelector('span').getAttribute('data-tooltip')).toBe(
      '2026-07-18 00:00:00 UTC',
    );
  });
});
