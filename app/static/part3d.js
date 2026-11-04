/* Part twin, 3D isometric: supplier dock -> warehouse rack (stock as boxes, Min/Max lines) -> the equipment that uses it.
   Driven by one simulated year from /api/twin/<material> (the same engine as Policy Lab). Schematic, not a map. */
(function () {
  const C = Math.cos(Math.PI / 6), S = 0.5, U = 34, OX = 300, OY = 88;
  const P = (x, y, z = 0) => [OX + (x - y) * C * U, OY + (x + y) * S * U - z * U];
  const pts = a => a.map(p => p.join(',')).join(' ');
  const poly = (a, fill, extra = '') => `<polygon points="${pts(a)}" fill="${fill}" ${extra}/>`;
  function box(x, y, z, w, d, h, c, extra = '') {
    const top = [P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h)];
    const left = [P(x, y + d, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x, y + d, z + h)];
    const right = [P(x + w, y, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x + w, y, z + h)];
    return `<g ${extra}>${poly(top, c[0])}${poly(left, c[1])}${poly(right, c[2])}</g>`;
  }
  const label = (x, y, z, t, cls = 'p3-lbl') => { const [a, b] = P(x, y, z); return `<text x="${a}" y="${b}" class="${cls}" text-anchor="middle">${t}</text>`; };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const RACK = { x: 7, y: 1.1, w: 3.2, d: 1.1, levels: 5, lh: 0.78, per: 4 };
  const SLOTS = RACK.levels * RACK.per;

  window.renderPart3D = function (el, cfg) {
    const st = { pol: 'recommended', day: 0, timer: null, data: null };
    el.innerHTML = `
      <div class="p3-bar">
        <div class="p3-seg" role="group" aria-label="Min/Max used">
          <button type="button" data-pol="current"><i class="fa-solid fa-clock-rotate-left"></i> Today ${cfg.min_now}/${cfg.max_now}</button>
          <button type="button" data-pol="recommended" class="on"><i class="fa-solid fa-wand-magic-sparkles"></i> Proposed ${cfg.rec_min}/${cfg.rec_max}</button></div>
        <button type="button" class="p3-play" aria-label="Play the simulated year"><i class="fa-solid fa-play"></i></button>
        <input type="range" min="0" max="364" value="0" class="p3-day" aria-label="Day of the simulated year">
        <span class="p3-daylbl">Day 1</span>
      </div>
      <div class="p3-body"><div class="p3-wrap"><svg viewBox="110 0 620 450" class="p3-svg" role="img" aria-label="3D part twin"></svg></div>
        <div class="p3-side"><div class="p3-hud"></div><div class="p3-cmp"></div></div></div>`;
    const svg = el.querySelector('svg'), hud = el.querySelector('.p3-hud'), cmp = el.querySelector('.p3-cmp');
    const dayIn = el.querySelector('.p3-day'), dayLbl = el.querySelector('.p3-daylbl'), play = el.querySelector('.p3-play');

    // static scene
    const ground = poly([P(-0.5, -0.5), P(12.5, -0.5), P(12.5, 8.3), P(-0.5, 8.3)], '#eef2f8', 'stroke="#d5deeb"');
    const road = poly([P(3, 1.2), P(7, 1.2), P(7, 2), P(3, 2)], '#d9e1ec') + poly([P(8.2, 2.3), P(9, 2.3), P(9, 5.6), P(8.2, 5.6)], '#d9e1ec');
    const dock = box(0, 0, 0, 3, 3, 2.2, ['#c9d6ea', '#9fb3d3', '#b4c5df']) + box(0.4, 3, 0, 2.2, 0.15, 1.4, ['#7d93b8', '#6b82a8', '#7d93b8'])
               + label(1.5, 1.5, 3.1, 'Supplier') + label(1.5, 1.5, 2.65, esc(cfg.supplier || 'PO history'), 'p3-sub');
    let frame = '';
    for (let l = 0; l <= RACK.levels; l++) frame += box(RACK.x - 0.1, RACK.y - 0.05, l * RACK.lh, RACK.w + 0.2, RACK.d + 0.1, 0.06, ['#64748b', '#475569', '#56657d']);
    [[0, 0], [RACK.w, 0], [0, RACK.d], [RACK.w, RACK.d]].forEach(([dx, dy]) => frame += box(RACK.x + dx - 0.1, RACK.y + dy - 0.05, 0, 0.1, 0.1, RACK.levels * RACK.lh + 0.06, ['#475569', '#334155', '#3d4a5f']));
    const machine = box(7.4, 5.7, 0, 2.4, 2.2, 0.35, ['#cbd5e1', '#94a3b8', '#a8b5c7']) + box(7.7, 6.0, 0.35, 1.8, 1.6, 1.2, ['#a7c4ef', '#6f95cf', '#86a9dd'])
               + box(9.3, 6.5, 0.6, 0.9, 0.6, 0.55, ['#a7c4ef', '#6f95cf', '#86a9dd'])
               + label(8.6, 6.8, 2.5, esc(cfg.machine || 'Equipment')) + label(8.6, 6.8, 2.05, `${cfg.locations} location${cfg.locations === 1 ? '' : 's'}${cfg.emergency ? ` · ${cfg.emergency} emergency` : ''}`, 'p3-sub');
    const rackLbl = label(RACK.x + RACK.w / 2, RACK.y + RACK.d / 2, RACK.levels * RACK.lh + 1.5, 'Warehouse rack') + label(RACK.x + RACK.w / 2, RACK.y + RACK.d / 2, RACK.levels * RACK.lh + 1.05, `part ${esc(cfg.material)}`, 'p3-sub');

    const maxU = () => Math.max(1, cfg.rec_max, cfg.max_now || 0, cfg.stock, ...(st.data ? ['current', 'recommended'].flatMap(k => st.data.policies[k].sample_path) : [0]));
    const perBox = () => Math.max(1, Math.ceil(maxU() / SLOTS));
    const zOf = v => Math.min(RACK.levels, (v / perBox()) / RACK.per) * RACK.lh;

    function boxes(onHand, tone) {
      const n = Math.max(0, Math.min(SLOTS, Math.ceil(onHand / perBox())));
      const col = { ok: ['#f6c983', '#d99a3a', '#e8ae55'], low: ['#fbd38d', '#e0902a', '#eea544'], out: ['#f3b0b0', '#cf4b4b', '#e07070'] }[tone];
      let g = '';
      for (let i = 0; i < n; i++) {
        const l = Math.floor(i / RACK.per), c = i % RACK.per;
        g += box(RACK.x + 0.12 + c * (RACK.w / RACK.per), RACK.y + 0.18, l * RACK.lh + 0.06, RACK.w / RACK.per - 0.2, RACK.d - 0.36, RACK.lh - 0.2, col);
      }
      return g;
    }
    function line(v, color, txt) {
      const z = zOf(v), a = P(RACK.x - 0.4, RACK.y + RACK.d + 0.05, z), b = P(RACK.x + RACK.w + 0.4, RACK.y + RACK.d + 0.05, z);
      return `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${color}" stroke-width="2.5" stroke-dasharray="6 4"/>
        <text x="${b[0] + 6}" y="${b[1] + 4}" class="p3-line" fill="${color}">${txt}</text>`;
    }
    const truckAt = t => { // along dock -> rack
      const a = [3.4 + t * 3, 1.6];
      return box(a[0] - 0.6, a[1] - 0.35, 0, 1.2, 0.7, 0.55, ['#4f7fd1', '#2d5aa8', '#3c6cc0']) + box(a[0] + 0.6, a[1] - 0.35, 0, 0.4, 0.7, 0.4, ['#93b4ea', '#5d86cc', '#79a0e0']);
    };
    const cartAt = t => box(8.38, 2.5 + t * 2.9, 0, 0.45, 0.45, 0.35, ['#f6c983', '#d99a3a', '#e8ae55']);

    let anim = null;
    function draw(fx = '') {
      const path = st.data ? st.data.policies[st.pol].sample_path : [cfg.stock];
      const v = path[Math.min(st.day, path.length - 1)];
      const mn = st.pol === 'current' ? cfg.min_now : cfg.rec_min, mx = st.pol === 'current' ? cfg.max_now : cfg.rec_max;
      const tone = v <= 0 ? 'out' : v <= mn ? 'low' : 'ok';
      svg.innerHTML = ground + road + dock + frame + boxes(v, tone) + (mx ? line(mx, '#0d9a6b', `Max ${mx}`) : '') + line(mn, '#d97706', `Min ${mn}`)
        + rackLbl + machine + fx + (v <= 0 ? label(RACK.x + RACK.w / 2, RACK.y, 0.9, 'OUT OF STOCK', 'p3-alarm') : '');
      const shortSoFar = path.slice(0, st.day + 1).filter(x => x <= 0).length;
      hud.innerHTML = `<div><small>On the rack</small><b class="${tone}">${Math.max(0, Math.round(v))} ${esc(cfg.unit)}</b></div>
        <div><small>Days short so far</small><b class="${shortSoFar ? 'out' : ''}">${shortSoFar}</b></div>
        <div><small>1 box =</small><b>${perBox()} ${esc(cfg.unit)}</b></div>`;
      dayLbl.textContent = `Day ${st.day + 1} of 365`;
    }
    function step() {
      const path = st.data.policies[st.pol].sample_path, d = st.day;
      const diff = d > 0 ? path[d] - path[d - 1] : 0;
      let t = 0; clearInterval(anim);
      if (diff > 0) anim = setInterval(() => { t += 0.2; draw(truckAt(Math.min(1, t))); if (t >= 1) clearInterval(anim); }, 16);
      else if (diff < 0) anim = setInterval(() => { t += 0.25; draw(cartAt(Math.min(1, t))); if (t >= 1) clearInterval(anim); }, 16);
      else draw();
    }
    function compare() {
      const r = k => st.data.policies[k], days = k => r(k).sample_path.filter(x => x <= 0).length;
      cmp.innerHTML = `<div class="p3-c"><span>Today ${cfg.min_now}/${cfg.max_now}</span><b class="${days('current') ? 'out' : ''}">${days('current')} days short</b><small>shortage in ${Math.round(100 * r('current').runs_with_shortage)}% of ${st.data.reps} runs · avg ${Math.round(r('current').avg_on_hand.mean)} on hand</small></div>
        <div class="p3-c good"><span>Proposed X2 ${cfg.rec_min}/${cfg.rec_max}</span><b class="${days('recommended') ? 'out' : ''}">${days('recommended')} days short</b><small>shortage in ${Math.round(100 * r('recommended').runs_with_shortage)}% of ${st.data.reps} runs · avg ${Math.round(r('recommended').avg_on_hand.mean)} on hand</small></div>
        <p class="p3-note"><b>SIMULATED</b> under stated assumptions: one simulated year shown, same demand and promised lead times for both settings. Not observed history.</p>`;
    }
    function stop() { clearInterval(st.timer); st.timer = null; play.innerHTML = '<i class="fa-solid fa-play"></i>'; }
    play.onclick = () => {
      if (!st.data) return;
      if (st.timer) return stop();
      if (st.day >= 364) st.day = 0;
      play.innerHTML = '<i class="fa-solid fa-pause"></i>';
      st.timer = setInterval(() => { st.day++; dayIn.value = st.day; step(); if (st.day >= 364) stop(); }, 70);
    };
    dayIn.oninput = () => { st.day = +dayIn.value; draw(); };
    el.querySelectorAll('[data-pol]').forEach(b => b.onclick = () => {
      st.pol = b.dataset.pol; el.querySelectorAll('[data-pol]').forEach(x => x.classList.toggle('on', x === b)); draw();
    });
    draw();
    hud.insertAdjacentHTML('beforeend', '<div class="p3-wait">loading the simulated year…</div>');
    fetch(`/api/twin/${encodeURIComponent(cfg.material)}?reps=60`).then(r => r.json()).then(d => {
      if (!d.policies) throw new Error('no data');
      st.data = d; draw(); compare();
    }).catch(() => { hud.insertAdjacentHTML('beforeend', '<div class="p3-wait">simulation unavailable for this part</div>'); });
  };
})();
