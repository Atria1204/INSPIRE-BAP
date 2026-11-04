// Supply-to-equipment twin for one part: Supplier -> Warehouse -> Equipment.
// A schematic flow, not a map: the data has no supplier location, route or freight (INSpire Logistics rule).
// "Play" drives the warehouse level with one simulated year from Policy Lab.
function renderFlow(el, d) {
  const W = 1100, H = 250;
  // layout: supplier 10-260 | arrow 272-398 | tags -488 | tank 500-620 | arrow 636-798 | equipment 810-1090
  const tankX = 500, tankW = 120, tankY = 52, tankH = 156;
  const cap = Math.max(d.rec_max, d.max_now, d.stock, 1) * 1.12;
  const yOf = v => tankY + tankH - Math.max(0, Math.min(v, cap)) / cap * tankH;
  const supW = Math.max(4, Math.min(9, 4 + d.bought_per_month / 8)), useW = Math.max(4, Math.min(9, 4 + d.used_per_month / 8));
  const short = d.stock <= 0;
  const fmt = v => v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(1);
  const tag = (v, cls, txt) => `<line class="${cls}" x1="${tankX - 6}" x2="${tankX + tankW + 6}" y1="${yOf(v)}" y2="${yOf(v)}"/>` +
    `<text class="fl-tag ${cls.includes('now') ? 'red' : 'teal'}" x="${tankX - 12}" y="${yOf(v) + 4}" text-anchor="end">${txt}</text>`;
  el.innerHTML = `
  <svg viewBox="0 0 ${W} ${H}" class="flow-svg" role="img" aria-label="Flow from supplier to warehouse to equipment">
    <defs>
      <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="22" markerHeight="22" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#8494aa"/></marker>
      <marker id="ahr" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="22" markerHeight="22" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#c93434"/></marker>
    </defs>
    <g class="fl-node"><rect x="10" y="30" width="250" height="190" rx="14"/>
      <text class="fl-k" x="28" y="58">SUPPLIER</text>
      <text class="fl-name" x="28" y="82">${esc((s => s.length > 24 ? s.slice(0, 23) + '…' : s)(d.supplier || 'Never purchased'))}</text>
      <text class="fl-big" x="28" y="126">${d.lead_days} days</text><text class="fl-s" x="28" y="146">promised lead time</text>
      <text class="fl-s" x="28" y="176">${d.pos} POs · ${d.bought.toLocaleString()} ${d.unit} requested</text>
      ${d.late_share ? `<text class="fl-warn" x="28" y="200">${Math.round(d.late_share * 100)}% promised later than asked</text>` : ''}</g>

    <text class="fl-flow" x="335" y="106" text-anchor="middle">${fmt(d.bought_per_month)} ${d.unit}/mo</text>
    <line id="flIn" class="fl-arrow" x1="272" y1="125" x2="396" y2="125" stroke-width="${supW}" marker-end="url(#ah)"/>
    <text class="fl-s" x="335" y="156" text-anchor="middle">requested on PRs</text>

    <text class="fl-k" x="${tankX + tankW / 2}" y="40" text-anchor="middle">WAREHOUSE</text>
    <rect class="fl-tank" x="${tankX}" y="${tankY}" width="${tankW}" height="${tankH}" rx="10"/>
    <rect id="flLevel" class="fl-level ${short ? 'empty' : ''}" x="${tankX + 4}" y="${yOf(d.stock)}" width="${tankW - 8}" height="${Math.max(0, tankY + tankH - 4 - yOf(d.stock))}" rx="7"/>
    ${tag(d.rec_max, 'fl-min-rec dim', `New Max ${d.rec_max}`)}
    ${tag(d.rec_min, 'fl-min-rec', `New Min ${d.rec_min}`)}
    ${tag(d.min_now, 'fl-min-now', `Min now ${d.min_now}`)}
    <text id="flStock" class="fl-stock ${short ? 'red' : ''}" x="${tankX + tankW / 2}" y="${tankY + tankH + 26}" text-anchor="middle">${Math.round(d.stock).toLocaleString()} ${d.unit} on hand</text>

    <text class="fl-flow" x="717" y="106" text-anchor="middle">${fmt(d.used_per_month)} ${d.unit}/mo</text>
    <line id="flOut" class="fl-arrow ${short ? 'short' : ''}" x1="636" y1="125" x2="796" y2="125" stroke-width="${useW}" marker-end="url(#${short ? 'ahr' : 'ah'})"/>
    <text class="fl-s ${short ? 'red' : ''}" x="717" y="156" text-anchor="middle" id="flOutLbl">${short ? 'jobs would wait' : 'issued to jobs'}</text>

    <g class="fl-node"><rect x="810" y="30" width="280" height="190" rx="14"/>
      <text class="fl-k" x="828" y="58">EQUIPMENT</text>
      <text class="fl-big" x="828" y="100">${d.locations} <tspan class="fl-s">locations</tspan></text>
      ${d.cats.slice(0, 3).map((c, i) => `<text class="fl-s" x="828" y="${130 + i * 20}">${esc(c.category)} · <tspan class="fl-strong">${c.n}</tspan></text>`).join('')}
      <text class="${d.emergency ? 'fl-warn' : 'fl-s'}" x="828" y="202">${d.emergency} emergency notifications</text></g>
  </svg>`;
  el._d = d; el._yOf = yOf; el._tank = { tankY, tankH };
}

async function playFlow(el, btn, policy) {
  const d = el._d; if (!d || btn.disabled) return;
  document.querySelectorAll('.flow-play').forEach(b => b.disabled = true);
  const label = btn.innerHTML; btn.innerHTML = '<span class="spin"></span> simulating…';
  const r = await (await fetch(`/api/twin/${d.material}?reps=40`)).json();
  const path = r.policies[policy].sample_path;
  const lvl = el.querySelector('#flLevel'), st = el.querySelector('#flStock'), inn = el.querySelector('#flIn'), out = el.querySelector('#flOut'), outL = el.querySelector('#flOutLbl');
  const day = document.getElementById('flowDay');
  const { tankY, tankH } = el._tank, yOf = el._yOf;
  const name = policy === 'current' ? 'Current Min/Max' : 'Recommended Min/Max';
  let i = 0, shortDays = 0;
  btn.innerHTML = '<i class="fa-solid fa-circle-play"></i> playing…';
  const tick = () => {
    if (i >= path.length) {
      document.querySelectorAll('.flow-play').forEach(b => b.disabled = false); btn.innerHTML = label;
      day.innerHTML = `<b>${name}:</b> <mark class="${shortDays > 30 ? 'm-crit' : 'm-violet'}">${shortDays} of 365 days with jobs waiting</mark>`; return;
    }
    const v = path[i], prev = i ? path[i - 1] : v, y = yOf(v);
    lvl.setAttribute('y', y); lvl.setAttribute('height', Math.max(0, tankY + tankH - 4 - y));
    lvl.classList.toggle('empty', v <= 0);
    st.textContent = v >= 0 ? `${Math.round(v)} ${d.unit} on hand` : `${Math.round(-v)} ${d.unit} owed to jobs`;
    st.classList.toggle('red', v <= 0);
    inn.classList.toggle('pulse', v > prev + 0.5);
    out.classList.toggle('short', v < 0);
    outL.textContent = v < 0 ? 'jobs waiting' : 'issued to jobs';
    outL.classList.toggle('red', v < 0);
    if (v < 0) shortDays++;
    day.innerHTML = `<b>${name}</b> · day ${i + 1} of 365`;
    i++; setTimeout(tick, 14);
  };
  tick();
}
