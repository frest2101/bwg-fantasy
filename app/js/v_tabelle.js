// Tab Tabelle: Gesamt, Division, All-Play, Punkte, Coaching, Ausblick (Seeding-Schalter).
// All-Play, Punkte und Coaching gibt es auch je Einzelwoche (#tabelle/allplay/w3): Wochen-Chips unter den Ansichten,
// gleich viele Spalten wie die Saisonsicht, Werte aus teams.json › wochen (Python rechnet, die App zeigt nur an).
const SUBS = [['', 'Gesamt'], ['division', 'Division'], ['allplay', 'All-Play'], ['punkte', 'Punkte'], ['coaching', 'Coaching'], ['ausblick', 'Ausblick']];
const WEEKLY = ['allplay', 'punkte', 'coaching'];
let U, S, h;

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const [s0, w0] = r.sub.split('/');
  const sub = SUBS.some(x => x[0] === s0) ? s0 : '';
  const label = SUBS.find(x => x[0] === sub)[1];
  // Wochensicht nur für gerechnete Wochen (meta.weeks); alles andere fällt still auf die Saisonsicht
  const m = WEEKLY.includes(sub) && /^w(\d+)$/.exec(w0 || '');
  const week = m && S.meta.weeks.includes(+m[1]) ? +m[1] : 0;
  const wi = week ? S.meta.weeks.indexOf(week) : -1;
  const wk = week ? S.weeks.find(x => x.week === week) : null;
  const path = k => '#tabelle' + (k ? '/' + k : '') + (week && WEEKLY.includes(k) ? '/w' + week : '');
  U.ap(box, h('h1', null, (sub ? 'Tabelle – ' + label : 'Tabelle') + (week ? ` · W${week}` : '')),
    week ? h('p', {class: 'note'}, `Einzelwoche W${week}${wk ? ' · ' + U.spanne(wk.start) : ''} · `,
      h('a', {href: '#spielplan/w' + week}, 'Paarungen und Top-Scorer'), U.ib('wochensicht', ''))
      : h('p', {class: 'note'}, `nach W${S.tw} · Regular Season W1–14`, U.ib('nach-wn', '')),
    U.chips('Ansichten der Tabelle', SUBS.map(([k, l]) => [path(k), l, k]), sub));
  if (WEEKLY.includes(sub)) U.centerChip(U.ap(box, U.weekChips('tabelle/' + sub, week)).lastChild);
  const svg = ['allplay', 'punkte', 'coaching', 'ausblick'].includes(sub) ? await ctx.mod('svg') : null;
  ({gesamt, division, allplay, punkte, coaching, ausblick})[sub || 'gesamt'](box, r, svg, wi, week);
}

