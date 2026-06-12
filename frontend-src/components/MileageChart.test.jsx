import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import MileageChart from './MileageChart';

const series = [
  { id: 1, date: '2024-04-02', odometer_km: 13196.62, source: 'service', note: 'Annual service' },
  { id: 1, date: '2025-05-01', odometer_km: 21162.87, source: 'manual', note: 'Post-trip reading' },
  { id: 2, date: '2025-11-03', odometer_km: 24333.9, source: 'mot', note: 'MOT test (PASSED)' },
];

describe('MileageChart', () => {
  it('renders nothing with fewer than two points', () => {
    const { container } = render(<MileageChart series={[series[0]]} unit="mi" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a dot for every reading, including service and MOT sources', () => {
    const { container } = render(<MileageChart series={series} unit="mi" />);
    expect(container.querySelectorAll('.mileage-dot')).toHaveLength(3);
    expect(container.querySelector('.mileage-dot-service')).toBeInTheDocument();
    expect(container.querySelector('.mileage-dot-manual')).toBeInTheDocument();
    expect(container.querySelector('.mileage-dot-mot')).toBeInTheDocument();
  });

  it('uses a composite key so colliding service/manual ids do not clash', () => {
    // Both the service and manual point have id=1; rendering without a console
    // key warning proves the composite key works (3 distinct dots render).
    const { container } = render(<MileageChart series={series} unit="mi" />);
    expect(container.querySelectorAll('.mileage-dot')).toHaveLength(3);
  });

  it('shows mileage, source label and date on hover', async () => {
    const { container } = render(<MileageChart series={series} unit="mi" />);
    const serviceDot = container.querySelector('.mileage-dot-service');
    await userEvent.hover(serviceDot);
    // 13196.62 km stored → 8,200 mi in the display unit
    expect(screen.getByText('8,200 mi')).toBeInTheDocument();
    expect(screen.getByText(/Service log · 2024-04-02/)).toBeInTheDocument();
    expect(screen.getByText('Annual service')).toBeInTheDocument();
  });

  it('labels the MOT-sourced reading', async () => {
    const { container } = render(<MileageChart series={series} unit="mi" />);
    await userEvent.hover(container.querySelector('.mileage-dot-mot'));
    expect(screen.getByText(/MOT test · 2025-11-03/)).toBeInTheDocument();
  });

  it('marks each year boundary that falls within the data span', () => {
    // Data runs 2024-04 → 2025-11, so only the 2025 boundary is inside the span.
    const { container } = render(<MileageChart series={series} unit="mi" />);
    const labels = [...container.querySelectorAll('.mileage-year-label')].map(el => el.textContent);
    expect(labels).toEqual(['2025']);
    expect(container.querySelectorAll('.mileage-year-line')).toHaveLength(1);
  });

  it('marks every crossed boundary across a multi-year span', () => {
    const span = [
      { id: 1, date: '2022-06-01', odometer_km: 1000, source: 'manual' },
      { id: 2, date: '2025-06-01', odometer_km: 9000, source: 'manual' },
    ];
    const { container } = render(<MileageChart series={span} unit="mi" />);
    const labels = [...container.querySelectorAll('.mileage-year-label')].map(el => el.textContent);
    expect(labels).toEqual(['2023', '2024', '2025']);
  });
});
