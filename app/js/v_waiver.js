// Bereich Markt (lädt waiver.json und players.json, dazu transactions.json) in drei Ansichten: Freie Spieler (#markt: beste
// verfügbare Spieler je Position nach Horizont, Tagesstand), Bedarf je Team (#markt/bedarf) und Reihenfolge & Claims
// (#markt/reihenfolge: Waiver-Reihenfolge, Claims der letzten 7 Tage). Zahlen kommen aus Python; hier nur Anzeige, Filter
// und die Zusammenführung von Tagesstand (waiver.json) und Wochenstand (players.json) je Spieler-ID.
// Matchup je Spieler (Feld mu) aus dem Wochenstand, dienstags vor dem Wochenabruf ausgeblendet (Hinweis „Gespielt, noch nicht
// gewertet“, U.zwischenstand); Wetter-Fähnchen aus wetter.json (Prognose der laufenden Woche).
// Horizont (Beschluss 30.09.2026): „Nächste Woche (Wn)“ = N+1 (Standard), „Nächste 3 Wochen“ = Summe N+1…N+3 oder „Rest der
// Saison“ – für die Liste und den Bedarf je Team; dazu „Langfristig (Marktwert)“ (Schlüssel zukunft, Session 9): freie Spieler
// nach Marktwert (FantasyCalc, waiver.json), nur für die Liste. Namen nach App-Konzept 04.10.2026 (P4).
let U, S, h;
const TITEL = {'': 'Freie Spieler', bedarf: 'Bedarf je Team', reihenfolge: 'Reihenfolge & Claims'};
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];
const FREE = ['WAIVERS', 'FREEAGENT'];
const ART = {WAIVER: 'Waiver', FREEAGENT: 'Free Agent'};
const DAYS7 = 7 * 864e5;
const fz = v => 'fz' + (U.ok(v) ? ' ' + U.fcls(v) : '');   // Farbzelle um F = 1,00; ohne Wert ohne Farbe
const HOR = ['woche', 'drei', 'ros', 'zukunft'];
const GRUND = {BYE: 'Bye', OUT: 'fällt aus', INJURY_RESERVE: 'IR', SUSPENSION: 'gesperrt', QUESTIONABLE: 'fraglich',
  DOUBTFUL: 'zweifelhaft', DAY_TO_DAY: 'Day-to-Day'};