// Spalten, die mehrere Ansichten nutzen
const c = {
  rang: () => ({k: 'rang', l: '#', v: t => t.rang, d: 1, f: t => t.rang}),
  team: () => ({k: 'team', l: 'Team', v: t => t.name.toLowerCase(), d: 1, f: t => U.tl(t.team_id)}),
  wl: () => ({k: 'wl', l: S.hasT ? 'W-L-T' : 'W-L', v: t => -t.rang, f: U.rec}),
  n: (k, l, f = U.num, d = -1) => ({k, l, num: 1, d, v: t => t[k], f: t => U.val(t[k], f)}),
  pct: (k, l) => ({k, l, num: 1, v: t => t[k], f: t => U.pct(t[k])}),
  po: seeding => ({k: 'po', l: 'PO %', num: 1, v: t => U.sp(t.sim?.[seeding]?.playoff), f: t => U.pbar(U.sp(t.sim?.[seeding]?.playoff))}),
  streak: () => ({k: 'streak', l: 'Streak', v: t => streakVal(t.streak), f: t => t.streak ?? '–'}),
  // Wochenspalten (Index wi in meta.weeks): Wochenrang als #, Wert einer Wochenreihe, Ergebnis, Gegner mit dessen Wochenrang
  wr: wi => ({k: 'wr', l: '#', v: t => t.wochen.wochenrang[wi], d: 1, f: t => t.wochen.wochenrang[wi] ?? '–'}),
  wk: (k, l, wi, f = U.num, d = -1) => ({k, l, num: 1, d, v: t => t.wochen[k][wi], f: t => U.val(t.wochen[k][wi], f, 'kein Spiel')}),
  erg: wi => ({k: 'e', l: 'Erg.', v: t => ({W: 1, T: 0, L: -1})[t.wochen.ergebnis[wi]] ?? null, f: t => U.res(t.wochen.ergebnis[wi])}),
  gegner: wi => ({k: 'gg', l: 'Gegner', v: t => U.kz(t.wochen.gegner[wi]), d: 1, f: t => {
    const o = U.team(t.wochen.gegner[wi]);
    if (!o) return '–';
    const rk = o.wochen.wochenrang[wi];
    return [h('a', {href: '#team/' + o.team_id, class: 'tl2', 'aria-label': o.name}, o.kuerzel), rk ? h('span', {class: 'note'}, ` (${rk}.)`) : null];
  }}),
  median: wi => ({k: 'md', l: 'Median', v: t => +!!t.wochen.median_win[wi], f: t => t.wochen.median_win[wi]
    ? h('span', {class: 'W'}, '✓', h('span', {class: 'vh'}, 'ja')) : h('span', {class: 'na'}, '–', h('span', {class: 'vh'}, 'nein'))}),
};
function streakVal(s) {
  const m = /^([WLT])(\d+)$/.exec(s || '');
  return m ? (m[1] === 'W' ? 1 : m[1] === 'L' ? -1 : 0) * +m[2] : null;
}

function gesamt(box) {
  const tbl = U.table({cap: `Tabelle Gesamt nach W${S.tw}`, cls: 'rk', rows: S.teams, sort: ['rang', 1], cols: [
    c.rang(), c.team(), c.wl(), c.n('pf', 'PF'), c.po('liga'), c.pct('allplay_pct', 'AP %'), c.n('pa', 'PA'),
    c.n('diff', 'Diff', U.sgn), c.pct('efficiency', 'Eff. %'), c.streak()]});
  const last = S.weeks.filter(w => w.status === 'final').at(-1);
  const strip = last ? h('section', {'aria-labelledby': 'wk-h'},
    h('h2', {id: 'wk-h'}, h('a', {href: '#spielplan/w' + last.week}, `W${last.week} kompakt`), h('span', {class: 'note'}, ' · ' + U.spanne(last.start))),
    U.scrollHint(h('ul', {class: 'strip', role: 'list'}, S.sched.games.filter(g => g.week === last.week).map(g => U.game(g, false))))) : null;
  const top = [...S.teams].filter(t => t.pr).sort((a, b) => a.pr.rang - b.pr.rang).slice(0, 5);
  const pr = top.length ? U.card(null, U.table({cap: h('a', {href: '#ranking'}, 'Power Ranking – Top 5'), cls: 'rk', rows: top, sortable: false, cols: [
    {k: 'r', l: '#', f: t => t.pr.rang}, c.team(), {k: 'mu', l: 'μ', num: 1, f: t => U.num(t.pr.mu, 1)},
    {k: 'tr', l: 'Trend', num: 1, f: t => U.trend(t.pr.trend, 'noch kein Vorwochenvergleich')}]})) : null;
  U.ap(box, h('div', {class: 'two g'},
    h('div', null, tbl, U.legend(['rang', 'wlt', 'pf', 'playoff', 'allplay', 'diff', 'effizienz', 'streak'])),
    h('div', null, strip, pr)));
}

function division(box) {
  for (const [d, name] of Object.entries(S.meta.divisions || {})) {
    const rows = S.teams.filter(t => String(t.division) === d);
    U.ap(box, h('div', {class: 'card'}, U.table({cap: `${name} nach W${S.tw}`, cls: 'rk', rows, sort: ['rd', 1], cols: [
      {k: 'rd', l: '#', v: t => t.rang_division, d: 1, f: t => t.rang_division}, c.team(), c.wl(), c.n('pf', 'PF'), c.n('pa', 'PA'),
      c.po('liga'), {k: 'dv', l: 'Div %', num: 1, v: t => U.sp(t.sim?.liga?.division), f: t => U.pbar(U.sp(t.sim?.liga?.division))},
      c.pct('allplay_pct', 'AP %'), c.streak(), {k: 'rg', l: 'Gesamt', num: 1, v: t => t.rang, d: 1, f: t => t.rang + '.'}]})));
  }
  U.ap(box, U.legend(['rang-div', 'wlt', 'pf', 'playoff', 'div-pct', 'allplay', 'streak']));
}

