# INSpire design system (derived from AETHER)

Source of truth: `aether/css/custom.css` (AETHER, the team's earlier prototype) and `app/static/aether.css` (an exact copy).
INSpire is an Operate surface: inventory planners and reliability engineers at a petrochemical plant, on a laptop, at a desk.
Scanability and consistency beat expression. Colour is only for meaning.

## 1. Foundations

| Token | Value | Use |
| --- | --- | --- |
| `--c-rail` | `#0f1f3d` | Sidebar, page banner, table header, primary button |
| `--c-canvas` | `#eef2f7` | Page background |
| Panel | `#fff`, border `#dbe2ea`, radius `14px` (0.875rem), shadow `0 1px 2px rgba(15,23,42,.05)` | Every card |
| Text | `#0f172a` primary, `#334155` body, `#475569` secondary, `#64748b` caption | Never lighter than `#64748b` on white |
| Font | Inter 400/500/600/700; JetBrains Mono only for part numbers and order numbers | |
| Numbers | `font-variant-numeric: tabular-nums` everywhere a number sits in a column | |

### Metric colours (one hue per meaning, three steps each)

| Metric | Base | Ink (text) | Soft (fill) | INSpire meaning |
| --- | --- | --- | --- | --- |
| loss | `#eb6834` | `#b4461a` | `#fdf0ea` | Critical at zero stock, run-out risk |
| priority | `#4a3aa7` | `#4a3aa7` | `#efedfa` | Capital above Max |
| incidents | `#2a78d6` | `#1c5cab` | `#eaf2fc` | Reorder, actions |
| downtime | `#1baf7a` | `#0d7a54` | `#e8f7f1` | Simulated improvement, INSpire values |
| crit / warn / good | `#d03b3b` / `#fab219` / `#0ca30c` | `#b42f2f` / `#8a5a00` / `#0a7a0a` | `#fcebeb` / `#fff6e0` / `#e9f7e9` | Status only, always with a word |

Rule: base for bars and marks, ink for text on white, soft for a tinted header or a selected row. Never text in the base colour.

## 2. Type scale

| Role | Size / weight |
| --- | --- |
| Page title (banner) | 24px / 600, white on navy |
| Panel title | 15–16px / 600–700 |
| KPI value | 24–28px / 600–700, letter-spacing -0.02em |
| Body, table cell | 13–14px / 400–500 |
| Caption, sub | 11.5–12.5px / 500, `#64748b` |
| Column header | 12px / 600 |
| Chip, tag | 11px / 600 |

No eyebrow labels above headings. No uppercase except table group labels and tiny tags.

## 3. Components

**Page banner.** Navy panel, 16px × 24px padding, radius 14px. Title, one sentence of purpose, optional count on the right. No kicker line.

**KPI card.** White panel. Top strip in the metric's soft colour with the metric name in its ink colour (15px/700) and a quiet provenance icon. Then one value, one caption, one segmented bar whose segments are the real breakdown, a one-line legend. Whole card is the link. Four per row on a laptop.

**Ranked list (plant-row).** The AETHER way to compare a few groups: a grid `name | bar | value`, row padding 7px 8px, radius 6px.
Bar track 8px tall, soft colour; fill in the metric base colour, drawn with `transform: scaleX()`.
Hover `#f1f5f9`. Selected: soft fill plus a 1.5px inset ring in the base colour. Others dim to 45% while one is selected.
One measure per list. To compare measures, switch the measure with a segmented control above the list, never squeeze three measures into one row.

**Segmented control.** Pill track `#f1f5f9`, radius 10px, padding 3px. The active segment is white with a soft shadow and the metric's ink colour; inactive segments are `#475569`.

**Featured card (Act first).** Light blue panel (`#eaf2fc` head), ranked hero rows: rank chip, name, one fact line, the action. Equal heights.

**Record detail.** Main column (decision panel, twin, history tabs) plus a 320px sticky facts rail. The decision panel: action word in the action's ink colour, evidence grade chip, buttons right; then a 3×2 grid of facts separated by 1px lines; then one "Why" line.

**Data table.** One style app-wide:
header row navy `#15284a` with `#dfe7f5` text, 12px/600; 1px grid lines `#e3e9f1` between cells; zebra `#fafbfd`; hover `#eef4fc`.
The table sits flush inside a white panel with 14px corners, and the header's outer corners follow that radius.
Numbers right-aligned. 20 rows per page, "Rows per page" 20/50/100 and a pager under the table.
Column titles are menus: sort ascending or descending and "Show only" values.

**Tags.** Provenance (Observed, Derived, Scenario, Assumption) is a small icon inside dense tiles and a 11px tag in panel heads. It always opens the "where this number comes from" popover.

## 4. Motion

150ms ease-out for hover and selection. Bars grow with `cubic-bezier(0.16, 1, 0.3, 1)` over 250ms. One authored moment per page (the twin's play). Respect `prefers-reduced-motion`.

## 5. Do not

- A colored border thicker than 1px on one side of a card.
- Three or more measures side by side in a narrow list.
- Gradient text, glass, decorative glows.
- Grey text lighter than `#64748b`.
- A number without its unit or what it counts.
- Calling a simulated result observed, or a capital figure a saving.
