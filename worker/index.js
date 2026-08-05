// whichcryptoexchange worker: serves static assets (automatic) and handles
// the user-report API, the contact form, affiliate links, and admin views.
//
// Affiliate links are deliberately NOT in data/exchanges/*.yaml (the
// regulator-sourced files rewritten wholesale by esma_sync.py) -- they live
// in D1 instead, managed live via /admin/links with no rebuild needed.
// Exchange pages fetch /api/links/<id> client-side, same pattern already
// used for /api/reports/<id> aggregates.
//
// Bindings required (see wrangler.jsonc + README-reports.md):
//   DB              - D1 database
//   SEND_EMAIL      - Email Routing send binding, destination jim@maxrespect.co.uk
//                     (contact form only -- fixed pre-verified destination,
//                     works fine on the free Workers plan)
//   RESEND_API_KEY  - secret: Resend API key, for watcher/digest confirm
//                     emails and the weekly digest send to arbitrary
//                     addresses (needs whichcryptoexchange.com verified as a
//                     sending domain in the Resend dashboard -- Cloudflare's
//                     own send_email binding can only reach pre-verified
//                     destinations without Workers Paid)
//   TURNSTILE_SECRET- secret: Cloudflare Turnstile secret key
//   ADMIN_KEY       - secret: long random string gating /admin/reports, /admin/links,
//                     /admin/submissions
//   DIGEST_SEND_KEY - secret: long random string gating /api/admin/digest-send,
//                     the weekly-roundup fan-out (separate from ADMIN_KEY --
//                     see handleDigestSend for why). Called only by the
//                     weekly-digest GitHub Actions workflow.
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

// Self-submissions from regulated exchanges asking to be added. This is a
// tip queue, not a listing mechanism -- nothing here ever reaches the site
// directly. A human (the curator) verifies the licence_reference against
// the actual primary regulator source before manually adding an entry to
// data/exchanges/*.yaml through the normal reviewed git process.
const SUBMISSION_JURISDICTIONS = new Set(['MICA', 'GB', 'CA', 'AE', 'SG', 'US', 'HK', 'GI', 'JP', 'MY', 'KR']);

async function handleSubmission(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400); }

  const ip = request.headers.get('CF-Connecting-IP') || '0.0.0.0';
  if (!(await verifyTurnstile(body.turnstile_token, env.TURNSTILE_SECRET, ip))) {
    return json({ error: 'verification failed — please retry the challenge' }, 403);
  }

  const brand_name = sanitizeHeader(body.brand_name, 200);
  const website = sanitizeHeader(body.website, 300);
  const country = String(body.country || '').toUpperCase();
  const legal_entity = sanitizeHeader(body.legal_entity, 300);
  const licence_reference = sanitizeHeader(body.licence_reference, 200);
  const contact_email = sanitizeHeader(body.contact_email, 200);
  const notes = String(body.notes || '').trim().slice(0, 1000);

  if (!brand_name) return json({ error: 'brand name is required' }, 400);
  if (!isHttpUrl(website)) return json({ error: 'a valid website URL is required' }, 400);
  if (!SUBMISSION_JURISDICTIONS.has(country)) return json({ error: 'invalid jurisdiction' }, 400);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact_email)) return json({ error: 'a valid contact email is required' }, 400);
  if (!body.consent) return json({ error: 'consent is required' }, 400);

  const ip_hash = await sha256hex(env.IP_SALT + ip);
  const { results: recent } = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM submissions WHERE ip_hash = ? AND created_at > datetime('now','-1 day')"
  ).bind(ip_hash).all();
  if (recent[0].n >= 5) return json({ error: 'rate limit reached — try again tomorrow' }, 429);

  await env.DB.prepare(
    'INSERT INTO submissions (brand_name, website, country, legal_entity, licence_reference, contact_email, notes, ip_hash) VALUES (?,?,?,?,?,?,?,?)'
  ).bind(brand_name, website, country, legal_entity || null, licence_reference || null, contact_email, notes || null, ip_hash).run();

  return json({ ok: true, message: 'Thanks — we independently verify every submission against the official regulator record before adding anything. This does not guarantee listing.' });
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