// ---------------------------------------------------------------- All-Play und Luck (Saison und Woche)
function allplay(box, r, svg, wi, week) {
  const W = t => t.wochen;
  if (wi >= 0) {
    // Einzelwoche: Wochenrang, All-Play-Bilanz der Woche, Median, Ergebnis, Gegner (mit Wochenrang) und der Luck-Beitrag
    // = Ergebnis − All-Play-Anteil; er erklärt, warum ein Sieg als Wochen-4. nur zu 6/9 „verdient“ ist
    const anyT = S.teams.some(t => W(t).allplay_t[wi] > 0);
    const rows = U.sortRows(S.teams, t => W(t).luck[wi], -1);
    U.ap(box, U.table({cap: `All-Play und Luck – W${week}`, cls: 'rk', rows: S.teams, sort: ['ap', -1], cols: [
      c.wr(wi), c.team(),
      {k: 'ap', l: anyT ? 'AP W-L-T' : 'AP W-L', num: 1, v: t => W(t).allplay_pct[wi], f: t => U.apwl(W(t).allplay_w[wi], W(t).allplay_l[wi], W(t).allplay_t[wi], anyT)},
      c.wk('allplay_pct', 'AP %', wi, U.pct), c.median(wi), c.erg(wi), c.gegner(wi), c.wk('luck', 'Luck-Beitrag', wi, U.sgn)],
    note: 'Gegner: Kürzel und dessen Wochenrang.'}),
    U.legend(['wochenrang', 'ap-wl', 'allplay', 'median', 'luck-beitrag']),
    svg.fig(`Luck-Beitrag W${week}`, svg.hbars({title: `Luck-Beitrag je Team – W${week}`, fmt: v => U.sgn(v),
      desc: `Von ${rows[0].name} (${U.sgn(W(rows[0]).luck[wi])}) bis ${rows.at(-1).name} (${U.sgn(W(rows.at(-1)).luck[wi])}); die Beiträge einer Woche heben sich über alle Teams auf.`,
      rows: rows.map(t => ({label: t.kuerzel, v: W(t).luck[wi]}))}),
    {heads: ['Team', 'Wochenrang', 'AP %', 'Erg.', 'Luck-Beitrag'], rows: rows.map(t => [t.name, W(t).wochenrang[wi], U.pct(W(t).allplay_pct[wi]), W(t).ergebnis[wi], U.sgn(W(t).luck[wi])])}));
    return;
  }
  const anyT = S.teams.some(t => t.allplay_t > 0);
  U.ap(box, U.table({cap: `All-Play und Luck nach W${S.tw}`, cls: 'rk', rows: S.teams, sort: ['allplay_pct', -1], cols: [
    c.rang(), c.team(), {k: 'apwl', l: anyT ? 'AP W-L-T' : 'AP W-L', num: 1, v: t => t.allplay_pct, f: t => U.apwl(t.allplay_w, t.allplay_l, t.allplay_t, anyT)},
    c.pct('allplay_pct', 'AP %'), c.n('median_w', 'Median-S.', U.nn), c.wl(),
    {k: 'luck', l: 'Luck ± Zufall', num: 1, v: t => t.luck, f: luckCell}],
  note: h('span', null, 'Luck je Woche: ', h('a', {href: '#tabelle/allplay/w' + S.tw}, `W${S.tw}`), ' oben wählen.')}),
  U.legend(['ap-wl', 'allplay', 'median', 'luck', 'luck-kum']));
  const rows = U.sortRows(S.teams, t => t.luck, -1);
  const most = rows[0], least = rows.at(-1);
  const weeks = S.meta.weeks, xl = weeks.map(w => 'W' + w);
  U.ap(box, svg.fig('Luck je Team', svg.hbars({title: 'Luck je Team', fmt: v => U.sgn(v),
    desc: `Sortiert von ${most.name} (${U.sgn(most.luck)}) bis ${least.name} (${U.sgn(least.luck)}); positiv = mehr Siege als die Punkte erwarten ließen. ${inBand(S.teams)} von ${S.teams.length} Teams liegen innerhalb ihres Zufallsbands.`,
    rows: rows.map(t => ({label: t.kuerzel, v: t.luck}))}),
  {heads: ['Team', 'Luck', '± Zufall', 'W-L', 'AP %'], rows: rows.map(t => [t.name, U.sgn(t.luck), U.val(t.luck_band, v => '±' + U.num(v)), U.rec(t), U.pct(t.allplay_pct)])}));
  // Luck kumuliert je Woche: Linien aller Teams, das glücklichste hervorgehoben; Datentabelle = Team × Woche
  const hi = most.team_id;
  U.ap(box, svg.fig('Luck-Verlauf', svg.lines({title: 'Luck kumuliert je Woche', zero: true, H: 200, yfmt: v => U.sgn(v, 1),
    desc: `Laufende Summe der Luck-Beiträge; ${most.name} hervorgehoben (zuletzt ${U.sgn(most.luck)}). Graue Linien: übrige Teams.`,
    x: xl, series: S.teams.map(t => ({name: t.kuerzel, vals: W(t).luck_kum, hi: t.team_id === hi}))}),
  () => ({heads: ['Woche', ...S.teams.map(t => t.kuerzel)], rows: weeks.map((w, i) => ['W' + w, ...S.teams.map(t => U.sgn(W(t).luck_kum[i]))])}),
  h('p', {class: 'note'}, 'Beitrag je Woche = Ergebnis (Sieg 1, Unentschieden 0,5, Niederlage 0) − All-Play-Anteil der Woche. ', U.ib('luck-beitrag', ''))));
}
// Luck mit Zufallsband: innerhalb ±Band grau (nicht vom Zufall zu unterscheiden); das Band steht als zweite Zeile
const within = t => U.ok(t.luck) && U.ok(t.luck_band) && Math.abs(t.luck) <= t.luck_band;
const inBand = teams => teams.filter(within).length;
function luckCell(t) {
  if (!U.ok(t.luck)) return '–';
  return h('span', within(t) ? {class: 'note', title: 'innerhalb der Zufallsstreuung'} : null, U.sgn(t.luck),
    U.ok(t.luck_band) ? h('span', {class: 'sub'}, `±${U.num(t.luck_band)}`) : null,
    within(t) ? h('span', {class: 'vh'}, ' (innerhalb der Zufallsstreuung)') : null);
}