// Spiel der Woche N+1 schon angepfiffen: Der Spieler bringt in dieser Woche nichts mehr (Anstoß aus waiver.json)
const played = (W, x) => U.ok(W.anstoss?.[x.nfl]) && W.anstoss[x.nfl] <= Date.now();
const span = W => W.horizont?.length ? `W${W.horizont[0]}` + (W.horizont.length > 1 ? `–${W.horizont.at(-1)}` : '') : 'nächste 3';

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const ansicht = r.view, liste = ansicht === '';
  U.kopf(box, r, TITEL[ansicht]);
  if (!S.man.files?.['waiver.json']) {
    U.ap(box, h('p', {class: 'warn'}, 'Noch keine Tagesdaten: Der Markt füllt sich mit dem ersten Tageslauf (stündlich von etwa 05:00 Uhr bis Mitternacht deutscher Zeit).'),
      h('p', null, h('a', {href: '#spieler?status=frei'}, `Freie Spieler (Stand nach W${S.tw})`)));
    return;
  }
  const [W, P] = await Promise.all([ctx.lazy('waiver.json', 'Tagesdaten', box), ctx.lazy('players.json', 'Spielerdaten', box)]);
  if (!r.alive()) return;
  // Claims (nur Reihenfolge & Claims) und Wetter (nur Freie Spieler) sind Zugabe: ohne sie bleibt die Ansicht nutzbar
  // (ohne Wetter keine Fähnchen)
  const [T, WX] = await Promise.all([ansicht === 'reihenfolge' ? ctx.load('transactions.json').catch(() => null) : null,
    liste && S.man.files?.['wetter.json'] ? ctx.load('wetter.json').catch(() => null) : null]);
  const wx = WX ? await ctx.mod('v_wetter').catch(() => null) : null;
  // Horizont „Langfristig (Marktwert)“ (zukunft) nur mit Marktwerten; Quelle, Format und Verweise kommen aus dem Keeper-Modul
  const kp = liste && W.wert_stand ? await ctx.mod('v_keeper').catch(() => null) : null;
  if (!r.alive()) return;
  const byId = new Map(P.players.map(p => [p.id, p]));
  // Tagesstand je Spieler, Stammdaten und ROS aus dem Wochenstand; wer dort fehlt, heißt wie im Tagesstand (ohne ROS)
  const rows = W.spieler.map(d => {
    const p = byId.get(d.id) || {};
    return {...p, ...d, name: p.name ?? d.name ?? `Spieler ${d.id}`, pos: p.pos ?? d.pos ?? null, nfl: p.nfl ?? d.nfl ?? null};
  });
  const rowById = new Map(rows.map(x => [x.id, x]));
  const name = id => byId.get(id)?.name ?? rowById.get(id)?.name ?? T?.spieler?.[String(id)] ?? `Spieler ${id}`;
  // Bezugsteam: #markt?team=N gilt nur für diesen Aufruf (Link von der Team-Seite), sonst Mein Team (Kopf)
  const qTeam = U.team(r.q.get('team')) ? +r.q.get('team') : 0;
  const me = {mine: qTeam || U.meinTeam(), q: qTeam};
  let draw = () => {};
  const mineSel = h('select', {'aria-label': 'Mein Team', onchange: e => {
    me.mine = +e.target.value; me.q = 0; U.setMeinTeam(me.mine);     // gilt wie die Wahl im Kopf überall
    if (!liste) U.setQ(r.base, {});       // die Liste schreibt ihre Parameter selbst (ohne team)
    // die Sicht eines anderen Teams endet: auch die Chips der Markt-Ansichten (Router, bereich) ohne ?team=
    for (const a of box.querySelectorAll('.chips.bv a')) a.setAttribute('href', a.getAttribute('href').split('?')[0]);
    draw();
  }}, h('option', {value: 0}, 'Mein Team wählen'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === me.mine}, `${t.kuerzel} · ${t.name}`)));
  // Dienstags vor dem Wochenabruf (U.zwischenstand): Hinweiszeile unter Freie Spieler und Bedarf je Team, nicht unter Reihenfolge &
  // Claims (dort gilt nur die Spalte Schwächen noch nach dem Wochenstand)
  const z = U.zwischenstand(W, P);
  U.ap(box, h('p', {class: 'note'}, `${U.standTxt(W.stand)} · Projektion und Bye-Hinweis für W${W.woche}`, ' ', U.ib('tagesstand', '')),
    ansicht !== 'reihenfolge' && z ? U.zwischenHinweis(z, liste ? 'Gegner und Faktor nächste 3 fehlen in der Tabelle bis dahin.' : null) : null,
    h('div', {class: 'row'}, h('label', null, qTeam ? 'Sicht von ' : 'Mein Team ', mineSel)));
  if (liste) {
    const av = available(box, W, P, rows, r, wx && (nfl => wx.flagLink(wx.gameOf(WX, nfl))), me, kp, z);
    draw = () => av.rebuild();
    return;
  }
  const wrap = h('div');
  U.ap(box, wrap);
  if (ansicht === 'bedarf') {
    let bsicht = W.bedarf_woche ? 'woche' : 'ros';
    draw = () => { wrap.replaceChildren(needs(W, P, name, me.mine, bsicht, v => { bsicht = v; draw(); }, rowById)); };
  } else draw = () => { wrap.replaceChildren(order(W, me.mine)); };
  draw();
  if (ansicht === 'reihenfolge') claims(box, T, name);
}

