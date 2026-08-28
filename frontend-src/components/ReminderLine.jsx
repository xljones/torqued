import { REMINDER_LABELS } from '../constants.js';
import { fmtDistance } from '../units.js';
import { overdueBy } from '../reminders.js';

/**
 * The innards of one reminder row — title, sub-line, status badge — shared by the dashboard
 * (where reminders nest under their vehicle) and the vehicle detail page.
 *
 * Spans rather than divs, so it stays valid inside the dashboard's <button> rows; the
 * classes are already flex, so it renders identically either way. `unit` defaults to the
 * reminder's own vehicle_odometer_unit, which every stream (service, schedule, MOT, tax)
 * sets.
 */
export default function ReminderLine({ reminder: r, unit = r.vehicle_odometer_unit }) {
  const over = overdueBy(r, unit);
  return (
    <>
      <span className="reminder-main">
        <span className="reminder-title">{r.category || r.title}</span>
        <span className="reminder-sub">
          {r.type === 'mot'
            ? `${r.status === 'overdue' ? 'Expired' : 'Expires'} ${r.next_due_date}`
            : r.type === 'tax'
            ? `${r.status === 'overdue' ? 'Expired' : 'Due'} ${r.next_due_date}`
            : <>
                After “{r.title}” ({r.date})
                {r.next_due_date && ` — due ${r.next_due_date}`}
                {r.next_due_km != null && ` — due at ${fmtDistance(r.next_due_km, unit)}`}
                {r.km_remaining != null && r.km_remaining > 0 && ` (${fmtDistance(r.km_remaining, unit)} to go)`}
              </>}
          {over && <span className="reminder-overdue"> — {over}</span>}
        </span>
      </span>
      <span className={`badge badge-${r.status}`}>{REMINDER_LABELS[r.status]}</span>
    </>
  );
}
