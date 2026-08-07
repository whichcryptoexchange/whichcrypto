// RSS 2.0 feed of the changelog -- hand-rolled rather than pulling in
// @astrojs/rss for one feed, following the same GET()-returns-Response
// pattern as the other src/pages/api/*.{csv,json}.js endpoints.
import { loadChangelog } from '../lib/data.js';

const SITE = 'https://whichcryptoexchange.com';

function escapeXml(s) {
  return String(s ?? '').replace(/[<>&'"]/g, (c) => ({
    '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;',
  })[c]);
}

export function GET() {
  const entries = loadChangelog();
  const items = entries.map((e) => `
    <item>
      <title>${escapeXml(e.title)}</title>
      <link>${SITE}/changelog/</link>
      <guid isPermaLink="false">${escapeXml(`${e.date}-${e.title}`)}</guid>
      <pubDate>${new Date(e.date).toUTCString()}</pubDate>
      <description>${escapeXml(e.body.trim())}</description>
    </item>`).join('');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>whichcryptoexchange.com — Changelog</title>
    <link>${SITE}/changelog/</link>
    <description>Changes to the independent crypto-exchange regulatory register.</description>
    <language>en</language>
    <atom:link xmlns:atom="http://www.w3.org/2005/Atom" href="${SITE}/changelog.xml" rel="self" type="application/rss+xml" />${items}
  </channel>
</rss>
`;

  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
