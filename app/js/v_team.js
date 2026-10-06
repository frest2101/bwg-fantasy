// Teamseite #team/N (App-Konzept Abschnitt 9, Paket P6): Kopf mit Mein Team, darunter die fünf Bereiche des Menüs als aufklappbare
// Abschnitte in derselben Reihenfolge (ab 900 px offen, auf dem Handy nur Liga): Liga (Platz, Playoff %, Spiel der Woche, Wochenliste,
// Duelle, Franchise-Historie), Stärke (Power Ranking, Kacheln, PF je Woche, Positionen, Verläufe), Woche (Lücken, Ausfälle, Byes und
// Wetter der eigenen Spieler aus waiver.json und wetter.json), Markt (Stärken und Schwächen, Bedarf Rest der Saison, Moves des Teams),
// Keeper (erwarteter Pick, Kader mit Herkunft, Alter und Marktwert, Draft-Picks mit Ertrag). Nachgeladen werden players.json,
// waiver.json, keeper.json, wetter.json, transactions.json und history.json; fehlt eine Datei, fehlt nur ihr Teil.
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];
// Profil-Gruppen (Python: players.PROFILE_GROUPS) mit Anzeige und Position der Absicherung (FLEX hat keine)
const GRP = {QB: ['QB+OP', 'QB'], RB: ['RB', 'RB'], WR: ['WR', 'WR'], TE: ['TE', 'TE'], FLEX: ['FLEX', null], 'D/ST': ['D/ST', 'D/ST'], K: ['K', 'K']};
// Slots in der Reihenfolge der Aufstellung (Sortierung im Kader)
const ORD = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'OP', 'D/ST', 'K', 'Bank', 'IR'];
const GRUND = {BYE: 'Bye', OUT: 'fällt aus', INJURY_RESERVE: 'IR', SUSPENSION: 'gesperrt', QUESTIONABLE: 'fraglich', DOUBTFUL: 'zweifelhaft',
  DAY_TO_DAY: 'Day-to-Day'};

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const t = U.team(r.sub);
  if (!t) {
    U.ap(box, h('p', null, h('a', {href: '#liga'}, '← Tabelle')), h('h1', null, 'Team nicht gefunden'),
      h('p', {class: 'note'}, 'Diese Team-Nummer gibt es in der Liga nicht (1–10). Der Link ist vermutlich veraltet oder vertippt.'));
    return;
  }
  const svg = await ctx.mod('svg');
  const id = t.team_id, div = S.meta.divisions?.[t.division] ?? 'Division ' + t.division;
  const sim = t.sim?.liga;
  // Mein Team (Kopf): auf den übrigen Team-Seiten ein Knopf zum Wählen, auf der eigenen derselbe Knopf gesperrt („Mein Team ✓“)
  const mein = id === U.meinTeam();
  U.ap(box, h('h1', null, t.name),
    h('p', {class: 'note'}, `${t.kuerzel} · Rang ${t.rang} gesamt · ${t.rang_division}. in ${div} · ${U.rec(t)} · Streak ${t.streak ?? '–'}`),
    // auf der eigenen Seite ein gesperrter Knopf an derselben Stelle: Ein Doppelklick auf „Als Mein Team wählen“ trifft so nach
    // dem Neuzeichnen nicht den Link der nächsten Zeile
    h('p', null, mein ? h('button', {type: 'button', class: 'btn mtb', disabled: true}, 'Mein Team ✓')
      : h('button', {type: 'button', class: 'btn', onclick: () => { U.setMeinTeam(id); ctx.route().then(() => ctx.say(`Mein Team: ${t.name}.`)); }},
        'Als Mein Team wählen')));

  // Abschnitte: Name und Frage aus BEREICHE (wie Menü und Startseite); ab 900 px alle offen, auf dem Handy nur Liga
  const wide = matchMedia('(min-width:900px)').matches;
  const B = Object.fromEntries(ctx.bereiche().map(b => [b.k, b]));
  const sec = (k, ...kids) => h('details', {class: 'sec tsec', open: wide || k === 'liga'},
    h('summary', null, h('h2', null, B[k].l), h('span', {class: 'tsq'}, B[k].frage)), h('div', {class: 'tsb'}, kids));
  const wege = links => h('p', {class: 'note'}, 'Mehr dazu: ', links.filter(Boolean).map(([href, txt], i) => [i ? ' · ' : '', h('a', {href}, txt)]));
  const warte = () => h('p', {class: 'loading'}, 'Lade …');

  // ---------------------------------------------------------------- Liga
  const fr = h('div');
  U.ap(box, sec('liga',
    h('div', {class: 'tiles'},
      U.tile('Tabellenplatz', `${t.rang}.`, `${U.rec(t)} · ${t.rang_division}. in ${div}`, 'rang'),
      U.tile('Playoff %', U.po(U.sp(sim?.playoff)), sim ? `Division ${U.po(U.sp(sim.division))} · Bye ${U.po(U.sp(sim.bye))}` : 'Simulation folgt', 'playoff'),
      spielKachel(t),
      U.tile('Streak', t.streak ?? '–', `PF ${U.num(t.pf)} · PA ${U.num(t.pa)}`, 'streak')),
    weekList(t), h2h(t),
    h('details', {class: 'dt'}, h('summary', null, 'Franchise-Historie 2015–2025'), fr),
    wege([['#liga/duelle?team=' + id, 'Duelle'], ['#liga', 'Tabelle'], ['#liga/ergebnisse', 'Ergebnisse'], ['#liga/rekorde/alltime', 'Rekorde › All-Time']])));

  // ---------------------------------------------------------------- Stärke
  const W0 = S.meta.weeks, wk = t.wochen, avg = W0.map(w => S.weeks.find(x => x.week === w)?.ligaschnitt ?? null);
  const best = wk.pf.length ? Math.max(...wk.pf) : null;
  const pfFig = svg.fig('PF je Woche', svg.bars({title: `PF je Woche – ${t.name}`,
    desc: `Säulen = PF mit Ergebnis (W/L/T), Strich = beste Aufstellung, gestrichelt = Ligaschnitt. Beste Woche ${U.num(best)}.`,
    x: W0.map(w => 'W' + w), vals: wk.pf, cls: i => 'b' + (wk.ergebnis[i] || 'N'), letter: i => wk.ergebnis[i],
    tick: wk.optimal, avg, yfmt: v => U.num(v, 0)}),
  {heads: ['Woche', 'PF', 'Erg.', 'Beste Aufstellung', 'Ligaschnitt'], rows: W0.map((w, i) => ['W' + w, U.num(wk.pf[i]), wk.ergebnis[i], U.num(wk.optimal[i]), U.num(avg[i])])},
  h('p', {class: 'note'}, 'Säule = PF mit Ergebnis W/L/T, orange Strich = beste Aufstellung, gestrichelt = Ligaschnitt.'));
  const pos = h('div');
  positions(pos, t);
  U.ap(box, sec('staerke',
    t.pr ? h('p', null, h('a', {href: '#staerke'}, 'Power Ranking'), ` ${t.pr.rang}. `, U.ok(t.pr.trend) ? U.trend(t.pr.trend) : null,
      ` · Stärke ${U.num(t.pr.mu, 1)}`, t.pr.p_quelle === 'vorjahr' ? h('span', {class: 'badge'}, 'Projektion Kader aus dem Vorjahr') : null, ' ', U.ib('mu', '')) : null,
    t.pr?.kernsatz ? h('blockquote', {class: 'card'}, t.pr.kernsatz) : null,
    h('div', {class: 'tiles'},
      U.tile('PF/Spiel', U.num(t.pf_per_game), `PF ${U.num(t.pf)} · PA ${U.num(t.pa)}`, 'pfspiel'),
      U.tile('All-Play %', U.pct(t.allplay_pct), `All-Play ${U.apwl(t.allplay_w, t.allplay_l, t.allplay_t)}`, 'allplay'),
      U.tile('Matchup-Glück', U.sgn(t.matchup_glueck), `Median-Bilanz ${t.median_w}-${t.median_l} · Spielplan ${U.sgn(t.spielplan_pkt, 0)} Pkt`, 'matchup'),
      U.tile('Eff. %', U.pct(t.efficiency), `verschenkt ${U.num(t.verschenkt)}`, 'effizienz'),
      U.tile('Form zu Saison', t.form_band == null ? U.na('ab 4 Spielen') : [U.sgn(t.form_delta), svg.mini(t.form_delta, t.form_band)],
        t.form_band == null ? 'ab 4 Spielen' : `Band ±${U.num(t.form_band)}`, 'form-delta')),
    h('div', {class: 'tg2'}, pfFig, pos),
    ...svg.verlauf(id, false),
    wege([['#staerke', 'Power Ranking'], ['#staerke/allplay', 'All-Play & Glück'], ['#staerke/punkte', 'Punkte & Form'], ['#staerke/coaching', 'Coaching']])));

  // ---------------------------------------------------------------- Woche, Markt, Keeper (Daten des Tageslaufs, nachgeladen)
  const woche = h('div', null, warte()), markt = h('div', null, warte()), keeper = h('div');
  const laeuft = U.saisonLaeuft();
  U.ap(box,
    sec('woche', woche, wege([laeuft ? ['#spieltag/' + id, 'Spieltag live (Aufstellung)'] : null, ['#woche/paarungen', 'Paarungen'],
      ['#woche/wetter', 'Wetter']])),
    sec('markt', markt, wege([['#markt?team=' + id, `Markt aus Sicht von ${t.kuerzel}`], ['#markt/bedarf', 'Bedarf je Team'],
      ['#markt/moves?team=' + id, 'Moves dieses Teams']])),
    sec('keeper', keeper, wege([['#keeper/herkunft?team=' + id, 'Herkunft der Spieler'], ['#keeper/draft?team=' + id, `Draft ${S.man.season}`],
      ['#keeper/draft-folgejahr', `Draft ${S.man.season + 1}`], ['#spieler?team=' + id + '&status=kader', 'Spielerliste des Teams']])));
  const opt = n => S.man.files?.[n] ? ctx.load(n).catch(() => null) : null;
  ctx.lazy('players.json', 'Spielerdaten', keeper).then(async P => {
    const [W, K, WX] = await Promise.all([opt('waiver.json'), opt('keeper.json'), opt('wetter.json')]);
    const [kp, sp, wx] = await Promise.all([K ? ctx.mod('v_keeper').catch(() => null) : null, ctx.mod('v_spieler'), WX ? ctx.mod('v_wetter').catch(() => null) : null]);
    if (!r.alive()) return;
    // Kader mit dem Stand des Tageslaufs (waiver.json) wie in der Spielerliste: aktuelle Zu- und Abgänge und Verletzungen
    const all = sp.merge(P, W);
    const name = new Map(all.map(p => [p.id, p.name]));
    const kader = all.filter(p => p.team === id);
    wocheTeil(woche, t, W, name, new Map(all.map(p => [p.id, p.nfl])), kader, WX && wx ? {WX, wx} : null);
    marktTeil(markt, t, W, name, ctx, r, U.zwischenstand(W, P));
    keeperTeil(keeper, t, P, kader, W, sp.nflTxt, kp && K, kp);
  }).catch(() => {
    for (const b of [woche, markt]) b.replaceChildren(h('p', {class: 'note'}, 'Spielerdaten konnten nicht geladen werden.'));
  });
  ctx.lazy('history.json', 'Historie', fr).then(H => r.alive() && franchise(fr, t, H, svg)).catch(() => {});
}

