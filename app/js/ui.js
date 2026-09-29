// Gemeinsame Bausteine aller Ansichten: DOM-Helfer, Zahlenformate, sortierbare Tabellen, Chips, i-Knöpfe.
// Zahlen kommen fertig gerundet aus dem Rechenwerk; hier wird nur formatiert (Komma, Minus, Prozent).
export const S = {};                 // gemeinsamer Zustand, füllt app.js (Manifest, Teams, Spielplan …)
const D = document;
let uid = 0;
export const id = p => (p || 'u') + (++uid);

export function h(tag, a, ...kids) {
  const e = D.createElement(tag);
  if (a) for (const k in a) {
    const v = a[k];
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  add(e, kids);
  return e;
}
export const ap = (e, ...kids) => add(e, kids);      // wie append, überspringt aber null/false
export function add(e, kids) {
  for (const c of kids) {
    if (c == null || c === false) continue;
    if (Array.isArray(c)) add(e, c); else e.append(c.nodeType ? c : String(c));
  }
  return e;
}

// ---------------------------------------------------------------- Zahlen und Daten
const NF = {};
const nf = d => NF[d] || (NF[d] = new Intl.NumberFormat('de-DE', {minimumFractionDigits: d, maximumFractionDigits: d}));
export const MINUS = '−', NB = ' ';
export const ok = v => v != null && v !== '' && isFinite(v);
export function num(v, d = 2) {
  if (!ok(v)) return '–';
  v = +v;
  if (Math.abs(v) < 0.5 * 10 ** -d) v = 0;          // kein „−0,00“
  return nf(d).format(v).replace('-', MINUS);
}
export const sgn = (v, d = 2) => ok(v) ? (v > 0 && Math.abs(v) >= 0.5 * 10 ** -d ? '+' : '') + num(v, d) : '–';
export const pct = (v, d = 1) => ok(v) ? num(v, d) + NB + '%' : '–';
export const nn = v => ok(v) ? num(v, Number.isInteger(+v) ? 0 : 1) : '–';   // ganze Zahl oder x,5
// Playoff-%: ganzzahlig, Ränder als „< 1 %“ / „> 99 %“ (Eingabe in Prozent)
export const po = v => !ok(v) ? '–' : v < 1 ? '< 1' + NB + '%' : v > 99 ? '> 99' + NB + '%' : num(v, 0) + NB + '%';
// Simulations-Anteile laut Vertrag 0–1; falls die Daten schon Prozent liefern, erkennt S.simFrac das
export const sp = v => ok(v) ? (S.simFrac === false ? +v : v * 100) : null;

const TZ = 'Europe/Berlin';
const DF = new Intl.DateTimeFormat('de-DE', {weekday: 'short', day: '2-digit', month: '2-digit', timeZone: TZ});
const TF = new Intl.DateTimeFormat('de-DE', {hour: '2-digit', minute: '2-digit', timeZone: TZ});
const toDate = x => typeof x === 'number' ? new Date(x) : x instanceof Date ? x : new Date(x + 'T12:00:00Z');
const parts = d => Object.fromEntries(DF.formatToParts(toDate(d)).map(p => [p.type, p.value]));
export function datum(x) { const p = parts(x); return `${p.weekday.replace('.', '')} ${p.day}.${p.month}.`; }
export const zeit = x => TF.format(toDate(x));
export function spanne(iso) {       // Woche Di–Mo, z. B. „08.–14.09.“
  const a = parts(iso), b = parts(new Date(toDate(iso).getTime() + 6 * 864e5));
  return a.month === b.month ? `${a.day}.–${b.day}.${b.month}.` : `${a.day}.${a.month}.–${b.day}.${b.month}.`;
}

// ---------------------------------------------------------------- Teams, fehlende Werte
export const team = tid => S.byId.get(+tid);
export const kz = tid => team(tid)?.kuerzel ?? '–';
export function tl(tid, cls) {       // Team-Link: Name, auf dem Handy in schmalen Tabellen das Kürzel
  const t = team(tid);
  if (!t) return tid === 0 ? 'FA' : '–';
  return h('a', {href: '#team/' + t.team_id, class: 'tl2' + (cls ? ' ' + cls : '')},
    h('span', {class: 'tn'}, t.name), h('span', {class: 'tk', 'aria-hidden': 'true'}, t.kuerzel));
}
export const rec = t => `${t.w}-${t.l}` + (S.hasT ? `-${t.t}` : '');
let naSet = null;
export function na(reason) {         // „–“ mit Grund: in Tabellen als Fußnote unter der Tabelle, sonst im Text (für Screenreader)
  if (naSet) { if (reason) naSet.add(reason); return h('span', {class: 'na'}, '–'); }
  return h('span', {class: 'na'}, '–', reason ? h('span', {class: 'vh'}, ` (${reason})`) : null);
}
export const val = (v, f, reason) => ok(v) ? f(v) : na(reason);

// ---------------------------------------------------------------- Speicher (nur Komfort, darf fehlen)
export const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ohne Speicher gilt der Standard */ } },
};

