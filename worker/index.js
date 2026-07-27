// whichcryptoexchange worker: serves static assets (automatic) and handles
// the user-report API, the contact form, and a minimal moderation view.
//
// Bindings required (see wrangler.jsonc + README-reports.md):
//   DB              - D1 database
//   SEND_EMAIL      - Email Routing send binding, destination jim@maxrespect.co.uk
//   TURNSTILE_SECRET- secret: Cloudflare Turnstile secret key
//   ADMIN_KEY       - secret: long random string gating /admin/reports
//   IP_SALT         - secret: random string for privacy-preserving IP hashing

import { EmailMessage } from 'cloudflare:email';

const OUTCOMES = new Set([
  'signup_ok','signup_blocked','kyc_blocked',
  'withdrawal_ok','withdrawal_delayed','withdrawal_refused',
  'account_closed','geo_blocked',
]);

const OUTCOME_LABELS = {
  signup_ok: 'Signed up successfully',
  signup_blocked: 'Blocked at signup',
  kyc_blocked: 'Blocked at KYC',
  withdrawal_ok: 'Withdrawal succeeded',
  withdrawal_delayed: 'Withdrawal delayed',
  withdrawal_refused: 'Withdrawal refused',
  account_closed: 'Account closed by exchange',
  geo_blocked: 'Geo-blocked',
};

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  });

async function sha256hex(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function verifyTurnstile(token, secret, ip) {
  if (!token) return false;
  const body = new URLSearchParams({ secret, response: token, remoteip: ip });
  const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    body,
  });
  const data = await r.json();
  return data.success === true;
}

async function handleSubmit(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400); }

  const ip = request.headers.get('CF-Connecting-IP') || '0.0.0.0';
  if (!(await verifyTurnstile(body.turnstile_token, env.TURNSTILE_SECRET, ip))) {
    return json({ error: 'verification failed — please retry the challenge' }, 403);
  }

  const exchange_id = String(body.exchange_id || '').toLowerCase();
  const country = String(body.country || '').toUpperCase();
  const outcome = String(body.outcome || '');
  const detail = String(body.detail || '').slice(0, 1000);
  const occurred_on = /^\d{4}-\d{2}-\d{2}$/.test(body.occurred_on || '') ? body.occurred_on : null;

  if (!/^[a-z0-9-]{1,60}$/.test(exchange_id)) return json({ error: 'invalid exchange' }, 400);
  if (!/^[A-Z]{2}$/.test(country)) return json({ error: 'invalid country' }, 400);
  if (!OUTCOMES.has(outcome)) return json({ error: 'invalid outcome' }, 400);

  // Rate limit: max 5 submissions per IP per 24h.
  const ip_hash = await sha256hex(env.IP_SALT + ip);
  const { results: recent } = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM reports WHERE ip_hash = ? AND created_at > datetime('now','-1 day')"
  ).bind(ip_hash).all();
  if (recent[0].n >= 5) return json({ error: 'rate limit reached — try again tomorrow' }, 429);

  await env.DB.prepare(
    'INSERT INTO reports (exchange_id, country, outcome, detail, occurred_on, ip_hash) VALUES (?,?,?,?,?,?)'
  ).bind(exchange_id, country, outcome, detail, occurred_on, ip_hash).run();

  return json({ ok: true, message: 'Thanks — your report is queued for review before publication.' });
}

function sanitizeHeader(s, max) {
  return String(s ?? '').replace(/[\r\n]+/g, ' ').trim().slice(0, max);
}