// ---------------------------------------------------------------- Punkte (Saison und Woche)
function punkte(box, r, svg, wi, week) {
  if (wi >= 0) {
    const W = t => t.wochen, wk = S.weeks.find(x => x.week === week) || {};
    const rows = U.sortRows(S.teams, t => W(t).pf[wi], -1);
    U.ap(box, U.table({cap: `Punkte – W${week}`, cls: 'rk', rows: S.teams, sort: ['pf', -1], cols: [
      c.wr(wi), c.team(), c.wk('pf', 'PF', wi), c.wk('pa', 'PA', wi), c.erg(wi), c.gegner(wi),
      c.wk('projektion', 'Proj.', wi), c.wk('projektions_delta', 'Proj.-Δ', wi, U.sgn)],
    note: 'Gegner: Kürzel und dessen Wochenrang.'}),
    U.legend(['wochenrang', 'pf', 'proj-delta']),
    svg.fig(`PF je Team – W${week}`, svg.dots({title: `PF je Team – W${week}`, fmt: v => U.num(v), tfmt: v => U.num(v, 0),
      desc: `Von ${rows[0].name} (${U.num(W(rows[0]).pf[wi])}) bis ${rows.at(-1).name} (${U.num(W(rows.at(-1)).pf[wi])}); Ligaschnitt ${U.num(wk.ligaschnitt)}, Median ${U.num(wk.median)}.`,
      rows: rows.map(t => ({label: t.kuerzel, v: W(t).pf[wi]})), ref: wk.ligaschnitt, refLabel: 'Ø'}),
    {heads: ['Team', 'PF', 'PA', 'Erg.'], rows: rows.map(t => [t.name, U.num(W(t).pf[wi]), U.num(W(t).pa[wi]), W(t).ergebnis[wi]])}));
    return;
  }
  const band = t => t.form_band == null ? U.na('ab 4 Spielen')
    : h('span', null, U.sgn(t.form_delta), h('span', {class: 'vh'}, ` (Band ±${U.num(t.form_band)})`), svg.mini(t.form_delta, t.form_band));
  U.ap(box, U.table({cap: `Punkte nach W${S.tw}`, cls: 'rk', rows: S.teams, sort: ['pf', -1], cols: [
    c.rang(), c.team(), c.n('pf', 'PF'), c.n('pf_per_game', 'PF/Spiel'), c.n('pa_per_game', 'PA/Spiel'), c.n('floor', 'Floor'),
    c.n('form', 'Form'), {k: 'fd', l: 'Form Δ', num: 1, v: t => t.form_band == null ? null : t.form_delta, f: band},
    c.n('projektions_delta', 'Proj.-Δ', U.sgn)]}),
  U.legend(['pfspiel', 'floor', 'form', 'form-delta', 'proj-delta']),
  ...svg.verlauf(S.teams[0].team_id, true));
}

