# User reports: setup

One-time setup for the report submission system (Worker + D1 + Turnstile).
All commands run from the repo root on your Mac.

## 1. Create the D1 database
```
npx wrangler d1 create wce-reports
```
Copy the `database_id` it prints into `wrangler.jsonc`, replacing
`REPLACE-WITH-YOUR-D1-DATABASE-ID` (that string is a placeholder — the deploy
fails if it's left in). Then apply the schema:
```
npx wrangler d1 execute wce-reports --remote --file=migrations/0001_reports.sql
```

## 2. Create a Turnstile widget
Cloudflare dashboard -> Turnstile -> Add site -> domain
`whichcryptoexchange.com`, mode Managed. It gives you a **site key**
(public) and a **secret key**.

## 3. Set the secrets
```
npx wrangler secret put TURNSTILE_SECRET   # paste the Turnstile secret key
npx wrangler secret put ADMIN_KEY          # invent a long random string
npx wrangler secret put IP_SALT            # invent another long random string
```

## 4. Set the public site key for the build
The form only renders when the build knows the Turnstile site key. In the
Cloudflare build settings for this project add an environment variable:
```
PUBLIC_TURNSTILE_SITEKEY = <your Turnstile site key>
```
(For local builds: `PUBLIC_TURNSTILE_SITEKEY=xxx npm run build`.)

## 5. Deploy
Commit + push; the connected build deploys. Or manually:
```
npm run build && npx wrangler deploy
```

## Moderation
Pending reports: `https://whichcryptoexchange.com/admin/reports?key=YOUR_ADMIN_KEY`
Approve/reject per row. Only approved reports appear in the public
aggregates at `/api/reports/<exchange-id>` and on exchange pages.
Editorial rule: user reports are displayed as community data, always
separate from regulator-sourced status. Never merge the two without a
`user-reported` provenance tag.

## Data model
See `migrations/0001_reports.sql`. Rate limit: 5 submissions per IP per
24h via salted IP hash (raw IPs are never stored).
