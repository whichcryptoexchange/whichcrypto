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
  GB: 'United Kingdom', CA: 'Canada', AE: 'UAE (Dubai Only)',
  SG: 'Singapore', US: 'United States', HK: 'Hong Kong', GI: 'Gibraltar',
  JP: 'Japan', MY: 'Malaysia', KR: 'South Korea',
};

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
