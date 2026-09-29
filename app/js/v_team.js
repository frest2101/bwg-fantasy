// Teamseite #team/N: Kopf, Kacheln, PF je Woche, Wochenliste, Verläufe, Positionen, H2H; Kader und Franchise lazy
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const t = U.team(r.sub);
  if (!t) { U.ap(box, h('h1', null, 'Team nicht gefunden'), h('p', null, h('a', {href: '#tabelle'}, 'Zur Tabelle'))); return; }
  const svg = await ctx.mod('svg');
  const div = S.meta.divisions?.[t.division] ?? 'Division ' + t.division;
  const sim = t.sim?.liga;
  U.ap(box, h('h1', null, t.name),
    h('p', {class: 'note'}, `${t.kuerzel} · ${div} · Rang ${t.rang} (Division ${t.rang_division}) · ${U.rec(t)} · Streak ${t.streak ?? '–'}`),
    t.pr ? h('p', null, h('a', {href: '#ranking'}, 'Power Ranking'), ` ${t.pr.rang}. `, U.ok(t.pr.trend) ? U.trend(t.pr.trend) : null,
      ` · μ ${U.num(t.pr.mu, 1)}`, t.pr.p_quelle === 'vorjahr' ? h('span', {class: 'badge'}, 'P aus Vorjahr') : null) : null,
    t.pr?.kernsatz ? h('blockquote', {class: 'card'}, t.pr.kernsatz) : null,
    h('div', {class: 'tiles'},
      U.tile('PF/Spiel', U.num(t.pf_per_game), `PF ${U.num(t.pf)} · PA ${U.num(t.pa)}`, 'pfspiel'),
      U.tile('All-Play %', U.pct(t.allplay_pct), `AP ${U.nn(t.allplay_w)}-${U.nn(t.allplay_l)}`, 'allplay'),
      U.tile('Matchup-Glück', U.sgn(t.matchup_glueck), `Median ${t.median_w}-${t.median_l} · Spielplan ${U.sgn(t.spielplan_pkt, 0)} Pkt`, 'matchup'),
      U.tile('Effizienz', U.pct(t.efficiency), `verschenkt ${U.num(t.verschenkt)}`, 'effizienz'),
      U.tile('Form Δ', t.form_band == null ? U.na('ab 4 Spielen') : [U.sgn(t.form_delta), svg.mini(t.form_delta, t.form_band)],
        t.form_band == null ? 'ab 4 Spielen' : `Band ±${U.num(t.form_band)}`, 'form-delta'),
      U.tile('Playoff-%', U.po(U.sp(sim?.playoff)), sim ? `Div ${U.po(U.sp(sim.division))} · Bye ${U.po(U.sp(sim.bye))}` : 'Simulation folgt', 'playoff')));

  const W = S.meta.weeks, wk = t.wochen, avg = W.map(w => S.weeks.find(x => x.week === w)?.ligaschnitt ?? null);
  const best = wk.pf.length ? Math.max(...wk.pf) : null;
  U.ap(box, h('div', {class: 'two'}, h('div', {class: 'side'}, svg.fig('PF je Woche', svg.bars({title: `PF je Woche – ${t.name}`,
    desc: `Säulen = PF mit Ergebnis (W/L/T), Strich = Optimal, gestrichelt = Ligaschnitt. Beste Woche ${U.num(best)}.`,
    x: W.map(w => 'W' + w), vals: wk.pf, cls: i => 'b' + (wk.ergebnis[i] || 'N'), letter: i => wk.ergebnis[i],
    tick: wk.optimal, avg, yfmt: v => U.num(v, 0)}),
  {heads: ['Woche', 'PF', 'Erg.', 'Optimal', 'Ligaschnitt'], rows: W.map((w, i) => ['W' + w, U.num(wk.pf[i]), wk.ergebnis[i], U.num(wk.optimal[i]), U.num(avg[i])])},
  h('p', {class: 'note'}, 'Säule = PF mit Ergebnis W/L/T, orange Strich = Optimal, gestrichelt = Ligaschnitt.'))),
  h('div', {class: 'm1'}, weekList(t))));
  // Kader direkt nach der Wochenliste; Verläufe und Franchise-Historie eingeklappt, auf dem Handy ist die Seite sonst
  // acht Bildschirme lang (ab 900 px offen)
  const wide = matchMedia('(min-width:900px)').matches;
  const sec = (title, ...kids) => h('details', {class: 'sec', open: wide}, h('summary', null, title), kids);
  const kader = U.card('Kader');
  const fr = U.card(null);
  U.ap(box, h('div', {class: 'two'}, kader, h('div', null, positions(t), h2h(t))));
  U.ap(box, sec('Verläufe', ...svg.verlauf(t.team_id, false)), sec('Franchise-Historie', fr),
    h('p', null, h('a', {href: '#moves?team=' + t.team_id}, 'Moves dieses Teams'), ' · ', h('a', {href: '#rekorde/h2h?team=' + t.team_id}, 'H2H'), ' · ',
      h('a', {href: '#spieler?team=' + t.team_id + '&status=kader'}, 'Spielerliste des Teams')));
  ctx.lazy('players.json', 'Spielerdaten', kader).then(P => r.alive() && roster(kader, t, P)).catch(() => {});
  ctx.lazy('history.json', 'Historie', fr).then(H => r.alive() && franchise(fr, t, H, svg)).catch(() => {});
}

