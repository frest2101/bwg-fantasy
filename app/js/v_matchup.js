// Positions-Matchup (lädt matchup.json): Faktor F je NFL-Defense und Position (QB, RB, WR, TE, K) mit derselben Formel wie
// die D/ST-Faktoren – wie viele Punkte Spieler der Position gegen diese Defense holen, relativ zum Ligaschnitt. Position gegen
// Defense, kein Einzelduell. Farbzellen wie im D/ST-Tab: blau = günstig für die Position (F > 1), orange = ungünstig.
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K'];
// Auslöser kommen als Schlüssel (delta, rang); die Langtexte liefert matchup.json in ausloeser_legende
const AUS = {delta: 'ΔF', rang: 'Rang'};
const aus = t => [].concat(t?.ausloeser || []).map(a => AUS[a] || a);
const fz = v => 'fz' + (U.ok(v) ? ' ' + U.fcls(v) : '');

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const pos = POS.find(p => p.toLowerCase() === r.sub) || '';
  U.ap(box, h('h1', null, pos ? `Positions-Matchup – ${pos}` : 'Positions-Matchup'), U.spGroup('matchup'),
    U.chips('Ansichten Positions-Matchup', [['#matchup', 'Übersicht', ''], ...POS.map(p => ['#matchup/' + p.toLowerCase(), p, p])], pos));
  if (!S.man.files?.['matchup.json']) {
    U.ap(box, h('p', {class: 'warn'}, 'Noch keine Matchup-Daten: Die Seite füllt sich mit dem nächsten Wochenabruf.'));
    return;
  }
  const M = await ctx.lazy('matchup.json', 'Positions-Matchup', box);
  if (!r.alive()) return;
  const ls = M.ligaschnitt?.[pos] || {};
  // Formel steht im i-Fenster „Faktor F (Position)“; hier nur Stand, Lesart und Ligaschnitt, damit die Tabelle früh beginnt
  U.ap(box, h('p', {class: 'note'}, `nach W${M.through_week ?? S.tw} · Position gegen Defense, kein Einzelduell`,
    pos ? [` · Ligaschnitt ${pos} je Spiel 2025 `, U.val(ls['2025'], U.num, 'Vorjahr noch nicht geladen'), ` · 2026 `, U.val(ls['2026'], U.num, 'noch kein Spiel')] : '', ' ',
    U.ib('positions-matchup', '')),
  M.vorjahr_quelle === 'ligamittel' ? h('p', {class: 'warn'}, 'Vorjahr noch nicht geladen – bis zum nächsten Wochenabruf gilt r25 = 1,00 (Ligamittel).') : null,
  h('ul', {class: 'leg', 'aria-label': 'Farben: F für die Position'}, [['f3', 'F ≥ 1,15 günstig'], ['f1', 'leicht günstig'], ['f0', 'um 1,00'], ['g1', 'leicht ungünstig'], ['g3', 'F ≤ 0,85 ungünstig']]
    .map(([c, t]) => h('li', null, h('span', {class: 'fz fzs ' + c, 'aria-hidden': 'true'}), t))));
  (pos ? position : overview)(box, M, pos);
}