// "Watch this exchange" email alerts -- double opt-in throughout. Nothing
// is emailed on a status change until the address itself has clicked a
// confirm link, so a stranger's email can never be signed up without
// their action, and the click itself is the consent record.
async function lookupBrand(env, request, exchangeId) {
  const brands = await fetchBrandList(env, request);
  return brands.find((b) => b.id === exchangeId)?.brand ?? exchangeId;
}

function randomToken() {
  return crypto.randomUUID().replace(/-/g, '') + crypto.randomUUID().replace(/-/g, '');
}

// Uses Resend's REST API rather than Cloudflare's own send_email binding --
// the latter can only reach pre-verified destination addresses on the free
// Workers plan (Email Sending requires Workers Paid), which is unworkable
// for a public signup form emailing arbitrary addresses. Needs RESEND_API_KEY
// as a secret and whichcryptoexchange.com verified as a sending domain in
// the Resend dashboard -- no binding/wrangler.jsonc entry required, just an
// HTTPS call.
async function sendResendEmail(env, to, subject, text) {
  const r = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: 'whichcryptoexchange.com <alerts@whichcryptoexchange.com>',
      to: [to],
      subject,
      text,
    }),
  });
  if (!r.ok) throw new Error(`Resend API error: ${r.status} ${await r.text()}`);
}

async function sendWatchConfirmEmail(env, email, brand, token) {
  const confirmUrl = `https://whichcryptoexchange.com/api/watch/confirm?token=${token}`;
  const text = [
    `Someone (hopefully you) asked to be emailed if ${brand}'s regulatory status changes on whichcryptoexchange.com.`,
    '',
    `Confirm and start watching ${brand}:`,
    confirmUrl,
    '',
    "If you didn't request this, ignore this email -- nothing is created unless you click the link above, and it will expire from disuse if never confirmed.",
  ].join('\n');
  await sendResendEmail(env, email, `Confirm: watch ${brand} for changes`, text);
}

async function handleWatchSignup(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400); }

  const ip = request.headers.get('CF-Connecting-IP') || '0.0.0.0';
  if (!(await verifyTurnstile(body.turnstile_token, env.TURNSTILE_SECRET, ip))) {
    return json({ error: 'verification failed — please retry the challenge' }, 403);
  }

  const exchange_id = String(body.exchange_id || '').toLowerCase();
  const email = sanitizeHeader(body.email, 200);
  if (!/^[a-z0-9-]{1,60}$/.test(exchange_id)) return json({ error: 'invalid exchange' }, 400);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ error: 'a valid email is required' }, 400);
  if (!body.consent) return json({ error: 'consent is required to watch an exchange' }, 400);

  const ip_hash = await sha256hex(env.IP_SALT + ip);
  const { results: recent } = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM watchers WHERE ip_hash = ? AND created_at > datetime('now','-1 hour')"
  ).bind(ip_hash).all();
  if (recent[0].n >= 10) return json({ error: 'rate limit reached — try again later' }, 429);

  const existing = await env.DB.prepare(
    'SELECT token, confirmed FROM watchers WHERE exchange_id = ? AND email = ?'
  ).bind(exchange_id, email).first();

  const brand = await lookupBrand(env, request, exchange_id);

  if (existing?.confirmed) {
    return json({ ok: true, message: `You're already watching ${brand}.` });
  }

  // Re-send the same confirm link rather than mint a new one if someone
  // re-submits before confirming -- avoids piling up dead unconfirmed rows
  // from the same address hitting "submit" twice.
  const token = existing?.token ?? randomToken();
  if (!existing) {
    await env.DB.prepare(
      'INSERT INTO watchers (exchange_id, email, token, ip_hash) VALUES (?,?,?,?)'
    ).bind(exchange_id, email, token, ip_hash).run();
  }

  try {
    await sendWatchConfirmEmail(env, email, brand, token);
  } catch {
    return json({ error: 'could not send confirmation email — please try again later' }, 502);
  }

  return json({ ok: true, message: `Check your email to confirm watching ${brand}.` });
}

