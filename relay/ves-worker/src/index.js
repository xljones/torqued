// Torqued DVLA VES relay (Cloudflare Worker).
//
// GET /ves/<REG>  ->  the full VES snapshot fetch_ves() returns:
//   { registration, tax_status, tax_due_date, mot_status, mot_expiry_date,
//     make, colour, date_of_first_registration, year_of_manufacture, cylinder_capacity,
//     co2_emissions, fuel_type, euro_status, real_driving_emissions, export_marker,
//     type_approval, wheelplan, revenue_weight, date_of_last_v5c }
//
// A faithful port of the 4-request gov.uk vehicle-enquiry wizard in
// backend-src/torqued/ves.py. It exists so a host whose outbound whitelist blocks
// vehicleenquiry.service.gov.uk (e.g. a free PythonAnywhere account) can still fetch the
// VES record: Cloudflare has no egress whitelist, and *.workers.dev IS on PythonAnywhere's.
//
// ves.py stays the reference implementation (local dev, the test suite, and the debug
// runbook all exercise it); this mirrors its selectors. When gov.uk drifts, fix ves.py
// first, then mirror the selector change here. See ../../docs/VES_API.md.

const BASE = 'https://vehicleenquiry.service.gov.uk';
const SAVE = '/vehicle-enquiry/save?locale=en';
// The default fetch UA is rejected by the service's WAF; look like a browser (matches _UA).
const UA = 'Mozilla/5.0 (compatible; Torqued/1.0; +https://github.com/xljones/torqued)';
const MONTHS = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
  july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
};
// HTML void elements — no end tag, so they never change nesting depth (mirrors ves._VOID).
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
  'meta', 'param', 'source', 'track', 'wbr']);
// snapshot key -> the result page's summary-row element id (mirrors ves._PROFILE_FIELDS).
const PROFILE_FIELDS = {
  make: 'make',
  colour: 'colour',
  date_of_first_registration: 'date_of_first_registration',
  year_of_manufacture: 'year_of_manufacture',
  cylinder_capacity: 'engine_capacity',
  co2_emissions: 'co2_emissions',
  fuel_type: 'fuel_type',
  euro_status: 'euro_status',
  real_driving_emissions: 'real_driving_emissions',
  export_marker: 'marked_for_export',
  type_approval: 'type_approval',
  wheelplan: 'wheelPlan',
  revenue_weight: 'revenue_weight',
  date_of_last_v5c: 'date_of_last_v5c_issued',
};

export default {
  async fetch(request, env) {
    // Fail closed: no secret configured, or a mismatch, is rejected. VES_RELAY_TOKEN on
    // the caller must equal the RELAY_TOKEN secret here (guards against open abuse that
    // would get this Worker's IP WAF-banned by gov.uk).
    const expected = env.RELAY_TOKEN ? `Bearer ${env.RELAY_TOKEN}` : '';
    if (!expected || request.headers.get('Authorization') !== expected) {
      return json({ error: 'Unauthorized' }, 401);
    }
    const match = new URL(request.url).pathname.match(/^\/ves\/([^/]+)\/?$/);
    if (request.method !== 'GET' || !match) return json({ error: 'Not found' }, 404);
    const reg = decodeURIComponent(match[1]).replace(/\s+/g, '').toUpperCase();
    try {
      return json(await lookup(reg));
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, (e && e.status) || 502);
    }
  },
};

async function lookup(reg) {
  const jar = new Map();

  const home = await fetchFollow(BASE + '/', { jar });
  const token1 = extractToken(home.body);
  if (!token1) throw fail('Could not read the vehicle-enquiry form', 502);

  const confirm = await fetchFollow(BASE + SAVE, {
    jar,
    body: form({
      authenticity_token: token1,
      'wizard_vehicle_enquiry_capture_vrn[vrn]': reg,
    }),
  });
  if (confirm.url.includes('VehicleNotFound')) {
    throw fail(`No vehicle found for registration ${reg}`, 404);
  }

  // The CSRF token is per-page — re-read it from the confirm page before posting again.
  const token2 = extractToken(confirm.body);
  if (!token2) throw fail('Could not read the confirm form', 502);
  const found = await fetchFollow(BASE + SAVE, {
    jar,
    body: form({
      authenticity_token: token2,
      'wizard_vehicle_enquiry_capture_confirm_vehicle[confirmed]': 'Yes',
    }),
  });
  if (!found.url.includes('VehicleFound')) {
    throw fail('Unexpected response from the vehicle enquiry service', 502);
  }

  return parseSnapshot(found.body, reg);
}

// Build the snapshot from the result page. Only a missing tax status is fatal; every other
// field is best-effort and left null when its row/panel is absent (mirrors fetch_ves).
export function parseSnapshot(html, reg) {
  const status = readById(html, 'vehicleStatus', 'dd');
  if (!status) throw fail('Could not read the vehicle tax status', 502);
  const snapshot = {
    registration: reg,
    tax_status: status,
    tax_due_date: parseDueDate(readById(html, 'tax-status-panel')),
    // MOT is on the same page: `mot_hidden_details` holds the status sentence and
    // `mot-status-panel` the "Expires: <date>". Both absent for a vehicle with no MOT.
    mot_status: readById(html, 'mot_hidden_details'),
    mot_expiry_date: parseDueDate(readById(html, 'mot-status-panel')),
  };
  for (const [key, id] of Object.entries(PROFILE_FIELDS)) {
    snapshot[key] = readById(html, id, 'dd');
  }
  return snapshot;
}

