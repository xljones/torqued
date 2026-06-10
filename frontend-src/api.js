const BASE = '/api';

async function handle(res) {
  if (res.status === 204) return null;
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error(`Server error (${res.status}) — please try again`);
  }
  if (!res.ok) throw new Error(data.error ?? 'Request failed');
  return data;
}

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return handle(res);
}

async function upload(path, formData) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });
  return handle(res);
}

export const api = {
  // Auth
  getMe:            ()                         => req('GET',  '/auth/me'),
  login:            (username, password)       => req('POST', '/auth/login', { username, password }),
  logout:           ()                         => req('POST', '/auth/logout'),
  changePassword:   (current_password, new_password) => req('PUT', '/auth/password', { current_password, new_password }),

  // Vehicles
  getVehicles:        (archived)       => req('GET',    `/vehicles${archived ? '?archived=1' : ''}`),
  getVehicle:         (id)             => req('GET',    `/vehicles/${id}`),
  createVehicle:      (body)           => req('POST',   '/vehicles', body),
  updateVehicle:      (id, body)       => req('PUT',    `/vehicles/${id}`, body),
  deleteVehicle:      (id)             => req('DELETE', `/vehicles/${id}`),
  getVehicleHistory:  (id)             => req('GET',    `/vehicles/${id}/history`),
  revertVehicle:      (id, versionId)  => req('POST',   `/vehicles/${id}/revert/${versionId}`),
  replaceSpecs:       (id, specs)      => req('PUT',    `/vehicles/${id}/specs`, { specs }),
  getMileage:         (id)             => req('GET',    `/vehicles/${id}/mileage`),

  // Service logs
  getServices:        ()               => req('GET',    '/services'),
  getVehicleServices: (vehicleId)      => req('GET',    `/vehicles/${vehicleId}/services`),
  createService:      (vehicleId, body)=> req('POST',   `/vehicles/${vehicleId}/services`, body),
  getService:         (id)             => req('GET',    `/services/${id}`),
  updateService:      (id, body)       => req('PUT',    `/services/${id}`, body),
  deleteService:      (id)             => req('DELETE', `/services/${id}`),
  getServiceHistory:  (id)             => req('GET',    `/services/${id}/history`),
  revertService:      (id, versionId)  => req('POST',   `/services/${id}/revert/${versionId}`),
  getPerformers:      ()               => req('GET',    '/services/performers'),

  // Reminders
  getReminders:       ()               => req('GET',    '/reminders'),

  // Odometer logs
  getOdometerLogs:    (vehicleId)      => req('GET',    `/vehicles/${vehicleId}/odometer`),
  createOdometerLog:  (vehicleId, body)=> req('POST',   `/vehicles/${vehicleId}/odometer`, body),
  deleteOdometerLog:  (id)             => req('DELETE', `/odometer/${id}`),

  // Photos
  uploadPhoto: (vehicleId, file, { caption, serviceLogId } = {}) => {
    const fd = new FormData();
    fd.append('file', file);
    if (caption) fd.append('caption', caption);
    if (serviceLogId) fd.append('service_log_id', serviceLogId);
    return upload(`/vehicles/${vehicleId}/photos`, fd);
  },
  updatePhoto:  (id, caption) => req('PUT',    `/photos/${id}`, { caption }),
  deletePhoto:  (id)          => req('DELETE', `/photos/${id}`),
  photoUrl:     (id)          => `${BASE}/photos/${id}/file`,

  // Admin
  getPythonAnywhereStats: () => req('GET', '/admin/pythonanywhere'),

  // Users
  getUsers:    ()      => req('GET',    '/users'),
  createUser:  (body)  => req('POST',   '/users', body),
  deleteUser:  (id)    => req('DELETE', `/users/${id}`),

  // Utilities
  search:  (q) => req('GET', `/search?q=${encodeURIComponent(q)}`),
};