// Kachel „Spiel Wn“: Spiel der laufenden Woche (Kalender) mit Ergebnis oder Siegchance aus schedule.json
function spielKachel(t) {
  const wk = U.aktuelleWoche();
  const g = S.sched.games.find(x => x.week === wk && (x.home === t.team_id || x.away === t.team_id));
  if (!g) return U.tile(`Spiel W${wk}`, '–', 'kein Spiel');
  if (g.home == null || g.away == null) return U.tile(`Spiel W${wk}`, 'Freilos', 'kein Gegner');
  const heim = g.home === t.team_id, opp = U.team(heim ? g.away : g.home);
  const gegen = (heim ? 'gegen ' : 'bei ') + (opp?.kuerzel ?? '–');
  if (g.winner != null) {
    const erg = g.winner === 'T' ? 'T' : g.winner === t.team_id ? 'W' : 'L';
    return U.tile(`Spiel W${wk}`, [U.res(erg), ' ', U.num(heim ? g.home_pf : g.away_pf)], `${gegen} · ${U.num(heim ? g.away_pf : g.home_pf)}`);
  }
  const ph = U.ok(g.p_home) ? U.sp(g.p_home) : null;
  return U.tile(`Spiel W${wk}`, ph == null ? 'offen' : U.po(heim ? ph : 100 - ph), ph == null ? gegen : `Siegchance ${gegen}`, 'siegchance');
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
  // Einfach / Ausführlich (Paket P5): Ergebnis, Wochenrang und Matchup-Glück einfach, der Rest ausführlich
  return h('div', {class: 'blk'}, U.table({cap: 'Wochenliste', cls: 'nr', rows, sortable: false, rh: 0, cols: [
    {k: 'w', l: 'W', f: x => h('a', {href: played(x) ? '#staerke/allplay/w' + x.week : '#liga/ergebnisse/w' + x.week, class: 'tl2'}, 'W' + x.week)},
    {k: 'o', l: 'Gegner', f: x => x.opp == null ? 'Freilos' : [x.home ? '' : '@', h('a', {href: '#team/' + x.opp, class: 'tl2', 'aria-label': `${x.home ? 'gegen' : 'bei'} ${U.team(x.opp)?.name}`}, U.kz(x.opp))]},
    {k: 'pf', l: 'PF : PA', num: 1, f: x => played(x) ? `${U.num(wk.pf[x.i])} : ${U.num(wk.pa[x.i])}` : (x.st === 'laeuft' ? 'läuft' : 'offen')},
    {k: 'e', l: 'Erg.', f: x => played(x) ? U.res(wk.ergebnis[x.i]) : x.p != null && x.st !== 'laeuft' ? U.po(x.p) : ''},
    {k: 'wr', l: 'Wochenrang', num: 1, f: x => played(x) ? wk.wochenrang[x.i] + '.' : ''},
    {k: 'mg', l: 'Matchup-Glück', num: 1, f: x => played(x) ? U.sgn(wk.matchup_glueck[x.i]) : ''},
    {k: 'ap', l: 'All-Play', num: 1, x: 1, f: x => played(x) ? U.apwl(wk.allplay_w[x.i], wk.allplay_l[x.i], wk.allplay_t[x.i], anyT) : ''},
    {k: 'md', l: 'zum Median', num: 1, x: 1, f: x => played(x) ? U.sgn(wk.median_abstand[x.i], 1) : ''},
    {k: 'ef', l: 'Eff. %', num: 1, x: 1, f: x => played(x) ? U.pct(wk.efficiency[x.i]) : ''},
    {k: 'vs', l: 'Verschenkt', num: 1, x: 1, f: x => played(x) ? U.num(wk.verschenkt[x.i]) : ''},
    {k: 'bk', l: 'Bankpunkte', num: 1, x: 1, f: x => played(x) ? U.num(wk.bank[x.i]) : ''}],
  note: '@ = auswärts. Matchup-Glück: Sieg unter dem Wochenmedian +, Niederlage über dem Median −, sonst 0; Summe = Kachel unter Stärke. Bei offenen Spielen steht unter „Erg.“ die Siegchance.'}),
  U.legend(['wochenrang', 'matchup-woche', 'ap-wl', 'median', 'eff-woche', 'verschenkt', 'bank']));
}

