// D/ST-Faktoren (lädt dst.json): Streaming aus Sicht der D/ST und Offenses mit Faktor F und Auslösern.
// Farbzellen divergierend um 1,00: blau = günstig für die D/ST, orange = ungünstig; die Zahl steht immer dabei.
let U, S, h;
const fcls = (f, st) => U.fcls(f, st);          // gemeinsame Farbklasse (ui.js), auch im Positions-Matchup
const OWN = {FREEAGENT: 'FA', WAIVERS: 'W'};
// Auslöser kommen als Schlüssel (delta, z, rang); die Langtexte liefert dst.json in ausloeser_legende
const AUS = {delta: 'ΔF', z: 'z', rang: 'Rang'};
const aus = t => [].concat(t.ausloeser || []).map(a => AUS[a] || a);

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const off = r.sub === 'offense';
  U.ap(box, h('h1', null, off ? 'D/ST – Offenses' : 'D/ST – Streaming'), U.spGroup('dst'),
    U.chips('Ansichten D/ST', [['#dst', 'Streaming', ''], ['#dst/offense', 'Offenses', 'offense']], off ? 'offense' : ''));
  const D = await ctx.lazy('dst.json', 'D/ST-Faktoren', box);
  if (!r.alive()) return;
  const ls = D.ligaschnitt || {};
  // Formel steht im i-Fenster „Faktor F“; hier nur Stand und Ligaschnitt, damit die Tabelle auf dem Handy früher beginnt
  U.ap(box, h('p', {class: 'note'}, `nach W${D.through_week ?? S.tw} · Ligaschnitt D/ST 2025 ${U.num(ls['2025'])} · 2026 ${U.num(ls['2026'])} · Faktor F`, U.ib('f', '')),
    h('ul', {class: 'leg'}, [['f3', 'F ≥ 1,15 günstig'], ['f1', 'leicht günstig'], ['f0', 'um 1,00'], ['g1', 'leicht ungünstig'], ['g3', 'F ≤ 0,85 ungünstig']]
      .map(([c, t]) => h('li', null, h('span', {class: 'fz ' + c, style: 'display:inline-block;min-width:1.4rem;height:.9rem;border-radius:3px;vertical-align:-2px;margin-right:4px'}), t))));
  if (!off) box.querySelector('ul.leg')?.append(h('li', null, h('span', {class: 'flag'}, '⚑ '), 'Auslöser bei dieser Offense – ', h('a', {href: '#dst/offense'}, 'Offenses')));
  (off ? offense : streaming)(box, D, r);
}

function streaming(box, D, r) {
  let frei = r.q.get('frei') === '1';
  const teams = D.teams || [];
  const nw = [0, 1, 2].map(i => teams.find(t => t.naechste?.[i])?.naechste[i]?.week);
  const fcell = v => U.val(v, x => U.num(x, 2), 'kein Gegner');
  // Auslöser gehören zur Offense: das Fähnchen markiert den Gegner in der Wochenzelle, nicht die D/ST
  const offBy = Object.fromEntries(teams.map(t => [t.abbrev, t]));
  const oflag = ab => {
    const a = offBy[ab] ? aus(offBy[ab]) : [];
    if (!a.length) return null;
    const txt = `Auslöser der Offense ${ab}: ${a.join(', ')}`;
    return h('span', {class: 'flag', title: txt}, h('span', {'aria-hidden': 'true'}, ' ⚑'), h('span', {class: 'vh'}, ' ' + txt));
  };
  const next = i => ({k: 'n' + i, l: nw[i] ? 'W' + nw[i] : '–', num: 1, v: t => t.naechste?.[i]?.f ?? null,
    cls: t => 'fz ' + (t.naechste?.[i]?.opp ? fcls(t.naechste[i].f) : 'bye'),
    f: t => { const x = t.naechste?.[i]; if (!x) return '–'; return x.opp ? [x.opp, oflag(x.opp), h('small', null, U.num(x.f, 2))] : ['Bye', h('small', null, '·')]; }});
  const cols = [
    {k: 'd', l: 'D/ST', v: t => t.abbrev, d: 1, flt: false, f: t => h('a', {href: '#spieler/' + -(16000 + t.id), class: 'tl2', 'aria-label': t.abbrev + ' D/ST'}, t.abbrev)},
    {k: 'n3', l: 'Ø nächste 3', num: 1, v: t => t.naechste3, cls: t => 'fz ' + fcls(t.naechste3), f: t => fcell(t.naechste3)},
    {k: 'b', l: 'Besitzer', v: t => t.besitzer > 0 ? U.kz(t.besitzer) : 'zz' + (OWN[t.status] || 'FA'), d: 1,
      f: t => t.besitzer > 0 ? h('a', {href: '#team/' + t.besitzer, class: 'tl2', 'aria-label': U.team(t.besitzer)?.name}, U.kz(t.besitzer)) : (OWN[t.status] || 'FA')},
    next(0), next(1), next(2),
    {k: 'rest', l: `Rest bis W14`, num: 1, v: t => t.rest, cls: t => 'fz ' + fcls(t.rest), f: t => fcell(t.rest)},
    {k: 'sos', l: 'SoS W15–17', num: 1, v: t => t.sos_po, cls: t => 'fz ' + fcls(t.sos_po), f: t => fcell(t.sos_po)},
    {k: 'bye', l: 'Bye', num: 1, cat: 1, v: t => t.bye, d: 1, f: t => U.val(t.bye, v => 'W' + v)}];
  const rows = () => teams.filter(t => !frei || !(t.besitzer > 0));
  const tbl = U.table({cap: 'D/ST-Streaming: Gegner der nächsten Wochen', cls: 'nr', rh: 0, rows: rows(), sort: ['n3', -1], filter: true, stick: true, cols});
  U.ap(box, h('div', {class: 'row'}, h('label', {class: 'chk'}, h('input', {type: 'checkbox', checked: frei, onchange: e => {
    frei = e.target.checked;
    tbl.upd(rows());
    U.setQ('dst', {frei: frei ? 1 : null});
  }}), 'nur freie D/ST (FA und Waivers)')), tbl,
  U.legend(['filter', 'f', 'naechste3', 'rest', 'sos', 'ausloeser']));
}

