// Woche › Matchups (#woche/matchups, je Position #woche/matchups/qb … /k und /dst; App-Konzept Paket P3: eine Ansicht statt
// Positions-Matchup und D/ST-Faktoren). Faktor (F) je NFL-Team als Gegner: für QB bis K gegen seine Defense (matchup.json),
// für D/ST gegen seine Offense (dst.json) – dieselbe Formel, wie viele Punkte die Position gegen dieses Team holt, relativ
// zum Ligaschnitt. Position gegen Team, kein Einzelduell. Die frühere Sicht „Streaming“ entfällt (Entscheidung Stephan
// 04.10.2026): freie D/ST mit Gegner und Faktor zeigt Markt › Freie Spieler › D/ST.
// Farbzellen: blau = günstig für die Position (F > 1), orange = ungünstig; die Zahl steht immer dabei.
// Schwacher Hinweis (Analyse 30.09.2026): Z je Position hält sich von Jahr zu Jahr kaum, deshalb keine Auslöser-Fähnchen.
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K'];
const fz = (v, st) => 'fz' + (U.ok(v) ? ' ' + U.fcls(v, st) : '');   // st = angezeigte Stellen (Standard 2)
const FARBEN = [['f3', 'Faktor ≥ 1,15 günstig'], ['f1', 'leicht günstig'], ['f0', 'um 1,00'], ['g1', 'leicht ungünstig'], ['g3', 'Faktor ≤ 0,85 ungünstig']];

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const dst = r.sub === 'dst', pos = POS.find(p => p.toLowerCase() === r.sub) || '';
  U.kopf(box, r, `Matchups – ${dst ? 'D/ST' : pos || 'Übersicht'}`);
  U.ap(box, U.muChips(dst ? 'dst' : pos.toLowerCase()));
  // Daten: Positionen aus matchup.json, D/ST aus dst.json; die Übersicht zeigt beide (fehlt eine Datei, fehlen ihre Spalten)
  const hasM = !!S.man.files?.['matchup.json'], hasD = !!S.man.files?.['dst.json'];
  if (dst ? !hasD : pos ? !hasM : !hasM && !hasD) {
    U.ap(box, h('p', {class: 'warn'}, 'Noch keine Matchup-Daten: Die Seite füllt sich mit dem nächsten Wochenabruf.'));
    return;
  }
  const [M, D] = await Promise.all([!dst && hasM ? ctx.lazy('matchup.json', 'Matchups', box) : null,
    (dst || !pos) && hasD ? ctx.lazy('dst.json', 'Matchups D/ST', box) : null]);
  if (!r.alive()) return;
  const tw = (M || D).through_week ?? S.tw;
  // Formel steht im i-Fenster „Faktor (Position)“ bzw. „Faktor (D/ST)“; hier nur Stand, Einordnung und Ligaschnitt, damit die
  // Tabelle auf dem Handy früh beginnt
  const ls = dst ? D.ligaschnitt || {} : pos ? M.ligaschnitt?.[pos] || {} : null;
  // „schwacher Hinweis“ gilt laut Rechenregel nur für QB bis K (Z je Position hält sich von Jahr zu Jahr kaum, D/ST deutlich besser)
  const schwach = dst ? '' : pos ? ' · schwacher Hinweis, die Unterschiede sind klein' : ' · QB bis K: schwacher Hinweis, die Unterschiede sind klein';
  U.ap(box, h('p', {class: 'note'}, `nach W${tw} · Position gegen NFL-Team, kein Einzelduell${schwach}`,
    ls ? [` · Ligaschnitt ${dst ? 'D/ST' : pos} je Spiel 2025 `, U.val(ls['2025'], U.num, 'Vorjahr noch nicht geladen'), ' · 2026 ',
      U.val(ls['2026'], U.num, 'noch kein Spiel')] : '', ' ', U.ib(dst ? 'f' : 'positions-matchup', '')),
  !dst && M?.vorjahr_quelle === 'ligamittel' ? h('p', {class: 'warn'}, 'Vorjahr für QB bis K noch nicht geladen – bis zum nächsten Wochenabruf gilt dort für 2025 das Ligamittel (Verhältnis 1,00).') : null,
  h('ul', {class: 'leg', 'aria-label': 'Farben: Faktor für die Position'}, FARBEN.map(([c, t]) => h('li', null, h('span', {class: 'fz fzs ' + c, 'aria-hidden': 'true'}), t))));
  if (dst) offense(box, D);
  else if (pos) position(box, M, pos);
  else overview(box, M, D);
}

