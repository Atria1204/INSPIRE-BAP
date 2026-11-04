// INSpire motion layer (AETHER style): staggered reveal, count-up numbers, growing bars.
// Pure enhancement: every page renders fully without it, and it does nothing under prefers-reduced-motion.
(() => {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const main = document.querySelector('main');
  if (!main) return;

  // ---- 1. staggered reveal: siblings come in one after another
  const REVEAL = ['.card', '.panel', '.kpi-card', '.act-card', '.feat-card', '.flow-steps > a', '.decision', '.evidence-row > *',
                  '.si-box', '.page-banner', '.result-count', '.quick .qv'].map(s => 'main ' + s).join(',');
  const els = [...document.querySelectorAll(REVEAL)].filter(e => !e.closest('.rv') && !e.closest('.site-twin'));
  const order = new Map();
  const io = new IntersectionObserver(entries => entries.forEach(en => {
    if (!en.isIntersecting) return;
    show(en.target);
    io.unobserve(en.target);
  }), { threshold: 0.06 });
  function show(el) {
    if (!el.classList.contains('rv') || el.classList.contains('in')) return;
    const d = Math.min(+el.dataset.rvi || 0, 7) * 55;
    el.style.transitionDelay = d + 'ms';
    el.classList.add('in');
    setTimeout(() => { el.classList.remove('rv', 'in'); el.style.transitionDelay = ''; }, d + 600);
  }
  els.forEach(e => {
    const p = e.parentElement, n = order.get(p) || 0;
    order.set(p, n + 1);
    e.dataset.rvi = n;
    e.classList.add('rv');
    io.observe(e);
  });
  setTimeout(() => els.forEach(show), 1400);   // never leave anything hidden

  // ---- 2. count-up: the first number in a headline value rolls up from zero
  const COUNT = ['.kpi .value', '.kpi-value', '.act-num', '.dc-nums > div > b', '.flow-steps b', '.bn-big', '.zn-kpis b',
                 '.feat-nums b', '.result-count > b', '.si-bar b'].map(s => 'main ' + s).join(',');
  const NUM = /(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?/;
  document.querySelectorAll(COUNT).forEach(el => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode()) && !NUM.test(node.nodeValue)) { /* find first text with a number */ }
    if (!node) return;
    const txt = node.nodeValue;
    if (/\d\s*\/\s*\d|\d-\d/.test(el.textContent)) return;          // skip "29 / 54" and dates
    const m = txt.match(NUM), whole = m[1], dec = m[2] || '';
    const target = parseFloat(whole.replace(/,/g, '') + dec), places = dec ? dec.length - 1 : 0;
    if (!isFinite(target) || target === 0) return;
    const before = txt.slice(0, m.index), after = txt.slice(m.index + m[0].length), comma = whole.includes(',');
    const fmt = v => {
      let s = v.toFixed(places);
      if (comma) { const [i, f] = s.split('.'); s = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (f ? '.' + f : ''); }
      return before + s + after;
    };
    const t0 = Date.now() + 120, dur = 750;
    node.nodeValue = fmt(0);
    const timer = setInterval(() => {
      const k = Math.min(1, Math.max(0, (Date.now() - t0) / dur)), e = 1 - Math.pow(1 - k, 3);
      node.nodeValue = k < 1 ? fmt(target * e) : txt;
      if (k >= 1) clearInterval(timer);
    }, 16);
    setTimeout(() => { clearInterval(timer); node.nodeValue = txt; }, dur + 600);   // the real value always lands
  });

  // ---- 3. bars grow from the left
  document.querySelectorAll('main .meter > span, main .si-bar em, main .fill, main .seg').forEach((b, i) => {
    b.classList.add('ae-grow');
    b.style.animationDelay = (150 + Math.min(i, 12) * 40) + 'ms';
  });
})();
