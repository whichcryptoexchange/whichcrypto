// Small dedicated index for the site-wide search box -- deliberately not
// the full /api/exchanges.json (1MB+): just enough per brand (or country)
// to filter and link, fetched once client-side by public/search.js.
import { loadExchanges, countriesInData, COUNTRY_NAMES } from '../../lib/data.js';

export function GET() {
  const exchanges = loadExchanges();
  const brandItems = exchanges.map((ex) => ({
    type: 'exchange',
    label: ex.brand,
    href: `/exchange/${ex.id}/`,
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