// ---------------------------------------------------------------- Coaching (Saison und Woche)
function coaching(box, r, svg, wi, week) {
  const proj = S.meta.kader_quelle === 'projektion';
  const effChart = (title, rows, val, liga, tab) => svg.fig(title, svg.dots({title, fmt: v => U.pct(v), tfmt: v => U.num(v, 0) + ' %',
    desc: `Von ${rows[0].name} (${U.pct(val(rows[0]))}) bis ${rows.at(-1).name} (${U.pct(val(rows.at(-1)))}); Liga ${U.pct(liga)}.`,
    rows: rows.map(t => ({label: t.kuerzel, v: val(t)})), ref: liga, refLabel: 'Liga', max: 100}), tab);
  if (wi >= 0) {
    const W = t => t.wochen, eff = t => W(t).efficiency[wi];
    const rows = U.sortRows(S.teams, eff, -1);
    U.ap(box, U.table({cap: `Coaching – W${week}`, cls: 'rk', rows: S.teams, sort: ['efficiency', -1], cols: [
      c.wr(wi), c.team(), c.wk('efficiency', 'Eff. %', wi, U.pct), c.wk('verschenkt', 'Verschenkt', wi), c.wk('optimal', 'Optimal', wi),
      c.wk('pf', 'PF', wi), c.wk('bank', 'Bank', wi), c.erg(wi)]}),
    U.legend(['wochenrang', 'eff-woche', 'verschenkt', 'optimal', 'bank']),
    effChart(`Coaching-Effizienz W${week}`, rows, eff, S.weeks.find(x => x.week === week)?.effizienz_liga,
      {heads: ['Team', 'Eff. %', 'Verschenkt', 'Optimal'], rows: rows.map(t => [t.name, U.pct(eff(t)), U.num(W(t).verschenkt[wi]), U.num(W(t).optimal[wi])])}));
    return;
  }
  U.ap(box, U.table({cap: `Coaching nach W${S.tw}`, cls: 'rk', rows: S.teams, sort: ['efficiency', -1], cols: [
    c.rang(), c.team(), c.pct('efficiency', 'Eff. %'), c.n('verschenkt', 'Verschenkt'), c.n('verschenkt_avg', 'Ø/Woche'),
    c.n('verschenkt_max', 'Max'), c.n('optimal', 'Optimal'), c.n('bench', 'Bank'), c.n('kader_potenzial', 'Kader-Pot.'),
    proj ? c.n('kader_projektion', 'Kader-Proj.') : null].filter(Boolean)}),
  U.legend(['effizienz', 'verschenkt', 'optimal', 'bank', 'kader-pot', ...(proj ? ['kader-proj'] : [])]));
  const rows = U.sortRows(S.teams, t => t.efficiency, -1);
  U.ap(box, effChart('Coaching-Effizienz', rows, t => t.efficiency, S.meta.effizienz_liga,
    {heads: ['Team', 'Eff. %', 'Verschenkt', 'Optimal'], rows: rows.map(t => [t.name, U.pct(t.efficiency), U.num(t.verschenkt), U.num(t.optimal)])}));
}

