// Small dedicated index for the site-wide search box -- deliberately not
// the full /api/exchanges.json (1MB+): just enough per brand to filter and
// link, fetched once client-side by public/search.js.
import { loadExchanges } from '../../lib/data.js';

export function GET() {
  const exchanges = loadExchanges();
  const index = exchanges.map((ex) => ({
    id: ex.id,
    brand: ex.brand,
    jurisdictions: Object.keys(ex.countries ?? {}).length,
  }));
  return new Response(JSON.stringify(index), { headers: { 'Content-Type': 'application/json' } });
}
