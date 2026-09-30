// Tab Spielplan: Wochenwahl W1–17, Kacheln, Paarungen, Wochentabelle, Top-Scorer, Saisonwochen
let U, S, h;
const STATUS = {final: 'final', laeuft: 'läuft', offen: 'offen'};

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const fin = S.weeks.filter(w => w.status === 'final');
  const def = fin.at(-1)?.week ?? S.weeks[0]?.week ?? 1;
  const m = /^w(\d+)$/.exec(r.sub);
  const W = S.weeks.find(w => w.week === (m ? +m[1] : def)) || S.weeks.find(w => w.week === def);
  if (!W) { U.ap(box, h('h1', null, 'Spielplan'), h('p', {class: 'note'}, 'Kein Spielplan vorhanden.')); return; }
  const wk = W.week, end = new Date(new Date(W.start + 'T12:00:00Z').getTime() + 6 * 864e5);
  const nav = U.chips('Woche wählen', S.weeks.map(w => ['#spielplan/w' + w.week,
    [`W${w.week}`, h('small', null, (w.playoff ? 'PO · ' : '') + U.spanne(w.start))], w.week, w.playoff ? 'po' : null]), wk, 'wk');
  U.ap(box, h('h1', null, `Spielplan – W${wk}`),
    h('p', {class: 'note'}, `${W.playoff ? 'Playoffs · ' : ''}${STATUS[W.status] || W.status} · ${U.datum(W.start)} bis ${U.datum(end)}`), nav);
  U.centerChip(nav);

  const games = S.sched.games.filter(g => g.week === wk);
  const svg = await ctx.mod('svg');
  if (W.status === 'final') U.ap(box, tiles(W));
  const poTxt = wk === 15 ? 'Die Paarungen stehen nach W14 fest (6 Teams, Seeds 1–2 mit Bye). ' : `Die Paarungen stehen nach W${wk - 1} fest. `;
  U.ap(box, h('h2', null, 'Paarungen'), games.length ? h('ul', {class: 'games'}, games.map(g => U.game(g, true)))
    : h('p', {class: 'note'}, W.playoff ? [poTxt, h('a', {href: '#tabelle/ausblick'}, 'Playoff-Chancen')] : 'Für diese Woche gibt es keine Paarungen.'));
  const wi = S.meta.weeks.indexOf(wk);
  if (W.status === 'final' && wi >= 0) U.ap(box, weekTable(wi, wk), h('div', {style: 'margin-top:16px'}, topScorer(W)));
  else if (W.status !== 'final') U.ap(box, h('p', {class: 'note'}, 'Wochentabelle und Top-Scorer erscheinen, sobald die Woche final ist.'));
  U.ap(box, seasonWeeks(fin, svg, wk));
}

function tiles(W) {
  const who = x => x ? [U.tl(x.team_id)] : null;
  return h('div', {class: 'tiles'},
    U.tile('Wochenbestwert', U.num(W.high?.pf), who(W.high)),
    U.tile('Ligaschnitt', U.num(W.ligaschnitt), null),
    U.tile('Median', U.num(W.median), null, 'wochenmedian'),
    U.tile('Tiefstwert', U.num(W.low?.pf), who(W.low)),
    U.tile('Verschenkt', U.num(W.bank_suende?.verschenkt), who(W.bank_suende), 'bank-suende'),
    U.tile('Liga-Effizienz', U.pct(W.effizienz_liga), null, 'eff-woche'));
}

function weekTable(i, wk) {
  const w = t => t.wochen, anyT = S.teams.some(t => w(t).allplay_t[i] > 0);
  const val = (k, f) => ({v: t => w(t)[k][i], f: t => U.val(w(t)[k][i], f, 'kein Spiel')});
  return h('div', null, h('p', {class: 'note'}, 'Diese Woche in der Tabelle: ', h('a', {href: '#tabelle/allplay/w' + wk}, 'All-Play'), ' · ',
    h('a', {href: '#tabelle/punkte/w' + wk}, 'Punkte'), ' · ', h('a', {href: '#tabelle/coaching/w' + wk}, 'Coaching')),
  U.table({cap: `Wochentabelle W${wk}`, cls: 'rk', rows: S.teams, sort: ['wr', 1], cols: [
    {k: 'wr', l: '#', v: t => w(t).wochenrang[i], d: 1, f: t => w(t).wochenrang[i]},
    {k: 'team', l: 'Team', v: t => t.name.toLowerCase(), d: 1, f: t => U.tl(t.team_id)},
    {k: 'opp', l: 'Gegner', v: t => U.kz(w(t).gegner[i]), d: 1, f: t => h('a', {href: '#team/' + w(t).gegner[i], class: 'tl2', 'aria-label': U.team(w(t).gegner[i])?.name}, U.kz(w(t).gegner[i]))},
    {k: 'pf', l: 'PF', num: 1, ...val('pf', U.num)},
    {k: 'pa', l: 'PA', num: 1, ...val('pa', U.num)},
    {k: 'e', l: 'Erg.', v: t => w(t).ergebnis[i], f: t => U.res(w(t).ergebnis[i])},
    {k: 'ef', l: 'Eff. %', num: 1, ...val('efficiency', U.pct)},
    {k: 'ap', l: anyT ? 'AP W-L-T' : 'AP W-L', num: 1, v: t => w(t).allplay_pct[i], f: t => U.apwl(w(t).allplay_w[i], w(t).allplay_l[i], w(t).allplay_t[i], anyT)},
    {k: 'md', l: 'Median', v: t => +!!w(t).median_win[i], f: t => w(t).median_win[i] ? h('span', {class: 'W'}, '✓', h('span', {class: 'vh'}, 'ja')) : h('span', {class: 'na'}, '–', h('span', {class: 'vh'}, 'nein'))},
    {k: 'mg', l: 'Matchup-Glück', num: 1, ...val('matchup_glueck', U.sgn)},
    {k: 'vs', l: 'Verschenkt', num: 1, ...val('verschenkt', U.num)},
    {k: 'bk', l: 'Bank', num: 1, ...val('bank', U.num)},
    {k: 'pd', l: 'Proj.-Δ', num: 1, ...val('projektions_delta', U.sgn)}],
  note: 'Matchup-Glück: Sieg unter dem Wochenmedian +, Niederlage über dem Median −, sonst 0.'}),
  U.legend(['wochenrang', 'eff-woche', 'ap-wl', 'median', 'matchup-woche', 'verschenkt', 'bank', 'proj-delta']));
}