// ---------------------------------------------------------------- Übersicht: NFL-Team × Position (QB–K gegen die Defense, D/ST gegen die Offense)
function overview(box, M, D) {
  const byD = new Map((D?.teams || []).map(t => [t.id, t]));
  // Zeilen: alle NFL-Teams aus beiden Dateien; je Zelle Faktor mit Rang darunter
  const ids = [...new Set([...(M?.defenses || []).map(d => d.id), ...byD.keys()])];
  const byM = new Map((M?.defenses || []).map(d => [d.id, d]));
  const rows = ids.map(id => {
    const m = byM.get(id), d = byD.get(id);
    return {id, abbrev: m?.abbrev ?? d?.abbrev, bye: m?.bye ?? d?.bye, pos: {...(m?.pos || {}), ...(d ? {'D/ST': {f: d.f, rang: d.rang}} : {})}};
  });
  const cell = p => ({k: p, l: p, num: 1, v: t => t.pos[p]?.f ?? null, cls: t => fz(t.pos[p]?.f),
    f: t => {
      const x = t.pos[p];
      if (!x || !U.ok(x.f)) return U.na('kein Faktor');
      return [U.num(x.f, 2), h('small', null, h('span', {class: 'vh'}, 'Rang '), U.ok(x.rang) ? x.rang + '.' : '')];
    }});
  const cols = [
    {k: 't', l: 'NFL-Team', v: t => t.abbrev, d: 1, flt: false, f: t => h('strong', null, t.abbrev)},
    ...(M ? M.positionen || POS : []).map(cell), ...(D ? [cell('D/ST')] : []),
    {k: 'bye', l: 'Bye', num: 1, cat: 1, v: t => t.bye, d: 1, f: t => U.val(t.bye, v => 'W' + v, 'kein Bye')}];
  U.ap(box, U.table({cap: 'Faktor je NFL-Team als Gegner (klein: Rang)', cls: 'nr', rh: 0, rows, sort: ['t', 1], filter: true, stick: true, cols,
    note: 'QB bis K: Faktor gegen die Defense des Teams; D/ST: gegen seine Offense.'}),
  U.legend(['positions-matchup', 'mu-f', ...(D ? ['f'] : []), 'mu-rang', 'filter']));
}

