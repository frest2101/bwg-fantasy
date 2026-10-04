// Diagramme als Inline-SVG ohne Bibliothek. Gezeichnet wird in der echten Breite des Containers
// (ResizeObserver), damit die Beschriftung auf dem Handy lesbar bleibt. Farben nur über CSS-Klassen,
// daher gelten Hell/Dunkel automatisch. Jedes Diagramm: role="img" mit title/desc und „Daten als Tabelle“.
let U;
export const init = c => { U = c.ui; };
const NS = 'http://www.w3.org/2000/svg';
const ok = v => v != null && isFinite(v);
let n = 0;

export function s(tag, a, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const k in a || {}) if (a[k] != null) e.setAttribute(k, a[k]);
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
function frame(w, H, title, desc) {
  const i = 'sv' + (++n);
  return s('svg', {viewBox: `0 0 ${w} ${H}`, width: w, height: H, class: 'ch', role: 'img', focusable: 'false',
    'aria-labelledby': `${i}t ${i}d`}, s('title', {id: i + 't'}, title), s('desc', {id: i + 'd'}, desc));
}
const lin = (d0, d1, r0, r1) => v => d1 === d0 ? (r0 + r1) / 2 : r0 + (v - d0) / (d1 - d0) * (r1 - r0);
function nice(lo, hi, k = 4) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / k, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(x => x >= raw);
  const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
  for (let v = a; v <= b + step / 1e6; v += step) t.push(+v.toFixed(10));
  return {lo: a, hi: b, t};
}
const P = (x, y) => x.toFixed(1) + ' ' + y.toFixed(1);

// Zeichnet draw(breite) in box und bei Größenänderung neu; box.redraw() nach Datenwechsel
export function mount(box, draw) {
  let last = 0, seen = false;
  const ro = new ResizeObserver(() => requestAnimationFrame(run));   // im nächsten Frame: keine RO-Schleife
  function run() {
    if (!box.isConnected) { if (seen) ro.disconnect(); return; }
    seen = true;
    const w = Math.round(box.clientWidth);
    if (!w || Math.abs(w - last) < 8) return;
    last = w;
    box.replaceChildren(draw(Math.max(260, w)));
  }
  ro.observe(box);
  box.redraw = () => { last = 0; run(); };
  return box;
}
// Figur mit Überschrift, Diagramm und aufklappbarer Datentabelle (erst beim Öffnen aufgebaut)
export function fig(title, draw, tab, ...extra) {
  const cv = mount(U.h('div', {class: 'cv'}), draw);
  const f = U.h('figure', {class: 'fig'}, U.h('figcaption', null, title), extra, cv, tab ? dataTable(title, tab) : null);
  f.cv = cv;
  return f;
}
function dataTable(title, tab) {
  const d = U.h('details', {class: 'dt'}, U.h('summary', null, 'Daten als Tabelle'));
  d.addEventListener('toggle', () => {
    if (!d.open || d.dataset.done) return;
    d.dataset.done = '1';
    const {h} = U, t = typeof tab === 'function' ? tab() : tab;
    d.append(U.scrollHint(h('div', {class: 'tw', role: 'region', tabindex: '0', 'aria-label': title + ' als Tabelle'},
      h('table', null, h('caption', {class: 'vh'}, title),
        h('thead', null, h('tr', null, t.heads.map((x, i) => h('th', {scope: 'col', class: i ? 'n' : null}, x)))),
        h('tbody', null, t.rows.map(r => h('tr', null, r.map((c, i) => i ? h('td', {class: 'n'}, c) : h('th', {scope: 'row'}, c)))))))));
  });
  return d;
}