async function handleContact(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400); }

  const ip = request.headers.get('CF-Connecting-IP') || '0.0.0.0';
  if (!(await verifyTurnstile(body.turnstile_token, env.TURNSTILE_SECRET, ip))) {
    return json({ error: 'verification failed — please retry the challenge' }, 403);
  }

  const name = sanitizeHeader(body.name, 100);
  const email = sanitizeHeader(body.email, 200);
  const message = String(body.message || '').trim().slice(0, 5000);

  if (!name) return json({ error: 'name is required' }, 400);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ error: 'a valid email is required' }, 400);
  if (!message) return json({ error: 'message is required' }, 400);

  const raw = [
    'From: whichcryptoexchange contact form <contact@whichcryptoexchange.com>',
    `Reply-To: ${email}`,
    'To: jim@maxrespect.co.uk',
    `Subject: Contact form: ${name}`,
    'Content-Type: text/plain; charset="UTF-8"',
    '',
    `From: ${name} <${email}>`,
    '',
    message,
  ].join('\r\n');

  try {
    await env.SEND_EMAIL.send(new EmailMessage(
      'contact@whichcryptoexchange.com',
      'jim@maxrespect.co.uk',
      raw,
    ));
  } catch {
    return json({ error: 'could not send — please try again later' }, 502);
  }

  return json({ ok: true, message: 'Thanks — your message has been sent.' });
}

async function handleAggregates(env, exchangeId) {
  const { results } = await env.DB.prepare(
    `SELECT country, outcome, COUNT(*) AS n, MAX(created_at) AS latest
     FROM reports WHERE exchange_id = ? AND status = 'approved'
     GROUP BY country, outcome`
  ).bind(exchangeId).all();
  const total = results.reduce((s, r) => s + r.n, 0);
  return json({ exchange_id: exchangeId, total, labels: OUTCOME_LABELS, rows: results });
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function handleAdmin(request, env, url) {
  if (url.searchParams.get('key') !== env.ADMIN_KEY || !env.ADMIN_KEY) {
    return new Response('forbidden', { status: 403 });
  }
  if (request.method === 'POST') {
    const form = await request.formData();
    const id = Number(form.get('id'));
    const action = form.get('action') === 'approve' ? 'approved' : 'rejected';
    await env.DB.prepare('UPDATE reports SET status = ? WHERE id = ?').bind(action, id).run();
    return Response.redirect(url.origin + url.pathname + '?key=' + env.ADMIN_KEY, 303);
  }
  const { results } = await env.DB.prepare(
    "SELECT * FROM reports WHERE status = 'pending' ORDER BY created_at ASC LIMIT 100"
  ).all();
  const rows = results.map((r) => `
    <tr>
      <td>${r.id}</td><td>${esc(r.exchange_id)}</td><td>${esc(r.country)}</td>
      <td>${esc(OUTCOME_LABELS[r.outcome] ?? r.outcome)}</td>
      <td>${esc(r.occurred_on ?? '')}</td><td>${esc(r.detail ?? '')}</td><td>${esc(r.created_at)}</td>
      <td>
        <form method="post" style="display:inline"><input type="hidden" name="id" value="${r.id}">
          <button name="action" value="approve">approve</button>
          <button name="action" value="reject">reject</button></form>
      </td>
    </tr>`).join('');
  return new Response(
    `<!doctype html><meta charset="utf-8"><title>Pending reports</title>
     <style>body{font:14px monospace;padding:20px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px;text-align:left;max-width:340px}</style>
     <h1>Pending reports (${results.length})</h1>
     <table><tr><th>id</th><th>exchange</th><th>cc</th><th>outcome</th><th>date</th><th>detail</th><th>submitted</th><th>action</th></tr>${rows}</table>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/api/report' && request.method === 'POST') return handleSubmit(request, env);
    if (url.pathname === '/api/contact' && request.method === 'POST') return handleContact(request, env);
    const agg = url.pathname.match(/^\/api\/reports\/([a-z0-9-]{1,60})$/);
    if (agg && request.method === 'GET') return handleAggregates(env, agg[1]);
    if (url.pathname === '/admin/reports') return handleAdmin(request, env, url);
    // Genuine catch-all: no route matched and no static asset matched either.
    // Serve the built 404 page with the right status rather than a bare 404.
    const notFound = await env.ASSETS.fetch(new Request(new URL('/404', request.url), request));
    return new Response(notFound.body, { status: 404, headers: notFound.headers });
  },
};
