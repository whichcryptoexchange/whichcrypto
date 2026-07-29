// Downloadable, normalised (one row per brand-country-entity) snapshot of
// the register -- meant for journalists/analysts doing their own numbers,
// not for the site itself. Alongside /api/exchanges.json (full nested
// JSON) for anyone who wants the raw structure instead.
import { loadExchanges } from '../../lib/data.js';

function csvField(v) {
  const s = v == null ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toRows(exchanges) {
  const rows = [];
  for (const ex of exchanges) {
    for (const [cc, entry] of Object.entries(ex.countries ?? {})) {
      const list = Array.isArray(entry) ? entry : [entry];
      for (const e of list) {
        rows.push([ex.id, ex.brand, cc, e.status ?? '', e.regime ?? '', e.entity ?? '', e.since ?? '']);
      }
    }
  }
  return rows;
}

export function GET() {
  const exchanges = loadExchanges();
  const asOf = new Date().toISOString().slice(0, 10);
  const header = ['brand_id', 'brand', 'country_code', 'status', 'regime', 'entity', 'since'];
  const lines = [header, ...toRows(exchanges)].map((r) => r.map(csvField).join(','));
  return new Response(lines.join('\n') + '\n', {
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="whichcryptoexchange-register-snapshot-${asOf}.csv"`,
    },
  });
}