// ---------------------------------------------------------------- Liniendiagramm (PF-Verlauf, Wochenrang, Wochen-Band)
// o = {title, desc, x: Labels, series: [{name, vals, hi}], avg, band: [lo, hi], invert, max, yfmt, H, zero (Nulllinie)}
export function lines(o) {
  return w => {
    const H = o.H || 220, L = 42, R = 50, T = 12, B = 24, nX = o.x.length;
    const vals = [...o.series.flatMap(x => x.vals), ...(o.avg || []), ...(o.band ? o.band.flat() : [])].filter(ok);
    let y, ticks;
    if (o.invert) {
      const mx = o.max || 10;
      y = lin(1, mx, T, H - B);
      ticks = [...new Set([1, Math.round((mx + 1) / 2), mx])];
    } else {
      const nc = nice(Math.min(...vals), Math.max(...vals));
      y = lin(nc.lo, nc.hi, H - B, T);
      ticks = nc.t;
    }
    const x = nX === 1 ? () => (L + w - R) / 2 : lin(0, nX - 1, L + 8, w - R);
    const g = frame(w, H, o.title, o.desc);
    for (const t of ticks) g.append(s('line', {x1: L, x2: w - R, y1: y(t), y2: y(t), class: o.zero && t === 0 ? 'z0' : 'gr'}),
      s('text', {x: L - 6, y: y(t) + 4, 'text-anchor': 'end'}, o.yfmt ? o.yfmt(t) : t));
    const step = Math.max(1, Math.ceil(nX * 30 / (w - L - R)));
    o.x.forEach((lab, i) => { if ((nX - 1 - i) % step === 0) g.append(s('text', {x: x(i), y: H - 6, 'text-anchor': 'middle'}, lab)); });
    const path = v => v.reduce((d, val, i) => ok(val) ? d + (d && ok(v[i - 1]) ? 'L' : 'M') + P(x(i), y(val)) : d, '');
    if (o.band) {
      const [lo, hi] = o.band;
      const pts = hi.map((v, i) => P(x(i), y(v))).concat(lo.map((v, i) => P(x(i), y(v))).reverse());
      g.append(s('path', {d: 'M' + pts.join('L') + 'Z', class: 'band'}));
    }
    const ends = [];
    const last = v => { for (let i = v.length - 1; i >= 0; i--) if (ok(v[i])) return i; return -1; };
    for (const sr of o.series) {
      if (sr.hi) continue;
      g.append(s('path', {d: path(sr.vals), class: 'lo'}));
      if (nX === 1) sr.vals.forEach((v, i) => ok(v) && g.append(s('circle', {cx: x(i), cy: y(v), r: 2.5, class: 'dl'})));
    }
    if (o.avg) { g.append(s('path', {d: path(o.avg), class: 'av'})); ends.push([o.avg, o.avgLabel || 'Ø Liga', null]); }
    for (const sr of o.series) {
      if (!sr.hi) continue;
      g.append(s('path', {d: path(sr.vals), class: 'hl'}));
      sr.vals.forEach((v, i) => ok(v) && g.append(s('circle', {cx: x(i), cy: y(v), r: 4, class: 'dt'})));
      ends.push([sr.vals, sr.name, 'lb']);
    }
    const lab = ends.map(([v, name, cls]) => { const i = last(v); return i < 0 ? null : {x: x(i) + 7, y: y(v[i]) + 4, name, cls}; })
      .filter(Boolean).sort((a, b) => a.y - b.y);
    for (let i = 1; i < lab.length; i++) if (lab[i].y - lab[i - 1].y < 13) lab[i].y = lab[i - 1].y + 13;
    lab.forEach(l => g.append(s('text', {x: l.x, y: l.y, class: l.cls}, l.name)));
    return g;
  };
}

// ---------------------------------------------------------------- Säulen (PF je Woche, Formkurve)
// o = {title, desc, x, vals, cls(i), letter(i), label(i), miss(i), tick: Werte (Strich), avg: Werte (Linie), yfmt, H}
export function bars(o) {
  return w => {
    const H = o.H || 200, L = 42, R = 10, T = 20, B = 24, nX = o.x.length;
    const all = [...o.vals, ...(o.tick || []), ...(o.avg || [])].filter(ok).map(v => Math.max(0, v));
    const nc = nice(0, Math.max(1, ...all));
    const y = lin(0, nc.hi, H - B, T), bw = (w - L - R) / nX, cx = i => L + bw * (i + 0.5), wid = Math.min(bw * 0.7, 46);
    const g = frame(w, H, o.title, o.desc);
    for (const t of nc.t) g.append(s('line', {x1: L, x2: w - R, y1: y(t), y2: y(t), class: t ? 'gr' : 'z0'}),
      s('text', {x: L - 6, y: y(t) + 4, 'text-anchor': 'end'}, o.yfmt ? o.yfmt(t) : t));
    const step = Math.max(1, Math.ceil(nX * 28 / (w - L - R)));
    o.vals.forEach((v, i) => {
      if ((nX - 1 - i) % step === 0) g.append(s('text', {x: cx(i), y: H - 6, 'text-anchor': 'middle'}, o.x[i]));
      if (!ok(v)) { g.append(s('text', {x: cx(i), y: y(0) - 6, 'text-anchor': 'middle', class: 'lb'}, o.miss ? o.miss(i) : '–')); return; }
      const yv = y(Math.max(0, v)), hgt = Math.max(1.5, y(0) - yv);
      g.append(s('rect', {x: cx(i) - wid / 2, y: y(0) - hgt, width: wid, height: hgt, rx: 2, class: o.cls ? o.cls(i) : 'bA'}));
      const lt = o.letter?.(i);
      if (lt && hgt > 18 && wid >= 14) g.append(s('text', {x: cx(i), y: y(0) - 6, 'text-anchor': 'middle', class: 'inv'}, lt));
      const lb = o.label?.(i);
      if (lb && bw >= 30) g.append(s('text', {x: cx(i), y: yv - 5, 'text-anchor': 'middle'}, lb));
      if (o.tick && ok(o.tick[i])) g.append(s('line', {x1: cx(i) - wid / 2 - 3, x2: cx(i) + wid / 2 + 3, y1: y(o.tick[i]), y2: y(o.tick[i]), class: 'tick'}));
    });
    if (o.avg) g.append(s('path', {class: 'av', d: o.avg.reduce((d, v, i) => ok(v) ? d + (d ? 'L' : 'M') + P(cx(i), y(v)) : d, '')}));
    return g;
  };
}

