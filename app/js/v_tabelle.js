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
  const path = k => '#tabelle' + (k ? '/' + k : '') + (week && WEEKLY.includes(k) ? '/w' + week : '');
  U.ap(box, h('h1', null, (sub ? 'Tabelle – ' + label : 'Tabelle') + (week ? ` · W${week}` : '')),
    week ? h('p', {class: 'note'}, `Einzelwoche W${week}: `,
      h('a', {href: '#spielplan/w' + week}, 'Paarungen und Top-Scorer'), U.ib('wochensicht', ''))
      : h('p', {class: 'note'}, `nach W${S.tw} · Regular Season W1–14`, U.ib('nach-wn', '')),
    U.chips('Ansichten der Tabelle', SUBS.map(([k, l]) => [path(k), l, k]), sub));
  if (WEEKLY.includes(sub)) U.centerChip(U.ap(box, U.weekChips('tabelle/' + sub, week)).lastChild);
  const svg = ['allplay', 'punkte', 'coaching', 'ausblick'].includes(sub) ? await ctx.mod('svg') : null;
  ({gesamt, division, allplay, punkte, coaching, ausblick})[sub || 'gesamt'](box, r, svg, wi, week);
}

// Spalten, die mehrere Ansichten nutzen
const c = {
  // „#“ nur, wo nach dem Tabellenplatz sortiert ist; sonst „Pl.“, damit die Folge 2, 1, 3 … nicht wie ein Sortierfehler wirkt
  rang: (l = '#') => ({k: 'rang', l: l === '#' ? '#' : h('abbr', {title: 'Tabellenplatz'}, l), v: t => t.rang, d: 1, f: t => t.rang}),
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
  const pr = top.length ? h('div', {class: 'blk'}, U.table({cap: h('a', {href: '#ranking'}, 'Power Ranking – Top 5'), cls: 'rk', rows: top, sortable: false, cols: [
    {k: 'r', l: '#', f: t => t.pr.rang}, c.team(), {k: 'mu', l: 'μ', num: 1, f: t => U.num(t.pr.mu, 1)},
    {k: 'tr', l: 'Trend', num: 1, f: t => U.trend(t.pr.trend, 'noch kein Vorwochenvergleich')}]})) : null;
  U.ap(box, h('div', {class: 'two g'},
    h('div', null, tbl, U.legend(['rang', 'wlt', 'pf', 'playoff', 'allplay', 'diff', 'effizienz', 'streak'])),
    h('div', null, strip, pr)));
}

function division(box) {
  for (const [d, name] of Object.entries(S.meta.divisions || {})) {
    const rows = S.teams.filter(t => String(t.division) === d);
    U.ap(box, h('div', {class: 'blk'}, U.table({cap: `${name} nach W${S.tw}`, cls: 'rk', rows, sort: ['rd', 1], cols: [
      {k: 'rd', l: '#', v: t => t.rang_division, d: 1, f: t => t.rang_division}, c.team(), c.wl(), c.n('pf', 'PF'),
      c.po('liga'), {k: 'dv', l: 'Div %', num: 1, v: t => U.sp(t.sim?.liga?.division), f: t => U.pbar(U.sp(t.sim?.liga?.division))},
      c.pct('allplay_pct', 'AP %'), c.n('pa', 'PA'), c.streak(), {k: 'rg', l: 'Gesamt', num: 1, v: t => t.rang, d: 1, f: t => t.rang + '.'}]})));
  }
  U.ap(box, U.legend(['rang-div', 'wlt', 'pf', 'playoff', 'div-pct', 'allplay', 'streak']));
}

