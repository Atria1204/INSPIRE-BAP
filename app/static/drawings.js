// Equipment drawings reused from the AETHER preliminary digital twin (features/asset/twin.js).
// Case 3 has no sensor readings, so components are NOT coloured by condition. A component is outlined when
// parts are installed on it, and marked red when one of those parts needs a reorder. Click a component to
// list its parts. Placement of a part on a component is inferred from the part description (PROPOSED rule).
const TW = {
  comp: (id, label, inner, lx, ly) => `<g class="tw-comp" data-comp="${id}" tabindex="0" role="button" aria-label="${label || id}">${inner}` +
    (label ? `<text class="tw-label" x="${lx}" y="${ly}" text-anchor="middle">${label}<tspan class="tw-count" data-count="${id}"></tspan></text>` : '') + `</g>`,
  skid: (x1, x2) => `<rect class="tw-skid" x="${x1}" y="205" width="${x2 - x1}" height="10" rx="2"/>`,
  shaft: (x1, x2) => `<line class="tw-shaft" x1="${x1}" y1="120" x2="${x2}" y2="120"/>`,
  motor: (x, w) => `<rect class="tw-body" x="${x}" y="70" width="${w}" height="100" rx="10"/>` +
    Array.from({ length: Math.floor((w - 30) / 16) }, (_, i) => `<line class="tw-fin" x1="${x + 18 + i * 16}" y1="80" x2="${x + 18 + i * 16}" y2="160"/>`).join('') +
    `<rect class="tw-foot" x="${x + 15}" y="170" width="${w - 30}" height="35"/>`,
  coupling: x => `<rect class="tw-body" x="${x}" y="100" width="30" height="40" rx="4"/>`,
  bearing: (x, w = 70) => `<rect class="tw-body" x="${x}" y="85" width="${w}" height="70" rx="6"/><rect class="tw-foot" x="${x + 10}" y="155" width="${w - 20}" height="50"/>`,
  pipe: (x, y, w, h) => `<rect class="tw-body" x="${x}" y="${y}" width="${w}" height="${h}" rx="3"/>`,
};

