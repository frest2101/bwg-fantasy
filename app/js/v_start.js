// Startseite (#start, leerer Hash, Marke im Kopf; App-Konzept 04.10.2026, Abschnitt 5, Paket P2): in einer Bildschirmhöhe, was
// los ist und wohin man geht – Wochenstatus, Mein Team und fünf Karten (je Bereich die Frage, eine Zahl und ein Satz).
// Daten nur aus teams.json, schedule.json (beide schon geladen) und waiver.json (Tageslauf, darf fehlen). Die Startseite rechnet
// nichts: Sie wählt fertige Werte aus und zählt höchstens (offene NFL-Spiele aus den Anstoßzeiten, Lücken je Slot).
let U, S, h;
const FRAGLICH = ['QUESTIONABLE', 'DOUBTFUL', 'DAY_TO_DAY'];

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const W = S.man.files?.['waiver.json'] ? await ctx.load('waiver.json').catch(e => { console.warn(e); return null; }) : null;
  if (!r.alive()) return;
  const tid = U.meinTeam(), t = U.team(tid);
  const wk = U.aktuelleWoche(), laeuft = U.saisonLaeuft(), vor = (S.weeks[0]?.start ?? '') > U.heute();
  // Anstoßzeiten der laufenden Woche (waiver.json, je NFL-Team): je Spiel zwei Teams mit derselben Zeit, Bye-Teams fehlen
  const ks = W?.woche === wk && W.anstoss ? Object.values(W.anstoss).filter(U.ok) : [];
  const jetzt = Date.now(), offenK = ks.filter(x => x > jetzt);
  const nfl = laeuft && ks.length ? {gesamt: Math.ceil(ks.length / 2), offen: Math.ceil(offenK.length / 2),
    naechster: offenK.length ? Math.min(...offenK) : null} : null;

  U.ap(box, h('h1', null, `BWG Fantasy Liga ${S.man.season}`), status(wk, laeuft, vor, nfl),
    t ? meinTeam(t, W, wk, laeuft, nfl, ctx) : waehlen(ctx),
    h('div', {class: 'sks'}, ctx.bereiche().map(B => karte(B, KARTE[B.k](t, W, {wk, laeuft, vor, nfl})))),
    h('p', {class: 'note'}, 'Neu hier? Die ', h('a', {href: '#erklaerungen'}, 'Erklärungen'), ' nennen jeden Begriff; Spieler und Teams findet die Lupe oben. Inoffizielle Auswertung, Daten von ESPN. ',
      U.ib('start', '')));
}

// Wochenstatus: laufende Woche nach Kalender, gewertete Woche und Stand des Tageslaufs
function status(wk, laeuft, vor, nfl) {
  const ds = S.man.datenstand || {}, sw = ds.playoff_woche ?? S.tw;
  const W0 = S.weeks.find(w => w.week === wk);
  const woche = vor ? `Saison ${S.man.season} beginnt ${U.datum(S.weeks[0].start)}`
    : !laeuft ? `Saison ${S.man.season} beendet`
    : `Woche ${wk}${W0?.playoff ? ' (Playoffs)' : ''}` + (!nfl ? ' läuft'
      : nfl.offen === nfl.gesamt ? ` · erster Anstoß ${U.stamp(nfl.naechster)}`
      : nfl.offen ? ` läuft · ${nfl.offen} von ${nfl.gesamt} NFL-Spielen offen` : ' · alle Spiele angepfiffen');
  return h('p', {class: 'note'}, [woche, sw ? `W${sw} gewertet` : null, ds.pool_stand ? U.standTxt(ds.pool_stand) : null].filter(Boolean).join(' · '),
    ' ', U.ib('nach-wn', ''));
}

// ---------------------------------------------------------------- Mein Team
function waehlen(ctx) {
  const btn = h('button', {type: 'button', class: 'btn pri', 'data-pop': '', 'aria-haspopup': 'dialog', 'aria-controls': 'pop', 'aria-expanded': 'false',
    onclick: () => ctx.meinTeam(btn)}, 'Mein Team wählen');
  return h('section', {class: 'card mtz', 'aria-labelledby': 'mtz-h'}, h('h2', {id: 'mtz-h'}, 'Mein Team'),
    h('p', null, 'Wähle dein Team: Die App hebt es dann in Tabellen, Diagrammen und Paarungen hervor, Markt, Herkunft und Spieltag live zeigen es zuerst. Gespeichert wird nur die Team-Nummer in diesem Browser.'),
    h('p', null, btn));
}