// ---------------------------------------------------------------- waagerechte Balken um 0 (Luck)
export function hbars(o) {
  return w => {
    const rh = 28, T = 6, H = T * 2 + o.rows.length * rh, L = 46, R = 62;
    const m = Math.max(0.25, ...o.rows.map(r => Math.abs(r.v || 0)));
    const x = lin(-m, m, L, w - R);
    const g = frame(w, H, o.title, o.desc);
    o.rows.forEach((r, i) => {
      const yc = T + i * rh + rh / 2, v = r.v || 0;
      g.append(s('text', {x: 4, y: yc + 4, class: 'lb'}, r.label),
        s('rect', {x: Math.min(x(0), x(v)), y: yc - 8, width: Math.max(1.5, Math.abs(x(v) - x(0))), height: 16, rx: 2, class: v < 0 ? 'neg' : 'pos'}),
        s('text', {x: w - 4, y: yc + 4, 'text-anchor': 'end'}, o.fmt(r.v)));
    });
    g.append(s('line', {x1: x(0), x2: x(0), y1: T - 2, y2: H - T + 2, class: 'z0'}));
    return g;
  };
}

// ---------------------------------------------------------------- Punktdiagramm (Effizienz, μ ± Intervall)
// o = {rows: [{label, v, lo, hi}], ref, refLabel, fmt, min, max}
export function dots(o) {
  return w => {
    const rh = 28, T = 24, B = 22, H = T + B + o.rows.length * rh, L = 46, R = 70;
    const vals = o.rows.flatMap(r => [r.v, r.lo, r.hi]).concat([o.ref, o.min, o.max]).filter(ok);
    const nc = nice(Math.min(...vals), Math.max(...vals));
    const x = lin(nc.lo, nc.hi, L, w - R);
    const g = frame(w, H, o.title, o.desc);
    const every = Math.max(1, Math.ceil(nc.t.length * 44 / (w - L - R)));
    nc.t.forEach((t, i) => {
      g.append(s('line', {x1: x(t), x2: x(t), y1: T - 4, y2: H - B, class: 'gr'}));
      if (i % every === 0) g.append(s('text', {x: x(t), y: H - 6, 'text-anchor': 'middle'}, o.tfmt ? o.tfmt(t) : t));
    });
    if (ok(o.ref)) g.append(s('line', {x1: x(o.ref), x2: x(o.ref), y1: T - 8, y2: H - B, class: 'av'}),
      s('text', {x: x(o.ref), y: T - 12, 'text-anchor': 'middle', class: 'lb'}, o.refLabel));
    o.rows.forEach((r, i) => {
      const yc = T + i * rh + rh / 2;
      g.append(s('text', {x: 4, y: yc + 4, class: 'lb'}, r.label));
      if (ok(r.lo) && ok(r.hi)) g.append(s('line', {x1: x(r.lo), x2: x(r.hi), y1: yc, y2: yc, class: 'wh'}));
      if (ok(r.v)) g.append(s('circle', {cx: x(r.v), cy: yc, r: 6, class: 'dt'}));
      g.append(s('text', {x: w - 4, y: yc + 4, 'text-anchor': 'end'}, o.fmt(r.v)));
    });
    return g;
  };
}

