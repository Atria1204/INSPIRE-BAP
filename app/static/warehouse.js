// Warehouse digital twin, building view (AETHER twin style): suppliers -> receiving dock -> five storage zones -> issue
// counter -> equipment families. Bins are parts; a bin turns red on the days that part is out of stock in the simulated year.
const ZONE_ICON = { 'Rotating equipment': 'pump', 'Valves': 'valve', 'Instruments and electrical': 'gauge',
  'Heat transfer and furnace': 'exchanger', 'Static and piping': 'pipe' };
const ZONE_SHORT = { 'Rotating equipment': 'Rotating', 'Valves': 'Valves', 'Instruments and electrical': 'Instruments',
  'Heat transfer and furnace': 'Heat transfer', 'Static and piping': 'Static & piping' };

function equipIcon(kind, x, y) {
  const g = { pump: `<circle cx="${x + 26}" cy="${y + 22}" r="16" class="wt-eq"/><rect x="${x - 6}" y="${y + 14}" width="18" height="16" rx="3" class="wt-eq"/><rect x="${x + 20}" y="${y}" width="12" height="9" class="wt-eq"/>`,
    valve: `<path d="M${x} ${y + 8} L${x + 24} ${y + 30} L${x} ${y + 30} L${x + 24} ${y + 8} Z" class="wt-eq"/><line x1="${x + 12}" y1="${y + 19}" x2="${x + 12}" y2="${y}" class="wt-eqline"/><rect x="${x + 2}" y="${y - 4}" width="20" height="6" rx="2" class="wt-eq"/>`,
    gauge: `<circle cx="${x + 14}" cy="${y + 18}" r="15" class="wt-eq"/><line x1="${x + 14}" y1="${y + 18}" x2="${x + 23}" y2="${y + 9}" class="wt-eqline"/>`,
    exchanger: `<rect x="${x - 6}" y="${y + 8}" width="46" height="22" rx="11" class="wt-eq"/><line x1="${x}" y1="${y + 15}" x2="${x + 34}" y2="${y + 15}" class="wt-eqline thin"/><line x1="${x}" y1="${y + 23}" x2="${x + 34}" y2="${y + 23}" class="wt-eqline thin"/>`,
    pipe: `<path d="M${x - 6} ${y + 26} H${x + 16} V${y + 6} H${x + 40}" class="wt-pipe"/>` };
  return g[kind] || '';
}

