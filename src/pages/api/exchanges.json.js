// Free machine-readable endpoint: the whole register as JSON, rebuilt on deploy.
import { loadExchanges } from '../../lib/data.js';

export function GET() {
  const exchanges = loadExchanges();
  return new Response(JSON.stringify({
    source: 'https://whichcryptoexchange.com',
    licence: 'Data derived from official public registers; attribution appreciated.',
    generated: new Date().toISOString().slice(0, 10),
    exchanges,
  }, null, 2), { headers: { 'Content-Type': 'application/json' } });
}