// ---------------------------------------------------------------- gestapelte Balken (Seeds, Positions-Anteile)
// o = {rows: [{label, parts}], total, cls(j), names}
export function stack(o) {
  return w => {
    const rh = 28, T = 4, H = T * 2 + o.rows.length * rh, L = 46, R = 6;
    const x = lin(0, o.total, L, w - R);
    const g = frame(w, H, o.title, o.desc);
    o.rows.forEach((r, i) => {
      const yc = T + i * rh + rh / 2;
      g.append(s('text', {x: 4, y: yc + 4, class: 'lb'}, r.label));
      let acc = 0;
      r.parts.forEach((v, j) => {
        if (!ok(v) || v <= 0) return;
        g.append(s('rect', {x: x(acc), y: yc - 9, width: Math.max(0.5, x(acc + v) - x(acc)), height: 18, class: o.cls(j) + ' sg'}, s('title', null, `${o.names[j]}: ${o.fmt ? o.fmt(v) : v}`)));
        acc += v;
      });
    });
    return g;
  };
}
export const swatches = (names, cls) => U.h('ul', {class: 'leg'}, names.map((nm, j) => U.h('li', null,
  s('svg', {width: 12, height: 12, viewBox: '0 0 12 12', 'aria-hidden': 'true'}, s('rect', {width: 12, height: 12, rx: 2, class: cls(j)})), nm)));

// Form Δ mit Band: grauer Balken ±Band, Punkt bei Δ (innerhalb grau, außerhalb farbig); Wert steht als Text daneben
export function mini(d, b) {
  const W = 64, H = 16, m = Math.max(Math.abs(d), b, 0.01) * 1.2, x = lin(-m, m, 4, W - 4);
  return s('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'ch mini', 'aria-hidden': 'true', focusable: 'false'},
    s('rect', {x: x(-b), y: 4, width: Math.max(1, x(b) - x(-b)), height: 8, rx: 2, class: 'bd'}),
    s('line', {x1: x(0), x2: x(0), y1: 1, y2: 15, class: 'z0'}),
    s('circle', {cx: x(d), cy: 8, r: 4, class: Math.abs(d) <= b ? 'din' : 'dout'}));
}

// ---------------------------------------------------------------- PF-Verlauf und Wochenrang-Verlauf (Tabelle › Punkte, Teamseite)
export function verlauf(hid, pick) {
  const {h, S, num, seg} = U;
  const weeks = S.meta.weeks || [], xl = weeks.map(w => 'W' + w);
  const avgW = weeks.map(w => S.weeks.find(x => x.week === w)?.ligaschnitt ?? null);
  let mode = 'woche', sel = +hid;
  const cum = v => { let c = 0; return v.map(x => ok(x) ? (c += x) : null); };
  const hiT = () => S.byId.get(sel);
  const d1 = w => {
    const t = hiT(), k = mode === 'kum';
    const vals = t.wochen.pf, a = k ? cum(avgW) : avgW;
    return lines({title: k ? 'PF-Verlauf kumuliert' : 'PF-Verlauf je Woche',
      desc: `${t.name} hervorgehoben${k ? ', kumuliert' : ''}: zuletzt ${num((k ? cum(vals) : vals).at(-1))} Punkte, Ligaschnitt ${num(a.at(-1))}. Graue Linien: übrige Teams.`,
      x: xl, series: S.teams.map(x => ({name: x.kuerzel, vals: k ? cum(x.wochen.pf) : x.wochen.pf, hi: x.team_id === sel})),
      avg: a, yfmt: v => num(v, 0)})(w);
  };
  const d2 = w => {
    const t = hiT();
    return lines({title: 'Wochenrang-Verlauf', desc: `${t.name}: Wochenrang zuletzt ${t.wochen.wochenrang.at(-1)} von ${S.teams.length} (1 = beste Woche).`,
      x: xl, series: S.teams.map(x => ({name: x.kuerzel, vals: x.wochen.wochenrang, hi: x.team_id === sel})),
      invert: true, max: S.teams.length, yfmt: v => v + '.', H: 200})(w);
  };
  const tab = key => () => ({heads: ['Woche', ...S.teams.map(t => t.kuerzel), ...(key === 'pf' ? ['Ø Liga'] : [])],
    rows: weeks.map((w, i) => ['W' + w, ...S.teams.map(t => key === 'pf' ? num(t.wochen.pf[i]) : t.wochen.wochenrang[i]),
      ...(key === 'pf' ? [num(avgW[i])] : [])])});
  const f1 = fig('PF-Verlauf', d1, tab('pf'));
  const f2 = fig('Wochenrang-Verlauf', d2, tab('rang'));
  const redraw = () => { f1.cv.redraw(); f2.cv.redraw(); };
  const ctl = h('div', {class: 'row'},
    pick ? h('label', null, 'Hervorheben ', h('select', {onchange: e => { sel = +e.target.value; redraw(); }},
      S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === sel}, t.name)))) : null,
    seg('Darstellung PF-Verlauf', [['woche', 'je Woche'], ['kum', 'kumuliert']], mode, v => { mode = v; redraw(); }));
  return [ctl, f1, f2];
}