// ---------------------------------------------------------------- beste verfügbare Spieler je Position
// zw = U.zwischenstand (dienstags vor dem Wochenabruf) oder null
function available(box, W, P, rows, r, wflag, me, kp, zw) {
  const q = r.q;
  const hasWeek = !!W.ersatz_woche, hasWert = !!kp;
  // erlaubte Horizonte: Nächste Woche und Nächste 3 Wochen nur mit Wochensicht, Langfristig (zukunft) nur mit Marktwerten
  const hors = HOR.filter(x => x === 'ros' || (x === 'zukunft' ? hasWert : hasWeek));
  const st = {pos: POS.includes(q.get('pos')) ? q.get('pos') : '', text: '',
    hor: hors.includes(q.get('h')) ? q.get('h') : (hasWeek ? 'woche' : 'ros'),
    // Status Frei · Alle · Kader (Stephan 06.10.2026): Alle = alle Spieler des Tagesstands, auch die in einem Kader
    status: ['alle', 'kader'].includes(q.get('status')) ? q.get('status') : 'frei'};
  const free = rows.filter(x => FREE.includes(x.status));
  const kader = rows.filter(x => x.team > 0);
  const pick = () => st.status === 'frei' ? free : st.status === 'kader' ? kader : rows;
  // Langfristig (zukunft): nur Spieler mit Marktwert (K und D/ST haben keinen)
  const rowsNow = () => pick().filter(x => (!st.pos || x.pos === st.pos) && (!st.text || x.name.toLowerCase().includes(st.text))
    && (st.hor !== 'zukunft' || U.ok(x.wert)));
  // Spieler, die nur der Tagesstand kennt (unter der Woche geholt, frei mit Marktwert), haben keine Wochenwerte
  const inWeek = new Set(P.players.map(p => p.id));
  const rosWhyBase = P.ros_nach_woche == null ? `ab Wochenabruf W${S.tw + 1}`
    : P.ros_nach_woche >= (S.weeks.at(-1)?.week ?? 17) ? 'Saison beendet, keine Restwoche' : 'keine Projektion für den Rest der Saison';
  const notInWeek = `nicht in den Daten nach W${S.tw}`;
  const rosWhy = x => inWeek.has(x.id) ? rosWhyBase : notInWeek;
  // why: Text oder Funktion der Zeile (Grund für „–“)
  const num = (k, l, f = U.num, why) => ({k, l, num: 1, v: x => x[k], f: x => U.val(x[k], f, typeof why === 'function' ? why(x) : why)});
  // Wetter-Fähnchen als eigener Link nach #wetter neben dem Spielerlink (kein Link im Link)
  const spieler = {k: 'name', l: 'Spieler', v: x => x.name.toLowerCase(), d: 1, flt: false, f: x => {
    const a = h('a', {href: '#spieler/' + x.id, class: 'pl'},
      h('span', null, x.name, U.inj(x.inj)), h('span', {class: 'sub'}, `${x.pos ?? '–'} · ${x.nfl ?? '–'} · ${x.team > 0 ? U.kz(x.team) : x.status === 'FREEAGENT' ? 'FA' : 'Waivers'}`
        + (played(W, x) ? ` · W${W.woche} gespielt` : '')));
    const fl = wflag?.(x.nfl);
    return fl ? h('span', {class: 'plw'}, a, fl) : a;
  }};
  // Matchup (players.json mu, Wochenstand): Spalte „Gegner Wn“ = Gegner in Woche mu_woche mit dem Faktor als Farbzelle wie
  // unter Matchups, Bye grau
  const hasMu = 'mu_woche' in P, week = inWeek;
  const muWhy = x => !hasMu ? 'ab dem nächsten Wochenabruf' : x.mu ? 'keine offene Woche' : !x.nfl ? 'kein NFL-Team'
    : week.has(x.id) ? 'kein Matchup-Wert für diese Position' : notInWeek;
  const mu = {k: 'mu', l: U.ok(P.mu_woche) ? `Gegner W${P.mu_woche}` : 'Gegner', num: 1, v: x => x.mu?.n1?.opp ? x.mu.n1.f ?? null : null,
    cls: x => x.mu?.n1 ? (x.mu.n1.opp ? fz(x.mu.n1.f) : 'fz bye') : 'fz',
    f: x => {
      const n = x.mu?.n1;
      if (!n) return U.na(muWhy(x));
      return n.opp ? [n.opp, h('small', null, U.val(n.f, v => U.num(v, 2), 'kein Faktor'))] : ['Bye', h('small', null, '·')];
    }};
  const mu3 = {k: 'mu3', l: 'Faktor nächste 3', num: 1, v: x => x.mu?.naechste3 ?? null, cls: x => fz(x.mu?.naechste3),
    f: x => U.val(x.mu?.naechste3, v => U.num(v, 2), x.mu ? 'kein Spiel in den nächsten 3 Wochen' : muWhy(x))};
  const bye = {k: 'bye', l: 'Bye', num: 1, cat: 1, v: x => x.bye, d: 1, f: x => !U.ok(x.bye) ? U.na(x.nfl && !inWeek.has(x.id) ? notInWeek : 'kein NFL-Team')
    : x.bye === W.woche ? h('span', {class: 'dn'}, 'W' + x.bye, h('span', {class: 'vh'}, ' – nächste Woche spielfrei')) : 'W' + x.bye};
  const verl = {k: 'inj', l: 'Verletzung', v: x => U.INJ[x.inj] ? x.inj : null, d: 1, f: x => U.INJ[x.inj]?.[1] || (x.inj === 'ACTIVE' ? 'aktiv' : '–')};
  const frist = {k: 'frist', l: 'Frist', v: x => x.status === 'WAIVERS' ? x.waiver_bis : null, d: 1,
    f: x => x.status === 'WAIVERS' ? U.val(x.waiver_bis, U.stamp, 'keine Frist gemeldet') : U.na(x.team > 0 ? 'im Kader' : 'Free Agent, sofort')};
  // Ränge (06.10.2026): je Horizont der Platz innerhalb der Position über alle Spieler des Wochenpools, Kader und frei
  // zusammen, mit dem Rang über alle Positionen klein darunter; dazu Saison (nach Punkten), Rest je Spiel und ESPNs eigener
  // Saison-Rang in Ausführlich. why: Text oder Funktion der Zeile (Grund für „–“)
  const rank = (k, l, kg, why) => ({k, l, num: 1, d: 1, v: x => x[k] ?? null,
    f: x => U.val(x[k], v => U.rang(x.pos, v, x[kg]), typeof why === 'function' ? why(x) : why)});
  const rangW = rank('rang_woche', `Rang W${W.woche}`, 'rang_woche_ges', x => played(W, x) ? 'Spiel der Woche schon angepfiffen'
    : x.bye === W.woche ? 'Bye' : 'kein Wochenwert (Ausfall oder keine Projektion)');
  const rang3 = rank('rang_3', `Rang ${span(W)}`, 'rang_3_ges', 'keine Projektion der Folgewochen');
  const rangRos = rank('ros_rang', 'Rang Rest je Spiel', 'ros_rang_ges', rosWhy);
  const rangSaison = rank('saison_rang', 'Rang Saison', 'saison_rang_ges', x => inWeek.has(x.id) ? 'ohne Spiel' : notInWeek);
  const rangEspn = rank('espn_rang', 'ESPN-Rang', 'espn_rang_ges', x => inWeek.has(x.id) ? 'kein ESPN-Rang' : notInWeek);
  const wertRang = {k: 'wert_rang', l: 'Marktwert-Rang', num: 1, d: 1, v: x => x.wert_rang,
    f: x => U.val(x.wert_rang, v => h('span', {class: 'rg'}, String(v), h('small', null, `${x.pos} ${x.wert_posrang}`)), 'kein Marktwert')};
  // Spalte „Gewinn für <Kürzel>“ = Zugewinn für das Bezugsteam (waiver.json spieler[].zug, Python): brutto, netto nur, wenn
  // ein Drop etwas kostet
  const gain = x => x.zug?.[st.hor]?.[String(me.mine)] ?? null;
  const lost = x => (st.hor === 'woche' || st.hor === 'drei') && played(W, x);
  const zugCol = () => ({k: 'zug', l: `Gewinn für ${U.kz(me.mine)}`, num: 1, v: x => lost(x) ? null : gain(x)?.b ?? null,
    f: x => {
      const z = gain(x);
      if (x.team > 0) return U.na(x.team === me.mine ? 'eigener Spieler' : 'im Kader von ' + U.kz(x.team));   // Zugewinn nur für freie Spieler
      if (lost(x)) return U.na('Spiel der Woche schon angepfiffen');
      if (!z) return U.na('verbessert die beste Aufstellung nicht');
      return z.n !== z.b ? [U.sgn(z.b), h('small', null, `netto ${U.sgn(z.n)}`)] : U.sgn(z.b);
    }});
  // Woche N+1: wer schon gespielt hat, bringt in dieser Woche nichts mehr – ohne Sortierwert ans Ende
  const weekWhy = x => x.pos === 'D/ST' || !U.ok(x.pos) ? 'kein freier Spieler der Position' : 'noch keine ESPN-Projektion';
  const projUe = {k: 'proj_ue', l: `Vorteil W${W.woche}`, num: 1, v: x => played(W, x) ? null : x.proj_ue,
    f: x => played(W, x) ? U.na('Spiel der Woche schon angepfiffen') : U.val(x.proj_ue, U.sgn, weekWhy(x))};
  const proj = num('proj', `Projektion W${W.woche}`, U.num, 'noch keine ESPN-Projektion');
  // Langfristig: Marktwert (FantasyCalc), Abstand zur Keeper-Linie, Gesamtrang mit Positionsrang, Trend 30 Tage, Alter
  const zukunft = hasWert ? [spieler, num('wert', 'Marktwert', kp.wertTxt), num('wert_ue', 'über Keeper-Linie', kp.wertSgn, 'keine Keeper-Linie'),
    wertRang, num('wert_trend', 'Trend 30 Tage', kp.wertSgn), {...num('alter', 'Alter', v => U.num(v, 1), 'nicht in den Stammdaten'), d: 1}] : [];
  // Einfach / Ausführlich (App-Konzept Abschnitt 8, Paket P5; ersetzt die Spalten-Sichten „Alle · Projektionen · Besitz“): X = nur
  // „Ausführlich“. Einfach je Horizont: Spieler, Gewinn für Mein Team, Vorteil, Projektion bzw. Rest je Spiel, Gegner, Bye, Verletzung;
  // Langfristig: die Marktwert-Spalten
  const X = col => ({...col, x: 1});
  // Nächste 3 Wochen: „Projektion W5–7“ = Summe der Projektionen N+1…N+3, „Vorteil W5–7“ = dieselbe Summe über dem Ersatzniveau
  const base = {
    woche: [spieler, projUe, proj, rangW],
    drei: [spieler, num('proj3_ue', `Vorteil ${span(W)}`, U.sgn, 'keine Projektion der Folgewochen'),
      num('proj3', `Projektion ${span(W)}`, U.num, 'keine Projektion der Folgewochen'), rang3, X(proj)],
    ros: [spieler, num('ros_ue', 'Vorteil Rest Saison', U.sgn, rosWhy), rangRos, X(proj)],
    zukunft};
  const SORT = {woche: 'proj_ue', drei: 'proj3_ue', ros: 'ros_ue', zukunft: 'wert'};
  const WER = {frei: 'Freie Spieler', alle: 'Alle Spieler', kader: 'Kaderspieler'};
  const CAP = () => ({woche: `${WER[st.status]} nach Vorteil W${W.woche}`, drei: `${WER[st.status]} nach Vorteil ${span(W)}`,
    ros: `${WER[st.status]} nach Vorteil Rest der Saison`, zukunft: `${WER[st.status]} nach Marktwert`})[st.hor];
  const rosG = num('ros_g', 'Rest je Spiel', U.num, rosWhy);
  const besitz = [num('own', 'Besitz %', v => U.pct(v)), num('own_d', 'seit gestern', v => U.sgn(v, 2)), num('started', 'aufgestellt %', v => U.pct(v))];
  // Spalten hinter dem Horizont; im Horizont „Rest der Saison“ ist Rest je Spiel einfach sichtbar, unter Langfristig alles ausführlich.
  // Gegner und Faktor nächste 3 fehlen dienstags vor dem Wochenabruf (zw) in allen Horizonten: Sie gälten noch für die gespielte
  // Woche („Gegner W4“ neben „Projektion W5“, der Faktor zählt W4 mit)
  // Ränge der anderen Horizonte, Saison und ESPN immer ausführlich; der Rang des eigenen Horizonts steht einfach in base
  const raenge = hor => [...(hasWeek && hor !== 'woche' ? [rangW] : []), ...(hasWeek && hor !== 'drei' ? [rang3] : []),
    ...(hor !== 'ros' ? [rangRos] : []), rangSaison, rangEspn, ...(hasWert && hor !== 'zukunft' ? [wertRang] : [])].map(X);
  const extra = hor => hor === 'zukunft' ? [...(zw ? [] : [mu, mu3]), bye, verl, rosG, ...raenge(hor), ...besitz, frist].map(X)
    : [...(zw ? [] : [mu, X(mu3)]), bye, verl, hor === 'ros' ? rosG : X(rosG), ...raenge(hor), ...besitz.map(X), X(frist)];
  const count = h('p', {class: 'note', 'aria-live': 'polite'});
  const slot = h('div');
  const fst = {}, filters = [{k: 'nfl', l: 'NFL-Team', v: x => x.nfl, d: 1, cat: 1, f: x => x.nfl},
    {k: 'status', l: 'Status', v: x => x.status, d: 1, cat: 1, f: x => U.STAT[x.status] || x.status}];
  let tbl;
  const build = () => {
    // „Gewinn für <Mein Team>“ nur in den Punkte-Horizonten; Langfristig (Marktwert) hat keinen Zugewinn
    const zug = me.mine && st.hor !== 'zukunft' ? [zugCol()] : [];
    tbl = U.table({cap: CAP(), cls: 'nr', rh: 0, rows: rowsNow(), sort: [SORT[st.hor], -1], limit: 50, filter: true,
      filters, fstate: fst, cols: [base[st.hor][0], ...zug, ...base[st.hor].slice(1), ...extra(st.hor)],
      rc: x => lost(x) ? 'gsp' : null,
      note: 'Frei = Waivers oder Free Agent laut Tageslauf.' + (st.status !== 'frei' ? ' Kaderspieler tragen ihr Team in der Unterzeile; Gewinn und Frist gibt es nur für freie Spieler.' : '')
        + (st.hor === 'zukunft' ? ' Nur Spieler mit Marktwert (K und D/ST haben keinen).' : '') + ' Ränge zählen über alle Spieler des Wochenpools, Kader und frei zusammen.'});
    slot.replaceChildren(tbl);
  };
  const refresh = rebuild => {
    if (rebuild) build(); else tbl.upd(rowsNow());
    count.textContent = `${rowsNow().length} ${st.status === 'frei' ? 'freie Spieler' : st.status === 'kader' ? 'Kaderspieler' : 'Spieler'}`;
    U.setQ(r.base, {team: me.q || null, pos: st.pos || null, h: st.hor !== (hasWeek ? 'woche' : 'ros') ? st.hor : null,
      status: st.status !== 'frei' ? st.status : null});
    ersNote.replaceChildren(); U.ap(ersNote, ersText());
  };
  let timer;
  // Ersatzniveau passend zum Horizont, benannt wie die Spalten: Projektion W(N+1), Projektion W(N+1)–(N+3) (Summe) oder Rest
  // je Spiel; bei Langfristig (Marktwert) die Keeper-Linie mit Quelle
  const ersText = () => {
    if (st.hor === 'zukunft') return ['Keeper-Linie ', U.val(W.keeper_linie, kp.wertTxt, 'zu wenige Kaderspieler mit Wert'), ' ', U.ib('keeper-linie', ''),
      ' · ', kp.fcQuelle(), `, ${U.standTxt(W.wert_stand)} · `, kp.fcRechner()];
    const [lbl, ers, gid] = {woche: [`Projektion W${W.woche}`, W.ersatz_woche, 'proj-ue'], drei: [`Projektion ${span(W)}`, W.ersatz_3, 'proj3'],
      ros: ['Rest je Spiel', P.ersatz, 'ersatz']}[st.hor];
    return [`Ersatzniveau (${lbl}): `, POS.map((p, i) => [i ? ' · ' : '', `${p} ${U.ok(ers?.[p]) ? U.num(ers[p]) : '–'}`]),
      ' ', U.ib(gid, '')];
  };
  const ersNote = h('p', {class: 'note'});
  const HLABEL = {woche: `Nächste Woche (W${W.woche})`, drei: 'Nächste 3 Wochen', ros: 'Rest der Saison', zukunft: 'Langfristig (Marktwert)'};
  const horSeg = hors.length > 1 ? U.seg('Horizont', hors.map(x => [x, HLABEL[x]]), st.hor,
    v => { st.hor = v; refresh(true); }) : null;
  U.ap(box,
    horSeg && h('div', {class: 'row'}, horSeg, U.ib('horizont', '')),
    ersNote,
    h('div', {class: 'row'}, U.seg('Position', [['', 'Alle'], ...POS.map(p => [p, p])], st.pos, v => { st.pos = v; refresh(); })),
    // Überschrift und Zähler nennen den Status, deshalb neu bauen
    h('div', {class: 'row'}, U.seg('Status', [['frei', 'Frei'], ['alle', 'Alle'], ['kader', 'Kader']], st.status, v => { st.status = v; refresh(true); }),
      U.ib('markt-status', '')),
    h('div', {class: 'row'}, h('label', null, h('span', {class: 'vh'}, 'Spieler suchen'),
      h('input', {type: 'search', placeholder: 'Name suchen', oninput: e => {
        clearTimeout(timer);
        timer = setTimeout(() => { st.text = e.target.value.trim().toLowerCase(); refresh(); }, 150);
      }}))),
    count, slot,
    U.legend(['verfuegbar', 'markt-status', 'horizont', 'zugewinn', 'proj-ue', 'proj3', 'gespielt', 'ros-ue', 'ersatz', 'ros-spiel', 'proj-naechste',
      'rang-woche', 'rang-3', 'ros-rang', 'rang-saison', 'espn-rang',
      ...(zw ? [] : ['mu-n1', 'mu-naechste3']), 'bye-hinweis', 'besitz-trend', 'frist',
      'wetter-markierung', ...(hasWert ? ['marktwert', 'keeper-linie', 'wert-ue', 'wert-trend'] : []), 'filter', 'projektionen']));
  refresh(true);
  return {rebuild: () => refresh(true)};
}