const watchPage = (title, body) => new Response(
  `<!doctype html><meta charset="utf-8"><title>${esc(title)} | whichcryptoexchange.com</title>
   <meta name="viewport" content="width=device-width, initial-scale=1">
   <meta name="robots" content="noindex">
   <link rel="icon" type="image/svg+xml" href="/favicon.svg">
   <style>body{font:16px/1.5 system-ui,sans-serif;max-width:520px;margin:80px auto;padding:0 20px;color:#14202e}
     a{color:#177245}h1{font-size:22px}</style>
   <h1>${esc(title)}</h1>${body}
   <p><a href="/">← back to whichcryptoexchange.com</a></p>`,
  { headers: { 'Content-Type': 'text/html; charset=utf-8' } },
);

async function handleWatchConfirm(env, request, token) {
  const row = await env.DB.prepare('SELECT * FROM watchers WHERE token = ?').bind(token).first();
  if (!row) return watchPage('Link not found', '<p>This confirmation link is invalid or has already been used.</p>');

  const brand = await lookupBrand(env, request, row.exchange_id);
  if (!row.confirmed) {
    await env.DB.prepare(
      "UPDATE watchers SET confirmed = 1, confirmed_at = datetime('now') WHERE token = ?"
    ).bind(token).run();
  }
  return watchPage(`Watching ${brand}`,
    `<p>You'll get an email if ${esc(brand)}'s regulatory status changes on whichcryptoexchange.com.</p>
     <p><a href="/api/watch/unsubscribe?token=${esc(token)}">Unsubscribe</a> any time, no login needed.</p>`);
}

async function handleWatchUnsubscribe(env, token) {
  const row = await env.DB.prepare('SELECT exchange_id FROM watchers WHERE token = ?').bind(token).first();
  await env.DB.prepare('DELETE FROM watchers WHERE token = ?').bind(token).run();
  return watchPage('Unsubscribed', row
    ? '<p>You will not receive any more emails about this exchange.</p>'
    : '<p>Already unsubscribed, or this link was invalid.</p>');
}

// Weekly roundup digest -- same double opt-in mechanism as watchers, but
// one subscription covers every brand, not just one. The actual weekly
// send (diffing the register and mailing confirmed subscribers) is a
// separate follow-up; this is just collecting and confirming signups.
async function sendDigestConfirmEmail(env, email, token) {
  const confirmUrl = `https://whichcryptoexchange.com/api/digest/confirm?token=${token}`;
  const text = [
    'Someone (hopefully you) asked to get the weekly regulatory roundup email from whichcryptoexchange.com -- every change across every tracked exchange, once a week.',
    '',
    'Confirm and subscribe:',
    confirmUrl,
    '',
    "If you didn't request this, ignore this email -- nothing is created unless you click the link above.",
  ].join('\n');
  await sendResendEmail(env, email, 'Confirm: weekly regulatory roundup', text);
}

async function handleDigestSignup(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400); }

  const ip = request.headers.get('CF-Connecting-IP') || '0.0.0.0';
  if (!(await verifyTurnstile(body.turnstile_token, env.TURNSTILE_SECRET, ip))) {
    return json({ error: 'verification failed — please retry the challenge' }, 403);
  }

  const email = sanitizeHeader(body.email, 200);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ error: 'a valid email is required' }, 400);
  if (!body.consent) return json({ error: 'consent is required to subscribe' }, 400);

  const ip_hash = await sha256hex(env.IP_SALT + ip);
  const { results: recent } = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM digest_subscribers WHERE ip_hash = ? AND created_at > datetime('now','-1 hour')"
  ).bind(ip_hash).all();
  if (recent[0].n >= 10) return json({ error: 'rate limit reached — try again later' }, 429);

  const existing = await env.DB.prepare(
    'SELECT token, confirmed FROM digest_subscribers WHERE email = ?'
  ).bind(email).first();

  if (existing?.confirmed) {
    return json({ ok: true, message: "You're already subscribed to the weekly roundup." });
  }

  const token = existing?.token ?? randomToken();
  if (!existing) {
    await env.DB.prepare(
      'INSERT INTO digest_subscribers (email, token, ip_hash) VALUES (?,?,?)'
    ).bind(email, token, ip_hash).run();
  }

  try {
    await sendDigestConfirmEmail(env, email, token);
  } catch {
    return json({ error: 'could not send confirmation email — please try again later' }, 502);
  }

  return json({ ok: true, message: 'Check your email to confirm your subscription.' });
}

