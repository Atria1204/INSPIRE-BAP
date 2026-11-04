// INSpire Site twin: an isometric scene of the spare-part chain on one site.
// Supplier gate -> five warehouse halls (storage zones) -> pipe rack -> five equipment families in the plant.
// Pins and colours come from the database (layers) or from the simulated year (playback). Schematic, not a map.
const K = 21;                               // iso tile size
const iso = (x, y, z = 0) => [(x - y) * K + 520, (x + y) * K / 2 - z * 22 + 70];
const pts = a => a.map(p => iso(...p).map(v => v.toFixed(1)).join(',')).join(' ');
const FACE = { top: '#5d6f8f', left: '#33425e', right: '#43546f' };

function box(x, y, z, w, d, h, c = FACE, cls = '') {
  return `<g class="${cls}">
    <polygon class="f-l" points="${pts([[x, y + d, z], [x + w, y + d, z], [x + w, y + d, z + h], [x, y + d, z + h]])}" fill="${c.left}"/>
    <polygon class="f-r" points="${pts([[x + w, y, z], [x + w, y + d, z], [x + w, y + d, z + h], [x + w, y, z + h]])}" fill="${c.right}"/>
    <polygon class="f-t" points="${pts([[x, y, z + h], [x + w, y, z + h], [x + w, y + d, z + h], [x, y + d, z + h]])}" fill="${c.top}"/></g>`;
}
function tank(cx, cy, r, h, c = FACE, cls = '') {
  const [sx, sy] = iso(cx, cy, 0), [, ty] = iso(cx, cy, h), rx = r * K * 1.42, ry = rx / 2;
  return `<g class="${cls}"><rect x="${sx - rx}" y="${ty}" width="${2 * rx}" height="${sy - ty}" fill="${c.right}"/>
    <ellipse cx="${sx}" cy="${sy}" rx="${rx}" ry="${ry}" fill="${c.left}"/>
    <rect x="${sx - rx}" y="${ty}" width="${rx}" height="${sy - ty}" fill="${c.left}" opacity=".55"/>
    <ellipse cx="${sx}" cy="${ty}" rx="${rx}" ry="${ry}" fill="${c.top}"/></g>`;
}
function hall(x, y, w, d, h, c) {   // warehouse hall with a ridge roof
  const ridge = [[x, y + d / 2, h + 1.1], [x + w, y + d / 2, h + 1.1]];
  return box(x, y, 0, w, d, h, c) +
    `<polygon points="${pts([[x, y, h], [x + w, y, h], ridge[1], ridge[0]])}" fill="${c.top}"/>
     <polygon points="${pts([[x, y + d, h], [x + w, y + d, h], ridge[1], ridge[0]])}" fill="${shade(c.top, -18)}"/>
     <polygon points="${pts([[x + w, y, h], [x + w, y + d, h], ridge[1]])}" fill="${c.right}"/>
     ${[0.2, 0.5, 0.8].map(t => `<polygon points="${pts([[x + w * t - .5, y + d, .01], [x + w * t + .5, y + d, .01], [x + w * t + .5, y + d, 1.6], [x + w * t - .5, y + d, 1.6]])}" fill="#1d2a42"/>`).join('')}`;
}
function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16), c = v => Math.max(0, Math.min(255, v + amt));
  return '#' + [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => c(v).toString(16).padStart(2, '0')).join('');
}
const TONE = {
  ok: { top: '#5d6f8f', left: '#33425e', right: '#43546f' },
  warn: { top: '#d9a23a', left: '#7a5a1c', right: '#9a7224' },
  crit: { top: '#e5484d', left: '#7e2629', right: '#a43236' },
  sel: { top: '#2fc787', left: '#16654a', right: '#1f8a62' },
};

// world layout: warehouse halls on the north row, plant families on the south row, same zone order
const HALL_X = i => 9 + i * 6.3;
const FAMILY = [
  (c) => [0, 1, 2, 3].map(k => box(8 + (k % 2) * 2.4, 21.5 + Math.floor(k / 2) * 2.6, 0, 1.8, 1.1, .8, c) + tank(8.9 + (k % 2) * 2.4, 22.7 + Math.floor(k / 2) * 2.6, .45, 1.3, c)).join(''),
  (c) => [0, 1, 2, 3, 4, 5].map(k => box(14.6 + (k % 3) * 1.5, 21.6 + Math.floor(k / 3) * 2.4, 0, .9, .9, .9, c) + box(14.85 + (k % 3) * 1.5, 21.85 + Math.floor(k / 3) * 2.4, .9, .4, .4, .7, c)).join(''),
  (c) => [0, 1, 2].map(k => box(20.4 + k * 1.6, 21.8, 0, 1, .7, 2.6, c)).join('') + box(20.4, 24.6, 0, 4.2, .8, 1.2, c),
  (c) => box(26.2, 21.4, .5, 4.6, 1.2, 1, c) + box(26.2, 23.6, .5, 4.6, 1.2, 1, c) + box(27, 26, 0, 2.6, 2, 3, c) + tank(27.6, 26.6, .3, 7, c) + tank(29, 26.6, .3, 6.2, c),
  (c) => tank(34, 22.5, 1.3, 3.4, c) + tank(37.4, 22.6, 1.1, 2.8, c) + tank(35.6, 26, 1.2, 3.1, c) + tank(39.2, 26, .9, 2.2, c),
];
const FAMILY_CENTER = [[10, 23.5, 2.6], [16.2, 22.8, 2.6], [22, 22.6, 3.6], [28, 24, 7.6], [36.2, 24, 4.4]];