// Hash-Parameter ändern, ohne die Ansicht neu zu laden (teilbarer Link)
export function setQ(path, params) {
  const q = new URLSearchParams();
  for (const k in params) if (params[k] != null && params[k] !== '') q.set(k, params[k]);
  const s = q.toString().replace(/%2C/g, ',');
  history.replaceState(null, '', '#' + path + (s ? '?' + s : ''));
}

// ---------------------------------------------------------------- Chips, Umschalter, Kacheln
// Waagerecht scrollende Bereiche (Tabellen, Chipleisten): Klasse „sc-more“, solange rechts etwas verborgen ist (CSS
// blendet die Kante aus), „sc-scrolled“ ab dem ersten Wischen (Schatten an der festen Team-Spalte). Auf dem Handy ist sonst nicht
// zu erkennen, dass eine Tabelle weitere Spalten hat.
export function scrollHint(el) {
  const upd = () => {
    el.classList.toggle('sc-more', el.scrollWidth - el.clientWidth - el.scrollLeft > 2);
    el.classList.toggle('sc-scrolled', el.scrollLeft > 2);
  };
  el.addEventListener('scroll', upd, {passive: true});
  new ResizeObserver(upd).observe(el);
  return el;
}
export const chips = (label, items, cur, cls) => scrollHint(h('nav', {class: 'chips' + (cls ? ' ' + cls : ''), 'aria-label': label},
  items.map(([href, text, key, extra]) => h('a', {href, 'aria-current': key === cur ? 'page' : null, class: extra}, text))));
// aktuellen Chip einer scrollenden Chipleiste in die Mitte holen (erst aufrufen, wenn die Leiste im DOM steht)
export function centerChip(nav) {
  const cur = nav.querySelector('[aria-current]');
  if (cur) nav.scrollLeft += cur.getBoundingClientRect().left - nav.getBoundingClientRect().left - (nav.clientWidth - cur.offsetWidth) / 2;
  return nav;
}
// Wochenwahl „Saison · W1 · W2 …“ über die gerechneten Wochen (meta.weeks): Links auf path bzw. path/wN
export function weekChips(path, cur) {
  const start = n => S.weeks.find(w => w.week === n)?.start;
  return chips('Woche wählen', [['#' + path, ['Saison', h('small', null, `nach W${S.tw}`)], 0],
    ...(S.meta.weeks || []).map(w => ['#' + path + '/w' + w, ['W' + w, h('small', null, start(w) ? spanne(start(w)) : '')], w])], cur, 'wk');
}
// All-Play-Bilanz „6-3“, mit Gleichständen „6-2-1“ (showT erzwingt die dritte Zahl, damit eine Spalte einheitlich bleibt)
export const apwl = (w, l, t, showT) => `${nn(w)}-${nn(l)}` + (showT || t ? `-${nn(t)}` : '');