// Issue a request and follow redirects manually, threading the cookie jar and returning
// the final URL + body. Redirects are followed as GET (the wizard uses POST-redirect-GET),
// and Set-Cookie from every hop is captured so a rotated session cookie is never lost.
async function fetchFollow(url, { jar, body = null }) {
  let current = url;
  let method = body != null ? 'POST' : 'GET';
  let payload = body;
  for (let hop = 0; hop < 8; hop++) {
    const headers = { 'User-Agent': UA, Accept: 'text/html' };
    if (payload != null) headers['Content-Type'] = 'application/x-www-form-urlencoded';
    const cookie = cookieHeader(jar);
    if (cookie) headers.Cookie = cookie;

    const resp = await fetch(current, { method, headers, body: payload, redirect: 'manual' });
    storeCookies(jar, resp);

    const location = resp.headers.get('location');
    if (resp.status >= 300 && resp.status < 400 && location) {
      current = new URL(location, current).toString();
      method = 'GET';
      payload = null;
      continue;
    }
    return { url: current, body: await resp.text() };
  }
  throw fail('Too many redirects from the vehicle enquiry service', 502);
}

// ── HTML parsing (mirrors _TokenParser / _FieldParser / _parse_due_date in ves.py) ──

// The `authenticity_token` from the form whose action posts to /vehicle-enquiry/save
// (the page also has one in the cookie-consent form — that one must be ignored).
export function extractToken(html) {
  const formRe = /<form\b[^>]*action="([^"]*)"[^>]*>([\s\S]*?)<\/form>/gi;
  let m;
  while ((m = formRe.exec(html)) !== null) {
    if (!m[1].includes('/vehicle-enquiry/save')) continue;
    const input = m[2].match(/<input\b[^>]*name="authenticity_token"[^>]*>/i);
    const value = input && input[0].match(/value="([^"]*)"/i);
    if (value) return value[1];
  }
  return null;
}

// Read the element carrying id=`id`, returning its collapsed text. With `valueTag` set, only
// the text inside the first descendant of that tag is kept (the GOV.UK summary rows key the
// id on the row <div> wrapping a <dt> label and the <dd> value, so `dd` drops the label).
// The element's end is found by depth-counting its own tag, so nested divs (panels) are
// bounded correctly. Mirrors ves._FieldParser.
export function readById(html, id, valueTag = null) {
  const open = new RegExp(`<([a-zA-Z][a-zA-Z0-9]*)\\b[^>]*\\bid="${id}"[^>]*>`, 'i').exec(html);
  if (!open) return null;
  const tag = open[1].toLowerCase();
  const start = open.index + open[0].length;
  let inner;
  if (VOID.has(tag)) {
    inner = '';
  } else {
    const walk = new RegExp(`<(/?)${tag}\\b[^>]*?(/?)>`, 'gi');
    walk.lastIndex = start;
    let depth = 1;
    let end = html.length;
    let t;
    while ((t = walk.exec(html)) !== null) {
      if (t[1] === '/') {
        if (--depth === 0) { end = t.index; break; }
      } else if (t[2] !== '/') {
        depth++;  // a non-self-closing open of the same tag
      }
    }
    inner = html.slice(start, end);
  }
  if (valueTag) {
    const v = new RegExp(`<${valueTag}\\b[^>]*>([\\s\\S]*?)</${valueTag}>`, 'i').exec(inner);
    return v ? stripTags(v[1]) || null : null;
  }
  return stripTags(inner) || null;
}

// Turn a "Tax due: 1 December 2026" / "Expires: 11 June 2027" style string into an ISO date.
export function parseDueDate(text) {
  const m = text && text.match(/(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})/);
  if (!m) return null;
  const day = parseInt(m[1], 10);
  const month = MONTHS[m[2].toLowerCase()];
  const year = parseInt(m[3], 10);
  if (!month) return null;
  const d = new Date(Date.UTC(year, month - 1, day));
  // Reject impossible dates (e.g. 31 February) — Date rolls them over.
  if (d.getUTCFullYear() !== year || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day) {
    return null;
  }
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function stripTags(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

// ── small helpers ──

function form(fields) {
  return Object.entries(fields)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');
}

function storeCookies(jar, resp) {
  const raw = typeof resp.headers.getSetCookie === 'function'
    ? resp.headers.getSetCookie()
    : (resp.headers.get('set-cookie') ? [resp.headers.get('set-cookie')] : []);
  for (const sc of raw) {
    const pair = sc.split(';', 1)[0];
    const eq = pair.indexOf('=');
    if (eq > 0) jar.set(pair.slice(0, eq).trim(), pair.slice(eq + 1).trim());
  }
}

function cookieHeader(jar) {
  return [...jar.entries()].map(([k, v]) => `${k}=${v}`).join('; ');
}

function fail(message, status) {
  const e = new Error(message);
  e.status = status;
  return e;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