// ---------------------------------------------------------------- All-Play und Matchup-Glück (Saison und Woche)
// Matchup-Glück je Woche: zählt nur, wenn das Ergebnis der Punkteseite widerspricht (Sieg unter dem Wochenmedian = +,
// Niederlage über dem Median = −), Gewicht = (eigener + Gegner-Abstand zum Median) / 2σ, gekappt bei 1. Ein Sieg als Wochen-4. ist kein Glück.
const mgCell = (v, abst, gabst, erg) => {
  if (!U.ok(v)) return U.na('kein Spiel');
  if (v === 0) return h('span', {class: 'na'}, '0,00', h('span', {class: 'vh'}, ' (verdient)'));
  const why = erg === 'W' ? `Sieg ${U.num(-abst, 1)} unter dem Median, Gegner ${U.num(-gabst, 1)} darunter` : `Niederlage ${U.num(abst, 1)} über dem Median, Gegner ${U.num(gabst, 1)} darüber`;
  // Begründung sichtbar (Touch hat keinen Hover): den eigenen Abstand zeigt die Nachbarspalte, hier der des Gegners
  return h('span', {class: v > 0 ? 'W' : 'L'}, U.sgn(v), h('span', {class: 'sub', 'aria-hidden': 'true'}, `Gegner ${U.sgn(gabst, 1)}`),
    h('span', {class: 'vh'}, ` (${why})`));
};
function allplay(box, r, svg, wi, week) {
  const W = t => t.wochen;
  if (wi >= 0) {
    const anyT = S.teams.some(t => W(t).allplay_t[wi] > 0);
    const rows = U.sortRows(S.teams, t => W(t).matchup_glueck[wi], -1);
    const mg = t => W(t).matchup_glueck[wi];
    U.ap(box, U.table({cap: `All-Play und Matchup-Glück – W${week}`, cls: 'rk', rows: S.teams, sort: ['ap', -1], cols: [
      c.wr(wi), c.team(),
      {k: 'ap', l: anyT ? 'AP W-L-T' : 'AP W-L', num: 1, v: t => W(t).allplay_pct[wi], f: t => U.apwl(W(t).allplay_w[wi], W(t).allplay_l[wi], W(t).allplay_t[wi], anyT)},
      c.wk('allplay_pct', 'AP %', wi, U.pct), c.erg(wi), c.gegner(wi),
      {k: 'md', l: 'zum Median', num: 1, v: t => W(t).median_abstand[wi], f: t => U.val(W(t).median_abstand[wi], v => U.sgn(v, 1), 'kein Spiel')},
      {k: 'mg', l: 'Matchup-Glück', num: 1, v: mg, f: t => mgCell(mg(t), W(t).median_abstand[wi], W(t).gegner_abstand[wi], W(t).ergebnis[wi])},
      c.wk('gegner_pkt', 'Spielplan Pkt', wi, U.sgn)],
    note: 'Gegner: Kürzel und dessen Wochenrang. Spielplan Pkt = Ligaschnitt − Punkte des Gegners (+ = leichter Gegner).'}),
    U.legend(['wochenrang', 'ap-wl', 'allplay', 'median', 'matchup-woche', 'spielplan-pkt']),
    svg.fig(`Matchup-Glück W${week}`, svg.hbars({title: `Matchup-Glück je Team – W${week}`, fmt: v => U.sgn(v),
      desc: `Von ${rows[0].name} (${U.sgn(mg(rows[0]))}) bis ${rows.at(-1).name} (${U.sgn(mg(rows.at(-1)))}); 0 = Ergebnis passt zu den Punkten.`,
      rows: rows.map(t => ({label: t.kuerzel, v: mg(t)}))}),
    {heads: ['Team', 'Wochenrang', 'zum Median', 'Erg.', 'Matchup-Glück'], rows: rows.map(t => [t.name, W(t).wochenrang[wi], U.sgn(W(t).median_abstand[wi], 1), W(t).ergebnis[wi], U.sgn(mg(t))])}));
    return;
  }
  const anyT = S.teams.some(t => t.allplay_t > 0);
  U.ap(box, U.table({cap: `All-Play und Matchup-Glück nach W${S.tw}`, cls: 'rk', rows: S.teams, sort: ['allplay_pct', -1], cols: [
    c.rang('Pl.'), c.team(), {k: 'apwl', l: anyT ? 'AP W-L-T' : 'AP W-L', num: 1, v: t => t.allplay_pct, f: t => U.apwl(t.allplay_w, t.allplay_l, t.allplay_t, anyT)},
    c.pct('allplay_pct', 'AP %'), c.wl(), {k: 'mb', l: 'Median-Bilanz', num: 1, v: t => t.median_w, f: t => `${t.median_w}-${t.median_l}`},
    {k: 'mg', l: 'Matchup-Glück', num: 1, v: t => t.matchup_glueck, f: t => U.ok(t.matchup_glueck) ? h('span', {class: t.matchup_glueck > 0 ? 'W' : t.matchup_glueck < 0 ? 'L' : 'na'}, U.sgn(t.matchup_glueck)) : '–'},
    c.n('spielplan_pkt', 'Spielplan Pkt', U.sgn)],
  note: h('span', null, 'Matchup-Glück je Woche mit Begründung: oben eine Woche wählen, z. B. ', h('a', {href: '#tabelle/allplay/w' + S.tw}, `W${S.tw}`), '.')}),
  U.legend(['rang', 'ap-wl', 'allplay', 'median-bilanz', 'matchup', 'spielplan-pkt']));
  const rows = U.sortRows(S.teams, t => t.matchup_glueck, -1);
  const most = rows[0], least = rows.at(-1);
  const weeks = S.meta.weeks, xl = weeks.map(w => 'W' + w);
  U.ap(box, svg.fig('Matchup-Glück je Team', svg.hbars({title: 'Matchup-Glück je Team', fmt: v => U.sgn(v),
    desc: `Sortiert von ${most.name} (${U.sgn(most.matchup_glueck)}) bis ${least.name} (${U.sgn(least.matchup_glueck)}); positiv = Siege, die die Punkte nicht hergaben, negativ = Niederlagen trotz Punkten über dem Median.`,
    rows: rows.map(t => ({label: t.kuerzel, v: t.matchup_glueck}))}),
  {heads: ['Team', 'Matchup-Glück', 'Median-Bilanz', 'W-L', 'Spielplan Pkt'], rows: rows.map(t => [t.name, U.sgn(t.matchup_glueck), `${t.median_w}-${t.median_l}`, U.rec(t), U.sgn(t.spielplan_pkt)])}));
  const hi = most.team_id;
  U.ap(box, svg.fig('Matchup-Glück im Saisonverlauf', svg.lines({title: 'Matchup-Glück kumuliert je Woche', zero: true, H: 200, yfmt: v => U.sgn(v, 1),
    desc: `Laufende Summe je Team; ${most.name} hervorgehoben (zuletzt ${U.sgn(most.matchup_glueck)}). Graue Linien: übrige Teams.`,
    x: xl, series: S.teams.map(t => ({name: t.kuerzel, vals: W(t).matchup_kum, hi: t.team_id === hi}))}),
  () => ({heads: ['Woche', ...S.teams.map(t => t.kuerzel)], rows: weeks.map((w, i) => ['W' + w, ...S.teams.map(t => U.sgn(W(t).matchup_kum[i]))])}),
  h('p', {class: 'note'}, 'Je Woche: Sieg unter dem Wochenmedian = Glück (+), Niederlage über dem Median = Pech (−), Gewicht = eigener und Gegner-Abstand zum Median in σ, höchstens 1. ', U.ib('matchup-woche', ''))));
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
    c.rang('Pl.'), c.team(), c.n('pf', 'PF'), c.n('pf_per_game', 'PF/Spiel'), c.n('pa_per_game', 'PA/Spiel'), c.n('floor', 'Floor'),
    c.n('form', 'Form'), {k: 'fd', l: 'Form Δ', num: 1, v: t => t.form_band == null ? null : t.form_delta, f: band},
    c.n('projektions_delta', 'Proj.-Δ', U.sgn)]}),
  U.legend(['rang', 'pfspiel', 'floor', 'form', 'form-delta', 'proj-delta']),
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
    c.rang('Pl.'), c.team(), c.pct('efficiency', 'Eff. %'), c.n('verschenkt', 'Verschenkt'), c.n('verschenkt_avg', 'Ø/Woche'),
    c.n('verschenkt_max', 'Max'), c.n('optimal', 'Optimal'), c.n('bench', 'Bank'), c.n('kader_potenzial', 'Kader-Pot.'),
    proj ? c.n('kader_projektion', 'Kader-Proj.') : null].filter(Boolean)}),
  U.legend(['rang', 'effizienz', 'verschenkt', 'optimal', 'bank', 'kader-pot', ...(proj ? ['kader-proj'] : [])]));
  const rows = U.sortRows(S.teams, t => t.efficiency, -1);
  U.ap(box, effChart('Coaching-Effizienz', rows, t => t.efficiency, S.meta.effizienz_liga,
    {heads: ['Team', 'Eff. %', 'Verschenkt', 'Optimal'], rows: rows.map(t => [t.name, U.pct(t.efficiency), U.num(t.verschenkt), U.num(t.optimal)])}));
}