export const spGroup = cur => chips('Spieler, D/ST und Moves',
  [['#spieler', 'Spieler', 'spieler'], ['#dst', 'D/ST-Faktoren', 'dst'], ['#moves', 'Moves', 'moves']], cur);

export function seg(label, opts, cur, on) {
  const g = scrollHint(h('div', {class: 'seg', role: 'group', 'aria-label': label}));
  const bs = opts.map(([v, text]) => h('button', {type: 'button', 'aria-pressed': String(v === cur), 'data-v': v}, text));
  g.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    bs.forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    on(b.dataset.v);
  });
  g.set = v => bs.forEach(x => x.setAttribute('aria-pressed', String(x.dataset.v === v)));
  add(g, bs);
  return g;
}

export const tile = (label, value, sub, gid) => h('div', {class: 'tile'},
  h('div', {class: 'tl'}, h('span', null, label), gid ? ib(gid, '') : null),
  h('div', {class: 'tv'}, value), sub ? h('div', {class: 'ts'}, sub) : null);

export const card = (title, ...kids) => h('section', {class: 'card'}, title ? h('h2', null, title) : null, kids);

// ---------------------------------------------------------------- i-Knöpfe (Text aus dem Glossar in index.html)
const term = gid => D.getElementById('g-' + gid);
export function ib(gid, label, extra) {
  const name = term(gid)?.textContent || gid;
  const text = label === '' ? null : label || name;
  return h('button', {type: 'button', class: text ? 'it' : 'i', 'aria-expanded': 'false', 'aria-controls': 'pop',
    'aria-haspopup': 'dialog', 'data-g': gid, 'data-x': extra || null, 'aria-label': 'Erklärung: ' + name},
  text ? [text, h('span', {class: 'i', 'aria-hidden': 'true'}, 'i')] : 'i');
}
export const legend = (ids, extra) => scrollHint(h('div', {class: 'lg'}, h('span', null, 'Erklärungen:'),
  ids.map(g => Array.isArray(g) ? ib(g[0], g[1], g[2]) : ib(g, null, extra?.[g]))));

let popBtn = null;
const pop = () => D.getElementById('pop');
export function showPop(btn, title, nodes) {
  const p = pop();
  if (popBtn === btn && !p.hidden) return closePop(true);
  closePop(false);
  p.replaceChildren(h('div', {class: 'ph'}, h('strong', {id: 'pop-t'}, title),
    h('button', {type: 'button', class: 'x', 'aria-label': 'Schließen', onclick: () => closePop(true)}, '×')), ...nodes.filter(Boolean));
  p.hidden = false;
  popBtn = btn;
  btn.setAttribute('aria-expanded', 'true');
  const r = btn.getBoundingClientRect(), w = Math.min(380, innerWidth - 32);
  p.style.width = w + 'px';
  p.style.left = Math.max(16, Math.min(r.left, innerWidth - w - 16)) + scrollX + 'px';
  p.style.top = r.bottom + scrollY + 6 + 'px';
  p.focus({preventScroll: true});
  const pr = p.getBoundingClientRect();
  if (pr.bottom > innerHeight) scrollBy({top: pr.bottom - innerHeight + 12});
}
export function closePop(refocus) {
  const p = pop();
  if (!p || p.hidden) return;
  p.hidden = true;
  if (popBtn) { popBtn.setAttribute('aria-expanded', 'false'); if (refocus) popBtn.focus(); }
  popBtn = null;
}
export function infoPop(btn) {        // i-Knopf: Begriff und Erklärung aus dem Glossar, dazu ggf. der Grund
  const dt = term(btn.dataset.g);
  showPop(btn, dt ? dt.textContent : btn.dataset.g, [
    h('p', null, dt ? dt.nextElementSibling.textContent : 'Keine Erklärung gefunden.'),
    btn.dataset.x ? h('p', {class: 'warn'}, btn.dataset.x) : null,
    h('p', null, h('a', {href: '#lesart/' + btn.dataset.g}, 'In der Lesart ansehen')),
  ]);
}

