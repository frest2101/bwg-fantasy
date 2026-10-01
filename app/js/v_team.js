// Teamseite #team/N: Kopf, Kacheln, PF je Woche, Wochenliste, Verläufe, Positionen, H2H; Kader und Franchise lazy.
// Stärken und Schwächen (Profil) aus waiver.json: Kurzzeile unter den Kacheln, Umschalter „Profil“ in der Karte Positionen.
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];
// Profil-Gruppen (Python: players.PROFILE_GROUPS) mit Anzeige und Position der Absicherung (FLEX hat keine)
const GRP = {QB: ['QB+OP', 'QB'], RB: ['RB', 'RB'], WR: ['WR', 'WR'], TE: ['TE', 'TE'], FLEX: ['FLEX', null], 'D/ST': ['D/ST', 'D/ST'], K: ['K', 'K']};
// Slots in der Reihenfolge der Aufstellung (Sortierung im Kader)
const ORD = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'OP', 'D/ST', 'K', 'Bank', 'IR'];

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const t = U.team(r.sub);
  if (!t) {
    U.ap(box, h('p', null, h('a', {href: '#tabelle'}, '← Tabelle')), h('h1', null, 'Team nicht gefunden'),
      h('p', {class: 'note'}, 'Diese Team-Nummer gibt es in der Liga nicht (1–10). Der Link ist vermutlich veraltet oder vertippt.'));
    return;
  }
  const svg = await ctx.mod('svg');
  const div = S.meta.divisions?.[t.division] ?? 'Division ' + t.division;
  const sim = t.sim?.liga;
  U.ap(box, h('h1', null, t.name),
    h('p', {class: 'note'}, `${t.kuerzel} · Rang ${t.rang} gesamt · ${t.rang_division}. in ${div} · ${U.rec(t)} · Streak ${t.streak ?? '–'}`),
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
  const kurz = h('p', {class: 'note', 'aria-live': 'polite'});
  U.ap(box, kurz);

  const W = S.meta.weeks, wk = t.wochen, avg = W.map(w => S.weeks.find(x => x.week === w)?.ligaschnitt ?? null);
  const best = wk.pf.length ? Math.max(...wk.pf) : null;
  const pfFig = svg.fig('PF je Woche', svg.bars({title: `PF je Woche – ${t.name}`,
    desc: `Säulen = PF mit Ergebnis (W/L/T), Strich = Optimal, gestrichelt = Ligaschnitt. Beste Woche ${U.num(best)}.`,
    x: W.map(w => 'W' + w), vals: wk.pf, cls: i => 'b' + (wk.ergebnis[i] || 'N'), letter: i => wk.ergebnis[i],
    tick: wk.optimal, avg, yfmt: v => U.num(v, 0)}),
  {heads: ['Woche', 'PF', 'Erg.', 'Optimal', 'Ligaschnitt'], rows: W.map((w, i) => ['W' + w, U.num(wk.pf[i]), wk.ergebnis[i], U.num(wk.optimal[i]), U.num(avg[i])])},
  h('p', {class: 'note'}, 'Säule = PF mit Ergebnis W/L/T, orange Strich = Optimal, gestrichelt = Ligaschnitt.'));
  // Kader direkt nach der Wochenliste; Verläufe und Franchise-Historie eingeklappt, auf dem Handy ist die Seite sonst
  // acht Bildschirme lang (ab 900 px offen)
  const wide = matchMedia('(min-width:900px)').matches;
  const sec = (title, ...kids) => h('details', {class: 'sec', open: wide}, h('summary', null, title), kids);
  const kader = h('div', {class: 'tg-k'});
  const fr = U.card(null);
  const pos = h('div');
  positions(pos, t, null, null);
  U.ap(box, h('div', {class: 'tg'}, h('div', {class: 'tg-f'}, pfFig), h('div', {class: 'tg-w'}, weekList(t)), kader,
    h('div', {class: 'tg-r'}, pos, h2h(t))));
  U.ap(box, sec('Verläufe', ...svg.verlauf(t.team_id, false)), sec('Franchise-Historie', fr),
    U.chips('Weiter zu', [['#moves?team=' + t.team_id, 'Moves dieses Teams', 'm'], ['#rekorde/h2h?team=' + t.team_id, 'H2H-Bilanz', 'h'],
      ['#spieler?team=' + t.team_id + '&status=kader', 'Spielerliste des Teams', 's'],
      ['#keeper/kader?team=' + t.team_id, 'Keeper und Kader', 'k'],
      ['#waiver?team=' + t.team_id, `Waiver aus Sicht von ${t.kuerzel}`, 'w']], null));
  // Kader mit dem Tagesstand (waiver.json) wie im Spieler-Tab: aktuelle Zu- und Abgänge und Verletzungen; dieselbe
  // Ladung liefert das Profil (Kurzzeile und Umschalter „Profil“)
  ctx.lazy('players.json', 'Spielerdaten', kader).then(async P => {
    const W = S.man.files?.['waiver.json'] ? await ctx.load('waiver.json').catch(() => null) : null;
    // Herkunft je Kaderspieler (keeper.json) ist Zugabe: ohne die Datei fehlt nur die Spalte
    const K = S.man.files?.['keeper.json'] ? await ctx.load('keeper.json').catch(() => null) : null;
    const kp = K ? await ctx.mod('v_keeper').catch(() => null) : null;
    const sp = await ctx.mod('v_spieler');
    if (!r.alive()) return;
    const all = sp.merge(P, W);
    roster(kader, t, P, all, W, sp.nflTxt, kp && K, kp);
    const name = new Map(all.map(p => [p.id, p.name]));
    const prof = W?.profil?.[String(t.team_id)];
    if (prof) { kurz.replaceChildren(...short(prof, W)); positions(pos, t, W, name); }
  }).catch(() => {});
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
// Kurzzeile unter den Kacheln: Schwächen mit Abstand und Rang, Stärken nur mit Namen
function short(prof, W) {
  const g = prof.gruppen;
  const weak = prof.schwach.map((k, i) => [i ? ' · ' : '', h('b', {class: 'dn'}, GRP[k][0]), ` ${U.sgn(g[k].abstand)} (${g[k].rang}.)`]);
  return [basisTxt(W), ': Schwach ', weak.length ? weak : '–', ' · Stark ', prof.stark.length ? prof.stark.map(k => GRP[k][0]).join(' · ') : '–',
    ' ', U.ib('profil', '')];
}
const basisTxt = W => W.bedarf_basis === 'playoffs' ? 'Stärken und Schwächen (Playoffs W15–17)' : 'Stärken und Schwächen (ROS)';

// Karte Positionen: Profil (Tagesstand, sobald waiver.json da ist) sowie PF nach Position und nach Slot (Ist W1–N)
function positions(box, t, W, name) {
  const P = t.positionen, prof = W?.profil?.[String(t.team_id)];
  if (!P && !prof) { box.replaceChildren(h('p', {class: 'note'}, 'Positionen folgen.')); return; }
  const out = h('div');
  const draw = key => {
    if (key === 'profil') { out.replaceChildren(...profile(t, W, prof, name)); return; }
    const o = P?.[key] || {};
    out.replaceChildren(U.table({cap: key === 'nach_slot' ? 'PF nach Slot' : 'PF nach Position', cls: 'nr', rows: Object.keys(o), sort: ['pts', -1], rh: 0, cols: [
      {k: 'p', l: key === 'nach_slot' ? 'Slot' : 'Position', f: k => k},
      {k: 'pts', l: 'Pkt', num: 1, v: k => o[k].pts, f: k => U.num(o[k].pts)},
      {k: 'a', l: 'Anteil', num: 1, v: k => share(o, k), f: k => U.pct(share(o, k))},
      {k: 'r', l: 'Ligarang', num: 1, v: k => o[k].rang, d: 1, f: k => U.val(o[k].rang, v => v + '.')}]}));
  };
  const opts = [...(prof ? [['profil', 'Profil']] : []), ...(P ? [['nach_position', 'PF Position'], ['nach_slot', 'PF Slot']] : [])];
  draw(opts[0][0]);
  box.replaceChildren(h('div', {class: 'row'}, U.seg('Aufteilung', opts, opts[0][0], draw), U.ib(prof ? 'profil' : 'positionen', '')), out);
}

// Profil: Gruppen mit ROS/Sp. der Starter, Abstand zum Ligaschnitt und Rang, Ist-Rang, Absicherung; darunter Byes und
// freie Spieler mit Zugewinn für dieses Team. Alle Zahlen aus Python (waiver.json profil, spieler[].zug)
function profile(t, W, prof, name) {
  const g = prof.gruppen, abs = prof.absicherung || {};
  const cls = k => g[k].wertung === 'schwach' ? 'dn' : g[k].wertung === 'stark' ? 'up' : null;
  const po = W.bedarf_basis === 'playoffs';
  const table = U.table({cap: po ? 'Profil nach Slot-Gruppen (Playoffs W15–17)' : 'Profil nach Slot-Gruppen (ROS)', cls: 'nr', rows: Object.keys(g), sortable: false, rh: 0, cols: [
    {k: 'g', l: 'Gruppe', f: k => h('span', {class: cls(k), title: g[k].ids.map(name.get, name).join(', ')}, GRP[k][0])},
    {k: 'w', l: po ? 'PO/Sp.' : 'ROS/Sp.', num: 1, f: k => U.num(g[k].wert)},
    {k: 'a', l: 'zum Schnitt', num: 1, f: k => [h('span', {class: cls(k)}, U.sgn(g[k].abstand)), h('small', null, ` ${g[k].rang}.`)]},
    {k: 'i', l: 'Ist-Rang', num: 1, f: k => U.val(g[k].ist_rang, v => v + '.', 'noch keine Woche')},
    {k: 's', l: 'Ausfall Bester', num: 1, f: k => {
      const a = GRP[k][1] && abs[GRP[k][1]];
      if (a?.frei_gleichwertig) return h('small', null, 'freier Ersatz gleichwertig');
      return a && U.ok(a.wert) ? [U.sgn(a.wert), h('small', null, ` ${a.rang}.`)] : U.na(GRP[k][1] ? 'kein Spieler der Position' : 'FLEX: aus RB/WR/TE');
    }}]});
  const gains = W.spieler.filter(x => x.zug?.ros?.[String(t.team_id)])
    .map(x => ({id: x.id, v: x.zug.ros[String(t.team_id)], st: x.status})).sort((a, b) => b.v.b - a.v.b).slice(0, 3);
  const zug = gains.length ? gains.map((x, i) => [i ? ', ' : '', h('a', {href: '#spieler/' + x.id}, name.get(x.id) ?? `Spieler ${x.id}`),
    ` ${U.sgn(x.v.b)}` + (x.v.n !== x.v.b ? ` (netto ${U.sgn(x.v.n)})` : '') + (x.st === 'WAIVERS' ? ' · Waivers' : '')])
    : 'keiner – Verstärkung nur per Trade';
  const byes = prof.byes.length ? prof.byes.map((b, i) => [i ? ' · ' : '', `W${b.woche} `, h('span', {class: 'dn'}, U.sgn(b.kosten)),
    b.ids.length > 1 ? ` (${b.ids.length} Starter)` : '']) : 'keine Verluste';
  const k = prof.kader;
  return [table,
    h('p', {class: 'note'}, `Freie Spieler, die hier starten würden (${po ? 'PO' : 'ROS'}/Sp.): `, zug, ' ', U.ib('zugewinn', '')),
    h('p', {class: 'note'}, 'Byes (Verlust der besten Aufstellung): ', byes, ' ', U.ib('bye-kosten', '')),
    h('p', {class: 'note'}, `Kader ${k.spieler} Spieler` + (k.ir ? ` (${k.ir} im IR-Slot)` : '') + (k.voll ? ', voll – ein Zugang braucht einen Drop' : '')
      + (k.limit.length ? `; am Positionslimit: ${k.limit.join(', ')}` : '') + `. Tagesstand ${U.stamp(W.stand)}.`),
    U.legend(['profil', 'absicherung', 'zugewinn', 'bye-kosten'])];
}

function h2h(t) {
  const rows = (S.sched.h2h || []).filter(e => e.spiele > 0 && (e.a === t.team_id || e.b === t.team_id)).map(e => {
    const me = e.a === t.team_id;
    return {opp: me ? e.b : e.a, n: e.spiele, w: me ? e.w_a : e.l_a, l: me ? e.l_a : e.w_a, t: e.t, d: me ? e.pf_diff : -e.pf_diff};
  });
  if (!rows.length) return h('p', {class: 'note'}, 'Noch keine direkten Duelle.');
  return h('div', {class: 'blk'}, U.table({cap: 'H2H 2026', cls: 'nr kurz', rows, sort: ['d', -1], rh: 0, cols: [
    {k: 'o', l: 'Gegner', v: x => U.kz(x.opp), d: 1, f: x => U.tl(x.opp)},
    {k: 'n', l: 'Spiele', num: 1, v: x => x.n, f: x => x.n},
    {k: 'b', l: 'Bilanz', v: x => x.w - x.l, f: x => `${x.w}-${x.l}` + (x.t ? `-${x.t}` : '')},
    {k: 'd', l: 'PF-Diff', num: 1, v: x => x.d, f: x => U.sgn(x.d)}]}), U.legend(['h2h']));
}

function roster(box, t, P, all, W, nflTxt, K, kp) {
  const last = (P.weeks || []).length - 1;
  const rows = all.filter(p => p.team === t.team_id)
    .sort((a, b) => POS.indexOf(a.pos) - POS.indexOf(b.pos) || (b.avg ?? -1) - (a.avg ?? -1));
  // Grund für „–“ bei ROS/Spiel: noch kein Auszug, Saisonende (ROS nach W17, Stufe 4) oder keine Projektion des Spielers
  const ros = P.ros_nach_woche == null ? 'ab Wochenabruf W' + (S.tw + 1)
    : P.ros_nach_woche >= (S.weeks.at(-1)?.week ?? 17) ? 'Saison beendet, keine Restwoche' : 'keine Projektion';
  // Herkunft (keeper.json, Kader heute): nur Zeilen dieses Teams, sonst wäre ein eben gewechselter Spieler falsch beschriftet
  const org = K ? kp.byPlayer(K) : null;
  const mine = p => { const o = org.get(p.id); return o && o.team === t.team_id ? o : null; };
  U.ap(box, U.table({cap: `Kader (${rows.length} Spieler)`, cls: 'nr', rows, sort: null, rh: 0, cols: [
    {k: 'n', l: 'Spieler', v: p => p.name, d: 1, f: p => h('a', {href: '#spieler/' + p.id, class: 'pl'}, h('span', null, p.name, U.inj(p.inj)), h('span', {class: 'sub'}, `${p.pos ?? '–'} · ${nflTxt(p)}`))},
    {k: 's', l: `Slot W${P.weeks?.[last] ?? ''}`, v: p => { const i = ORD.indexOf(U.slot(p.wk?.[last]?.[4])); return i < 0 ? null : i; }, d: 1, f: p => U.slot(p.wk?.[last]?.[4])},
    org ? {k: 'h', l: 'Herkunft', v: p => kp.herkunftOrd(mine(p)), d: 1,
      f: p => kp.herkunft(mine(p), K) ?? U.na('noch nicht zugeordnet')} : null,
    {k: 'a', l: 'Ø', num: 1, v: p => p.avg, f: p => U.val(p.avg, U.num, 'ohne Spiel')},
    {k: 'f', l: 'Form', num: 1, v: p => p.form, f: p => [U.val(p.form, U.num, 'ohne Spiel'), p.trend ? ' ' + p.trend : '']},
    {k: 'r', l: 'ROS/Sp.', num: 1, v: p => p.ros_g, f: p => U.val(p.ros_g, U.num, ros)}].filter(Boolean)}),
  org ? U.legend(['herkunft']) : null,
  h('p', {class: 'note'}, W?.stand ? `Kader und Verletzung: Tagesstand ${U.stamp(W.stand)}. ` : `Verletzung: Stand nach W${S.man.datenstand?.pool_woche ?? S.tw}. `,
    'Q fraglich · D zweifelhaft · O fällt aus · IR Injured Reserve · DTD Day-to-Day.'));
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
  // Name nur, wenn er sich über die Saisons geändert hat, und dann hinten
  new Set(ts.map(x => x.team_name)).size > 1
    ? {heads: ['Saison', 'Endplatz', 'W-L', 'PF+', 'Name'], rows: ts.map(x => [x.season, x.final_rank + '.', `${x.w}-${x.l}`, U.num(x.pf_plus, 1), x.team_name])}
    : {heads: ['Saison', 'Endplatz', 'W-L', 'PF+'], rows: ts.map(x => [x.season, x.final_rank + '.', `${x.w}-${x.l}`, U.num(x.pf_plus, 1)])}));
}