function ausblick(box, r, svg) {
  let seeding = r.q.get('seeding') === 'espn' ? 'espn' : 'liga';
  const has = S.teams.some(t => t.sim);
  const espn = S.teams.some(t => U.ok(t.espn_sim?.playoff));
  // Liga-Regel: die Divisionssieger bekommen das Bye, Bye % = Div % – die Spalte nur im ESPN-Vergleich
  const cols = () => [c.rang('Pl.'), c.team(), c.wl(), c.po(seeding),
    {k: 'dv', l: seeding === 'espn' ? 'Div %' : 'Div/Bye %', num: 1, v: t => U.sp(t.sim?.[seeding]?.division), f: t => U.po(U.sp(t.sim?.[seeding]?.division))},
    seeding === 'espn' ? {k: 'by', l: 'Bye %', num: 1, v: t => U.sp(t.sim?.[seeding]?.bye), f: t => U.po(U.sp(t.sim?.[seeding]?.bye))} : null,
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
    U.seg('Seeding der Simulation', [['liga', 'Liga'], ['espn', 'ESPN']], seeding, v => {
      seeding = v;
      U.setQ('tabelle/ausblick', {seeding: v === 'espn' ? 'espn' : null});
      draw();
    }), U.ib('seeding', '')),
  has ? null : h('p', {class: 'warn'}, 'Die Playoff-Simulation liegt noch nicht vor.'),
  wrap, U.legend(['rang', 'playoff', 'div-pct', 'bye', 'restsiege', 'simulation', 'waiver', 'moves']), chart);
  draw();
}
