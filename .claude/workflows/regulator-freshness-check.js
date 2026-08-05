export const meta = {
  name: 'regulator-freshness-check',
  description: 'Re-verify regulator_details.yaml facts against live primary sources, flag drift or unverifiable claims',
  whenToUse: 'Run periodically (e.g. quarterly) to catch stale or incorrect regulatory facts (capital figures, tier classification, checks) before they mislead readers -- built after a real incident where an unverified AI-search claim about four Korean brands went live without being checked against the primary source.',
  phases: [
    { title: 'Load', detail: 'read data/regulator_details.yaml' },
    { title: 'Check', detail: 'one agent per regulator, fetch source_url and adversarially verify each stated fact' },
    { title: 'Synthesize', detail: 'compile a findings report' },
  ],
}

const LOAD_SCHEMA = {
  type: 'object',
  properties: {
    entries: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          code: { type: 'string' },
          name: { type: 'string' },
          tier: { type: 'string' },
          tier_label: { type: 'string' },
          scope: { type: 'string' },
          capital: { type: 'string' },
          checks: { type: 'array', items: { type: 'string' } },
          note: { type: 'string' },
          source_url: { type: 'string' },
          verified: { type: 'string' },
        },
        required: ['code', 'name', 'source_url'],
      },
    },
  },
  required: ['entries'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    code: { type: 'string' },
    overall: { type: 'string', enum: ['confirmed', 'drift', 'unverifiable'] },
    capital_status: { type: 'string', enum: ['confirmed', 'drift', 'unverifiable'] },
    capital_note: { type: 'string' },
    checks_status: { type: 'string', enum: ['confirmed', 'drift', 'unverifiable'] },
    checks_note: { type: 'string' },
    tier_status: { type: 'string', enum: ['confirmed', 'drift', 'unverifiable'] },
    tier_note: { type: 'string' },
    source_quality: { type: 'string', description: 'Was the source_url itself sufficient, or did verification require a supplementary search?' },
  },
  required: ['code', 'overall', 'capital_status', 'checks_status', 'tier_status'],
}

phase('Load')
const loaded = await agent(
  'Read data/regulator_details.yaml in the current repo and return its full contents as structured JSON matching the schema. Do not summarize or omit any entry -- return all of them, exactly as written (code, name, tier, tier_label, scope, capital, checks array, note if present, source_url, verified date).',
  { schema: LOAD_SCHEMA, label: 'load regulator_details.yaml' }
)
const entries = loaded.entries
log(`Loaded ${entries.length} regulator entries to verify`)

phase('Check')
const verdicts = await pipeline(
  entries,
  (entry) => agent(
    `You are adversarially fact-checking a regulatory claim published on a crypto-exchange register site. Do NOT confirm anything you cannot point to specific supporting text for -- if you are not certain, mark it "unverifiable", not "confirmed". A false "confirmed" here previously caused a real incident (an unverified claim about four companies had to be retracted after publication), so default to skepticism.

Regulator: ${entry.name} (${entry.code})
Currently stated on the site:
  - Tier: ${entry.tier_label}
  - Scope: ${entry.scope}
  - Capital requirement: ${entry.capital}
  - What it checks: ${(entry.checks || []).join('; ')}
  ${entry.note ? `- Note: ${entry.note}` : ''}
Source URL cited: ${entry.source_url}

Steps:
1. Fetch the source_url directly.
2. If it does not itself contain the capital figure or checks list (many regulator index pages just link out to a PDF/guideline), do ONE supplementary web search for the current official guideline/law and use that instead -- note this in source_quality.
3. For EACH of tier, capital, and checks: does the live source support what's currently stated? Quote or closely paraphrase the specific supporting text if confirmed. If the source contradicts it, or you cannot find support at all, do not mark it confirmed.
4. Return your verdict as structured output.`,
    { schema: VERDICT_SCHEMA, label: `verify ${entry.code}`, phase: 'Check' }
  )
)

phase('Synthesize')
const results = entries.map((entry, i) => ({ entry, verdict: verdicts[i] })).filter((r) => r.verdict)
const needsReview = results.filter((r) => r.verdict.overall !== 'confirmed')
log(`${results.length} checked, ${needsReview.length} need review`)

return {
  checked: results.length,
  clean: results.length - needsReview.length,
  needsReview: needsReview.map((r) => ({
    code: r.entry.code,
    name: r.entry.name,
    source_url: r.entry.source_url,
    overall: r.verdict.overall,
    tier: { status: r.verdict.tier_status, note: r.verdict.tier_note },
    capital: { status: r.verdict.capital_status, note: r.verdict.capital_note },
    checks: { status: r.verdict.checks_status, note: r.verdict.checks_note },
    source_quality: r.verdict.source_quality,
  })),
  allResults: results.map((r) => ({ code: r.entry.code, overall: r.verdict.overall })),
}