function offense(box, D) {
  const cols = [
    {k: 'o', l: 'Offense', v: t => t.abbrev, d: 1, flt: false, f: t => h('strong', null, t.abbrev)},
    {k: 'f', l: 'F', num: 1, v: t => t.f, cls: t => 'fz ' + fcls(t.f, 3), f: t => U.num(t.f, 3)},
    {k: 'd', l: 'ΔF', num: 1, v: t => t.delta, f: t => U.val(t.delta, v => U.sgn(v, 3), 'keine Vorwoche')},
    {k: 'r', l: 'Rang', num: 1, v: t => t.rang, d: 1, f: t => [t.rang + '.', h('span', {class: 'sub'}, U.ok(t.rang_vorwoche) ? `Vorw. ${t.rang_vorwoche}.` : '')]},
    {k: 'z25', l: 'Z25', num: 1, v: t => t.z25, f: t => U.num(t.z25)},
    {k: 'z26', l: 'Z26 (n)', num: 1, v: t => t.z26, f: t => [U.val(t.z26, U.num, 'noch kein Spiel'), ` (${t.n ?? 0})`]},
    {k: 'r25', l: 'r25', num: 1, v: t => t.r25, f: t => U.num(t.r25, 3)},
    {k: 'r26', l: 'r26', num: 1, v: t => t.r26, f: t => U.val(t.r26, v => U.num(v, 3), 'noch kein Spiel')},
    {k: 'z3', l: 'Z letzte 3', num: 1, v: t => t.z_last3, f: t => U.val(t.z_last3, U.num, 'ab 4 Spielen')},
    {k: 'a', l: 'Auslöser', v: t => (t.ausloeser || []).length || null, f: t => {
      const a = aus(t);
      return a.length ? h('span', {class: 'flag'}, '⚑ ' + a.join(' · ')) : t.beobachten ? h('span', {class: 'note'}, 'beobachten') : '–';
    }}];
  const L = D.ausloeser_legende || {};
  U.ap(box, U.table({cap: 'Offenses: Off. zugelassen und Faktor F', cls: 'nr', rh: 0, rows: D.teams || [], sort: ['f', -1], filter: true, cols}),
    Object.keys(L).length ? h('ul', {class: 'leg', 'aria-label': 'Auslöser'}, Object.entries(L).map(([k, v]) => h('li', null, h('strong', null, '⚑ ' + (AUS[k] || k) + ': '), v))) : null,
    U.legend(['filter', 'z-dst', 'r', 'f', 'delta-f', 'ausloeser', 'beobachten']));
}