const DRAWINGS = {
  pump: () => TW.skid(25, 700) + TW.shaft(150, 430) +
    TW.comp('motor', 'Motor', TW.motor(35, 190), 130, 235) +
    TW.comp('coupling', 'Coupling', TW.coupling(240), 255, 262) +
    TW.comp('bearing', 'Bearing housing', TW.bearing(285, 100), 335, 235) +
    TW.comp('seal', 'Mechanical seal', `<rect class="tw-body" x="390" y="95" width="22" height="50" rx="3"/><path class="tw-line" d="M401 95 V55 H440"/>`, 405, 262) +
    TW.comp('casing', 'Pump casing', `<circle class="tw-body" cx="505" cy="125" r="68"/><circle class="tw-inner" cx="505" cy="125" r="26"/>`, 505, 235) +
    TW.comp('discharge', 'Discharge / flanges', TW.pipe(485, 20, 40, 45), 600, 48) +
    TW.comp('suction', 'Suction', TW.pipe(570, 110, 125, 32), 640, 100),
  compressor: () => TW.skid(25, 700) + TW.shaft(160, 660) +
    TW.comp('driver', 'Driver', TW.motor(30, 160), 110, 235) +
    TW.comp('coupling', 'Coupling', TW.coupling(200), 215, 262) +
    TW.comp('bearing_de', 'DE bearing', TW.bearing(240, 55), 268, 235) +
    TW.comp('casing', 'Compressor casing', `<rect class="tw-body" x="300" y="55" width="300" height="130" rx="18"/>
      <rect class="tw-body" x="330" y="20" width="44" height="38" rx="3"/><rect class="tw-body" x="526" y="20" width="44" height="38" rx="3"/>`, 450, 126) +
    TW.comp('bearing_nde', 'NDE bearing', TW.bearing(605, 55), 633, 235) +
    TW.comp('lube', 'Lube-oil console', `<path class="tw-pipe" d="M290 150 H312 V250 H330"/><rect class="tw-body" x="330" y="232" width="250" height="48" rx="6"/>`, 455, 296),
  motorpump: () => TW.skid(25, 700) + TW.shaft(330, 520) +
    TW.comp('stator', 'Motor (stator and winding)', TW.motor(30, 270), 165, 235) +
    TW.comp('terminal', 'Terminal box', `<rect class="tw-body" x="120" y="30" width="80" height="40" rx="4"/>`, 160, 22) +
    TW.comp('motor_de', 'Motor DE bearing', TW.bearing(300, 50), 325, 262) +
    TW.comp('coupling', 'Coupling', TW.coupling(370), 395, 235) +
    TW.comp('pump', 'Driven pump', `<rect class="tw-body" x="420" y="90" width="60" height="60" rx="5"/><circle class="tw-body" cx="565" cy="120" r="60"/><rect class="tw-body" x="545" y="20" width="40" height="42" rx="3"/>`, 560, 235),
  exchanger: () =>
    TW.comp('shell', 'Shell', `<rect class="tw-body" x="150" y="70" width="420" height="110" rx="50"/>`, 420, 236) +
    TW.comp('tubes', 'Tube bundle', `<g class="tw-tubes">${[95, 115, 135, 155].map(y => `<line x1="165" y1="${y}" x2="555" y2="${y}"/>`).join('')}</g>`, 360, 62) +
    TW.comp('channel', 'Channel / gaskets', `<rect class="tw-body" x="80" y="80" width="70" height="90" rx="8"/>`, 60, 196) +
    `<rect class="tw-body" x="570" y="85" width="40" height="80" rx="16"/>` +
    `<rect class="tw-foot" x="200" y="180" width="30" height="25"/><rect class="tw-foot" x="490" y="180" width="30" height="25"/>` + TW.skid(150, 570) +
    TW.comp('nozzles', 'Nozzles', TW.pipe(96, 25, 30, 55) + TW.pipe(470, 25, 30, 47), 290, 22),
  blower: () => TW.skid(25, 700) + TW.shaft(220, 420) +
    TW.comp('motor', 'Motor', TW.motor(30, 190), 125, 235) +
    TW.comp('coupling', 'Coupling', TW.coupling(240), 255, 262) +
    TW.comp('bearing', 'Bearing pedestal', TW.bearing(290, 80), 330, 235) +
    TW.comp('housing', 'Housing and impeller', `<path class="tw-body" d="M480 205 A85 85 0 1 1 565 120 L565 35 L635 35 L635 125 A155 155 0 0 1 560 205 Z"/><circle class="tw-inner" cx="480" cy="120" r="30"/>`, 520, 262),
};

/** Render a drawing into `el`. hotspots: {componentId: {parts, reorder}}. onPick(componentId|null). */
function renderDrawing(el, type, hotspots, onPick) {
  if (!DRAWINGS[type]) { el.innerHTML = ''; return; }
  el.innerHTML = `<svg viewBox="0 0 720 305" class="tw-svg" role="img" aria-label="Equipment drawing">${DRAWINGS[type]()}</svg>`;
  el.querySelectorAll('.tw-comp').forEach(g => {
    const id = g.dataset.comp, h = hotspots[id];
    const c = el.querySelector(`[data-count="${id}"]`);
    if (h && h.parts) {
      g.classList.add(h.reorder ? 'hs-reorder' : 'hs-parts');
      if (c) c.textContent = ` · ${h.parts}`;
    }
    const pick = () => {
      const on = !g.classList.contains('hs-on');
      el.querySelectorAll('.tw-comp').forEach(x => x.classList.remove('hs-on'));
      if (on) g.classList.add('hs-on');
      onPick(on ? id : null);
    };
    g.addEventListener('click', pick);
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
  });
}
