# whichcryptoexchange.com

An independent, machine-readable register answering one question: **which crypto
exchanges are licensed in your country?** Built from official regulator
registers, with every change tracked in Git history.

## Architecture

Static Astro site on Cloudflare Pages. The dataset is the product; pages are a
projection of it.

```
data/exchanges/*.yaml    one file per exchange brand (generated + curated)
data/brand_map.yaml      curated LEI -> brand mapping (manual, the moat)
data/registry/           machine artefacts (per-source summaries)
scripts/esma_sync.py     ESMA CASP register normaliser
tests/fixtures/          verbatim source samples used as parser tests
src/pages/index.astro    country picker (geo-suggested via user_country cookie)
src/pages/[country].astro  /de/, /fr/, ... one static page per country
src/pages/exchange/[id].astro  per-exchange registry record
src/pages/api/exchanges.json.js  free JSON endpoint of the full register
.github/workflows/esma-sync.yml  twice-weekly fetch -> diff -> PR
```

## Data pipeline

1. CI fetches the raw register (currently: [ESMA interim MiCA register](https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation/markets-crypto-assets-regulation-mica),
   `CASPS.csv`, republished roughly weekly).
2. `esma_sync.py` normalises it — see the docstring for the catalogue of
   real-world defects it corrects (mixed separators, `EL`/`GR`, `SL` typos,
   duplicate rows, two date formats, withdrawn records).
3. Entities are grouped by LEI, then mapped to consumer brands via
   `data/brand_map.yaml`. **Every new brand in a sync PR needs a mapping
   entry** — that mapping is manual curation the raw register cannot provide.
4. Changes arrive as a PR. Git history is the changelog; status changes are
   content opportunities.

## Local development

```
npm install
python3 scripts/esma_sync.py --input tests/fixtures/CASPS_sample_2026-07-24.csv
npm run dev
```

## Country status model

Per exchange, per country, one of:

- `licensed` — authorised by that country's regulator or passported into it
  (currently derived from ESMA data; the record names entity, regime, and route)
- `accessible` — accepts residents without local authorisation *(curated —
  not yet populated)*
- `restricted` — geo-blocks or excludes the country in its terms *(curated)*
- `warned` — appears on that jurisdiction's regulator warning list
  *(next source: ESMA `NCASP.csv`, FCA warning list)*

## Roadmap: additional sources

In order: ESMA `NCASP.csv` (non-compliant entities) -> UK FCA cryptoasset
register (API) -> Singapore MAS directory -> Dubai VARA register -> Hong Kong
SFC VATP list -> Japan FSA list -> US state money-transmitter grind (NMLS).

## Editorial rules

Licence status comes from registers, never from us. If a claim cannot be
traced to an official source, it does not ship. The site is not affiliated
with any regulator and nothing on it is financial advice.