function ausblick(box, r, svg) {
  let seeding = r.q.get('seeding') === 'espn' ? 'espn' : 'liga';
  const has = S.teams.some(t => t.sim);
  const espn = S.teams.some(t => U.ok(t.espn_sim?.playoff));
  const cols = () => [c.rang(), c.team(), c.wl(), c.po(seeding),
    {k: 'dv', l: 'Div %', num: 1, v: t => U.sp(t.sim?.[seeding]?.division), f: t => U.po(U.sp(t.sim?.[seeding]?.division))},
    {k: 'by', l: 'Bye %', num: 1, v: t => U.sp(t.sim?.[seeding]?.bye), f: t => U.po(U.sp(t.sim?.[seeding]?.bye))},
    {k: 'rs', l: 'Restsiege', num: 1, v: t => t.sim?.[seeding]?.restsiege, f: t => U.val(t.sim?.[seeding]?.restsiege, v => U.num(v, 1), 'Simulation folgt')},
    espn ? {k: 'es', l: 'ESPN PO %', num: 1, v: t => U.sp(t.espn_sim?.playoff), f: t => U.po(U.sp(t.espn_sim?.playoff))} : null,
    c.n('waiver_prio', 'Waiver', v => v, 1), c.n('moves', 'Moves', v => v)].filter(Boolean);
  const wrap = h('div');
  const chart = h('div');
  const draw = () => {
    wrap.replaceChildren(U.table({cap: `Ausblick – Playoff-Simulation (${seeding === 'espn' ? 'ESPN: Top 6 gesamt' : 'Liga: Top 3 je Division'})`,
      cls: 'rk', rows: S.teams, sort: ['po', -1], cols: cols()}));
    if (!has) return;
    const rows = U.sortRows(S.teams, t => t.sim?.[seeding]?.playoff, -1);
    const names = ['Seed 1', 'Seed 2', 'Seed 3', 'Seed 4', 'Seed 5', 'Seed 6', 'raus'];
    const parts = t => { const sd = (t.sim?.[seeding]?.seeds || []).map(U.sp); return [...sd, Math.max(0, 100 - sd.reduce((a, v) => a + (v || 0), 0))]; };
    chart.replaceChildren(svg.fig('Seed-Verteilung', svg.stack({title: 'Seed-Verteilung je Team', total: 100, names, fmt: v => U.pct(v),
      desc: `Anteil der Simulationsläufe je Seed 1–6 und „raus“; ${rows[0].name} führt mit ${U.po(U.sp(rows[0].sim[seeding].playoff))} Playoff-Chance.`,
      cls: j => j < 6 ? 's' + (j + 1) : 's0', rows: rows.map(t => ({label: t.kuerzel, parts: parts(t)}))}),
    {heads: ['Team', ...names], rows: rows.map(t => [t.name, ...parts(t).map(v => U.pct(v))])},
    svg.swatches(names, j => j < 6 ? 's' + (j + 1) : 's0')));
  };
  U.ap(box, h('div', {class: 'row'}, h('span', {class: 'note'}, 'Seeding'),
    U.seg('Seeding der Simulation', [['liga', 'Liga: Top 3 je Division'], ['espn', 'ESPN: Top 6 gesamt']], seeding, v => {
      seeding = v;
      U.setQ('tabelle/ausblick', {seeding: v === 'espn' ? 'espn' : null});
      draw();
    }), U.ib('seeding', '')),
  has ? null : h('p', {class: 'warn'}, 'Die Playoff-Simulation liegt noch nicht vor.'),
  wrap, U.legend(['playoff', 'div-pct', 'bye', 'restsiege', 'simulation', 'waiver', 'moves']), chart);
  draw();
}
