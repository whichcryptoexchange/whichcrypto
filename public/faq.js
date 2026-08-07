// /faq/ search + filter. Same "fetch a small index once, filter client-side"
// pattern as search.js, but rendered as an accordion rather than a dropdown,
// and with a category filter (general/country/brand) on top of the search
// box. Default (no query, "All" category) shows only the general questions
// -- the whole point is a searchable tool, not a 445-item dump. Browsing a
// specific category (or a search with many matches) paginates via a "Show
// more" button rather than silently truncating with no way to see the rest.
(() => {
  const input = document.getElementById('faq-search');
  const results = document.getElementById('faq-results');
  const chips = document.querySelectorAll('.faq-chip');
  if (!input || !results) return;

  const PAGE_SIZE = 50;
  let index = null;
  let indexPromise = null;
  let activeCategory = 'all';
  let visibleCount = PAGE_SIZE;

  const loadIndex = () => {
    if (!indexPromise) {
      indexPromise = fetch('/api/faq-index.json')
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => { index = d; runSearch(); })
        .catch(() => { index = []; runSearch(); });
    }
    return indexPromise;
  };

  const CATEGORY_LINK_LABEL = {
    brand: 'View full record →',
    country: 'View country page →',
    general: 'Read more →',
  };

  const render = (items, { showingDefault, remaining }) => {
    results.innerHTML = '';
    if (!items.length) {
      const p = document.createElement('p');
      p.className = 'sourced';
      p.innerHTML = 'No matching questions. Try a different search, or <a href="/contact/">ask us directly</a>.';
      results.append(p);
      return;
    }
    if (showingDefault) {
      const p = document.createElement('p');
      p.className = 'sourced faq-default-note';
      p.textContent = 'Showing general questions — search for a brand or country to see more.';
      results.append(p);
    }
    for (const item of items) {
      const details = document.createElement('details');
      details.className = 'faq-item';
      const summary = document.createElement('summary');
      summary.textContent = item.question;
      details.append(summary);
      const answer = document.createElement('p');
      answer.textContent = item.answer;
      details.append(answer);
      const a = document.createElement('a');
      a.href = item.href;
      a.className = 'faq-source-link';
      a.textContent = CATEGORY_LINK_LABEL[item.category] ?? 'Read more →';
      details.append(a);
      results.append(details);
    }
    if (remaining > 0) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'faq-load-more';
      btn.textContent = `Show ${Math.min(PAGE_SIZE, remaining)} more (${remaining} remaining)`;
      btn.addEventListener('click', () => { visibleCount += PAGE_SIZE; runSearch(); });
      results.append(btn);
    }
  };

  const runSearch = () => {
    if (!index) return;
    const q = input.value.trim().toLowerCase();
    let pool = activeCategory === 'all' ? index : index.filter((e) => e.category === activeCategory);

    if (!q) {
      if (activeCategory === 'all') {
        render(index.filter((e) => e.category === 'general'), { showingDefault: true, remaining: 0 });
        return;
      }
      render(pool.slice(0, visibleCount), { showingDefault: false, remaining: Math.max(0, pool.length - visibleCount) });
      return;
    }

    const scored = pool
      .map((e) => {
        const qPos = e.question.toLowerCase().indexOf(q);
        if (qPos !== -1) return { e, rank: 0, pos: qPos };
        const aPos = e.answer.toLowerCase().indexOf(q);
        return aPos === -1 ? null : { e, rank: 1, pos: aPos };
      })
      .filter(Boolean)
      .sort((a, b) => a.rank - b.rank || a.pos - b.pos)
      .map((s) => s.e);
    render(scored.slice(0, visibleCount), { showingDefault: false, remaining: Math.max(0, scored.length - visibleCount) });
  };

  input.addEventListener('input', () => { visibleCount = PAGE_SIZE; runSearch(); });

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chips.forEach((c) => c.classList.toggle('active', c === chip));
      activeCategory = chip.dataset.category;
      visibleCount = PAGE_SIZE;
      runSearch();
    });
  });

  // This page's whole purpose is searching the index, unlike the small nav
  // search box on every other page -- load it immediately, not on focus.
  loadIndex();
})();
