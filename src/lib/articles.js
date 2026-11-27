// Long-form /learn/ articles: data/articles/<slug>.md, YAML frontmatter plus
// a Markdown body whose citations are GFM footnotes ([^key] ... [^key]: [Title](url)).
// Same sourcing rule as data/licensing_guides/: every regulatory claim cites
// the regulator or legislation, nothing from memory or secondary summaries.
//
// Bodies can embed live register figures as {{token:args}}, resolved at
// build time from data/exchanges/*.yaml so the numbers never go stale
// between edits:
//   {{home_count:DE}}        entries on ESMA's register with home state DE
//   {{home_brands:DE:8}}     first 8 of those brands, linked, comma-joined
//   {{country_count:AE}}     brands with any entry for that country page
//   {{nca_table:12}}         Markdown table of the top 12 home authorities
//   {{synced}}               date the register data was last synced
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';
import { createMarkdownProcessor } from '@astrojs/markdown-remark';
import { footerStats } from './data.js';

const DIR = path.resolve('data/articles');
const REQUIRED = ['title', 'description', 'audience', 'updated'];

function parse(file) {
  const raw = fs.readFileSync(path.join(DIR, file), 'utf8');
  const m = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!m) throw new Error(`article ${file}: missing frontmatter`);
  const meta = yaml.load(m[1]);
  for (const k of REQUIRED) if (!meta[k]) throw new Error(`article ${file}: missing ${k}`);
  return { slug: file.replace(/\.md$/, ''), ...meta, body: m[2] };
}

function homeEntries(exchanges) {
  const byState = {};
  const byAuthority = {};
  for (const ex of exchanges) {
    for (const ent of ex.entities ?? []) {
      if (!ent.home_state || !ent.records?.some((r) => r.status === 'authorised')) continue;
      (byState[ent.home_state] ??= new Map()).set(ex.id, ex);
      byAuthority[ent.regulator] = (byAuthority[ent.regulator] ?? 0) + 1;
    }
  }
  return { byState, byAuthority };
}

function resolveTokens(body, exchanges, slug) {
  const { byState, byAuthority } = homeEntries(exchanges);
  return body.replace(/\{\{(\w+)(?::([^}]*))?\}\}/g, (_, name, args = '') => {
    const [a, b] = args.split(':');
    switch (name) {
      case 'home_count':
        return String(byState[a]?.size ?? 0);
      case 'home_brands':
        return [...(byState[a]?.values() ?? [])]
          .slice(0, Number(b) || 8)
          .map((ex) => `[${ex.brand}](/exchange/${ex.id}/)`)
          .join(', ');
      case 'country_count':
        return String(exchanges.filter((ex) => ex.countries?.[a]).length);
      case 'nca_table': {
        const rows = Object.entries(byAuthority).sort((x, y) => y[1] - x[1]).slice(0, Number(a) || 12);
        return ['| Home authority | Register entries |', '|---|---|', ...rows.map(([n, c]) => `| ${n} | ${c} |`)].join('\n');
      }
      case 'synced':
        return footerStats(exchanges).lastSynced;
      default:
        throw new Error(`article ${slug}: unknown token {{${name}}}`);
    }
  });
}

let processor;
export async function loadArticles(exchanges) {
  if (!fs.existsSync(DIR)) return [];
  processor ??= await createMarkdownProcessor({ gfm: true });
  const articles = fs.readdirSync(DIR).filter((f) => f.endsWith('.md')).map(parse);
  const slugs = new Set(articles.map((a) => a.slug));
  for (const a of articles) {
    for (const r of a.related ?? []) if (!slugs.has(r)) throw new Error(`article ${a.slug}: related "${r}" not found`);
    const md = resolveTokens(a.body, exchanges, a.slug);
    // An unresolved [^ref] renders as literal text rather than failing, so
    // check every reference has a definition before trusting the output.
    const refs = new Set([...md.matchAll(/\[\^([^\]]+)\](?!:)/g)].map((x) => x[1]));
    const defs = new Set([...md.matchAll(/^\[\^([^\]]+)\]:/gm)].map((x) => x[1]));
    for (const r of refs) if (!defs.has(r)) throw new Error(`article ${a.slug}: citation [^${r}] has no source`);
    a.html = (await processor.render(md)).code;
  }
  return articles.sort((x, y) => (x.order ?? 99) - (y.order ?? 99));
}