// Anteile: Vertrag ohne Einheit – Summe ≈ 1 heißt Anteil 0–1, sonst Prozent
const share = (obj, k) => { const tot = Object.values(obj).reduce((a, x) => a + (x?.anteil || 0), 0); const v = obj[k]?.anteil; return U.ok(v) ? (tot <= 1.5 ? v * 100 : v) : null; };
// Kurzzeile über dem Profil: Schwächen mit Abstand und Rang, Stärken nur mit Namen
function short(prof, W) {
  const g = prof.gruppen;
  const weak = prof.schwach.map((k, i) => [i ? ' · ' : '', h('b', {class: 'dn'}, GRP[k][0]), ` ${U.sgn(g[k].abstand)} (${g[k].rang}.)`]);
  return [basisTxt(W), ': Schwach ', weak.length ? weak : '–', ' · Stark ', prof.stark.length ? prof.stark.map(k => GRP[k][0]).join(' · ') : '–',
    ' ', U.ib('profil', '')];
}
const basisTxt = W => W.bedarf_basis === 'playoffs' ? 'Stärken und Schwächen (Playoffs W15–17)' : 'Stärken und Schwächen (Rest der Saison)';

// Karte Positionen (Stärke): PF nach Position und nach Slot (Ist W1–N); das Profil steht seit P6 unter Markt
function positions(box, t) {
  const P = t.positionen;
  if (!P) { box.replaceChildren(h('p', {class: 'note'}, 'Positionen folgen.')); return; }
  const out = h('div');
  const draw = key => {
    const o = P[key] || {};
    out.replaceChildren(U.table({cap: key === 'nach_slot' ? 'PF nach Slot' : 'PF nach Position', cls: 'nr', rows: Object.keys(o), sort: ['pts', -1], rh: 0, cols: [
      {k: 'p', l: key === 'nach_slot' ? 'Slot' : 'Position', f: k => k},
      {k: 'pts', l: 'Pkt', num: 1, v: k => o[k].pts, f: k => U.num(o[k].pts)},
      {k: 'a', l: 'Anteil', num: 1, v: k => share(o, k), f: k => U.pct(share(o, k))},
      {k: 'r', l: 'Ligarang', num: 1, v: k => o[k].rang, d: 1, f: k => U.val(o[k].rang, v => v + '.')}]}));
  };
  draw('nach_position');
  box.replaceChildren(h('div', {class: 'row'}, U.seg('Aufteilung', [['nach_position', 'PF Position'], ['nach_slot', 'PF Slot']], 'nach_position', draw),
    U.ib('positionen', '')), out);
}

