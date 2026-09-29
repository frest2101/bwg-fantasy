// Tab Tabelle: Gesamt, Division, All-Play, Punkte, Coaching, Ausblick (Seeding-Schalter)
const SUBS = [['', 'Gesamt'], ['division', 'Division'], ['allplay', 'All-Play'], ['punkte', 'Punkte'], ['coaching', 'Coaching'], ['ausblick', 'Ausblick']];
let U, S, h;

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const sub = SUBS.some(x => x[0] === r.sub) ? r.sub : '';
  const label = SUBS.find(x => x[0] === sub)[1];
  U.ap(box, h('h1', null, sub ? 'Tabelle – ' + label : 'Tabelle'),
    h('p', {class: 'note'}, `nach W${S.tw} · Regular Season W1–14`, U.ib('nach-wn', '')),
    U.chips('Ansichten der Tabelle', SUBS.map(([k, l]) => ['#tabelle' + (k ? '/' + k : ''), l, k]), sub));
  const svg = ['allplay', 'punkte', 'coaching', 'ausblick'].includes(sub) ? await ctx.mod('svg') : null;
  ({gesamt, division, allplay, punkte, coaching, ausblick})[sub || 'gesamt'](box, r, svg);
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
};
function streakVal(s) {
  const m = /^([WLT])(\d+)$/.exec(s || '');
  return m ? (m[1] === 'W' ? 1 : m[1] === 'L' ? -1 : 0) * +m[2] : null;
}

function gesamt(box) {
  const tbl = U.table({cap: `Tabelle Gesamt nach W${S.tw}`, cls: 'rk', rows: S.teams, sort: ['rang', 1], cols: [
    c.rang(), c.team(), c.wl(), c.n('pf', 'PF'), c.po('espn'), c.pct('allplay_pct', 'AP %'), c.n('pa', 'PA'),
    c.n('diff', 'Diff', U.sgn), c.pct('efficiency', 'Eff. %'), c.streak()]});
  const last = S.weeks.filter(w => w.status === 'final').at(-1);
  const strip = last ? h('section', {'aria-labelledby': 'wk-h'},
    h('h2', {id: 'wk-h'}, h('a', {href: '#spielplan/w' + last.week}, `W${last.week} kompakt`), h('span', {class: 'note'}, ' · ' + U.spanne(last.start))),
    h('ul', {class: 'strip', role: 'list'}, S.sched.games.filter(g => g.week === last.week).map(g => U.game(g, false)))) : null;
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
      c.po('espn'), {k: 'dv', l: 'Div %', num: 1, v: t => U.sp(t.sim?.espn?.division), f: t => U.pbar(U.sp(t.sim?.espn?.division))},
      c.pct('allplay_pct', 'AP %'), c.streak(), {k: 'rg', l: 'Gesamt', num: 1, v: t => t.rang, d: 1, f: t => t.rang + '.'}]})));
  }
  U.ap(box, U.legend(['rang-div', 'wlt', 'pf', 'playoff', 'div-pct', 'allplay', 'streak']));
}

function allplay(box, r, svg) {
  const anyT = S.teams.some(t => t.allplay_t > 0);
  const apwl = t => `${U.nn(t.allplay_w)}-${U.nn(t.allplay_l)}` + (anyT ? `-${U.nn(t.allplay_t)}` : '');
  U.ap(box, U.table({cap: `All-Play und Luck nach W${S.tw}`, cls: 'rk', rows: S.teams, sort: ['allplay_pct', -1], cols: [
    c.rang(), c.team(), {k: 'apwl', l: anyT ? 'AP W-L-T' : 'AP W-L', num: 1, v: t => t.allplay_pct, f: apwl},
    c.pct('allplay_pct', 'AP %'), c.n('median_w', 'Median-S.', U.nn), c.wl(), c.n('luck', 'Luck', U.sgn)]}),
  U.legend(['ap-wl', 'allplay', 'median', 'luck']));
  const rows = U.sortRows(S.teams, t => t.luck, -1);
  const most = rows[0], least = rows.at(-1);
  U.ap(box, svg.fig('Luck je Team', svg.hbars({title: 'Luck je Team', fmt: v => U.sgn(v),
    desc: `Sortiert von ${most.name} (${U.sgn(most.luck)}) bis ${least.name} (${U.sgn(least.luck)}); positiv = mehr Siege als die Punkte erwarten ließen.`,
    rows: rows.map(t => ({label: t.kuerzel, v: t.luck}))}),
  {heads: ['Team', 'Luck', 'W-L', 'AP %'], rows: rows.map(t => [t.name, U.sgn(t.luck), U.rec(t), U.pct(t.allplay_pct)])}));
}

