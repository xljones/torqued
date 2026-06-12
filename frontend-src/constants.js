export const FormMode = Object.freeze({
  CREATE: 'create',
  EDIT: 'edit',
});

export const VehicleKind = Object.freeze({
  CAR: 'car',
  MOTORCYCLE: 'motorcycle',
});

export const KIND_LABELS = Object.freeze({
  car: 'Car',
  motorcycle: 'Motorcycle',
});

export const KIND_ICONS = Object.freeze({
  car: '🚗',
  motorcycle: '🏍️',
});

export const SERVICE_CATEGORIES = Object.freeze([
  'Service',
  'Oil change',
  'Tyres',
  'Brakes',
  'Chain & sprockets',
  'Inspection',
  'Repair',
  'Modification',
  'Detailing',
  'Other',
]);

export const ROLE_LABELS = Object.freeze({
  owner: 'Owner',
  member: 'Member',
  readonly: 'Read-only',
});

export const REMINDER_LABELS = Object.freeze({
  overdue: 'Overdue',
  due_soon: 'Due soon',
  upcoming: 'Upcoming',
});