// ---------------------------------------------------------------- Woche: Bedarf der nächsten Woche und Wetter der eigenen Spieler
function wocheTeil(box, t, W, name, nflOf, kader, wetter) {
  const B = W?.bedarf_woche?.[String(t.team_id)];
  // Kandidaten wie unter Markt › Bedarf je Team: wessen Spiel der Woche schon angepfiffen ist, bringt in dieser Woche nichts mehr
  const offen = ks => (ks || []).filter(k => { const ko = W?.anstoss?.[nflOf.get(k)]; return !(U.ok(ko) && ko <= Date.now()); });
  const pl = id => h('a', {href: '#spieler/' + id}, name.get(id) ?? `Spieler ${id}`);
  const liste = (items, f) => h('ul', {class: 'tli'}, items.map(x => h('li', null, f(x))));
  const teile = [];
  if (!W) teile.push(h('p', {class: 'note'}, 'Lücken und Ausfälle der nächsten Woche und Byes der Wochen danach erscheinen mit dem ersten Tageslauf.'));
  else if (!B) teile.push(h('p', {class: 'note'}, 'Kein Bedarf für die nächste Woche (vor der ersten Projektion oder nach der Saison).'));
  else {
    teile.push(h('h3', null, `Nächste Woche (W${W.woche})`, ' ', U.ib('bedarf-woche', '')));
    const lu = B.luecken || [], au = B.ausfaelle || [], by = B.byes || [];
    teile.push(lu.length ? [h('p', null, h('strong', null, 'Lücken')), liste(lu, x => [`${x.slot}: `, x.id ? pl(x.id) : 'leer',
      x.grund ? ` (${GRUND[x.grund] || x.grund})` : U.ok(x.proj) ? ` (Projektion ${U.num(x.proj)})` : '',
      offen(x.kandidaten).length ? [' → ', offen(x.kandidaten).map((k, i) => [i ? ', ' : '', pl(k)])] : ' → kein besserer freier Spieler'])]
      : h('p', null, h('strong', null, 'Lücken: '), 'keine'));
    teile.push(au.length ? [h('p', null, h('strong', null, 'Ausfälle und fraglich')), liste(au, x => [`${x.slot}: `, pl(x.id), ` (${GRUND[x.grund] || x.grund})`])]
      : h('p', null, h('strong', null, 'Ausfälle und fraglich: '), 'keine'));
    const wochen = [...new Set(by.map(x => x.woche))];
    teile.push(wochen.length ? h('p', null, h('strong', null, 'Byes: '), wochen.map((w, i) => [i ? ' · ' : '', `W${w} `,
      by.filter(x => x.woche === w).map((x, j) => [j ? ', ' : '', pl(x.id)])])) : h('p', null, h('strong', null, 'Byes: '), 'keine in den Wochen danach'));
  }
  // Wetter: markierte, noch nicht angepfiffene Spiele der Kaderspieler in der laufenden Woche (wetter.json, Prognose); ohne
  // Prognosewoche (nach W17, Offseason) entfällt der Teil
  if (wetter && U.ok(wetter.WX.woche)) {
    const {WX, wx} = wetter, spiele = new Map();
    for (const p of kader) {
      const g = wx.gameOf(WX, p.nfl);
      if (g && !wx.played(g) && wx.flagText(g)) spiele.set(g.id, [g, [...(spiele.get(g.id)?.[1] || []), p]]);
    }
    teile.push(h('h3', null, `Wetter W${WX.woche}`, ' ', U.ib('wetter-markierung', '')),
      spiele.size ? liste([...spiele.values()], ([g, ps]) => [h('span', {class: 'flag', 'aria-hidden': 'true'}, '⚑ '), `${g.gast} @ ${g.heim}: `,
        wx.flagText(g).replace(/^Wetter W\d+: /, ''), ' – ', ps.map((p, i) => [i ? ', ' : '', pl(p.id)])])
        : h('p', {class: 'note'}, 'Kein markiertes Spiel eines Kaderspielers vor dem Anstoß.'));
  }
  box.replaceChildren();
  U.ap(box, teile);
}