// ---------------------------------------------------------------- Übersicht: Defense × Position
function overview(box, M) {
  const flag = (d, p, x) => {
    const a = aus(x);
    if (!a.length) return null;
    const txt = `Auslöser ${p} gegen ${d.abbrev}: ${a.join(', ')}`;
    return h('span', {class: 'flag', title: txt}, h('span', {'aria-hidden': 'true'}, ' ⚑'), h('span', {class: 'vh'}, ' ' + txt));
  };
  const col = p => ({k: p, l: p, num: 1, v: d => d.pos?.[p]?.f ?? null, cls: d => fz(d.pos?.[p]?.f),
    f: d => {
      const x = d.pos?.[p];
      if (!x || !U.ok(x.f)) return U.na('kein Faktor');
      return [U.num(x.f, 2), flag(d, p, x), h('small', null, h('span', {class: 'vh'}, 'Rang '), U.ok(x.rang) ? x.rang + '.' : '')];
    }});
  const cols = [
    {k: 'd', l: 'Defense', v: d => d.abbrev, d: 1, flt: false, f: d => h('strong', null, d.abbrev)},
    ...(M.positionen || POS).map(col),
    {k: 'bye', l: 'Bye', num: 1, cat: 1, v: d => d.bye, d: 1, f: d => U.val(d.bye, v => 'W' + v, 'kein Bye')}];
  U.ap(box, U.table({cap: 'Faktor F je Defense und Position (klein: Rang)', cls: 'nr', rh: 0, rows: M.defenses || [], sort: ['d', 1], filter: true, stick: true, cols}),
    h('ul', {class: 'leg'}, h('li', null, h('span', {class: 'flag'}, '⚑ '), 'Auslöser bei dieser Position – Details in der Positionsansicht')),
    U.legend(['positions-matchup', 'mu-f', 'mu-rang', 'mu-ausloeser', 'filter']));
}

// ---------------------------------------------------------------- eine Position: wie D/ST-Offenses
function position(box, M, pos) {
  const prior = M.vorjahr_quelle === 'basis';
  const rows = (M.defenses || []).map(d => ({...(d.pos?.[pos] || {}), id: d.id, abbrev: d.abbrev}));
  const cols = [
    {k: 'o', l: 'Defense', v: t => t.abbrev, d: 1, flt: false, f: t => h('strong', null, t.abbrev)},
    {k: 'f', l: 'F', num: 1, v: t => t.f, cls: t => fz(t.f), f: t => U.val(t.f, v => U.num(v, 3), 'kein Faktor')},
    {k: 'd', l: 'ΔF', num: 1, v: t => t.delta, f: t => U.val(t.delta, v => U.sgn(v, 3), 'keine Vorwoche')},
    {k: 'r', l: 'Rang', num: 1, v: t => t.rang, d: 1, f: t => [U.val(t.rang, v => v + '.', 'kein Faktor'),
      h('span', {class: 'sub'}, U.ok(t.rang_vorwoche) ? `Vorw. ${t.rang_vorwoche}.` : '')]},
    {k: 'z25', l: 'Z25', num: 1, v: t => t.z25, f: t => U.val(t.z25, U.num, prior ? 'kein Spiel 2025' : 'Vorjahr noch nicht geladen')},
    {k: 'z26', l: 'Z26 (n)', num: 1, v: t => t.z26, f: t => [U.val(t.z26, U.num, 'noch kein Spiel'), ` (${t.n ?? 0})`]},
    {k: 'r25', l: 'r25', num: 1, v: t => t.r25, f: t => U.val(t.r25, v => U.num(v, 3), 'kein Wert')},
    {k: 'r26', l: 'r26', num: 1, v: t => t.r26, f: t => U.val(t.r26, v => U.num(v, 3), 'noch kein Spiel')},
    {k: 'a', l: 'Auslöser', v: t => aus(t).length || null, f: t => {
      const a = aus(t);
      return a.length ? h('span', {class: 'flag'}, '⚑ ' + a.join(' · ')) : '–';
    }}];
  const L = M.ausloeser_legende || {};
  U.ap(box, U.table({cap: `${pos}: Punkte gegen die Defense und Faktor F`, cls: 'nr', rh: 0, rows, sort: ['f', -1], filter: true, cols}),
    Object.keys(L).length ? h('ul', {class: 'leg', 'aria-label': 'Auslöser'}, Object.entries(L).map(([k, v]) => h('li', null, h('strong', null, '⚑ ' + (AUS[k] || k) + ': '), v))) : null,
    U.legend(['filter', 'mu-z', 'mu-r', 'mu-f', 'delta-f', 'mu-rang', 'mu-ausloeser']));
}
