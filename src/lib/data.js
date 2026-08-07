// Loads the normalised exchange YAML files at build time.
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';

const DIR = path.resolve('data/exchanges');

export function loadExchanges() {
  return fs.readdirSync(DIR)
    .filter((f) => f.endsWith('.yaml'))
    .map((f) => yaml.load(fs.readFileSync(path.join(DIR, f), 'utf8')))
    .sort((a, b) => a.brand.localeCompare(b.brand));
}

export function loadChangelog() {
  const file = path.resolve('data/changelog.yaml');
  return (yaml.load(fs.readFileSync(file, 'utf8')) || [])
    .sort((a, b) => b.date.localeCompare(a.date));
}

// Editorial "Technology Provider Profile" pages -- explicitly NOT part of
// the regulator register. These cover companies that are not themselves
// licensed/registered anywhere, but rely on a custodian/execution partner
// that IS -- e.g. a wallet app whose assets are actually held by a
// MiCA-licensed custodian. Every fact here is tagged verified (checked by
// us against a primary source) or disclosed (the company's own claim,
// unverified) -- see src/pages/providers/[id].astro.
const PROVIDERS_DIR = path.resolve('data/providers');

export function loadProviders() {
  if (!fs.existsSync(PROVIDERS_DIR)) return [];
  return fs.readdirSync(PROVIDERS_DIR)
    .filter((f) => f.endsWith('.yaml'))
    .map((f) => yaml.load(fs.readFileSync(path.join(PROVIDERS_DIR, f), 'utf8')))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// What each regulator actually checks before granting status -- manually
// researched reference content, not brand data, so it lives in its own file
// rather than data/exchanges/*.yaml. See data/regulator_details.yaml for the
// verified date and source per entry.
export function loadRegulatorDetails() {
  const file = path.resolve('data/regulator_details.yaml');
  return yaml.load(fs.readFileSync(file, 'utf8')) || [];
}

export function countriesInData(exchanges) {
  const set = new Set();
  for (const ex of exchanges) for (const c of Object.keys(ex.countries || {})) set.add(c);
  return [...set].sort((a, b) => (COUNTRY_NAMES[a] ?? a).localeCompare(COUNTRY_NAMES[b] ?? b));
}

// A handful of `website` fields across data/exchanges/*.yaml turned out to
// be scrape/entry artifacts rather than URLs -- a page title ("N26 - Die
// erste Onlinebank..."), a registered-office postal address, several
// pipe-or-newline-separated multi-URL values. Never render one of those as
// a link: validate first, and fall back to no link at all rather than a
// broken or embarrassing one.
function normalizeWebsite(raw) {
  if (!raw) return null;
  const candidate = raw.split(/[|\n]/)[0].trim();
  if (/\s/.test(candidate.replace(/^https?:\/\//i, ''))) return null;
  const withProtocol = /^https?:\/\//i.test(candidate) ? candidate : `https://${candidate}`;
  let u;
  try { u = new URL(withProtocol); } catch { return null; }
  if (!/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(u.hostname)) return null;
  return u.href;
}

// A brand's website can live at the top level (non-EEA-only brands, e.g.
// the NY DFS additions) or nested per EEA entity -- try every candidate in
// order and use the first that survives normalizeWebsite.
export function brandWebsite(ex) {
  const candidates = [ex.website, ...(ex.entities ?? []).map((e) => e.website)].filter(Boolean);
  for (const c of candidates) {
    const normalized = normalizeWebsite(c);
    if (normalized) return normalized;
  }
  return null;
}

// ISO 3166-1 alpha-2 -> flag emoji, via the regional indicator symbol trick
// (each letter maps to U+1F1E6..U+1F1FF, offset from 'A').
export function countryFlag(code) {
  return [...code.toUpperCase()]
    .map((c) => String.fromCodePoint(127397 + c.charCodeAt(0)))
    .join('');
}

export const COUNTRY_NAMES = {
  AT: 'Austria', BE: 'Belgium', BG: 'Bulgaria', CY: 'Cyprus', CZ: 'Czechia',
  DE: 'Germany', DK: 'Denmark', EE: 'Estonia', ES: 'Spain', FI: 'Finland',
  FR: 'France', GR: 'Greece', HR: 'Croatia', HU: 'Hungary', IE: 'Ireland',
  IS: 'Iceland', IT: 'Italy', LI: 'Liechtenstein', LT: 'Lithuania',
  LU: 'Luxembourg', LV: 'Latvia', MT: 'Malta', NL: 'Netherlands',
  NO: 'Norway', PL: 'Poland', PT: 'Portugal', RO: 'Romania', SE: 'Sweden',
  SI: 'Slovenia', SK: 'Slovakia',
  GB: 'United Kingdom', CA: 'Canada', AE: 'UAE (Dubai & Abu Dhabi)',
  SG: 'Singapore', US: 'United States', HK: 'Hong Kong', GI: 'Gibraltar',
  JP: 'Japan', MY: 'Malaysia', KR: 'South Korea',
};

// Non-EEA jurisdictions (list-shaped countries.<CC>, unlike the single-object
// EEA/MiCA shape) get a "<prefix> · Registered/Authorised/Licensed" stamp
// each -- shared between exchange/[id].astro's rendering and the plain-text
// summary below so the two can never say different things.
// AE was 'Dubai' until ADGM (Abu Dhabi) joined VARA (Dubai) under the same
// country page -- an ADGM-only brand with no Dubai connection at all would
// have shown a wrong "Dubai · Licensed" badge, so this needs to stay
// generic. The full Dubai-vs-Abu-Dhabi distinction is explained on the
// country page itself; this compact badge just needs to not be wrong.
export const NON_EEA_PREFIX = { GB: 'UK', CA: 'CA', AE: 'UAE', SG: 'SG', US: 'US', HK: 'HK', GI: 'GI', JP: 'JP', MY: 'MY', KR: 'KR' };

export function listJoin(arr) {
  return arr.length <= 1 ? (arr[0] ?? '')
    : arr.length === 2 ? `${arr[0]} and ${arr[1]}`
    : `${arr.slice(0, -1).join(', ')}, and ${arr[arr.length - 1]}`;
}

// Every fact this computes is a restatement of the verified register
// entries elsewhere on a brand's own page -- used by the visible
// summary-box paragraph, the per-brand FAQ answer, and that page's
// FAQPage structured data, so all three always agree with each other.
export function licenceFacts(ex) {
  const countryCodes = Object.keys(ex.countries ?? {})
    .sort((a, b) => (COUNTRY_NAMES[a] ?? a).localeCompare(COUNTRY_NAMES[b] ?? b));
  const nonEEAEntries = Object.entries(NON_EEA_PREFIX)
    .flatMap(([cc, prefix]) => (ex.countries?.[cc] ?? []).map((entry) => ({ ...entry, prefix })));
  const nonEEAStatusesByPrefix = {};
  for (const e of nonEEAEntries) {
    (nonEEAStatusesByPrefix[e.prefix] ??= new Set()).add(e.status);
  }
  const genuineLicenceJurisdictions = [];
  if (ex.eu_status === 'authorised') genuineLicenceJurisdictions.push('the EU/EEA (MiCA)');
  for (const [prefix, statuses] of Object.entries(nonEEAStatusesByPrefix)) {
    if (statuses.has('licensed')) genuineLicenceJurisdictions.push(prefix);
  }
  const amlOnlyJurisdictions = Object.entries(nonEEAStatusesByPrefix)
    .filter(([, statuses]) => statuses.has('registered'))
    .map(([prefix]) => prefix);
  const hasSeparateUKAuthorisation = nonEEAStatusesByPrefix.UK?.has('authorised');
  const allDates = [
    ...(ex.entities ?? []).flatMap((ent) => (ent.records ?? []).map((r) => r.authorised).filter(Boolean)),
    ...nonEEAEntries.map((e) => e.since).filter(Boolean),
  ].sort();
  const firstSeen = allDates[0];
  const totalEntities = (ex.entities ?? []).length + new Set(nonEEAEntries.map((e) => e.entity)).size;
  return { countryCodes, nonEEAEntries, genuineLicenceJurisdictions, amlOnlyJurisdictions, hasSeparateUKAuthorisation, firstSeen, totalEntities };
}

// Plain-text (no links/markup) version of the same summary shown on a
// brand's own page -- suitable for a FAQ answer or a JSON-LD `text` field.
export function licenceSummaryText(ex) {
  const f = licenceFacts(ex);
  let text = f.firstSeen
    ? `${ex.brand} first appears in our register on ${f.firstSeen}, `
    : `${ex.brand} appears in our register `;
  text += `and is currently tracked across ${f.countryCodes.length} jurisdiction${f.countryCodes.length === 1 ? '' : 's'} through ${f.totalEntities} legal entit${f.totalEntities === 1 ? 'y' : 'ies'}.`;
  if (f.genuineLicenceJurisdictions.length > 0) {
    text += ` It holds a genuine crypto-specific licence in ${listJoin(f.genuineLicenceJurisdictions)}.`;
  }
  if (f.amlOnlyJurisdictions.length > 0) {
    text += ` It also holds an AML-only registration (not a licence) in ${listJoin(f.amlOnlyJurisdictions)}.`;
  }
  if (f.hasSeparateUKAuthorisation) {
    text += ' A group entity is separately, fully FCA-authorised in the UK, usually for a different, non-crypto activity.';
  }
  if (ex.eu_status === 'withdrawn') {
    text += ' Its EU MiCA authorisation has since been withdrawn.';
  }
  if (f.genuineLicenceJurisdictions.length === 0 && f.amlOnlyJurisdictions.length === 0 && ex.eu_status !== 'authorised' && ex.eu_status !== 'withdrawn') {
    text += ` We have not independently verified a genuine crypto-specific licence or registration for ${ex.brand} in any jurisdiction we track.`;
  }
  return text;
}

export const SERVICE_NAMES = {
  a: 'Custody and administration of crypto-assets',
  b: 'Operation of a trading platform',
  c: 'Exchange of crypto-assets for funds',
  d: 'Exchange of crypto-assets for other crypto-assets',
  e: 'Execution of orders',
  f: 'Placing of crypto-assets',
  g: 'Reception and transmission of orders',
  h: 'Advice on crypto-assets',
  i: 'Portfolio management',
  j: 'Transfer services',
};
