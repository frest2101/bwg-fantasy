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
  const cur = nav.querySelector('[aria-current]');
  if (cur) nav.scrollLeft += cur.getBoundingClientRect().left - nav.getBoundingClientRect().left - (nav.clientWidth - cur.offsetWidth) / 2;

  const games = S.sched.games.filter(g => g.week === wk);
  const svg = await ctx.mod('svg');
  if (W.status === 'final') U.ap(box, tiles(W));
  U.ap(box, h('h2', null, 'Paarungen'), games.length ? h('ul', {class: 'games'}, games.map(g => U.game(g, true)))
    : h('p', {class: 'note'}, W.playoff ? 'Die Playoff-Paarungen stehen nach W14 fest (6 Teams, W15–17).' : 'Für diese Woche gibt es keine Paarungen.'));
  const wi = S.meta.weeks.indexOf(wk);
  if (W.status === 'final' && wi >= 0) U.ap(box, weekTable(wi, wk), h('div', {style: 'margin-top:16px'}, topScorer(W)));
  else if (W.status !== 'final') U.ap(box, h('p', {class: 'note'}, 'Wochentabelle und Top-Scorer erscheinen, sobald die Woche final ist.'));
  U.ap(box, seasonWeeks(fin, svg));
}

function tiles(W) {
  const who = x => x ? [U.tl(x.team_id)] : null;
  return h('div', {class: 'tiles'},
    U.tile('Wochenbestwert', U.num(W.high?.pf), who(W.high)),
    U.tile('Ligaschnitt', U.num(W.ligaschnitt), null),
    U.tile('Median', U.num(W.median), null, 'median'),
    U.tile('Tiefstwert', U.num(W.low?.pf), who(W.low)),
    U.tile('Größte Bank-Sünde', U.num(W.bank_suende?.verschenkt), who(W.bank_suende), 'verschenkt'));
}

function weekTable(i, wk) {
  const w = t => t.wochen;
  // Proj.-Δ nur, wenn beide Werte da sind (null würde sonst als 0 gerechnet)
  const pd = t => U.ok(w(t).pf[i]) && U.ok(w(t).projektion[i]) ? w(t).pf[i] - w(t).projektion[i] : null;
  return h('div', null, U.table({cap: `Wochentabelle W${wk}`, cls: 'rk kurz', rows: S.teams, sort: ['wr', 1], cols: [
    {k: 'wr', l: '#', v: t => w(t).wochenrang[i], d: 1, f: t => w(t).wochenrang[i]},
    {k: 'team', l: 'Team', v: t => t.name.toLowerCase(), d: 1, f: t => U.tl(t.team_id)},
    {k: 'opp', l: 'Gegner', v: t => U.kz(w(t).gegner[i]), d: 1, f: t => h('a', {href: '#team/' + w(t).gegner[i], class: 'tl2'}, U.kz(w(t).gegner[i]))},
    {k: 'pf', l: 'PF', num: 1, v: t => w(t).pf[i], f: t => U.num(w(t).pf[i])},
    {k: 'pa', l: 'PA', num: 1, v: t => w(t).pa[i], f: t => U.num(w(t).pa[i])},
    {k: 'e', l: 'Erg.', v: t => w(t).ergebnis[i], f: t => U.res(w(t).ergebnis[i])},
    {k: 'ap', l: 'AP-W', num: 1, v: t => w(t).allplay_w[i], f: t => U.nn(w(t).allplay_w[i])},
    {k: 'md', l: 'Median', v: t => +!!w(t).median_win[i], f: t => w(t).median_win[i] ? h('span', {class: 'W'}, '✓', h('span', {class: 'vh'}, 'ja')) : h('span', {class: 'na'}, '–', h('span', {class: 'vh'}, 'nein'))},
    {k: 'vs', l: 'Verschenkt', num: 1, v: t => w(t).verschenkt[i], f: t => U.num(w(t).verschenkt[i])},
    {k: 'bk', l: 'Bank', num: 1, v: t => w(t).bank[i], f: t => U.num(w(t).bank[i])},
    {k: 'pr', l: 'Proj.', num: 1, v: t => w(t).projektion[i], f: t => U.num(w(t).projektion[i])},
    {k: 'pd', l: 'Proj.-Δ', num: 1, v: t => pd(t), f: t => U.val(pd(t), U.sgn, 'keine Projektion')}]}),
  U.legend(['wochenrang', 'ap-wl', 'median', 'verschenkt', 'bank', 'proj-delta']));
}