function siteScene(state) {
  const { zones, tone, pins, selected } = state;
  let s = `<polygon points="${pts([[0, 0, 0], [46, 0, 0], [46, 34, 0], [0, 34, 0]])}" fill="#16233b" stroke="#2b3d5e" stroke-width="1.5"/>`;
  for (let g = 2; g < 46; g += 2) s += `<polyline points="${pts([[g, 0, 0], [g, 34, 0]])}" stroke="#1d2c47" stroke-width="1"/>`;
  for (let g = 2; g < 34; g += 2) s += `<polyline points="${pts([[0, g, 0], [46, g, 0]])}" stroke="#1d2c47" stroke-width="1"/>`;
  // road and gate
  s += `<polygon points="${pts([[0, 13, .02], [46, 13, .02], [46, 15.4, .02], [0, 15.4, .02]])}" fill="#22324f"/>`;
  for (let d = 1; d < 46; d += 3) s += `<polygon points="${pts([[d, 14.1, .03], [d + 1.4, 14.1, .03], [d + 1.4, 14.3, .03], [d, 14.3, .03]])}" fill="#4b5d80"/>`;
  s += `<g class="st-obj" data-zone="gate">${box(1.5, 4, 0, 4.2, 6, 1.8, FACE)}${box(1.5, 10.2, 0, .3, .3, 2.4, FACE)}</g>`;
  // warehouse halls (back to front by x)
  zones.forEach((z, i) => {
    const c = selected === i ? TONE.sel : TONE[tone[i]] || FACE;
    s += `<g class="st-obj" data-zone="${i}"><title>${z.zone} warehouse zone: ${z.parts} parts in use, ${z.high} class A/S likely to run out. Click for details.</title>${hall(HALL_X(i), 3, 5.2, 8, 2.8, c)}</g>`;
  });
  // pipe rack between warehouse and plant
  s += box(6, 17.2, 1.5, 36, .5, .25, { top: '#7f93b8', left: '#3d4d6b', right: '#506282' });
  s += box(6, 18.2, 1.5, 36, .5, .25, { top: '#7f93b8', left: '#3d4d6b', right: '#506282' });
  for (let x = 7; x < 42; x += 5) s += box(x, 17.2, 0, .25, 1.5, 1.5, { top: '#5d6f8f', left: '#33425e', right: '#43546f' });
  // equipment families
  zones.forEach((z, i) => {
    const c = selected === i ? TONE.sel : TONE[state.plantTone[i]] || FACE;
    s += `<g class="st-obj" data-zone="${i}"><title>${z.family}: the equipment these parts are installed on. Click for details.</title>${FAMILY[i](c)}</g>`;
  });
  // labels on the ground
  zones.forEach((z, i) => {
    const [lx, ly] = iso(HALL_X(i) + 2.6, 11.8, 0), [px, py] = iso(FAMILY_CENTER[i][0], 29.6, 0);
    s += `<text class="st-lbl" x="${lx}" y="${ly}" text-anchor="middle">${z.short}</text><text class="st-lbl dim" x="${px}" y="${py}" text-anchor="middle">${z.family}</text>`;
  });
  const [gx, gy] = iso(3.6, 11.4, 0);
  s += `<text class="st-lbl" x="${gx}" y="${gy}" text-anchor="middle">Supplier gate</text>`;
  // pins
  pins.forEach(p => {
    const [x, y] = p.where === 'hall' ? iso(HALL_X(p.i) + 2.6, 7, 5.2) : iso(...FAMILY_CENTER[p.i]);
    const r = p.text.length > 3 ? 27 : 20;
    s += `<g class="st-pin ${p.kind}" data-zone="${p.i}"><title>${state.zones[p.i].zone}: ${p.text}</title><line x1="${x}" y1="${y}" x2="${x}" y2="${y + 30}"/>
      ${p.kind === 'crit' ? `<circle class="st-ring" cx="${x}" cy="${y}" r="${r}"/>` : ''}<circle cx="${x}" cy="${y}" r="${r}"/>
      <text x="${x}" y="${y + 6}" text-anchor="middle">${p.text}</text></g>`;
  });
  return `<svg viewBox="${state.view.join(' ')}" class="st-svg" role="img" aria-label="Site twin">${s}</svg>`;
}

// Vehicles live on their own layer so the scene can repaint every simulated day without restarting them.
// Truck: supplier gate -> the warehouse zone that receives a delivery. Carts: zone -> the machines it serves, when a part is issued.
const TRUCK_HOME = 2;
function truckShift(i) {                       // screen offset from the gate to the road in front of hall i
  const dx = (i == null ? 0 : HALL_X(i) + 1.2 - TRUCK_HOME);
  return [dx * K, dx * K / 2];
}
function cartShift(i) {                        // hall door -> equipment family
  const [hx, hy] = [HALL_X(i) + 2.6, 11.4], [fx, fy] = [FAMILY_CENTER[i][0], 20.8];
  return [((fx - hx) - (fy - hy)) * K, ((fx - hx) + (fy - hy)) * K / 2];
}
function fxLayer(view, n) {
  let s = `<g id="truck" class="st-truck">${box(TRUCK_HOME, 13.5, 0, 2.6, 1.2, 1.1, { top: '#9fc3ff', left: '#2a5aa0', right: '#3a6fc0' })}${box(TRUCK_HOME + 2.6, 13.5, 0, .9, 1.2, .8, { top: '#cfe0ff', left: '#2a5aa0', right: '#3a6fc0' })}</g>`;
  for (let i = 0; i < n; i++) {
    const [x, y] = iso(HALL_X(i) + 2.6, 11.4, .3), [dx, dy] = cartShift(i);
    s += `<circle class="st-cart" data-zone="${i}" cx="${x}" cy="${y}" r="7" style="--dx:${dx}px;--dy:${dy}px"/>`;
  }
  return `<svg viewBox="${view.join(' ')}" class="st-svg st-fx" aria-hidden="true">${s}</svg>`;
}
