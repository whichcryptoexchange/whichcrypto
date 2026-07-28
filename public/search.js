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
  // should find Germany before any brand containing "de"), otherwise
  // matches are ranked by how early the needle appears in the label.
  const search = (q) => {
    if (!q) { render([]); return; }
    const needle = q.toLowerCase();
    render(
      (index ?? [])
        .filter((e) => e.label.toLowerCase().includes(needle) || e.meta?.toLowerCase() === needle)
        .sort((a, b) => {
          const aCode = a.type === 'country' && a.meta.toLowerCase() === needle ? 0 : 1;
          const bCode = b.type === 'country' && b.meta.toLowerCase() === needle ? 0 : 1;
          if (aCode !== bCode) return aCode - bCode;
          return a.label.toLowerCase().indexOf(needle) - b.label.toLowerCase().indexOf(needle);
        })
        .slice(0, 8)
    );
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
