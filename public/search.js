// Site-wide brand search. Progressive enhancement: fetches the small
// search index once, then filters client-side as you type -- no server
// round trip per keystroke. Wired up on any page that has a
// #site-search input + #site-search-results container in its header.
(() => {
  const input = document.getElementById('site-search');
  const results = document.getElementById('site-search-results');
  if (!input || !results) return;

  let index = null;
  let indexPromise = null;
  const loadIndex = () => {
    if (!indexPromise) {
      indexPromise = fetch('/api/search-index.json')
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => { index = d; })
        .catch(() => { index = []; });
    }
    return indexPromise;
  };

  let active = -1;

  const render = (matches) => {
    results.innerHTML = '';
    active = -1;
    if (!matches.length) { results.hidden = true; return; }
    for (const m of matches) {
      const a = document.createElement('a');
      a.href = m.href;
      a.className = 'site-search-item';
      a.textContent = m.label;
      if (m.meta) {
        const span = document.createElement('span');
        span.className = 'site-search-meta';
        span.textContent = m.meta;
        a.append(span);
      }
      results.append(a);
    }
    results.hidden = false;
  };

  // Countries surface first on an exact/prefix code match (typing "DE"
  // should find Germany before any brand containing "de"), then brand-label
  // matches by how early the needle appears, then legal-entity-name (alias)
  // matches -- e.g. "Block" finds Cash App (licensed as Block, Inc.) even
  // though "Block" never appears in the displayed label.
  const search = (q) => {
    if (!q) { render([]); return; }
    const needle = q.toLowerCase();
    const scored = (index ?? [])
      .map((e) => {
        const labelPos = e.label.toLowerCase().indexOf(needle);
        if (labelPos !== -1) return { e, rank: 0, pos: labelPos };
        if (e.meta?.toLowerCase() === needle) return { e, rank: 0, pos: 0 };
        const aliasPos = (e.aliases ?? [])
          .map((a) => a.toLowerCase().indexOf(needle))
          .filter((i) => i !== -1)
          .sort((a, b) => a - b)[0];
        return aliasPos === undefined ? null : { e, rank: 1, pos: aliasPos };
      })
      .filter(Boolean)
      .sort((a, b) => {
        const aCode = a.e.type === 'country' && a.e.meta.toLowerCase() === needle ? 0 : 1;
        const bCode = b.e.type === 'country' && b.e.meta.toLowerCase() === needle ? 0 : 1;
        if (aCode !== bCode) return aCode - bCode;
        if (a.rank !== b.rank) return a.rank - b.rank;
        return a.pos - b.pos;
      })
      .map((s) => s.e)
      // 12 rather than 8 -- the results box already scrolls, and a common
      // substring like "block" can have 8+ genuine label matches (BlockBen,
      // Fireblocks, Blockchain.com...) before an alias match like Cash App
      // (licensed as Block, Inc.) gets a chance to appear at all.
      .slice(0, 12);
    render(scored);
  };

  input.addEventListener('focus', loadIndex);
  input.addEventListener('input', () => loadIndex().then(() => search(input.value.trim())));

  input.addEventListener('keydown', (e) => {
    const items = [...results.querySelectorAll('.site-search-item')];
    if (!items.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      active = (active + 1) % items.length;
      items.forEach((el, i) => el.classList.toggle('active', i === active));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active - 1 + items.length) % items.length;
      items.forEach((el, i) => el.classList.toggle('active', i === active));
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault();
      items[active].click();
    } else if (e.key === 'Escape') {
      render([]);
      input.blur();
    }
  });

  document.addEventListener('click', (e) => {
    if (!results.contains(e.target) && e.target !== input) render([]);
  });
})();

// Weekly digest signup -- shared across every top-level page so the form
// markup + Turnstile widget don't need a duplicated inline handler on each.
(() => {
  const form = document.getElementById('digest-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = form.querySelector('.form-msg');
    const fd = new FormData(form);
    const token = form.querySelector('[name="cf-turnstile-response"]')?.value;
    msg.textContent = 'Submitting…';
    try {
      const res = await fetch('/api/digest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: fd.get('email'), consent: fd.get('consent') === 'on', turnstile_token: token,
        }),
      });
      const data = await res.json();
      msg.textContent = data.message ?? data.error ?? 'Something went wrong.';
      if (res.ok) form.reset();
    } catch { msg.textContent = 'Network error — please try again.'; }
  });
})();