function meinTeam(t, W, wk, laeuft, nfl, ctx) {
  const sim = t.sim?.liga, div = S.meta.divisions?.[t.division] ?? 'Division ' + t.division;
  const btn = h('button', {type: 'button', class: 'btn', 'data-pop': '', 'aria-haspopup': 'dialog', 'aria-controls': 'pop', 'aria-expanded': 'false',
    onclick: () => ctx.meinTeam(btn)}, 'ändern');
  const zeilen = [
    [U.rec(t), `${t.rang}. der Tabelle`, `${t.rang_division}. ${div}`, U.ok(sim?.playoff) ? `Playoff ${U.po(U.sp(sim.playoff))}` : null].filter(Boolean).join(' · '),
    spiel(t, wk, laeuft, nfl),
    bedarf(t, W),
  ];
  return h('section', {class: 'card mtz', 'aria-labelledby': 'mtz-h'},
    h('div', {class: 'row mth'}, h('h2', {id: 'mtz-h'}, h('span', {class: 'note'}, 'Mein Team '), h('a', {href: '#team/' + t.team_id}, t.name)), btn),
    zeilen.filter(Boolean).map(z => h('p', null, z)));
}

// Spiel der laufenden Woche: Ergebnis, läuft (dann Spieltag live) oder Siegchance aus schedule.json; der Teamname oben führt
// zur Team-Seite, „Bedarf Wn“ zu Markt › Bedarf je Team
function spiel(t, wk, laeuft, nfl) {
  const g = S.sched.games.find(x => x.week === wk && (x.home === t.team_id || x.away === t.team_id));
  if (!g) return laeuft ? `W${wk}: kein Spiel` : null;
  const heim = g.home === t.team_id, opp = U.team(heim ? g.away : g.home);
  const gegen = ['gegen ', h('a', {href: '#team/' + opp?.team_id}, opp?.name ?? '–')];
  if (g.winner != null) {
    const erg = g.winner === 'T' ? 'Unentschieden' : g.winner === t.team_id ? 'Sieg' : 'Niederlage';
    return [`W${wk}: ${erg} ${U.num(heim ? g.home_pf : g.away_pf)} : ${U.num(heim ? g.away_pf : g.home_pf)} `, ...gegen];
  }
  // Siegchance wie in den Paarungen (U.game): Heimchance in Prozent, Gast = 100 − Heim
  const ph = U.ok(g.p_home) ? U.sp(g.p_home) : null, chance = ph == null ? null : heim ? ph : 100 - ph;
  const begonnen = nfl && nfl.offen < nfl.gesamt;
  return [`W${wk} `, ...gegen, chance != null ? `: Siegchance ${U.po(chance)}` : '', U.ib('siegchance', ''),
    begonnen ? [' · läuft, Punkte unter ', h('a', {href: '#spieltag'}, 'Spieltag live')] : null];
}

// Bedarf der nächsten Woche laut Tageslauf (waiver.json › bedarf_woche): Lücken je Slot, Ausfälle, Byes der Wochen danach
function bedarf(t, W) {
  const B = W?.bedarf_woche?.[String(t.team_id)];
  if (!B) return null;
  const luecken = (B.luecken || []).map(x => x.slot);
  const aus = B.ausfaelle || [], fr = aus.filter(x => FRAGLICH.includes(x.grund)), weg = aus.filter(x => !FRAGLICH.includes(x.grund));
  const byes = new Map();
  for (const x of B.byes || []) byes.set(x.woche, [...(byes.get(x.woche) || []), x.pos]);
  const teile = [luecken.length ? `Lücken ${luecken.join(', ')}` : 'keine Lücke',
    weg.length ? `fällt aus: ${weg.map(x => x.pos).join(', ')}` : null, fr.length ? `fraglich: ${fr.map(x => x.pos).join(', ')}` : null,
    ...[...byes].map(([w, p]) => `Bye W${w}: ${p.join(', ')}`)].filter(Boolean);
  return [h('a', {href: '#markt/bedarf'}, `Bedarf W${W.woche}`), `: ${teile.join(' · ')} `, U.ib('bedarf-woche', '')];
}