function punkte(box, r, svg) {
  const band = t => t.form_band == null ? U.na('ab 4 Spielen')
    : h('span', null, U.sgn(t.form_delta), h('span', {class: 'vh'}, ` (Band ±${U.num(t.form_band)})`), svg.mini(t.form_delta, t.form_band));
  U.ap(box, U.table({cap: `Punkte nach W${S.tw}`, cls: 'rk kurz', rows: S.teams, sort: ['pf', -1], cols: [
    c.rang(), c.team(), c.n('pf', 'PF'), c.n('pf_per_game', 'PF/Spiel'), c.n('pa_per_game', 'PA/Spiel'), c.n('floor', 'Floor'),
    c.n('form', 'Form'), {k: 'fd', l: 'Form Δ', num: 1, v: t => t.form_band == null ? null : t.form_delta, f: band},
    c.n('projektions_delta', 'Proj.-Δ', U.sgn)]}),
  U.legend(['pfspiel', 'floor', 'form', 'form-delta', 'proj-delta']),
  ...svg.verlauf(S.teams[0].team_id, true));
}

function coaching(box, r, svg) {
  const proj = S.meta.kader_quelle === 'projektion';
  U.ap(box, U.table({cap: `Coaching nach W${S.tw}`, cls: 'rk kurz', rows: S.teams, sort: ['efficiency', -1], cols: [
    c.rang(), c.team(), c.pct('efficiency', 'Eff. %'), c.n('verschenkt', 'Verschenkt'), c.n('verschenkt_avg', 'Ø/Woche'),
    c.n('verschenkt_max', 'Max'), c.n('optimal', 'Optimal'), c.n('bench', 'Bank'), c.n('kader_potenzial', 'Kader-Pot.'),
    proj ? c.n('kader_projektion', 'Kader-Proj.') : null].filter(Boolean)}),
  U.legend(['effizienz', 'verschenkt', 'optimal', 'bank', 'kader-pot', ...(proj ? ['kader-proj'] : [])]));
  const rows = U.sortRows(S.teams, t => t.efficiency, -1);
  const sp = S.teams.reduce((a, t) => a + t.pf, 0), so = S.teams.reduce((a, t) => a + t.optimal, 0);
  const liga = so ? sp / so * 100 : null;
  U.ap(box, svg.fig('Coaching-Effizienz', svg.dots({title: 'Coaching-Effizienz je Team', fmt: v => U.pct(v), tfmt: v => U.num(v, 0) + ' %',
    desc: `Von ${rows[0].name} (${U.pct(rows[0].efficiency)}) bis ${rows.at(-1).name} (${U.pct(rows.at(-1).efficiency)}); Liga ${U.pct(liga)}.`,
    rows: rows.map(t => ({label: t.kuerzel, v: t.efficiency})), ref: liga, refLabel: 'Liga', max: 100}),
  {heads: ['Team', 'Eff. %', 'Verschenkt', 'Optimal'], rows: rows.map(t => [t.name, U.pct(t.efficiency), U.num(t.verschenkt), U.num(t.optimal)])}));
}

function ausblick(box, r, svg) {
  let seeding = r.q.get('seeding') === 'div' ? 'div' : 'espn';
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
    wrap.replaceChildren(U.table({cap: `Ausblick – Playoff-Simulation (Seeding ${seeding === 'div' ? 'Divisionssieger 1–2' : 'ESPN'})`,
      cls: 'rk kurz', rows: S.teams, sort: ['po', -1], cols: cols()}));
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
    U.seg('Seeding der Simulation', [['espn', 'ESPN (W, dann PF)'], ['div', 'Divisionssieger 1–2']], seeding, v => {
      seeding = v;
      U.setQ('tabelle/ausblick', {seeding: v === 'div' ? 'div' : null});
      draw();
    }), U.ib('seeding', '')),
  has ? null : h('p', {class: 'warn'}, 'Die Playoff-Simulation liegt noch nicht vor.'),
  wrap, U.legend(['playoff', 'div-pct', 'bye', 'restsiege', 'simulation', 'waiver', 'moves']), chart);
  draw();
}