// ---------------------------------------------------------------- Bedarf je Team
// sicht 'woche' („Nächste Woche (Wn)“): Lücken der Woche N+1 mit Grund und freien Kandidaten, Ausfälle der ROS-Aufstellung,
// Byes N+2…N+3; 'ros' („Rest der Saison“): Lücken der ROS-optimalen Aufstellung (Regular Season)
function needs(W, P, name, mine, sicht, onSicht, rowById) {
  const card = U.card(null);            // Überschrift ist die Ansicht (Markt › Bedarf je Team)
  if (W.bedarf_woche) U.ap(card, h('div', {class: 'row'}, U.seg('Bedarf', [['woche', `Nächste Woche (W${W.woche})`], ['ros', 'Rest der Saison']], sicht, onSicht)));
  const teams = key => [...S.teams].sort((a, b) => (b.team_id === mine) - (a.team_id === mine) || a.rang - b.rang)
    .map(t => ({t, b: W[key]?.[String(t.team_id)]}));
  const rc = x => x.t.team_id === mine ? 'me' : null;
  const link = id => h('a', {href: '#spieler/' + id}, name(id));
  // Team mit Schwächen laut Profil (waiver.json profil) als Unterzeile, in beiden Sichten
  const teamCell = x => [U.tl(x.t.team_id), weakSub(W, x.t.team_id)];
  if (sicht === 'woche' && W.bedarf_woche) {
    const byId = rowById;
    const cand = all => { const ids = all.filter(id => !played(W, byId.get(id) || {})); return ids.length ? [' → ', ids.map((id, i) => [i ? ', ' : '', link(id), ` ${U.num(byId.get(id)?.proj)}`])] : ' → kein freier Spieler mit mehr'; };
    const gap = g => [`${g.slot}: `, g.id == null ? 'unbesetzt' : [link(g.id), U.inj(byId.get(g.id)?.inj),
      ` ${U.num(g.proj)}` + (g.grund ? ` (${GRUND[g.grund] || g.grund})` : '')], cand(g.kandidaten)];
    const miss = a => [link(a.id), ` ${a.slot}: ${GRUND[a.grund] || a.grund}`];
    const bye = b => [`W${b.woche} `, link(b.id), ` (${b.slot})`];
    const list = (arr, f, none) => arr.length ? arr.map((x, i) => [i ? h('br') : '', f(x)]) : h('span', {class: 'note'}, none);
    U.ap(card, U.table({cap: `Lücken der besten Aufstellung für W${W.woche}`, cls: 'nr', rh: 0, rows: teams('bedarf_woche'), sortable: false, rc, cols: [
      {k: 't', l: 'Team', f: teamCell},
      {k: 'n', l: 'Lücken', num: 1, f: x => x.b ? (x.b.luecken.length || h('span', {class: 'note'}, 'keine')) : '–'},
      {k: 'l', l: `Lücken W${W.woche} und Kandidaten`, cls: 'wrap', f: x => x.b ? list(x.b.luecken, gap, '–') : '–'},
      {k: 'a', l: 'Ausfälle und fraglich', cls: 'wrap', f: x => x.b ? list(x.b.ausfaelle, miss, '–') : '–'},
      {k: 'y', l: `Byes ${W.horizont?.length > 1 ? `W${W.horizont[1]}–${W.horizont.at(-1)}` : ''}`, cls: 'wrap', f: x => x.b ? list(x.b.byes, bye, '–') : '–'}]}),
    U.legend(['bedarf-woche', 'proj-ue', 'gespielt', 'profil']));
    return card;
  }
  if (!W.bedarf) {
    U.ap(card, h('p', {class: 'note'}, P.ros_nach_woche == null ? `Bedarf ab der ersten Projektion für den Rest der Saison (Wochenabruf W${S.tw + 1}).` : 'Nach W17 gibt es keinen Bedarf mehr.'));
    return card;
  }
  const po = W.bedarf_basis === 'playoffs';   // nach W14: ROS Playoffs/Spiel W15–17 mit dem Ersatzniveau der Playoffs
  const ers = W.bedarf_ersatz || P.ersatz || {};
  const gap = g => g.id == null ? `${g.slot}: unbesetzt`
    : [`${g.slot}: `, link(g.id), ` ${U.num(g.ros_g)}` + (U.ok(ers[g.pos]) ? ` (Ersatz ${U.num(ers[g.pos])})` : '')];
  U.ap(card, U.table({cap: po ? 'Lücken der besten Aufstellung für W15–17' : 'Lücken der besten Aufstellung für den Rest der Saison', cls: 'nr', rh: 0,
    rows: teams('bedarf'), sortable: false, rc, cols: [
    {k: 't', l: 'Team', f: teamCell},
    {k: 'n', l: 'Lücken', num: 1, f: x => x.b ? (x.b.luecken.length || h('span', {class: 'note'}, 'keine')) : '–'},
    {k: 'l', l: 'Starter unter Ersatzniveau', cls: 'wrap', f: x => x.b ? x.b.luecken.map((g, i) => [i ? h('br') : '', gap(g)]) : '–'},
    {k: 'u', l: 'Tiefe je Position', cls: 'wrap', f: x => x.b ? POS.map((p, i) => [i ? ' · ' : '', `${p} ${x.b.ueber_ersatz[p] ?? '–'}`]) : '–'}]}),
  U.legend(['bedarf', 'ersatz', 'profil']));
  return card;
}