// ---------------------------------------------------------------- fünf Karten (je Bereich: Frage, Zahl, ein Satz)
// Karte: Überschrift mit Link (die ganze Karte ist klickbar, CSS .sk h2 a::after), darunter Zahl mit Beschriftung und ein Satz
function karte(B, x) {
  return h('section', {class: 'sk'},
    h('h2', null, h('a', {href: '#' + B.k}, B.l), h('span', null, B.frage)),
    x.wert != null ? h('p', {class: 'skz'}, h('b', null, x.wert), h('span', null, x.lab)) : null,
    h('p', null, x.satz));
}
const nach = (rows, f) => [...rows].sort((a, b) => f(a) - f(b));
const namen = ts => ts.map(x => x.name).join(', ').replace(/, ([^,]*)$/, ' und $1');
const KARTE = {
  liga: t => {
    const [a, ...rest] = nach(S.teams, x => x.rang), po = x => U.ok(x?.sim?.liga?.playoff) ? `Playoff-Chance ${U.po(U.sp(x.sim.liga.playoff))}` : null;
    if (!t) return {wert: U.rec(a), lab: 'Tabellenführer', satz: `${a.name} vor ${namen(rest.slice(0, 2))}; dazu Ergebnisse, Playoff-Chancen, Duelle und Rekorde.`};
    // Bilanz von Mein Team steht schon in der Zeile darüber; hier der Abstand nach vorn und die Playoff-Chance
    return {wert: `${t.rang}.`, lab: `Tabellenplatz ${t.kuerzel}`,
      satz: [t === a ? `${t.kuerzel} führt die Tabelle an` : `Vorn: ${a.name} (${U.rec(a)})`, po(t) && `${po(t)} für ${t.kuerzel}`].filter(Boolean).join('; ') + '.'};
  },
  staerke: t => {
    const pr = nach(S.teams.filter(x => x.pr), x => x.pr.rang), a = pr[0];
    if (!a) return {satz: 'Das Power Ranking folgt.'};
    const mu = x => U.num(x.pr.mu, 1);
    if (!t?.pr) return {wert: mu(a), lab: `Stärke ${a.kuerzel}, Platz 1`, satz: `Power Ranking nach Punkten statt Siegen: ${a.name} vor ${namen(pr.slice(1, 3))}.`};
    const tr = t.pr.trend, trTxt = U.ok(tr) && tr ? ` (${tr > 0 ? '↑' : '↓'}${Math.abs(tr)} zur Vorwoche)` : '';
    return {wert: `${t.pr.rang}.`, lab: `Power Ranking ${t.kuerzel}`,
      satz: (t === a ? `${t.kuerzel} vorn mit Stärke ${mu(t)}` : `Vorn ${a.name} mit Stärke ${mu(a)}, ${t.kuerzel} ${mu(t)}`) + trTxt + '.'};
  },
  woche: (t, W, z) => {
    if (z.vor) return {wert: 'W1', lab: `ab ${U.datum(S.weeks[0].start)}`, satz: 'Paarungen mit Siegchance, Matchups je Position und Wetter.'};
    if (!z.laeuft) return {satz: `Saison ${S.man.season} beendet – Ergebnisse unter Liga, der Draft ${S.man.season + 1} unter Keeper.`};
    if (!z.nfl) return {wert: `W${z.wk}`, lab: 'läuft', satz: 'Punkte live, Paarungen mit Siegchance, Matchups je Position und Wetter.'};
    return {wert: String(z.nfl.offen), lab: `von ${z.nfl.gesamt} NFL-Spielen in W${z.wk} offen`,
      satz: z.nfl.offen ? `Nächster Anstoß ${U.stamp(z.nfl.naechster)}; Punkte live unter Spieltag live.` : 'Alle Spiele angepfiffen; Punkte live unter Spieltag live, gewertet wird nach dem Wochenabruf am Dienstag.'};
  },
  markt: (t, W) => {
    if (!W) return {satz: 'Beste freie Spieler, Bedarf je Team und Waiver-Reihenfolge erscheinen mit dem ersten Tageslauf.'};
    const rf = W.reihenfolge || [], B = t && W.bedarf_woche?.[String(t.team_id)];
    if (!t || !rf.includes(t.team_id)) {
      const a = U.team(rf[0]);
      return {wert: a?.kuerzel ?? null, lab: 'Waiver-Platz 1', satz: `Beste freie Spieler für W${W.woche}, Bedarf je Team und alle Moves; ${U.standTxt(W.stand)}.`};
    }
    const lu = (B?.luecken || []).map(x => x.slot);
    return {wert: `${rf.indexOf(t.team_id) + 1}.`, lab: `Waiver-Reihenfolge ${t.kuerzel}`,
      satz: !B ? `Beste freie Spieler für W${W.woche} und Gewinn für ${t.kuerzel}.`
        : lu.length ? `Lücken für W${W.woche}: ${lu.join(', ')} – freie Kandidaten unter Bedarf je Team.` : `Keine Lücke für W${W.woche}; Gewinn für ${t.kuerzel} je freiem Spieler unter Freie Spieler.`};
  },
  keeper: t => {
    const next = S.man.season + 1, L = x => x.sim?.liga;
    if (t && U.ok(L(t)?.pick)) return {wert: U.num(L(t).pick, 1), lab: `erwarteter Pick ${next} ${t.kuerzel}`,
      satz: `Draft ${next} in umgekehrter Endplatzierung, laut Simulation; dazu Keeper-Bilanz, Herkunft, Alter und Marktwert.`};
    const p1 = S.teams.filter(x => U.ok(L(x)?.pick1)).sort((a, b) => L(b).pick1 - L(a).pick1)[0];
    if (p1) return {wert: p1.kuerzel, lab: `am ehesten Pick 1 ${next} (${U.po(U.sp(L(p1).pick1))})`,
      satz: 'Woher die Punkte kommen, Alter und Marktwert der Kader, Draft laut Simulation.'};
    return {satz: 'Woher die Punkte kommen, Alter, Marktwert und Draft.'};
  },
};