function weekList(t) {
  const wk = t.wochen;
  const rows = S.sched.games.filter(g => g.home === t.team_id || g.away === t.team_id).map(g => {
    const home = g.home === t.team_id, i = S.meta.weeks.indexOf(g.week);
    return {week: g.week, opp: home ? g.away : g.home, home, i, st: S.weeks.find(w => w.week === g.week)?.status,
      p: U.ok(g.p_home) ? (home ? U.sp(g.p_home) : 100 - U.sp(g.p_home)) : null};
  }).sort((a, b) => a.week - b.week);
  const played = x => x.i >= 0;
  const anyT = wk.allplay_t.some(v => v > 0);
  return h('div', null, U.table({cap: 'Wochenliste', cls: 'nr', rows, sortable: false, rh: 0, cols: [
    {k: 'w', l: 'W', f: x => h('a', {href: played(x) ? '#tabelle/allplay/w' + x.week : '#spielplan/w' + x.week, class: 'tl2'}, 'W' + x.week)},
    {k: 'o', l: 'Gegner', f: x => [x.home ? '' : '@', h('a', {href: '#team/' + x.opp, class: 'tl2', 'aria-label': `${x.home ? 'gegen' : 'bei'} ${U.team(x.opp)?.name}`}, U.kz(x.opp))]},
    {k: 'pf', l: 'PF : PA', num: 1, f: x => played(x) ? `${U.num(wk.pf[x.i])} : ${U.num(wk.pa[x.i])}` : (x.st === 'laeuft' ? 'läuft' : 'offen')},
    {k: 'e', l: 'Erg.', f: x => played(x) ? U.res(wk.ergebnis[x.i]) : x.p != null && x.st !== 'laeuft' ? U.po(x.p) : ''},
    {k: 'wr', l: 'W-Rang', num: 1, f: x => played(x) ? wk.wochenrang[x.i] + '.' : ''},
    {k: 'ap', l: 'AP', num: 1, f: x => played(x) ? U.apwl(wk.allplay_w[x.i], wk.allplay_l[x.i], wk.allplay_t[x.i], anyT) : ''},
    {k: 'md', l: 'zum Median', num: 1, f: x => played(x) ? U.sgn(wk.median_abstand[x.i], 1) : ''},
    {k: 'mg', l: 'Matchup-Glück', num: 1, f: x => played(x) ? U.sgn(wk.matchup_glueck[x.i]) : ''},
    {k: 'ef', l: 'Eff. %', num: 1, f: x => played(x) ? U.pct(wk.efficiency[x.i]) : ''},
    {k: 'vs', l: 'Verschenkt', num: 1, f: x => played(x) ? U.num(wk.verschenkt[x.i]) : ''},
    {k: 'bk', l: 'Bank', num: 1, f: x => played(x) ? U.num(wk.bank[x.i]) : ''}],
  note: '@ = auswärts. Matchup-Glück: Sieg unter dem Wochenmedian +, Niederlage über dem Median −, sonst 0; Summe = Kachel. Bei offenen Spielen steht unter „Erg.“ die Siegchance.'}),
  U.legend(['wochenrang', 'ap-wl', 'median', 'matchup-woche', 'eff-woche', 'verschenkt', 'bank']));
}

// Anteile: Vertrag ohne Einheit – Summe ≈ 1 heißt Anteil 0–1, sonst Prozent
const share = (obj, k) => { const tot = Object.values(obj).reduce((a, x) => a + (x?.anteil || 0), 0); const v = obj[k]?.anteil; return U.ok(v) ? (tot <= 1.5 ? v * 100 : v) : null; };
function positions(t) {
  const P = t.positionen;
  if (!P) return h('p', {class: 'note'}, 'Positionen folgen.');
  const box = h('div');
  const draw = key => {
    const o = P[key] || {};
    box.replaceChildren(U.table({cap: key === 'nach_slot' ? 'PF nach Slot' : 'PF nach Position', cls: 'nr', rows: Object.keys(o), sort: ['pts', -1], rh: 0, cols: [
      {k: 'p', l: key === 'nach_slot' ? 'Slot' : 'Position', f: k => k},
      {k: 'pts', l: 'Pkt', num: 1, v: k => o[k].pts, f: k => U.num(o[k].pts)},
      {k: 'a', l: 'Anteil', num: 1, v: k => share(o, k), f: k => U.pct(share(o, k))},
      {k: 'r', l: 'Ligarang', num: 1, v: k => o[k].rang, d: 1, f: k => U.val(o[k].rang, v => v + '.')}]}));
  };
  draw('nach_position');
  return h('div', null, h('div', {class: 'row'}, U.seg('Aufteilung', [['nach_position', 'Position'], ['nach_slot', 'Slot']], 'nach_position', draw), U.ib('positionen', '')), box);
}