// Schwächen eines Teams laut Profil als Unterzeile („schwach: WR · RB“); leer ohne Profil oder ohne Schwäche
const PROF_NAME = {QB: 'QB+OP'};
const weakText = (W, tid) => (W.profil?.[String(tid)]?.schwach || []).map(g => PROF_NAME[g] || g).join(' · ');
const weakSub = (W, tid) => weakText(W, tid) ? h('span', {class: 'sub'}, 'schwach: ' + weakText(W, tid)) : null;

// ---------------------------------------------------------------- Waiver-Reihenfolge
function order(W, mine) {
  const card = U.card('Waiver-Reihenfolge');
  const list = W.reihenfolge || [];
  if (!list.length) { U.ap(card, h('p', {class: 'note'}, 'Noch keine Reihenfolge gemeldet.')); return card; }
  const src = W.reihenfolge_quelle === 'tageslauf' ? U.standTxt(W.reihenfolge_stand || W.stand)
    : `Stand des Wochenabrufs (nach W${S.tw}); die aktuelle Reihenfolge kommt mit dem nächsten Tageslauf`;
  U.ap(card, U.table({cap: 'Reihenfolge der Claims', cls: 'nr', rh: 1, rows: list.map((tid, i) => ({i: i + 1, tid})), sortable: false,
    rc: x => x.tid === mine ? 'me' : null, cols: [
      {k: 'p', l: 'Platz', num: 1, f: x => x.i + '.'},
      {k: 't', l: 'Team', f: x => U.tl(x.tid)},
      ...(W.profil ? [{k: 's', l: 'Schwächen', cls: 'wrap', f: x => weakText(W, x.tid) || '–'}] : [])]}),
  h('p', {class: 'note'}, src, '. ESPN verarbeitet Waiver um 07:00 UTC; in der ESPN-App sind die Ergebnisse erfahrungsgemäß erst 10:30–11:00 Uhr sichtbar. Die Reihenfolge rollt: Wer erfolgreich claimt, rückt ans Ende. ', U.ib('waiver-reihenfolge', '')));
  return card;
}