// ---------------------------------------------------------------- sortierbare Tabelle
// o = {cap, cols: [{k, l, v: Zeile → Sortierwert, f: Zeile → Inhalt, num, d (1 auf-, −1 absteigend), cls}],
//      rows, sort: [key, dir], cls (z. B. 'rk': Rang und Team fest, auf dem Handy Kürzel), rh (Index der Zeilenkopf-Spalte), rc (Zeile → Klasse), limit}
export function table(o) {
  const capId = id('c');
  const cols = o.cols;
  let sk = o.sort?.[0], sd = o.sort?.[1] ?? -1, limit = o.limit || 1e9;
  const heads = cols.map(c => {
    const th = h('th', {scope: 'col', class: c.num ? 'n' : null});
    if (c.v && o.sortable !== false) th.append(h('button', {type: 'button', onclick: () => {
      if (sk === c.k) sd = -sd; else { sk = c.k; sd = c.d ?? -1; }
      draw();
    }}, c.l, h('span', {class: 'si', 'aria-hidden': 'true'})));
    else th.append(c.l);
    return th;
  });
  const tb = h('tbody'), fn = h('p', {class: 'fn', id: id('f')}), more = h('div');
  const tbl = h('table', {class: o.cls}, h('caption', {id: capId}, o.cap), h('thead', null, h('tr', null, heads)), tb);
  const wrap = scrollHint(h('div', {class: 'tw', role: 'region', tabindex: '0', 'aria-labelledby': capId}, tbl));
  const box = h('div', {class: 'tbox'}, wrap, fn, more);
  const rh = o.rh ?? 1;
  function draw() {
    let rows = o.rows;
    const c = cols.find(x => x.k === sk);
    if (c?.v) rows = sortRows(rows, c.v, sd);
    heads.forEach((th, i) => {
      if (cols[i].k === sk) th.setAttribute('aria-sort', sd > 0 ? 'ascending' : 'descending'); else th.removeAttribute('aria-sort');
    });
    naSet = new Set();
    const shown = rows.slice(0, limit);
    tb.replaceChildren(...shown.map((r, i) => h('tr', {class: o.rc?.(r)}, cols.map((col, j) => h(j === rh ? 'th' : 'td',
      {scope: j === rh ? 'row' : null, class: [col.num && 'n', typeof col.cls === 'function' ? col.cls(r) : col.cls].filter(Boolean).join(' ') || null},
      col.f(r, i))))));
    const reasons = [...naSet];
    naSet = null;
    // leere Auswahl (z. B. Filter ohne Treffer) sichtbar machen, statt nur einen leeren Tabellenkörper zu zeigen
    const txt = [rows.length ? '' : 'Keine Einträge für diese Auswahl.', reasons.length ? '„–“: ' + reasons.join(' · ') : ''].filter(Boolean).join(' ');
    fn.replaceChildren(txt);
    fn.hidden = !txt && !o.note;
    if (o.note) fn.append(txt ? ' · ' : '', o.note);
    if (fn.hidden) tbl.removeAttribute('aria-describedby'); else tbl.setAttribute('aria-describedby', fn.id);
    more.replaceChildren(rows.length > shown.length ? h('button', {type: 'button', class: 'btn more', onclick: () => {
      limit += o.limit;
      draw();
    }}, `Weitere ${Math.min(o.limit, rows.length - shown.length)} anzeigen (${shown.length} von ${rows.length})`) : '');
  }
  box.upd = rows => { o.rows = rows; if (o.limit) limit = o.limit; draw(); };
  draw();
  return box;
}
export function sortRows(rows, fn, dir) {
  const miss = x => x == null || x === '' || Number.isNaN(x);
  return rows.map((r, i) => [fn(r), i, r]).sort((a, b) => {
    const ma = miss(a[0]), mb = miss(b[0]);
    if (ma || mb) return (ma - mb) || a[1] - b[1];        // fehlende Werte immer ans Ende
    if (a[0] < b[0]) return -dir;
    if (a[0] > b[0]) return dir;
    return a[1] - b[1];
  }).map(x => x[2]);
}