async function handleDigestConfirm(env, token) {
  const row = await env.DB.prepare('SELECT * FROM digest_subscribers WHERE token = ?').bind(token).first();
  if (!row) return watchPage('Link not found', '<p>This confirmation link is invalid or has already been used.</p>');

  if (!row.confirmed) {
    await env.DB.prepare(
      "UPDATE digest_subscribers SET confirmed = 1, confirmed_at = datetime('now') WHERE token = ?"
    ).bind(token).run();
  }
  return watchPage('Subscribed',
    `<p>You'll get the weekly regulatory roundup from whichcryptoexchange.com.</p>
     <p><a href="/api/digest/unsubscribe?token=${esc(token)}">Unsubscribe</a> any time, no login needed.</p>`);
}

async function handleDigestUnsubscribe(env, token) {
  const row = await env.DB.prepare('SELECT id FROM digest_subscribers WHERE token = ?').bind(token).first();
  await env.DB.prepare('DELETE FROM digest_subscribers WHERE token = ?').bind(token).run();
  return watchPage('Unsubscribed', row
    ? '<p>You will not receive the weekly roundup any more.</p>'
    : '<p>Already unsubscribed, or this link was invalid.</p>');
}

// Fan-out for the actual weekly send. Triggered by a GitHub Actions cron
// (scripts/weekly_digest.py diffs the register and posts the resulting
// content here) -- not reachable from any public-facing form. Uses its own
// DIGEST_SEND_KEY rather than the existing ADMIN_KEY: a leaked report
// moderation key only exposes pending user reports, but a leaked send key
// could email every subscriber arbitrary content, so the two stay separate.
async function handleDigestSend(request, env, url) {
  if (!env.DIGEST_SEND_KEY || url.searchParams.get('key') !== env.DIGEST_SEND_KEY) {
    return json({ error: 'forbidden' }, 403);
  }
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400); }
  const subject = String(body.subject || '').slice(0, 200);
  const text = String(body.text || '').slice(0, 20000);
  if (!subject || !text) return json({ error: 'subject and text are required' }, 400);

  const { results: subscribers } = await env.DB.prepare(
    'SELECT email, token FROM digest_subscribers WHERE confirmed = 1'
  ).all();

  let sent = 0;
  let failed = 0;
  for (const sub of subscribers) {
    const unsubUrl = `https://whichcryptoexchange.com/api/digest/unsubscribe?token=${sub.token}`;
    try {
      await sendResendEmail(env, sub.email, subject, `${text}\n\n---\nUnsubscribe: ${unsubUrl}`);
      sent++;
    } catch {
      failed++;
    }
  }
  return json({ total: subscribers.length, sent, failed });
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