// ---------------------------------------------------------------- Claims der letzten 7 Tage
function claims(box, T, name) {
  U.ap(box, h('h2', null, 'Claims der letzten 7 Tage'));
  if (!T) { U.ap(box, h('p', {class: 'note'}, 'Transaktionen konnten nicht geladen werden. ', h('a', {href: '#markt/moves'}, 'Zu den Moves'))); return; }
  const since = Date.now() - DAYS7;
  const items = (T.items || []).filter(x => ART[x.type] && U.ok(x.datum) && x.datum >= since);
  const part = (x, kind) => (x.items || []).filter(i => i.type === kind);
  // Spieler ohne Seite in der App (in_app false, z. B. gedroppt ohne Einsatz) nur als Name, wie unter Moves
  const pl = list => list.length ? list.map((i, k) => {
    const txt = i.name || name(i.player_id);
    return [k ? ', ' : '', i.in_app === false ? h('span', null, txt) : h('a', {href: '#spieler/' + i.player_id}, txt)];
  }) : '–';
  if (!items.length) { U.ap(box, h('p', {class: 'note'}, 'Keine ausgeführten Claims oder Free-Agent-Zugänge in den letzten 7 Tagen. ', h('a', {href: '#markt/moves'}, 'Alle Moves'))); return; }
  U.ap(box, U.table({cap: 'Ausgeführte Waiver-Claims und Free-Agent-Zugänge (neueste zuerst)', cls: 'nr', rh: 1, limit: 50, rows: items, sort: ['d', -1], cols: [
    {k: 'd', l: 'Datum', v: x => x.datum, f: x => U.stamp(x.datum)},
    {k: 't', l: 'Team', v: x => U.kz(x.team_id), d: 1, f: x => U.tl(x.team_id)},
    {k: 'a', l: 'Art', v: x => x.type, d: 1, f: x => ART[x.type] || x.type},
    {k: 'z', l: 'Zugang', f: x => pl(part(x, 'ADD'))},
    {k: 'b', l: 'Abgang', f: x => pl(part(x, 'DROP'))}]}),
  h('p', {class: 'note'}, h('a', {href: '#markt/moves'}, 'Alle Moves'), ' · ', h('a', {href: '#keeper/draft'}, `Keeper › Draft ${S.man.season}`), ' ', U.ib('claims', '')));
}