function renderWarehouse(el, data) {
  const W = 1240, H = 560;
  const zones = data.zones;
  const hallX = 300, hallY = 80, hallW = 560, hallH = 420, zoneH = 74, gap = 8;
  const PER_BIN = 5;   // one bin = 5 parts
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="wt-svg" role="img" aria-label="Warehouse twin">
    <defs><marker id="wa" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="14" markerHeight="14" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#8494aa"/></marker>
          <marker id="war" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="14" markerHeight="14" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#d03b3b"/></marker></defs>`;
  // suppliers + trucks
  svg += `<g class="wt-block"><rect x="14" y="170" width="200" height="200" rx="14"/>
    <text class="wt-k" x="34" y="198">SUPPLIERS</text><text class="wt-big" x="34" y="240">${data.supply.suppliers}</text>
    <text class="wt-s" x="34" y="262">suppliers · ${data.supply.pos.toLocaleString()} POs</text>
    <text class="wt-s" x="34" y="284">avg promised ${data.supply.avg_lt} days</text>
    <text class="wt-warn" x="34" y="306">${Math.round(data.supply.late_share * 100)}% promised later than asked</text>
    <g id="wtTruck" class="wt-truck"><rect x="34" y="324" width="52" height="26" rx="4"/><rect x="86" y="332" width="20" height="18" rx="3"/><circle cx="48" cy="352" r="5"/><circle cx="96" cy="352" r="5"/></g></g>
    <line id="wtIn" class="wt-arrow" x1="222" y1="270" x2="${hallX - 6}" y2="270" stroke-width="10" marker-end="url(#wa)"/>
    <text class="wt-s" x="${(222 + hallX) / 2}" y="256" text-anchor="middle">receipts</text>`;
  // building shell
  svg += `<path class="wt-roof" d="M${hallX - 16} ${hallY} L${hallX + hallW / 2} ${hallY - 50} L${hallX + hallW + 16} ${hallY} Z"/>
    <text class="wt-title" x="${hallX + hallW / 2}" y="${hallY - 14}" text-anchor="middle">WAREHOUSE · ${data.parts.toLocaleString()} parts in use</text>
    <rect class="wt-hall" x="${hallX}" y="${hallY}" width="${hallW}" height="${hallH}" rx="6"/>
    <rect class="wt-dock" x="${hallX}" y="${hallY}" width="34" height="${hallH}"/><text class="wt-vert" x="${hallX + 22}" y="${hallY + hallH / 2}" transform="rotate(-90 ${hallX + 22} ${hallY + hallH / 2})" text-anchor="middle">RECEIVING</text>
    <rect class="wt-dock" x="${hallX + hallW - 34}" y="${hallY}" width="34" height="${hallH}"/><text class="wt-vert" x="${hallX + hallW - 12}" y="${hallY + hallH / 2}" transform="rotate(-90 ${hallX + hallW - 12} ${hallY + hallH / 2})" text-anchor="middle">ISSUE COUNTER</text>`;
  // zones with bins
  zones.forEach((z, i) => {
    const y = hallY + 12 + i * (zoneH + gap), x = hallX + 46, w = hallW - 92;
    const bins = Math.max(1, Math.round(z.parts / PER_BIN)), cols = 30, bw = (w - 160) / cols - 2, rows = Math.ceil(bins / cols);
    const bh = Math.min(12, (zoneH - 30) / Math.max(rows, 1) - 2);
    svg += `<g class="wt-zone" data-zone="${i}"><rect class="wt-zone-bg" x="${x}" y="${y}" width="${w}" height="${zoneH}" rx="8"/>
      <text class="wt-zname" x="${x + 12}" y="${y + 22}">${ZONE_SHORT[z.zone]}</text>
      <text class="wt-s" x="${x + 12}" y="${y + 40}">${z.parts} parts · ${z.critical} A/S</text>
      <text class="wt-zout" id="wtOut${i}" x="${x + 12}" y="${y + 60}"></text>`;
    for (let b = 0; b < bins; b++) {
      const bx = x + 150 + (b % cols) * (bw + 2), by = y + 14 + Math.floor(b / cols) * (bh + 2);
      svg += `<rect class="wt-bin" data-z="${i}" data-b="${b}" x="${bx.toFixed(1)}" y="${by.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5"/>`;
    }
    svg += `</g>`;
    // arrow to equipment family
    const ey = y + zoneH / 2;
    svg += `<line id="wtArr${i}" class="wt-arrow" x1="${hallX + hallW + 6}" y1="${ey}" x2="1010" y2="${ey}" stroke-width="6" marker-end="url(#wa)"/>
      <text class="wt-s" id="wtArrL${i}" x="${(hallX + hallW + 1010) / 2}" y="${ey - 8}" text-anchor="middle"></text>
      <g class="wt-eqg">${equipIcon(ZONE_ICON[z.zone], 1030, ey - 20)}<text class="wt-s strong" x="1084" y="${ey + 4}">${ZONE_SHORT[z.zone]}</text></g>`;
  });
  svg += `<text class="wt-k" x="1030" y="${hallY - 4}">EQUIPMENT</text>
    <text class="wt-s" x="1030" y="${hallY + hallH + 30}">${data.issues.n.toLocaleString()} issues · ${data.issues.orders.toLocaleString()} work orders</text></svg>`;
  el.innerHTML = svg;
  el._bins = [...el.querySelectorAll('.wt-bin')];
  el._perBin = PER_BIN;
  showDay(el, data, null, 0);
}

function showDay(el, data, policy, day) {
  data.zones.forEach((z, i) => {
    const short = policy ? z[policy === 'current' ? 'short_now' : 'short_rec'][day] : null;
    const bins = el._bins.filter(b => +b.dataset.z === i);
    const red = short == null ? 0 : Math.ceil(short / el._perBin);
    bins.forEach((b, k) => b.setAttribute('class', 'wt-bin' + (k < red ? ' out' : '')));
    const out = el.querySelector('#wtOut' + i), arr = el.querySelector('#wtArr' + i), al = el.querySelector('#wtArrL' + i);
    if (short == null) { out.textContent = ''; al.textContent = 'issues to jobs'; arr.setAttribute('class', 'wt-arrow'); arr.setAttribute('marker-end', 'url(#wa)'); return; }
    out.textContent = `${short} out of stock`;
    out.setAttribute('class', 'wt-zout' + (short > 0 ? ' red' : ''));
    al.textContent = short > 0 ? `${short} parts missing for jobs` : 'all parts available';
    arr.setAttribute('class', 'wt-arrow' + (short > z.parts * 0.04 ? ' short' : ''));
    arr.setAttribute('marker-end', short > z.parts * 0.04 ? 'url(#war)' : 'url(#wa)');
  });
}

function playWarehouse(el, data, policy, onDay, onEnd) {
  if (el._timer) clearInterval(el._timer);
  let d = 0;
  const truck = el.querySelector('#wtTruck');
  el._timer = setInterval(() => {
    showDay(el, data, policy, d);
    truck.style.transform = `translateX(${(d % 20) * 6}px)`;
    onDay(d);
    d += 1;
    if (d >= 365) { clearInterval(el._timer); el._timer = null; onEnd(); }
  }, 32);
}
