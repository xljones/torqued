import { useState, useEffect } from 'react';

function toUtcDate(value) {
  // Date-only values (YYYY-MM-DD) → treat as UTC midnight
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return new Date(value + 'T00:00:00Z');
  // SQLite stores UTC datetimes without trailing Z — normalise before parsing
  return new Date(value.endsWith('Z') ? value : value + 'Z');
}

function relativeTime(date) {
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.round(diffMs / 1000);
  const fmt = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  if (Math.abs(diffSec) < 60)    return fmt.format(-diffSec, 'second');
  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60)    return fmt.format(-diffMin, 'minute');
  const diffHour = Math.round(diffMin / 60);
  if (Math.abs(diffHour) < 24)   return fmt.format(-diffHour, 'hour');
  const diffDay = Math.round(diffHour / 24);
  if (Math.abs(diffDay) < 7)     return fmt.format(-diffDay, 'day');
  const diffWeek = Math.round(diffDay / 7);
  if (Math.abs(diffWeek) < 5)    return fmt.format(-diffWeek, 'week');
  const diffMonth = Math.round(diffDay / 30.5);
  if (Math.abs(diffMonth) < 12)  return fmt.format(-diffMonth, 'month');
  return fmt.format(-Math.round(diffMonth / 12), 'year');
}

function absoluteTime(date) {
  return date.toISOString().replace('T', ' ').replace(/\.\d+Z$/, '') + ' UTC';
}

export default function RelativeTime({ value }) {
  const [, tick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => tick(n => n + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  if (!value) return '—';

  const date = toUtcDate(value);
  return (
    <span data-tooltip={absoluteTime(date)} style={{ display: 'inline-block', position: 'relative', cursor: 'default' }}>
      {relativeTime(date)}
    </span>
  );
}
