// RSS 2.0 feed of news mentions -- same hand-rolled pattern as
// changelog.xml.js. Chronological (newest first) rather than the
// regulatory-first sort news.astro uses for display: an RSS reader
// expects a feed to move forward in time, not have items jump around
// as new regulatory-tagged entries arrive and get pinned above older
// unread ones.
import { loadExchanges } from '../lib/data.js';

const SITE = 'https://whichcryptoexchange.com';

function escapeXml(s) {
  return String(s ?? '').replace(/[<>&'"]/g, (c) => ({
    '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;',
  })[c]);
}

export function GET() {
  const exchanges = loadExchanges();
  const rows = exchanges
    .flatMap((ex) => (ex.news_mentions ?? []).map((n) => ({ ex, ...n })))
    .sort((a, b) => (b.published || '').localeCompare(a.published || ''))
    .slice(0, 100);

  const items = rows.map((r) => `
    <item>
      <title>${escapeXml(`${r.ex.brand}: ${r.title}`)}</title>
      <link>${escapeXml(r.url)}</link>
      <guid isPermaLink="true">${escapeXml(r.url)}</guid>
      ${r.published ? `<pubDate>${new Date(r.published).toUTCString()}</pubDate>` : ''}
      <description>${escapeXml(
        `${r.category === 'regulatory' ? 'Regulatory' : 'General'} — ${r.source}${r.published ? ` — ${r.published}` : ''}`
      )}</description>
    </item>`).join('');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>whichcryptoexchange.com — Crypto Exchange News and Regulation Updates</title>
    <link>${SITE}/news/</link>
    <description>Headlines naming a tracked crypto exchange, tagged Regulatory or General — see /news/ for what those tags mean.</description>
    <language>en</language>
    <atom:link xmlns:atom="http://www.w3.org/2005/Atom" href="${SITE}/news.xml" rel="self" type="application/rss+xml" />${items}
  </channel>
</rss>
`;

  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
