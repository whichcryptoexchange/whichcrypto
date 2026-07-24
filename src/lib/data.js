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

export function countriesInData(exchanges) {
  const set = new Set();
  for (const ex of exchanges) for (const c of Object.keys(ex.countries || {})) set.add(c);
  return [...set].sort();
}

export const COUNTRY_NAMES = {
  AT: 'Austria', BE: 'Belgium', BG: 'Bulgaria', CY: 'Cyprus', CZ: 'Czechia',
  DE: 'Germany', DK: 'Denmark', EE: 'Estonia', ES: 'Spain', FI: 'Finland',
  FR: 'France', GR: 'Greece', HR: 'Croatia', HU: 'Hungary', IE: 'Ireland',
  IS: 'Iceland', IT: 'Italy', LI: 'Liechtenstein', LT: 'Lithuania',
  LU: 'Luxembourg', LV: 'Latvia', MT: 'Malta', NL: 'Netherlands',
  NO: 'Norway', PL: 'Poland', PT: 'Portugal', RO: 'Romania', SE: 'Sweden',
  SI: 'Slovenia', SK: 'Slovakia',
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