function topScorer(W) {
  const rows = W.top_scorer || [];
  if (!rows.length) return h('p', {class: 'note'}, 'Keine Top-Scorer vorhanden.');
  return h('div', null, U.table({cap: `Top-Scorer W${W.week} (alle Kader, auch Bank)`, cls: 'rk', rows, sort: ['pts', -1], cols: [
    // # = Punkterang der Woche (fest, auch nach dem Umsortieren); Pkt direkt hinter dem Namen, auf dem Handy sonst außer Sicht
    {k: 'i', l: '#', v: p => p.rang, d: 1, f: (p, i) => p.rang ?? i + 1},
    {k: 'name', l: 'Spieler', v: p => p.name, d: 1, f: p => h('a', {href: '#spieler/' + p.player_id, class: 'tl2'}, p.name)},
    {k: 'pts', l: 'Pkt', num: 1, v: p => p.pts, f: p => U.num(p.pts)},
    {k: 'sl', l: 'Slot', v: p => U.slot(p.slot), d: 1, f: p => U.bench(p.slot) ? h('strong', null, U.slot(p.slot)) : U.slot(p.slot)},
    {k: 'tm', l: 'Team', v: p => U.kz(p.team_id), d: 1, f: p => h('a', {href: '#team/' + p.team_id, class: 'tl2', 'aria-label': U.team(p.team_id)?.name}, U.kz(p.team_id))},
    {k: 'pos', l: 'Pos', v: p => p.pos, d: 1, f: p => p.pos},
    {k: 'nfl', l: 'NFL', v: p => p.nfl, d: 1, f: p => p.nfl || 'FA'},
    {k: 'proj', l: 'Proj.', num: 1, v: p => p.proj, f: p => U.val(p.proj, U.num, 'keine Projektion')}]}));
}

function seasonWeeks(fin, svg, cur) {
  if (!fin.length) return h('p', {class: 'note'}, 'Noch keine abgeschlossene Woche.');
  const who = x => x ? h('span', null, U.num(x.pf), ' ', h('a', {href: '#team/' + x.team_id, class: 'tl2', 'aria-label': U.team(x.team_id)?.name}, U.kz(x.team_id))) : '–';
  // gewählte Woche hervorgehoben; „Top-Team“ entfällt, es ist per Definition das Team mit dem Wochenhoch
  const tbl = U.table({cap: 'Saisonwochen', cls: 'nr', rows: fin, sort: ['w', 1], rc: w => w.week === cur ? 'me' : null, cols: [
    {k: 'w', l: 'Woche', v: w => w.week, d: 1, f: w => h('a', {href: '#spielplan/w' + w.week, class: 'tl2'}, 'W' + w.week)},
    {k: 'ls', l: 'Ligaschnitt', num: 1, v: w => w.ligaschnitt, f: w => U.num(w.ligaschnitt)},
    {k: 'hi', l: 'Hoch', num: 1, v: w => w.high?.pf, f: w => who(w.high)},
    {k: 'lo', l: 'Tief', num: 1, v: w => w.low?.pf, f: w => who(w.low)},
    {k: 'md', l: 'Median', num: 1, v: w => w.median, f: w => U.num(w.median)}], rh: 0});
  const x = fin.map(w => 'W' + w.week);
  const f = svg.fig('Wochen-Band', svg.lines({title: 'Wochen-Band: Hoch, Tief und Ligaschnitt je Woche',
    desc: `Band von Tief- bis Hochwert, gestrichelt der Ligaschnitt; zuletzt ${U.num(fin.at(-1).ligaschnitt)}.`,
    x, series: [], avg: fin.map(w => w.ligaschnitt), band: [fin.map(w => w.low?.pf), fin.map(w => w.high?.pf)], yfmt: v => U.num(v, 0), H: 200}),
  {heads: ['Woche', 'Tief', 'Ligaschnitt', 'Hoch'], rows: fin.map(w => ['W' + w.week, U.num(w.low?.pf), U.num(w.ligaschnitt), U.num(w.high?.pf)])},
  h('p', {class: 'note'}, 'Fläche: Tief- bis Hochwert der Woche · gestrichelt: Ligaschnitt'));
  return h('section', {class: 'two sw'}, h('div', null, tbl), f);
}
