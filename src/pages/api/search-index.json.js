// Small dedicated index for the site-wide search box -- deliberately not
// the full /api/exchanges.json (1MB+): just enough per brand (or country)
// to filter and link, fetched once client-side by public/search.js.
import { loadExchanges, countriesInData, COUNTRY_NAMES } from '../../lib/data.js';

// A brand's legal entity name is often unrecognisable next to its consumer
// brand (Block is licensed as "Block, Inc."; Strike as "Zap Solutions,
// Inc."; Ripple as "Ripple Markets DE LLC, f/k/a XRP II LLC") -- collect
// every distinct one so a search for the entity still finds the brand,
// without showing the entity name in the results list itself. Some brands
// also need the reverse: a hand-curated top-level `aliases` field for a
// consumer-facing product name that ISN'T a legal entity at all (Block's
// own brand card links to block.xyz, not cash.app, so "Cash App" has to be
// added explicitly or it would stop being findable).
function entityAliases(ex) {
  const names = new Set(ex.aliases ?? []);
  for (const ent of ex.entities ?? []) {
    if (ent.legal_name) names.add(ent.legal_name);
    if (ent.commercial_name) names.add(ent.commercial_name);
  }
  for (const entries of Object.values(ex.countries ?? {})) {
    // Non-EEA jurisdictions store a list of entries per country; EEA/MiCA
    // ones store a single object -- same shape distinction as [country].astro.
    for (const entry of Array.isArray(entries) ? entries : [entries]) {
      if (entry.entity) names.add(entry.entity);
    }
  }
  names.delete(ex.brand);
  return [...names];
}

export function GET() {
  const exchanges = loadExchanges();
  const brandItems = exchanges.map((ex) => ({
    type: 'exchange',
    label: ex.brand,
    href: `/exchange/${ex.id}/`,
    aliases: entityAliases(ex),
    meta: (() => {
      const n = Object.keys(ex.countries ?? {}).length;
      return `${n} jurisdiction${n === 1 ? '' : 's'}`;
    })(),
  }));
  const countryItems = countriesInData(exchanges).map((cc) => ({
    type: 'country',
    label: COUNTRY_NAMES[cc] ?? cc,
    href: `/${cc.toLowerCase()}/`,
    meta: cc,
  }));
  const index = [...countryItems, ...brandItems];
  return new Response(JSON.stringify(index), { headers: { 'Content-Type': 'application/json' } });
}
