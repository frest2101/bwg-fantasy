// Woche › Matchups › D/ST (#woche/matchups/dst, lädt dst.json): D/ST-Faktoren je NFL-Offense mit Faktor (F). Die frühere Sicht
// „Streaming“ entfällt (Entscheidung Stephan 04.10.2026): freie D/ST mit Gegner und Faktor zeigt Markt › Freie Spieler › D/ST.
// Farbzellen divergierend um 1,00: blau = günstig für die D/ST, orange = ungünstig; die Zahl steht immer dabei.
let U, S, h;
const fcls = (f, st) => U.fcls(f, st);          // gemeinsame Farbklasse (ui.js), auch in den Matchups je Position

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  U.kopf(box, r, 'Matchups – D/ST');
  U.ap(box, U.muChips('dst'));
  const D = await ctx.lazy('dst.json', 'Matchups D/ST', box);
  if (!r.alive()) return;
  const ls = D.ligaschnitt || {};
  // Formel steht im i-Fenster „Faktor (D/ST)“; hier nur Stand und Ligaschnitt, damit die Tabelle auf dem Handy früher beginnt
  U.ap(box, h('p', {class: 'note'}, `nach W${D.through_week ?? S.tw} · Ligaschnitt D/ST 2025 ${U.num(ls['2025'])} · 2026 ${U.num(ls['2026'])} · Faktor`, U.ib('f', '')),
    h('ul', {class: 'leg'}, [['f3', 'Faktor ≥ 1,15 günstig'], ['f1', 'leicht günstig'], ['f0', 'um 1,00'], ['g1', 'leicht ungünstig'], ['g3', 'Faktor ≤ 0,85 ungünstig']]
      .map(([c, t]) => h('li', null, h('span', {class: 'fz ' + c, style: 'display:inline-block;min-width:1.4rem;height:.9rem;border-radius:3px;vertical-align:-2px;margin-right:4px'}), t))));
  offense(box, D);
  U.ap(box, h('p', {class: 'note'}, 'Freie D/ST mit Gegner, Faktor und Bye: ', h('a', {href: '#markt?pos=' + encodeURIComponent('D/ST')}, 'Markt › Freie Spieler › D/ST'), '.'));
}

function offense(box, D) {
  const cols = [
    {k: 'o', l: 'Offense', v: t => t.abbrev, d: 1, flt: false, f: t => h('strong', null, t.abbrev)},
    {k: 'f', l: 'Faktor', num: 1, v: t => t.f, cls: t => 'fz ' + fcls(t.f, 3), f: t => U.num(t.f, 3)},
    {k: 'd', l: 'zur Vorwoche', num: 1, v: t => t.delta, f: t => U.val(t.delta, v => U.sgn(v, 3), 'keine Vorwoche')},
    {k: 'r', l: 'Rang', num: 1, v: t => t.rang, d: 1, f: t => [t.rang + '.', h('span', {class: 'sub'}, U.ok(t.rang_vorwoche) ? `Vorwoche ${t.rang_vorwoche}.` : '')]},
    {k: 'z25', l: 'Zugelassen 2025', num: 1, v: t => t.z25, f: t => U.num(t.z25)},
    {k: 'z26', l: 'Zugelassen 2026 (Spiele)', num: 1, v: t => t.z26, f: t => [U.val(t.z26, U.num, 'noch kein Spiel'), ` (${t.n ?? 0})`]},
    {k: 'r25', l: 'Verhältnis 2025', num: 1, v: t => t.r25, f: t => U.num(t.r25, 3)},
    {k: 'r26', l: 'Verhältnis 2026', num: 1, v: t => t.r26, f: t => U.val(t.r26, v => U.num(v, 3), 'noch kein Spiel')},
    {k: 'z3', l: 'Zugelassen letzte 3', num: 1, v: t => t.z_last3, f: t => U.val(t.z_last3, U.num, 'noch kein Spiel')}];
  U.ap(box, U.table({cap: 'Offenses: Punkte zugelassen und Faktor', cls: 'nr', rh: 0, rows: D.teams || [], sort: ['f', -1], filter: true, cols}),
    U.legend(['filter', 'z-dst', 'r', 'f', 'delta-f', 'z-letzte3']));
}