// ---------------------------------------------------------------- Markt: Stärken und Schwächen, Bedarf Rest der Saison, Moves
// z = U.zwischenstand: dienstags vor dem Wochenabruf rechnen Profil und Bedarf noch mit dem Rest der Saison nach der Woche davor
// (Byes schon ab der neuen Woche) – die Hinweiszeile steht dann über beiden
function marktTeil(box, t, W, name, ctx, r, z) {
  const prof = W?.profil?.[String(t.team_id)], B = W?.bedarf?.[String(t.team_id)];
  const moves = h('div');
  box.replaceChildren();
  if (!W) U.ap(box, h('p', {class: 'note'}, 'Stärken und Schwächen und Bedarf erscheinen mit dem ersten Tageslauf.'));
  if (z && (prof || B)) U.ap(box, U.zwischenHinweis(z));
  if (prof) U.ap(box, h('p', null, ...short(prof, W)), profile(t, W, prof, name));
  if (B) {
    const pl = id => h('a', {href: '#spieler/' + id}, name.get(id) ?? `Spieler ${id}`);
    const ue = Object.entries(B.ueber_ersatz || {}).filter(([, v]) => v != null);
    U.ap(box, h('h3', null, 'Bedarf Rest der Saison', ' ', U.ib('bedarf', '')),
      h('p', null, h('strong', null, 'Starter unter Ersatzniveau: '), (B.luecken || []).length
        ? B.luecken.map((x, i) => [i ? ' · ' : '', `${x.slot} `, x.id ? pl(x.id) : 'leer', U.ok(x.ros_g) ? ` (${U.num(x.ros_g)} je Spiel)` : ''])
        : 'keine'),
      ue.length ? h('p', null, h('strong', null, 'Tiefe je Position: '), ue.map(([p, v]) => `${p} ${v}`).join(' · ')) : null);
  }
  U.ap(box, h('h3', null, 'Moves', ' ', U.ib('transaktionen', '')), moves);
  if (!S.man.files?.['transactions.json']) { moves.append(h('p', {class: 'note'}, 'Noch keine Transaktionen.')); return; }
  ctx.load('transactions.json').then(T => {
    if (!r.alive()) return;
    const alle = (T.items || []).filter(x => x.team_id === t.team_id).sort((a, b) => (b.datum ?? 0) - (a.datum ?? 0)), items = alle.slice(0, 5);
    const leute = (x, art) => (x.items || []).filter(i => i.type === art)
      .map((i, k) => [k ? ', ' : '', i.in_app === false ? (i.name || T.spieler?.[String(i.player_id)] || '–') : h('a', {href: '#spieler/' + i.player_id}, i.name || T.spieler?.[String(i.player_id)] || `Spieler ${i.player_id}`)]);
    moves.replaceChildren(items.length ? h('ul', {class: 'tli'}, items.map(x => h('li', null, U.ok(x.datum) ? `${U.datum(x.datum)} ` : '',
      x.type === 'TRADE_ACCEPT' && !(x.items || []).length ? 'Trade (ohne Spieler laut ESPN)'
        : [leute(x, 'ADD').length ? ['+ ', leute(x, 'ADD')] : '', leute(x, 'ADD').length && leute(x, 'DROP').length ? ' · ' : '',
          leute(x, 'DROP').length ? ['− ', leute(x, 'DROP')] : '']))) : h('p', {class: 'note'}, 'Noch keine Moves in dieser Saison.'),
    items.length ? h('p', {class: 'note'}, alle.length > 5 ? `Die letzten fünf von ${alle.length}, neueste zuerst.` : 'Neueste zuerst.') : null);
  }).catch(() => moves.replaceChildren(h('p', {class: 'note'}, 'Transaktionen konnten nicht geladen werden.')));
}

