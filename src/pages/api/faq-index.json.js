// Dedicated index for the /faq/ search box -- same "small, purpose-built,
// fetched once client-side" pattern as /api/search-index.json.js.
import { loadExchanges, loadRegulatorDetails } from '../../lib/data.js';
import { buildFaqEntries } from '../../lib/faq.js';

export function GET() {
  const exchanges = loadExchanges();
  const regulatorDetails = loadRegulatorDetails();
  const entries = buildFaqEntries(exchanges, regulatorDetails);
  return new Response(JSON.stringify(entries), { headers: { 'Content-Type': 'application/json' } });
}