async function handleAdminSubmissions(request, env, url) {
  if (url.searchParams.get('key') !== env.ADMIN_KEY || !env.ADMIN_KEY) {
    return new Response('forbidden', { status: 403 });
  }
  if (request.method === 'POST') {
    const form = await request.formData();
    const id = Number(form.get('id'));
    const action = form.get('action') === 'approve' ? 'approved' : 'rejected';
    await env.DB.prepare('UPDATE submissions SET status = ? WHERE id = ?').bind(action, id).run();
    return Response.redirect(url.origin + url.pathname + '?key=' + env.ADMIN_KEY, 303);
  }
  const { results } = await env.DB.prepare(
    "SELECT * FROM submissions WHERE status = 'pending' ORDER BY created_at ASC LIMIT 100"
  ).all();
  const rows = results.map((r) => `
    <tr>
      <td>${r.id}</td><td>${esc(r.brand_name)}</td><td><a href="${esc(r.website)}">${esc(r.website)}</a></td>
      <td>${esc(r.country)}</td><td>${esc(r.legal_entity ?? '')}</td><td>${esc(r.licence_reference ?? '')}</td>
      <td>${esc(r.contact_email)}</td><td>${esc(r.notes ?? '')}</td><td>${esc(r.created_at)}</td>
      <td>
        <form method="post" style="display:inline"><input type="hidden" name="id" value="${r.id}">
          <button name="action" value="approve">approve</button>
          <button name="action" value="reject">reject</button></form>
      </td>
    </tr>`).join('');
  return new Response(
    `<!doctype html><meta charset="utf-8"><title>Pending submissions</title>
     <style>body{font:14px monospace;padding:20px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px;text-align:left;max-width:260px;word-break:break-word}</style>
     <h1>Pending submissions (${results.length})</h1>
     <p>Approving here does NOT publish anything -- verify licence_reference against the primary
     regulator source, then add the brand to data/exchanges/*.yaml by hand.</p>
     <table><tr><th>id</th><th>brand</th><th>website</th><th>jurisdiction</th><th>legal entity</th>
     <th>reference</th><th>contact</th><th>notes</th><th>submitted</th><th>action</th></tr>${rows}</table>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

async function handleLinkGet(env, exchangeId) {
  const row = await env.DB.prepare(
    'SELECT url, label FROM affiliate_links WHERE exchange_id = ?'
  ).bind(exchangeId).first();
  if (!row) return json({ error: 'not found' }, 404);
  return json({ exchange_id: exchangeId, url: row.url, label: row.label });
}

// All known brands, sourced from the site's own build output rather than
// duplicated here -- always in sync with whatever's actually deployed.
async function fetchBrandList(env, request) {
  const r = await env.ASSETS.fetch(new Request(new URL('/api/exchanges.json', request.url)));
  if (!r.ok) return [];
  const data = await r.json();
  return (data.exchanges ?? [])
    .map((ex) => ({ id: ex.id, brand: ex.brand }))
    .sort((a, b) => a.brand.localeCompare(b.brand));
}

function isHttpUrl(s) {
  try {
    const u = new URL(s);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

async function handleAdminLinks(request, env, url) {
  if (url.searchParams.get('key') !== env.ADMIN_KEY || !env.ADMIN_KEY) {
    return new Response('forbidden', { status: 403 });
  }

  if (request.method === 'POST') {
    const form = await request.formData();
    const exchange_id = String(form.get('exchange_id') || '');
    const action = form.get('action');
    if (action === 'delete') {
      await env.DB.prepare('DELETE FROM affiliate_links WHERE exchange_id = ?').bind(exchange_id).run();
    } else {
      const link_url = String(form.get('url') || '').trim();
      const label = String(form.get('label') || '').trim().slice(0, 100) || null;
      if (exchange_id && isHttpUrl(link_url)) {
        await env.DB.prepare(
          `INSERT INTO affiliate_links (exchange_id, url, label, updated_at) VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(exchange_id) DO UPDATE SET url = excluded.url, label = excluded.label, updated_at = excluded.updated_at`
        ).bind(exchange_id, link_url, label).run();
      }
    }
    return Response.redirect(url.origin + url.pathname + '?key=' + env.ADMIN_KEY, 303);
  }

  const [brands, { results: links }] = await Promise.all([
    fetchBrandList(env, request),
    env.DB.prepare('SELECT * FROM affiliate_links').all(),
  ]);
  const linkByExchange = Object.fromEntries(links.map((l) => [l.exchange_id, l]));

  // Inputs live in their own <td> cells (a <form> can't validly wrap
  // multiple <td> siblings — browsers foster-parent it out of the table and
  // silently break the layout), associated with a same-row <form> via the
  // HTML5 form="..." attribute instead of DOM nesting.
  const rows = brands.map((b) => {
    const l = linkByExchange[b.id];
    const formId = `f-${b.id}`;
    return `
    <tr>
      <td>${esc(b.brand)}</td>
      <td><code>${esc(b.id)}</code></td>
      <td><input form="${formId}" type="url" name="url" value="${esc(l?.url ?? '')}" placeholder="https://..." size="30"></td>
      <td><input form="${formId}" type="text" name="label" value="${esc(l?.label ?? '')}" placeholder="Visit ${esc(b.brand)}" size="16"></td>
      <td>${l ? esc(l.updated_at) : '—'}</td>
      <td>
        <form id="${formId}" method="post" style="display:inline">
          <input type="hidden" name="exchange_id" value="${esc(b.id)}">
          <button name="action" value="save">save</button>
          ${l ? '<button name="action" value="delete">remove</button>' : ''}
        </form>
      </td>
    </tr>`;
  }).join('');

  return new Response(
    `<!doctype html><meta charset="utf-8"><title>Affiliate links</title>
     <style>
       body{font:14px monospace;padding:20px}
       table{border-collapse:collapse;width:100%}
       td,th{border:1px solid #ccc;padding:6px;text-align:left}
       input#search{font:14px monospace;padding:6px;margin-bottom:12px;width:300px}
     </style>
     <h1>Affiliate links (${brands.length} brands, ${links.length} with a link set)</h1>
     <input id="search" placeholder="Filter by brand or id…" oninput="
       const q = this.value.toLowerCase();
       document.querySelectorAll('tbody tr').forEach(r => {
         r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
       });">
     <table>
       <thead><tr><th>Brand</th><th>id</th><th>URL</th><th>Button label</th><th>Updated</th><th>Action</th></tr></thead>
       <tbody>${rows}</tbody>
     </table>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/api/report' && request.method === 'POST') return handleSubmit(request, env);
    if (url.pathname === '/api/contact' && request.method === 'POST') return handleContact(request, env);
    if (url.pathname === '/api/submit' && request.method === 'POST') return handleSubmission(request, env);
    if (url.pathname === '/api/watch' && request.method === 'POST') return handleWatchSignup(request, env);
    if (url.pathname === '/api/watch/confirm' && request.method === 'GET') {
      return handleWatchConfirm(env, request, url.searchParams.get('token') || '');
    }
    if (url.pathname === '/api/watch/unsubscribe' && request.method === 'GET') {
      return handleWatchUnsubscribe(env, url.searchParams.get('token') || '');
    }
    if (url.pathname === '/api/digest' && request.method === 'POST') return handleDigestSignup(request, env);
    if (url.pathname === '/api/digest/confirm' && request.method === 'GET') {
      return handleDigestConfirm(env, url.searchParams.get('token') || '');
    }
    if (url.pathname === '/api/digest/unsubscribe' && request.method === 'GET') {
      return handleDigestUnsubscribe(env, url.searchParams.get('token') || '');
    }
    if (url.pathname === '/api/admin/digest-send' && request.method === 'POST') {
      return handleDigestSend(request, env, url);
    }
    const agg = url.pathname.match(/^\/api\/reports\/([a-z0-9-]{1,60})$/);
    if (agg && request.method === 'GET') return handleAggregates(env, agg[1]);
    if (url.pathname === '/admin/reports') return handleAdmin(request, env, url);
    if (url.pathname === '/admin/links') return handleAdminLinks(request, env, url);
    if (url.pathname === '/admin/submissions') return handleAdminSubmissions(request, env, url);
    const link = url.pathname.match(/^\/api\/links\/([a-z0-9-]{1,60})$/);
    if (link && request.method === 'GET') return handleLinkGet(env, link[1]);
    // Genuine catch-all: no route matched and no static asset matched either.
    // Serve the built 404 page with the right status rather than a bare 404.
    const notFound = await env.ASSETS.fetch(new Request(new URL('/404', request.url), request));
    return new Response(notFound.body, { status: 404, headers: notFound.headers });
  },
};