function topScorer(W) {
  const rows = W.top_scorer || [];
  if (!rows.length) return h('p', {class: 'note'}, 'Keine Top-Scorer vorhanden.');
  return h('div', null, U.table({cap: `Top-Scorer W${W.week} (alle Kader, auch Bank)`, cls: 'rk', rows, sort: ['pts', -1], cols: [
    {k: 'i', l: '#', f: (p, i) => i + 1},
    {k: 'name', l: 'Spieler', v: p => p.name, d: 1, f: p => h('a', {href: '#spieler/' + p.player_id, class: 'tl2'}, p.name)},
    {k: 'pos', l: 'Pos', v: p => p.pos, d: 1, f: p => p.pos},
    {k: 'nfl', l: 'NFL', v: p => p.nfl, d: 1, f: p => p.nfl},
    {k: 'tm', l: 'Team', v: p => U.kz(p.team_id), d: 1, f: p => h('a', {href: '#team/' + p.team_id, class: 'tl2', 'aria-label': U.team(p.team_id)?.name}, U.kz(p.team_id))},
    {k: 'sl', l: 'Slot', v: p => U.slot(p.slot), d: 1, f: p => U.bench(p.slot) ? h('strong', null, U.slot(p.slot)) : U.slot(p.slot)},
    {k: 'pts', l: 'Pkt', num: 1, v: p => p.pts, f: p => U.num(p.pts)},
    {k: 'proj', l: 'Proj.', num: 1, v: p => p.proj, f: p => U.val(p.proj, U.num, 'keine Projektion')}]}));
}

function seasonWeeks(fin, svg) {
  if (!fin.length) return h('p', {class: 'note'}, 'Noch keine abgeschlossene Woche.');
  const who = x => x ? h('span', null, U.num(x.pf), ' ', h('a', {href: '#team/' + x.team_id, 'aria-label': U.team(x.team_id)?.name}, U.kz(x.team_id))) : '–';
  const tbl = U.table({cap: 'Saisonwochen', cls: 'nr', rows: fin, sort: ['w', 1], cols: [
    {k: 'w', l: 'Woche', v: w => w.week, d: 1, f: w => h('a', {href: '#spielplan/w' + w.week, class: 'tl2'}, 'W' + w.week)},
    {k: 'ls', l: 'Ligaschnitt', num: 1, v: w => w.ligaschnitt, f: w => U.num(w.ligaschnitt)},
    {k: 'hi', l: 'Hoch', num: 1, v: w => w.high?.pf, f: w => who(w.high)},
    {k: 'lo', l: 'Tief', num: 1, v: w => w.low?.pf, f: w => who(w.low)},
    {k: 'md', l: 'Median', num: 1, v: w => w.median, f: w => U.num(w.median)},
    {k: 'tt', l: 'Top-Team', v: w => U.kz(w.top_team_id), d: 1, f: w => U.tl(w.top_team_id)}], rh: 0});
  const x = fin.map(w => 'W' + w.week);
  const f = svg.fig('Wochen-Band', svg.lines({title: 'Wochen-Band: Hoch, Tief und Ligaschnitt je Woche',
    desc: `Band von Tief- bis Hochwert, gestrichelt der Ligaschnitt; zuletzt ${U.num(fin.at(-1).ligaschnitt)}.`,
    x, series: [], avg: fin.map(w => w.ligaschnitt), band: [fin.map(w => w.low?.pf), fin.map(w => w.high?.pf)], yfmt: v => U.num(v, 0), H: 200}),
  {heads: ['Woche', 'Tief', 'Ligaschnitt', 'Hoch'], rows: fin.map(w => ['W' + w.week, U.num(w.low?.pf), U.num(w.ligaschnitt), U.num(w.high?.pf)])});
  return h('section', {class: 'two', style: 'margin-top:8px'}, h('div', null, tbl), f);
}