// ---------------------------------------------------------------- eine Position (QB–K): Defenses
function position(box, M, pos) {
  const prior = M.vorjahr_quelle === 'basis';
  const rows = (M.defenses || []).map(d => ({...(d.pos?.[pos] || {}), id: d.id, abbrev: d.abbrev}));
  const cols = [
    {k: 'o', l: 'Defense', v: t => t.abbrev, d: 1, flt: false, f: t => h('strong', null, t.abbrev)},
    {k: 'f', l: 'Faktor', num: 1, v: t => t.f, cls: t => fz(t.f, 3), f: t => U.val(t.f, v => U.num(v, 3), 'kein Faktor')},
    {k: 'd', l: 'zur Vorwoche', num: 1, v: t => t.delta, f: t => U.val(t.delta, v => U.sgn(v, 3), 'keine Vorwoche')},
    {k: 'r', l: 'Rang', num: 1, v: t => t.rang, d: 1, f: t => [U.val(t.rang, v => v + '.', 'kein Faktor'),
      h('span', {class: 'sub'}, U.ok(t.rang_vorwoche) ? `Vorwoche ${t.rang_vorwoche}.` : '')]},
    {k: 'z25', l: 'Zugelassen 2025', num: 1, v: t => t.z25, f: t => U.val(t.z25, U.num, prior ? 'kein Spiel 2025' : 'Vorjahr noch nicht geladen')},
    {k: 'z26', l: 'Zugelassen 2026 (Spiele)', num: 1, v: t => t.z26, f: t => [U.val(t.z26, U.num, 'noch kein Spiel'), ` (${t.n ?? 0})`]},
    {k: 'r25', l: 'Verhältnis 2025', num: 1, v: t => t.r25, f: t => U.val(t.r25, v => U.num(v, 3), 'kein Wert')},
    {k: 'r26', l: 'Verhältnis 2026', num: 1, v: t => t.r26, f: t => U.val(t.r26, v => U.num(v, 3), 'noch kein Spiel')}];
  U.ap(box, U.table({cap: `${pos}: Punkte gegen die Defense und Faktor`, cls: 'nr', rh: 0, rows, sort: ['f', -1], filter: true, cols}),
    U.legend(['filter', 'mu-z', 'mu-r', 'mu-f', 'delta-f', 'mu-rang']));
}

// ---------------------------------------------------------------- D/ST: Offenses (bis P3 eigene Ansicht v_dst.js)
function offense(box, D) {
  const cols = [
    {k: 'o', l: 'Offense', v: t => t.abbrev, d: 1, flt: false, f: t => h('strong', null, t.abbrev)},
    {k: 'f', l: 'Faktor', num: 1, v: t => t.f, cls: t => fz(t.f, 3), f: t => U.val(t.f, v => U.num(v, 3), 'kein Faktor')},
    {k: 'd', l: 'zur Vorwoche', num: 1, v: t => t.delta, f: t => U.val(t.delta, v => U.sgn(v, 3), 'keine Vorwoche')},
    {k: 'r', l: 'Rang', num: 1, v: t => t.rang, d: 1, f: t => [U.val(t.rang, v => v + '.', 'kein Faktor'),
      h('span', {class: 'sub'}, U.ok(t.rang_vorwoche) ? `Vorwoche ${t.rang_vorwoche}.` : '')]},
    {k: 'z25', l: 'Zugelassen 2025', num: 1, v: t => t.z25, f: t => U.val(t.z25, U.num, 'kein Spiel 2025')},
    {k: 'z26', l: 'Zugelassen 2026 (Spiele)', num: 1, v: t => t.z26, f: t => [U.val(t.z26, U.num, 'noch kein Spiel'), ` (${t.n ?? 0})`]},
    {k: 'r25', l: 'Verhältnis 2025', num: 1, v: t => t.r25, f: t => U.val(t.r25, v => U.num(v, 3), 'kein Wert')},
    {k: 'r26', l: 'Verhältnis 2026', num: 1, v: t => t.r26, f: t => U.val(t.r26, v => U.num(v, 3), 'noch kein Spiel')},
    {k: 'z3', l: 'Zugelassen letzte 3', num: 1, v: t => t.z_last3, f: t => U.val(t.z_last3, U.num, 'noch kein Spiel')}];
  U.ap(box, U.table({cap: 'D/ST: Punkte gegen die Offense und Faktor', cls: 'nr', rh: 0, rows: D.teams || [], sort: ['f', -1], filter: true, cols}),
    U.legend(['filter', 'z-dst', 'r', 'f', 'delta-f', 'z-letzte3']),
    h('p', {class: 'note'}, 'Freie D/ST mit Gegner, Faktor und Bye: ', h('a', {href: '#markt?pos=' + encodeURIComponent('D/ST')}, 'Markt › Freie Spieler › D/ST'), '.'));
}
