import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { loadExchanges } from './src/lib/data.js';

// Per-brand and per-country "freshest data we actually have" date, used
// as each sitemap entry's lastmod -- built from the same `retrieved`
// dates already shown on the page itself, not a fabricated "everything
// changed today" stamp (which Google explicitly discounts as a signal).
const exchanges = loadExchanges();

function maxRetrieved(ex) {
  const dates = [
    ...(ex.sources ?? []).map((s) => s.retrieved),
    ...(ex.third_party_reviews ?? []).map((r) => r.retrieved),
    ...(ex.news_mentions ?? []).map((n) => n.retrieved),
    ...(ex.company_facts ?? []).map((c) => c.retrieved),
    ...(ex.notable_incidents ?? []).map((i) => i.retrieved),
  ].filter(Boolean);
  return dates.sort().at(-1);
}

const brandLastmod = {};
const countryLastmod = {};
for (const ex of exchanges) {
  const d = maxRetrieved(ex);
  if (!d) continue;
  brandLastmod[ex.id] = d;
  for (const cc of Object.keys(ex.countries ?? {})) {
    if (!countryLastmod[cc] || d > countryLastmod[cc]) countryLastmod[cc] = d;
  }
}

export default defineConfig({
  site: 'https://whichcryptoexchange.com',
  trailingSlash: 'always',
  integrations: [
    sitemap({
      serialize(item) {
        const pathname = new URL(item.url).pathname;
        const brandMatch = pathname.match(/^\/exchange\/([a-z0-9-]+)\/$/);
        if (brandMatch && brandLastmod[brandMatch[1]]) {
          return { ...item, lastmod: brandLastmod[brandMatch[1]] };
        }
        const countryMatch = pathname.match(/^\/([a-z]{2})\/$/);
        if (countryMatch && countryLastmod[countryMatch[1].toUpperCase()]) {
          return { ...item, lastmod: countryLastmod[countryMatch[1].toUpperCase()] };
        }
        return item;
      },
    }),
  ],
});