// Playoff-%-Zelle mit dünnem 0–100-Balken
export const pbar = v => ok(v) ? h('span', {class: 'pb', style: `--p:${Math.max(0, Math.min(100, v)).toFixed(1)}%`}, po(v)) : na('Simulation folgt');
// Trendpfeil mit Zahl (Farbe nie allein)
export function trend(v, reason) {
  if (!ok(v)) return na(reason);
  const pl = Math.abs(v) === 1 ? 'Platz' : 'Plätze';
  if (v > 0) return h('span', {class: 'up'}, '↑' + v, h('span', {class: 'vh'}, ` ${pl} besser`));
  if (v < 0) return h('span', {class: 'dn'}, '↓' + -v, h('span', {class: 'vh'}, ` ${pl} schlechter`));
  return h('span', {class: 'eq'}, '→', h('span', {class: 'vh'}, 'unverändert'));
}
export const res = r => r ? h('span', {class: r}, r) : '–';
// ESPN-lineupSlotId → Kürzel (falls der Export schon Text liefert, bleibt er)
const SLOTS = {0: 'QB', 2: 'RB', 4: 'WR', 6: 'TE', 7: 'OP', 16: 'D/ST', 17: 'K', 20: 'Bank', 21: 'IR', 23: 'FLEX'};
export const slot = v => v == null ? '–' : typeof v === 'number' ? SLOTS[v] ?? String(v) : v;
export const bench = v => v === 20 || v === 21 || v === 'Bank' || v === 'IR' || v === 'BE';
// Paarung als Karte; full = mit Teamnamen und Wochenrängen, sonst Kürzel (Woche kompakt)
export function game(g, full) {
  const fin = g.winner != null, st = S.weeks.find(w => w.week === g.week)?.status, wi = S.meta.weeks.indexOf(g.week);
  const side = (tid, pts) => {
    const r = fin ? (g.winner === 'T' ? 'T' : g.winner === tid ? 'W' : 'L') : null;
    return h('div', {class: 'gl' + (r === 'W' ? ' win' : '')}, h('span', {class: 'res'}, r ? res(r) : ''),
      full ? tl(tid) : h('a', {href: '#team/' + tid, class: 'tl2', 'aria-label': team(tid)?.name}, kz(tid)),
      h('span', {class: 'pts'}, fin ? num(pts) : ''));
  };
  let meta, info = null;
  if (fin) {
    meta = g.winner === 'T' ? 'Unentschieden' : 'Differenz ' + num(Math.abs(g.home_pf - g.away_pf));
    if (full && wi >= 0) meta += ` · Wochenrang ${team(g.home).wochen.wochenrang[wi]}. und ${team(g.away).wochen.wochenrang[wi]}.`;
  } else if (st === 'laeuft') meta = 'läuft – Ergebnis nach dem Wochenabruf';
  else if (ok(g.p_home)) {
    const p = sp(g.p_home);
    meta = `Siegchance ${kz(g.home)} ${po(p)} · ${kz(g.away)} ${po(100 - p)}`;
    info = full ? ib('siegchance', '') : null;
  } else meta = 'offen';
  return h('li', {class: 'game'}, side(g.home, g.home_pf), side(g.away, g.away_pf), h('div', {class: 'gm row'}, h('span', null, meta), info));
}
export const errBox = (e, retry) => h('div', {class: 'err', role: 'alert'},
  h('p', null, 'Die Daten konnten nicht geladen werden.'), h('p', {class: 'note'}, String(e?.message || e)),
  retry ? h('button', {type: 'button', class: 'btn', onclick: retry}, 'Erneut versuchen') : null);