function h2h(t) {
  const rows = (S.sched.h2h || []).filter(e => e.spiele > 0 && (e.a === t.team_id || e.b === t.team_id)).map(e => {
    const me = e.a === t.team_id;
    return {opp: me ? e.b : e.a, n: e.spiele, w: me ? e.w_a : e.l_a, l: me ? e.l_a : e.w_a, t: e.t, d: me ? e.pf_diff : -e.pf_diff};
  });
  if (!rows.length) return h('p', {class: 'note'}, 'Noch keine direkten Duelle.');
  return h('div', null, U.table({cap: 'H2H 2026', cls: 'nr', rows, sort: ['d', -1], rh: 0, cols: [
    {k: 'o', l: 'Gegner', v: x => U.kz(x.opp), d: 1, f: x => U.tl(x.opp)},
    {k: 'n', l: 'Spiele', num: 1, v: x => x.n, f: x => x.n},
    {k: 'b', l: 'Bilanz', v: x => x.w - x.l, f: x => `${x.w}-${x.l}` + (x.t ? `-${x.t}` : '')},
    {k: 'd', l: 'PF-Diff', num: 1, v: x => x.d, f: x => U.sgn(x.d)}]}), U.legend(['h2h']));
}

function roster(box, t, P) {
  const last = (P.weeks || []).length - 1;
  const rows = P.players.filter(p => p.team === t.team_id)
    .sort((a, b) => POS.indexOf(a.pos) - POS.indexOf(b.pos) || (b.avg ?? -1) - (a.avg ?? -1));
  const ros = 'ab Wochenabruf W' + (S.tw + 1);
  U.ap(box, U.table({cap: `Kader (${rows.length} Spieler)`, cls: 'nr', rows, sort: null, rh: 0, cols: [
    {k: 'n', l: 'Spieler', v: p => p.name, d: 1, f: p => h('a', {href: '#spieler/' + p.id, class: 'pl'}, h('span', null, p.name), h('span', {class: 'sub'}, `${p.pos} · ${p.nfl}`))},
    {k: 's', l: `Slot W${P.weeks?.[last] ?? ''}`, v: p => U.slot(p.wk?.[last]?.[4]), d: 1, f: p => U.slot(p.wk?.[last]?.[4])},
    {k: 'a', l: 'Ø', num: 1, v: p => p.avg, f: p => U.val(p.avg, U.num, 'ohne Spiel')},
    {k: 'f', l: 'Form', num: 1, v: p => p.form, f: p => [U.val(p.form, U.num, 'ohne Spiel'), p.trend ? ' ' + p.trend : '']},
    {k: 'r', l: 'ROS/Sp.', num: 1, v: p => p.ros_g, f: p => U.val(p.ros_g, U.num, ros)}]}));
}

function franchise(box, t, H, svg) {
  const a = (H.alltime || []).find(x => x.slot === t.team_id);
  if (!a) { U.ap(box, h('p', {class: 'note'}, 'Keine Historie für diesen Franchise-Slot.')); return; }
  const ts = (H.team_seasons || []).filter(x => x.slot === t.team_id).sort((x, y) => x.season - y.season);
  U.ap(box, h('p', null, h('strong', null, 'Namen: '), a.namenskette),
    h('div', {class: 'tiles'},
      U.tile('Saisons', a.saisons, `${a.w}-${a.l} · W ${U.pct(a.w_pct)}`, 'wpct-alltime'),
      U.tile('Titel', a.titel, (a.titel_saisons || []).join(', ') || '–'),
      U.tile('Playoffs', a.playoffs, `Finals ${a.finals} · Div ${a.divisionssiege}`),
      U.tile('Ø PF+', U.num(a.pf_plus_avg, 1), `Ø Platz ${U.num(a.platz_avg, 1)}`, 'pfplus-avg')));
  if (ts.length > 1) U.ap(box, svg.fig('Endplatz-Verlauf', svg.lines({title: 'Endplatz je Saison (1 = Champion)',
    desc: `${ts.length} Saisons, bester Endplatz ${Math.min(...ts.map(x => x.final_rank))}.`,
    x: ts.map(x => String(x.season).slice(2)), series: [{name: t.kuerzel, vals: ts.map(x => x.final_rank), hi: true}],
    invert: true, max: 10, yfmt: v => v + '.', H: 180}),
  {heads: ['Saison', 'Name', 'W-L', 'PF+', 'Endplatz'], rows: ts.map(x => [x.season, x.team_name, `${x.w}-${x.l}`, U.num(x.pf_plus, 1), x.final_rank + '.'])}));
}