// Profil: Gruppen mit Wert je Spiel der Starter (Rest der Saison, nach W14 Playoffs W15–17), Abstand zum Ligaschnitt
// und Rang, Ist-Rang, Absicherung; darunter Byes und freie Spieler mit Zugewinn für dieses Team. Alle Zahlen aus Python
// (waiver.json profil, spieler[].zug)
function profile(t, W, prof, name) {
  const g = prof.gruppen, abs = prof.absicherung || {};
  const cls = k => g[k].wertung === 'schwach' ? 'dn' : g[k].wertung === 'stark' ? 'up' : null;
  const po = W.bedarf_basis === 'playoffs';
  const table = U.table({cap: po ? 'Profil nach Slot-Gruppen (Playoffs W15–17)' : 'Profil nach Slot-Gruppen (Rest der Saison)', cls: 'nr', rows: Object.keys(g), sortable: false, rh: 0, cols: [
    {k: 'g', l: 'Gruppe', f: k => h('span', {class: cls(k), title: g[k].ids.map(name.get, name).join(', ')}, GRP[k][0])},
    {k: 'w', l: 'je Spiel', num: 1, f: k => U.num(g[k].wert)},
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
  return h('div', null, table,
    h('p', {class: 'note'}, `Freie Spieler, die hier starten würden (${po ? 'Playoffs' : 'Rest'} je Spiel): `, zug, ' ', U.ib('zugewinn', '')),
    h('p', {class: 'note'}, 'Byes (Verlust der besten Aufstellung): ', byes, ' ', U.ib('bye-kosten', '')),
    h('p', {class: 'note'}, `Kader ${k.spieler} Spieler` + (k.ir ? ` (${k.ir} im IR-Slot)` : '') + (k.voll ? ', voll – ein Zugang braucht einen Drop' : '')
      + (k.limit.length ? `; am Positionslimit: ${k.limit.join(', ')}` : '') + `. ${U.standTxt(W.stand)}.`),
    U.legend(['profil', 'absicherung', 'zugewinn', 'bye-kosten']));
}

function h2h(t) {
  const rows = (S.sched.h2h || []).filter(e => e.spiele > 0 && (e.a === t.team_id || e.b === t.team_id)).map(e => {
    const me = e.a === t.team_id;
    return {opp: me ? e.b : e.a, n: e.spiele, w: me ? e.w_a : e.l_a, l: me ? e.l_a : e.w_a, t: e.t, d: me ? e.pf_diff : -e.pf_diff};
  });
  if (!rows.length) return h('p', {class: 'note'}, 'Noch keine direkten Duelle.');
  return h('div', {class: 'blk'}, U.table({cap: `Duelle ${S.man.season}`, cls: 'nr kurz', rows, sort: ['d', -1], rh: 0, cols: [
    {k: 'o', l: 'Gegner', v: x => U.kz(x.opp), d: 1, f: x => U.tl(x.opp)},
    {k: 'n', l: 'Spiele', num: 1, v: x => x.n, f: x => x.n},
    {k: 'b', l: 'Bilanz', v: x => x.w - x.l, f: x => `${x.w}-${x.l}` + (x.t ? `-${x.t}` : '')},
    {k: 'd', l: 'PF-Diff', num: 1, v: x => x.d, f: x => U.sgn(x.d)}]}), U.legend(['h2h']));
}

// ---------------------------------------------------------------- Keeper: erwarteter Pick, Kader mit Herkunft, Alter, Marktwert, Draft-Picks
function keeperTeil(box, t, P, kader, W, nflTxt, K, kp) {
  const sim = t.sim?.liga, kt = K?.teams?.find(x => x.team_id === t.team_id);
  const next = S.man.season + 1;
  U.ap(box, h('div', {class: 'tiles'},
    U.tile(`Erwarteter Pick ${next}`, U.val(sim?.pick, v => U.num(v, 1), 'Simulation folgt'), U.ok(sim?.pick1) ? `Pick 1: ${U.po(U.sp(sim.pick1))}` : null, 'draft-folgejahr'),
    kt ? U.tile('Keeper %', U.pct(kt.pf?.anteil?.keeper), `Keeper im Kader ${kt.keeper_da} von ${kt.keeper}`, 'keeper-bilanz') : null,
    kt?.marktwert ? U.tile(`Wert Top ${K.keeper_zahl}`, kp.wertTxt(kt.marktwert.kern), `Spieler ab Linie ${U.val(kt.marktwert.n_linie, v => v, '–')}`, 'kern-wert') : null,
    kt?.altersprofil ? U.tile('Ø Alter', U.val(kt.altersprofil.kader, v => U.num(v, 1), 'keine Altersdaten'), `unter 26: ${kt.altersprofil.jung} · ab 30: ${kt.altersprofil.alt}`, 'alter') : null),
  kt?.marktwert ? h('p', {class: 'note'}, kp.fcQuelle(), ` · ${U.standTxt(K.marktwert_stand)}`) : null);
  roster(box, t, P, kader, W, nflTxt, K, kp);
  if (K) picks(box, t, K, kp);
}

function roster(box, t, P, rows0, W, nflTxt, K, kp) {
  const last = (P.weeks || []).length - 1;
  const rows = [...rows0].sort((a, b) => POS.indexOf(a.pos) - POS.indexOf(b.pos) || (b.avg ?? -1) - (a.avg ?? -1));
  // Grund für „–“ bei Rest je Spiel: noch kein Auszug, Saisonende (ROS nach W17, Stufe 4) oder keine Projektion des Spielers
  const ros = P.ros_nach_woche == null ? 'ab Wochenabruf W' + (S.tw + 1)
    : P.ros_nach_woche >= (S.weeks.at(-1)?.week ?? 17) ? 'Saison beendet, keine Restwoche' : 'keine Projektion';
  // Herkunft, Alter und Marktwert (keeper.json, Kader heute): nur Zeilen dieses Teams, sonst wäre ein eben gewechselter Spieler falsch beschriftet
  const org = K ? kp.byPlayer(K) : null;
  const mine = p => { const o = org?.get(p.id); return o && o.team === t.team_id ? o : null; };
  const ohneWert = p => p.pos === 'K' || p.pos === 'D/ST' ? 'K und D/ST ohne Marktwert' : 'nicht bei FantasyCalc';
  // Einfach / Ausführlich (Paket P5): mit keeper.json Herkunft, Alter, Marktwert einfach, Ø Punkte und Form ausführlich
  U.ap(box, U.table({cap: `Kader (${rows.length} Spieler)`, cls: 'nr', rows, sort: null, rh: 0, cols: [
    {k: 'n', l: 'Spieler', v: p => p.name, d: 1, f: p => h('a', {href: '#spieler/' + p.id, class: 'pl'}, h('span', null, p.name, U.inj(p.inj)), h('span', {class: 'sub'}, `${p.pos ?? '–'} · ${nflTxt(p)}`))},
    {k: 's', l: `Slot W${P.weeks?.[last] ?? ''}`, v: p => { const i = ORD.indexOf(U.slot(p.wk?.[last]?.[4])); return i < 0 ? null : i; }, d: 1, f: p => U.slot(p.wk?.[last]?.[4])},
    org ? {k: 'h', l: 'Herkunft', v: p => kp.herkunftOrd(mine(p)), d: 1, f: p => kp.herkunft(mine(p), K) ?? U.na('noch nicht zugeordnet')} : null,
    org && K.alter_stichtag ? {k: 'al', l: 'Alter', num: 1, v: p => mine(p)?.alter, f: p => U.val(mine(p)?.alter, v => U.num(v, 1), p.pos === 'D/ST' ? 'D/ST ohne Alter' : 'nicht in den Stammdaten')} : null,
    org && K.marktwert_stand ? {k: 'mw', l: 'Marktwert', num: 1, v: p => mine(p)?.wert, f: p => U.val(mine(p)?.wert, kp.wertTxt, ohneWert(p))} : null,
    {k: 'r', l: 'Rest je Spiel', num: 1, v: p => p.ros_g, f: p => U.val(p.ros_g, U.num, ros)},
    {k: 'a', l: 'Ø Punkte', num: 1, x: !!org, v: p => p.avg, f: p => U.val(p.avg, U.num, 'ohne Spiel')},
    {k: 'f', l: 'Form', num: 1, x: !!org, v: p => p.form, f: p => [U.val(p.form, U.num, 'ohne Spiel'), p.trend ? ' ' + p.trend : '']}].filter(Boolean)}),
  U.legend([...(org ? ['herkunft', 'alter', 'marktwert'] : []), 'ros-spiel', 'avg', 'form-sp']),
  h('p', {class: 'note'}, W?.stand ? `Kader und Verletzung: ${U.standTxt(W.stand)}. ` : `Verletzung: Stand nach W${S.man.datenstand?.pool_woche ?? S.tw}. `,
    org && K.alter_stichtag ? `Alter am ${U.datum(K.alter_stichtag)} ` : null, 'Q fraglich · D zweifelhaft · O fällt aus · IR Injured Reserve · DTD Day-to-Day.'));
}

// Draft-Picks des Teams mit Ertrag (keeper.json picks): wie Keeper › Draft, nur dieses Team
function picks(box, t, K, kp) {
  const rows = (K.picks || []).filter(p => p.team_id === t.team_id);
  if (!rows.length) return;
  const bleib = p => p.da ? 'im Kader' : p.team_jetzt ? `bei ${U.kz(p.team_jetzt)}` : 'frei';
  U.ap(box, h('div', {class: 'blk'}, U.table({cap: `Draft ${S.man.season} (inklusive Keeper)`, cls: 'nr', rh: 1, rows, sort: ['p', 1], cols: [
    {k: 'p', l: 'Pick', num: 1, v: p => p.pick, d: 1, f: p => p.pick},
    {k: 's', l: 'Spieler', v: p => (p.name || '').toLowerCase(), d: 1, f: p => [p.in_app === false ? (p.name ?? `Spieler ${p.player_id}`)
      : h('a', {href: '#spieler/' + p.player_id, class: 'tl2'}, p.name ?? `Spieler ${p.player_id}`), p.keeper ? h('span', {class: 'kp'}, 'Keeper') : null]},
    {k: 'b', l: 'Verbleib', v: bleib, d: 1, f: bleib},
    {k: 'st', l: 'Starts', num: 1, v: p => p.starts, f: p => p.starts},
    {k: 'pf', l: 'Punkte fürs Team', num: 1, v: p => p.pf, f: p => U.num(p.pf)},
    {k: 'r', l: 'Runde', num: 1, x: 1, v: p => p.runde, d: 1, f: p => p.runde},
    {k: 'pt', l: 'Pkt', num: 1, x: 1, v: p => p.pts, f: p => U.val(p.pts, U.num, 'keine Wochendaten')}]}),
  U.legend(['draft', 'draft-ertrag'])));
}

function franchise(box, t, H, svg) {
  const a = (H.alltime || []).find(x => x.slot === t.team_id);
  if (!a) { U.ap(box, h('p', {class: 'note'}, 'Keine Historie für diesen Franchise-Slot.')); return; }
  const ts = (H.team_seasons || []).filter(x => x.slot === t.team_id).sort((x, y) => x.season - y.season);
  U.ap(box, h('p', null, h('strong', null, 'Namen: '), a.namenskette),
    h('div', {class: 'tiles'},
      U.tile('Saisons', a.saisons, `${a.w}-${a.l} · W ${U.pct(a.w_pct)}`, 'wpct-alltime'),
      U.tile('Titel', a.titel, (a.titel_saisons || []).join(', ') || '–'),
      U.tile('Playoffs', a.playoffs, `Finals ${a.finals} · Divisionssiege ${a.divisionssiege}`),
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
