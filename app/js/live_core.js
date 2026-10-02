// Live-Ansicht (#spieltag), Rechenkern: reine Funktionen ohne DOM und ohne Netz. Aus den ESPN-Antworten des Browsers
// (Liga mit vier Views, NFL-Scoreboard, bei Bedarf kona_player_info) und einem Auszug der App-Daten entsteht ein
// Ergebnisobjekt: Kopf, NFL-Spiele nach Status, Matchups, Aufstellungen, Bewegungen, Kadervergleich.
// Vorlage ist scripts/claude_stand.py (Stand-Skript für den Chat) – dieselben Regeln für Starterzahlen, Bye, „ohne
// Team“, verschobene Spiele, Bank-Hinweis und Bewegungen. Die Gegenprobe mit node gegen dessen Ausgabe liegt nicht im
// Repo: Wer diese Datei oder das Skript ändert, wiederholt sie von Hand (docs/app_daten.md, Abschnitt Live-Ansicht).
// Mit Absicht anders als das Skript (öffentliche App): keine gescheiterten Claims und keine sonstigen Einträge
// (Glossar „Transaktionen“), Aufstellungswechsel gezählt wie im Moves-Tab (records.lineup_changes), und ein
// unlesbares Scoreboard-Spiel macht seine Teams nicht still zu „Bye“ (Status „unklar“).
// Positivliste: Gelesen werden nur die unten genannten Ligafelder. Angaben zu Managern und ESPN-Redaktionstexte,
// die ESPN in denselben Antworten mitschickt, fasst dieses Modul nicht an; das Ergebnis enthält sie nicht.
// Zahlen bleiben ungerundet (ESPN-Werte), gerundet wird erst bei der Anzeige mit runden() (round half up).
// Saisonwechsel: LIGA_ID muss zu scripts/espn_fetch.py passen (tests/test_live_ansicht.py vergleicht).
export const LIGA_ID = 1166555857;
export const LIGA_VIEWS = ['mMatchupScore', 'mRoster', 'mTeam', 'mTransactions2'];   // ohne scoringPeriodId: laufende Periode
export const KONA_VIEW = 'kona_player_info';
export const ligaUrl = saison => `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${saison}/segments/0/leagues/${LIGA_ID}`;
export const SCOREBOARD_URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard';

export const SLOT = {0: 'QB', 2: 'RB', 4: 'WR', 6: 'TE', 23: 'FLEX', 7: 'OP', 16: 'D/ST', 17: 'K', 20: 'Bank', 21: 'IR'};
export const STARTER_SLOTS = [0, 2, 4, 6, 23, 7, 16, 17];      // Reihenfolge der Anzeige
export const STARTER_ZAHL = 13;                                // QB, 2 RB, 3 WR, TE, 2 FLEX, OP, 2 D/ST, K
const SLOT_BANK = 20, SLOT_IR = 21;
const POS = {1: 'QB', 2: 'RB', 3: 'WR', 4: 'TE', 5: 'K', 16: 'D/ST'};
const NFL = {0: 'FA', 1: 'ATL', 2: 'BUF', 3: 'CHI', 4: 'CIN', 5: 'CLE', 6: 'DAL', 7: 'DEN', 8: 'DET', 9: 'GB', 10: 'TEN',
  11: 'IND', 12: 'KC', 13: 'LV', 14: 'LAR', 15: 'MIA', 16: 'MIN', 17: 'NE', 18: 'NO', 19: 'NYG', 20: 'NYJ',
  21: 'PHI', 22: 'ARI', 23: 'PIT', 24: 'LAC', 25: 'SF', 26: 'SEA', 27: 'TB', 28: 'WSH', 29: 'CAR', 30: 'JAX',
  33: 'BAL', 34: 'HOU'};
const KEIN_STATUS = ['ACTIVE', 'NORMAL'];
const MOVE_TYPEN = ['WAIVER', 'FREEAGENT', 'ROSTER', 'FUTURE_ROSTER'];
const LINEUP_TYPEN = ['ROSTER', 'FUTURE_ROSTER'];
const SPIELER_ITEMS = ['ADD', 'DROP'];
// Spielstatus eines Spielers: pre/in/post (Scoreboard), verschoben (laut ESPN beendet, aber ohne Ergebnis), bye und
// ohne (kein NFL-Team); ohne Scoreboard zu/auf (lineupLocked). OFFEN: Der Slot ist noch nicht gesperrt.
// Dazu unklar: Das Scoreboard führt ein Spiel, das sich nicht lesen lässt, und das Team des Spielers steht weder in
// einem lesbaren Spiel noch in ESPNs Bye-Liste – dann lieber „Status ?“ als ein stilles „Bye“ (zählt weder als offen
// noch als spielfrei).
export const OFFEN = ['pre', 'bye', 'ohne', 'auf', 'verschoben'];
export const SPIELFREI = ['bye', 'ohne'];      // zählt 0; ESPN projiziert D/ST auch in ihrer Bye-Woche
export const SAMMEL_AB = 3;                    // zeigen mehr Bankspieler auf denselben Starter: eine Sammelzeile
const TEXT_MAX = 40;                           // Zeichen je Fremdtext (Spielername, Scoreboard-Detail)

// ---------------------------------------------------------------- Zahlen, Zeit, Fremdtext
// Zahl × 10^hoch auf feste Stellen, round half up an der Dezimaldarstellung (wie Decimal(str(x)) in Python): 0,285 als
// Prozent wird 29, nicht 28 wie bei 0.285 * 100 in Gleitkomma. null/undefined/NaN → null.
export function runden(wert, stellen = 2, hoch = 0) {
  if (wert == null || wert === '' || !isFinite(wert)) return null;
  const s = String(+wert);
  if (/e/i.test(s)) return +(+wert * 10 ** hoch).toFixed(stellen);     // sehr kleine oder sehr große Zahlen
  const neg = s[0] === '-';
  let [g, f = ''] = (neg ? s.slice(1) : s).split('.');
  f = f.padEnd(hoch, '0');
  g += f.slice(0, hoch);
  f = f.slice(hoch);
  let ziffern = BigInt(g + f.slice(0, stellen).padEnd(stellen, '0'));
  if (f.length > stellen && f[stellen] >= '5') ziffern += 1n;
  const t = ziffern.toString().padStart(stellen + 1, '0');
  const out = +(stellen ? `${t.slice(0, -stellen)}.${t.slice(-stellen)}` : t);
  return neg && out ? -out : out;
}

// Fremdtext für die Anzeige: eine Zeile (Steuerzeichen, Zeilenumbrüche und Leerraum werden ein Leerzeichen), höchstens
// n Zeichen („…“ am Ende, wenn gekürzt).
export function kurz(text, n = TEXT_MAX) {
  const s = String(text).replace(/[\p{C}\p{Z}]/gu, ' ').split(' ').filter(Boolean).join(' ');
  const z = Array.from(s);
  return z.length <= n ? s : z.slice(0, n - 1).join('').trimEnd() + '…';
}

// Scoreboard-Zeit („2026-10-02T00:15Z“, auch mit Sekunden) → Epoch-ms; Unlesbares → null
export function ausIso(text) {
  const m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)(?::(\d\d))?Z$/.exec(typeof text === 'string' ? text : '');
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) : null;
}

const vgl = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const zaehl = (m, k) => m.set(k, (m.get(k) || 0) + 1);

// ---------------------------------------------------------------- Rohdaten lesen
// null, wenn die Liga-Antwort brauchbar ist; sonst der Grund als Text
export function ligaMangel(liga) {
  if (!liga || typeof liga !== 'object') return 'keine Antwort';
  const fehlt = ['scoringPeriodId', 'teams', 'schedule'].filter(k => !liga[k] || (Array.isArray(liga[k]) && !liga[k].length));
  return fehlt.length ? `Antwort ohne ${fehlt.join(', ')}` : null;
}

// Das Scoreboard zeigt die Regular-Season-Woche der Liga (sonst holt der Abruf sie gezielt nach)
export function scoreboardPasst(sb, woche) {
  return !!sb && sb.week?.number === woche && sb.season?.type === 2;
}

// Scoreboard → {jeTeam: Map proTeamId → Spiel, liste, defekt}. state: pre (offen), in (läuft), post (beendet),
// verschoben (ESPN meldet state „post“, aber completed false – für ein abgesagtes Spiel belegt, für ein verschobenes
// angenommen; solche Spiele bilden eine eigene Gruppe mit ESPNs Detailtext, ihre Starter gelten wie offene als tauschbar).
// defekt = Zahl der Spiele, die sich nicht lesen lassen (keine zwei Seiten, Seite ohne Team oder Team-ID): Sie werden
// übersprungen und gezählt, damit ihre Teams nicht still als „Bye“ erscheinen (siehe Status „unklar“).
export function spieleAus(sb) {
  const jeTeam = new Map(), liste = [];
  const hatTeam = x => x?.team?.id != null && isFinite(+x.team.id);
  let defekt = 0;
  for (const ev of sb?.events || []) {
    const c = (ev?.competitions || [])[0] || {};
    const typ = (c.status || ev?.status || {}).type || {};
    const seiten = {};
    for (const x of c.competitors || []) if (x) seiten[x.homeAway] = x;
    const heim = seiten.home, gast = seiten.away;
    if (!hatTeam(heim) || !hatTeam(gast)) { defekt++; continue; }
    const hk = kurz(heim.team.abbreviation ?? '?', 5), gk = kurz(gast.team.abbreviation ?? '?', 5);
    let state = ['pre', 'in', 'post'].includes(typ.state) ? typ.state : 'pre';
    if (state === 'post' && !typ.completed) state = 'verschoben';
    const zeitOk = 'timeValid' in c ? c.timeValid : true;
    const spiel = {state, detail: kurz(typ.shortDetail || typ.description || ''),
      anstoss: zeitOk ? ausIso(ev.date || c.date) : null, paarung: `${gk}@${hk}`,
      stand: `${kurz(gast.score ?? '?', 4)}:${kurz(heim.score ?? '?', 4)}`};
    liste.push(spiel);
    jeTeam.set(+heim.team.id, {...spiel, gegner: `vs ${gk}`});
    jeTeam.set(+gast.team.id, {...spiel, gegner: `@ ${hk}`});
  }
  return {jeTeam, liste, defekt};
}

// appliedTotal des Wochen-Eintrags (statSplitTypeId 1): quelle 0 = Ist, 1 = Projektion; null ohne Eintrag
export function wochenwert(player, woche, saison, quelle) {
  for (const s of player.stats || []) {
    if (s.scoringPeriodId === woche && s.statSplitTypeId === 1 && s.statSourceId === quelle && s.seasonId === saison) return s.appliedTotal ?? null;
  }
  return null;
}

// Ein Spieler aus playerPoolEntry (mRoster) bzw. einem kona-Eintrag – beide haben dieselbe Form.
// sb = {hatSb, jeTeam, defekt, bye (Kürzel laut ESPNs Bye-Liste)}
function spielerzeile(ppe, woche, saison, sb) {
  const p = ppe.player || {};
  const pro = p.proTeamId;
  // ohne Scoreboard: ESPN sperrt den Slot mit dem Anstoß (lineupLocked); Byes sind dann nicht erkennbar.
  // Team ohne Spiel = Bye – außer das Scoreboard hat ein unlesbares Spiel und ESPNs Bye-Liste nennt das Team nicht
  const state = !sb.hatSb ? (ppe.lineupLocked ? 'zu' : 'auf') : sb.jeTeam.has(pro) ? sb.jeTeam.get(pro).state
    : !pro ? 'ohne' : sb.defekt && !sb.bye.includes(NFL[pro]) ? 'unklar' : 'bye';
  const pid = p.id ?? ppe.id;
  const inj = p.injuryStatus && !KEIN_STATUS.includes(p.injuryStatus) ? kurz(p.injuryStatus, 20) : null;
  return {id: pid, name: kurz(p.fullName || `Spieler ${pid}`), pos: POS[p.defaultPositionId] ?? '?', pro, nfl: NFL[pro] ?? '?', inj,
    ist: wochenwert(p, woche, saison, 0), proj: wochenwert(p, woche, saison, 1), wahl: p.eligibleSlots || [], state,
    slot: null, team: null, status: ppe.status ?? null};
}

// Zeit einer Transaktion wie in der App (transactions.json datum): processDate, sonst proposedDate (Epoch-ms)
export const txZeit = t => t.processDate || t.proposedDate || null;

// Transaktionen der laufenden Periode wie im Moves-Tab der App (scripts/records.py): Moves (ausgeführt, mit Zugang
// oder Abgang), angenommene Trades (ESPN nennt dort keine Spieler) und die Zahl der ausgeführten Aufstellungswechsel
// je Team (ROSTER/FUTURE_ROSTER mit LINEUP-Item, wie records.lineup_changes). Alles andere – gescheiterte und
// zurückgezogene Claims, Trade-Vorschläge – liest dieses Modul nicht aus: Die öffentliche App zeigt es nicht
// (Beschluss Session 4, Glossar „Transaktionen“).
export function bewegungen(liga) {
  const aus = {moves: [], trades: [], lineup: new Map()};
  for (const t of liga.transactions || []) {
    const typ = t.type, status = t.status;
    const arten = new Set((t.items || []).map(i => i.type));
    if (MOVE_TYPEN.includes(typ) && status === 'EXECUTED' && SPIELER_ITEMS.some(a => arten.has(a))) aus.moves.push(t);
    else if (typ === 'TRADE_ACCEPT' && (status == null || status === 'EXECUTED')) aus.trades.push(t);
    if (LINEUP_TYPEN.includes(typ) && status === 'EXECUTED' && arten.has('LINEUP')) zaehl(aus.lineup, t.teamId);
  }
  for (const liste of [aus.moves, aus.trades]) liste.sort((a, b) => (txZeit(a) || 0) - (txZeit(b) || 0) || vgl(String(a.id), String(b.id)));
  return aus;
}

// IDs der Spieler aus Moves, die heute in keinem Kader stehen und die die App nicht benennen kann (bekannt = IDs mit
// Namen in den App-Daten) – nur sie braucht der kona-Abruf
export function unbekannteSpieler(liga, bekannt = []) {
  const weg = new Set((bekannt || []).map(Number));
  for (const t of liga.teams || []) for (const e of t.roster?.entries || []) weg.add(e.playerId);
  const ids = new Set();
  for (const t of bewegungen(liga).moves) for (const i of t.items || []) {
    if (SPIELER_ITEMS.includes(i.type) && i.playerId != null && !weg.has(i.playerId)) ids.add(i.playerId);
  }
  return [...ids].sort((a, b) => a - b);
}

// X-Fantasy-Filter für kona_player_info; ohne sortPercOwned antwortet ESPN mit HTTP 400
export function konaFilter(ids, woche) {
  return {players: {filterIds: {value: [...ids]}, limit: Math.max(50, ids.length),
    sortPercOwned: {sortPriority: 1, sortAsc: false}, filterStatsForCurrentSeasonScoringPeriodId: {value: [woche]}}};
}

// Auszug der App-Daten als Nachschlagetabellen. app = {teams: [{id, kz, name}], spieler: {id: {name, pos, nfl}},
// kader: {team_id: [Spieler-IDs]} oder null (Tagesstand waiver.json), tx: [Transaktions-IDs] oder null
// (transactions.json führt jede ausgeführte Bewegung mit ihrer ESPN-ID)}
function appIndex(app) {
  const a = app || {};
  const teams = new Map((a.teams || []).map(t => [+t.id, t]));
  const spieler = new Map(Object.entries(a.spieler || {}).map(([k, v]) => [+k, v]));
  const kader = a.kader ? new Map(Object.entries(a.kader).map(([k, v]) => [+k, new Set(v)])) : null;
  return {teams, spieler, kader, tx: a.tx ? new Set(a.tx.map(String)) : null};
}

// Laufende Matchup-Periode; in den Playoffs und nach W17 muss sie nicht die Woche (scoringPeriodId) sein
export const periodeVon = liga => liga.status?.currentMatchupPeriod ?? liga.scoringPeriodId;
export const paarungen = liga => (liga.schedule || []).filter(m => m.matchupPeriodId === periodeVon(liga));
const seitenIds = m => ['home', 'away'].map(s => m[s]?.teamId);
export const paarungVon = (liga, tid) => paarungen(liga).find(m => seitenIds(m).includes(tid)) || null;
// Team-ID des Gegners in der laufenden Matchup-Periode; null bei Freilos oder ohne Paarung
export function gegnerVon(liga, tid) {
  const m = paarungVon(liga, tid);
  return m ? seitenIds(m).find(i => i !== tid && i != null) ?? null : null;
}

// Kein laufender Spieltag: 'nach' = ESPN zählt schon über die letzte Woche der Liga hinaus (Saison beendet),
// 'ohne' = keine Paarung in der laufenden Matchup-Periode; sonst null
export function ruheGrund(liga) {
  const ende = liga.status?.finalScoringPeriod;
  if (ende != null && liga.scoringPeriodId > ende) return 'nach';
  return paarungen(liga).length ? null : 'ohne';
}

// Alles, was die Abschnitte brauchen: Woche, Teams, Kürzel, Spiele, Kader je Team, Spieler je ID
function lageAus(liga, scoreboard, kona, app) {
  const woche = liga.scoringPeriodId, saison = liga.seasonId;
  // Scoreboard: passt die Woche nicht oder lässt es sich nicht lesen (sbFehler), gilt gesperrt/offen laut ESPN-Kader
  let sb = {hatSb: false, jeTeam: new Map(), liste: [], defekt: 0, bye: []}, sbFehler = null;
  if (scoreboardPasst(scoreboard, woche)) {
    try {
      sb = {hatSb: true, ...spieleAus(scoreboard), bye: (scoreboard.week?.teamsOnBye || []).map(t => kurz(t?.abbreviation ?? '?', 5))};
    } catch (e) {
      sbFehler = technik(e);
    }
  }
  const teams = new Map(liga.teams.map(t => [t.id, t]));
  const spieler = new Map(), kader = new Map();
  for (const [tid, team] of teams) {
    const zeilen = [];
    for (const e of team.roster?.entries || []) {
      const z = spielerzeile(e.playerPoolEntry || {}, woche, saison, sb);
      z.slot = e.lineupSlotId;
      z.team = tid;
      zeilen.push(z);
      spieler.set(z.id, z);
    }
    kader.set(tid, zeilen);
  }
  for (const eintrag of kona?.players || []) {
    const z = spielerzeile(eintrag, woche, saison, sb);
    z.team = eintrag.onTeamId || null;       // zwischen Liga- und kona-Abruf geholt: dann steht hier das Team
    if (!spieler.has(z.id)) spieler.set(z.id, z);
  }
  const kz = new Map([...teams].map(([tid, t]) => [tid, app.teams.get(tid)?.kz || kurz(t.abbrev || `T${tid}`, 6)]));
  return {woche, saison, liga, teams, hatSb: sb.hatSb, sbFehler, spiele: sb.liste, jeTeam: sb.jeTeam, defekt: sb.defekt, bye: sb.bye,
    kader, spieler, app, kz};
}

// ---------------------------------------------------------------- Abschnitte
// NFL-Spiele der Woche nach Status; offene Spiele je Anstoß (Epoch-ms, null = Zeit offen, zuletzt)
function nflSpiele(L) {
  const von = st => L.spiele.filter(s => s.state === st);
  const offen = new Map();
  for (const s of von('pre')) offen.set(s.anstoss, [...(offen.get(s.anstoss) || []), s.paarung]);
  return {final: von('post').map(s => ({paarung: s.paarung, stand: s.stand})),
    laeuft: von('in').map(s => ({paarung: s.paarung, stand: s.stand, detail: s.detail})),
    offen: [...offen].sort((a, b) => (a[0] == null) - (b[0] == null) || a[0] - b[0]).map(([anstoss, spiele]) => ({anstoss, spiele})),
    offenZahl: von('pre').length,
    verschoben: von('verschoben').map(s => ({paarung: s.paarung, detail: s.detail})), bye: L.bye, defekt: L.defekt};
}

// Starter eines Teams nach Spielstatus: post/in/pre, dazu bye, ohne (kein NFL-Team), verschoben und unklar (Spiel im
// Scoreboard nicht lesbar); ohne Scoreboard zu/auf
function starterzahl(L, tid) {
  const c = {post: 0, in: 0, pre: 0, bye: 0, ohne: 0, verschoben: 0, unklar: 0, zu: 0, auf: 0};
  for (const z of L.kader.get(tid) || []) if (STARTER_SLOTS.includes(z.slot)) c[z.state] = (c[z.state] || 0) + 1;
  return c;
}

// Je Matchup beide Seiten: Punkte live, Live-Projektion, Siegwahrscheinlichkeit (ESPN), Starter nach Spielstatus
function matchups(L, mein) {
  return paarungen(L.liga).map(m => {
    const seiten = ['home', 'away'].map(k => m[k]).filter(Boolean).map(s => {
      const rec = L.teams.get(s.teamId)?.record?.overall || {};
      return {teamId: s.teamId, kz: L.kz.get(s.teamId) ?? String(s.teamId), w: rec.wins ?? 0, l: rec.losses ?? 0, t: rec.ties ?? 0,
        punkte: s.totalPointsLive ?? s.totalPoints ?? null, proj: s.totalProjectedPointsLive ?? null,
        chance: s.winProbability ?? null, starter: starterzahl(L, s.teamId)};
    });
    const sieger = {HOME: m.home, AWAY: m.away}[m.winner];
    return {seiten, freilos: seiten.length === 1, mein: seiten.some(s => s.teamId === mein),
      sieger: sieger ? sieger.teamId ?? null : null, unentschieden: m.winner === 'TIE',
      runde: m.playoffTierType && m.playoffTierType !== 'NONE' ? kurz(m.playoffTierType, 30) : null};   // Playoffs: ESPNs Bezeichnung
  });
}

// Projektion eines Starters, der noch getauscht werden kann; Bye und ohne Team zählen 0
const wert = z => SPIELFREI.includes(z.state) ? 0 : z.proj || 0;

// Eine Zeile der Aufstellung. Ohne Spiel (Bye, ohne NFL-Team) ist proj null: ESPN projiziert D/ST auch in ihrer
// Bye-Woche, die Zahl wäre keine Erwartung (gezählt wird 0).
function zeile(L, z, hinweis) {
  const sp = L.hatSb && !SPIELFREI.includes(z.state) ? L.jeTeam.get(z.pro) : null;
  return {id: z.id, name: z.name, pos: z.pos, nfl: z.nfl, slot: SLOT[z.slot] ?? 'Bank', state: z.state,
    spiel: sp ? {gegner: sp.gegner, detail: sp.detail, anstoss: sp.anstoss} : null,
    ist: z.ist, proj: SPIELFREI.includes(z.state) ? null : z.proj, inj: z.inj, hinweis: hinweis || null};
}

// Starter eines Teams und seine ganze Bank samt IR. Hinweis an einem Bankspieler: mehr Projektion als ein noch
// tauschbarer Starter im passenden Slot (der schwächste davon); zeigen mehr als SAMMEL_AB Bankspieler auf denselben
// Starter, gibt es statt der Einzelhinweise eine Sammelzeile.
function aufstellung(L, tid) {
  const team = L.teams.get(tid);
  const kader = L.kader.get(tid) || [];
  const starter = kader.filter(z => STARTER_SLOTS.includes(z.slot))
    .sort((a, b) => STARTER_SLOTS.indexOf(a.slot) - STARTER_SLOTS.indexOf(b.slot) || (b.proj || 0) - (a.proj || 0) || vgl(a.name, b.name));
  const tauschbar = starter.filter(z => OFFEN.includes(z.state));
  const reserve = kader.filter(z => !STARTER_SLOTS.includes(z.slot))
    .sort((a, b) => (a.slot === SLOT_IR) - (b.slot === SLOT_IR) || (b.proj || 0) - (a.proj || 0) || vgl(a.name, b.name));
  const ziel = new Map();      // Bankspieler-ID → schwächster tauschbarer Starter im passenden Slot mit weniger Projektion
  for (const z of reserve) {
    if (z.slot !== SLOT_BANK || !['pre', 'auf'].includes(z.state) || !z.proj) continue;
    if (z.pos === 'D/ST' && !L.hatSb) continue;      // ohne Scoreboard ist ein Bye nicht erkennbar, ESPN projiziert D/ST aber auch dann
    const schwaecher = tauschbar.filter(s => z.wahl.includes(s.slot) && wert(s) < z.proj);
    if (schwaecher.length) ziel.set(z.id, schwaecher.reduce((a, s) => wert(s) < wert(a) ? s : a));
  }
  const jeStarter = new Map();
  for (const s of ziel.values()) zaehl(jeStarter, s.id);
  const ziel0 = s => ({id: s.id, name: s.name, slot: SLOT[s.slot], state: s.state, wert: wert(s)});
  const m = paarungVon(L.liga, tid);
  return {id: tid, kz: L.kz.get(tid), name: L.app.teams.get(tid)?.name || kurz(team?.name || `Team ${tid}`),
    starter: starter.map(z => zeile(L, z)), besetzt: starter.length, soll: STARTER_ZAHL,
    reserve: reserve.map(z => {
      const s = ziel.get(z.id);
      return zeile(L, z, s && jeStarter.get(s.id) <= SAMMEL_AB ? ziel0(s) : null);
    }),
    sammel: starter.filter(s => jeStarter.get(s.id) > SAMMEL_AB)
      .map(s => ({starter: ziel0(s), spieler: reserve.filter(z => ziel.get(z.id) === s).map(z => ({id: z.id, name: z.name, proj: z.proj}))})),
    gegner: gegnerVon(L.liga, tid), paarung: m ? (seitenIds(m).filter(i => i != null).length > 1 ? 'spiel' : 'freilos') : null};
}

// Bewegter Spieler: Name, Position und NFL-Team – live aus Kader bzw. kona, sonst laut App, sonst nur die ID
function nenn(L, pid) {
  const z = L.spieler.get(pid), a = L.app.spieler.get(pid) || {};
  return z ? {id: pid, name: z.name, pos: z.pos, nfl: z.nfl}
    : {id: pid, name: kurz(a.name || `Spieler ${pid}`), pos: a.pos ? kurz(a.pos, 5) : '?', nfl: a.nfl ? kurz(a.nfl, 5) : '?'};
}

// Bewegungen der laufenden Periode. neu: true = steht noch nicht in der App (keine Transaktion mit dieser ESPN-ID in
// transactions.json), false = steht dort, null = ohne die Datei nicht feststellbar. Aufstellungswechsel nur gezählt.
function bewegungZeilen(L) {
  const b = bewegungen(L.liga), tx = L.app.tx;
  const marke = t => tx ? !tx.has(String(t.id)) : null;
  const zeilen = [];
  for (const t of b.moves) {
    const von = art => (t.items || []).filter(i => i.type === art).map(i => nenn(L, i.playerId));
    zeilen.push({id: t.id, zeit: txZeit(t), teamId: t.teamId, typ: t.type, zu: von('ADD'), ab: von('DROP'), neu: marke(t)});
  }
  for (const t of b.trades) zeilen.push({id: t.id, zeit: txZeit(t), teamId: t.teamId, typ: 'TRADE_ACCEPT', zu: [], ab: [], neu: marke(t)});
  zeilen.sort((x, y) => (x.zeit || 0) - (y.zeit || 0));
  const gezaehlt = m => [...m].sort((x, y) => y[1] - x[1] || vgl(String(x[0]), String(y[0]))).map(([teamId, n]) => ({teamId, n}));
  return {zeilen, marken: !!tx, neu: zeilen.filter(z => z.neu).length, moves: b.moves.length,
    lineup: gezaehlt(b.lineup), lineupSumme: [...b.lineup.values()].reduce((x, y) => x + y, 0)};
}

// Kader live gegen den Tagesstand der App je Team – zeigt auch Trades, zu denen ESPN keine Spieler nennt
function kadervergleich(L) {
  const alt = L.app.kader;
  if (!alt) return {moeglich: false, abweichungen: [], teams: L.kader.size};
  const name = pid => ({id: pid, name: kurz((L.spieler.get(pid) || L.app.spieler.get(pid) || {}).name || `Spieler ${pid}`)});
  const abweichungen = [];
  for (const tid of [...L.kader.keys()].sort((a, b) => a - b)) {
    const live = new Set(L.kader.get(tid).map(z => z.id)), app = alt.get(tid) || new Set();
    const plus = [...live].filter(p => !app.has(p)).sort((a, b) => a - b), minus = [...app].filter(p => !live.has(p)).sort((a, b) => a - b);
    if (plus.length || minus.length) abweichungen.push({teamId: tid, plus: plus.map(name), minus: minus.map(name)});
  }
  return {moeglich: true, abweichungen, teams: L.kader.size};
}

// Fehlertext des Browsers für die Konsole (englisch, je Browser verschieden) – in die Seite kommt nur der deutsche Satz
const technik = e => `${e?.name || 'Fehler'}: ${kurz(e?.message ?? e, 80)}`;
export const FORM = 'unerwartete Form der ESPN-Antwort';

// Ein Abschnitt, der an einer unerwarteten Antwort scheitert, wird {fehler: Text, technik} – der Rest bleibt stehen
function sicher(fn) {
  try { return fn(); } catch (e) { return {fehler: FORM, technik: technik(e)}; }
}

// Das ganze Ergebnis aus den geladenen Antworten (scoreboard/kona null = Ausfall); kein Netz, keine Uhr.
// ein = {liga, scoreboard, kona, app (siehe appIndex), meinTeam}
// → {ok: false, grund, technik} bei unbrauchbarer Liga-Antwort, sonst {ok: true, woche, periode, saison, ruhe, hatSb,
//    sbWoche, sbFehler, nfl, matchups, teams (Aufstellung je team_id), reihenfolge (team_ids in der Reihenfolge der
//    Paarungen), bewegungen, kader, neuer (Bewegungen oder Kader neuer als die App-Daten)}
export function stand(ein) {
  const {liga, scoreboard = null, kona = null, meinTeam = null} = ein;
  const mangel = ligaMangel(liga);
  if (mangel) return {ok: false, grund: mangel};
  let L;
  try {
    L = lageAus(liga, scoreboard, kona, appIndex(ein.app));
  } catch (e) {        // z. B. ESPN ändert die Form von teams oder roster
    return {ok: false, grund: `Antwort nicht auswertbar (${FORM})`, technik: technik(e)};
  }
  const ruhe = sicher(() => ruheGrund(liga));
  const reihenfolge = sicher(() => paarungen(liga).flatMap(seitenIds).filter(i => i != null));
  const bew = sicher(() => bewegungZeilen(L)), kader = sicher(() => kadervergleich(L));
  return {ok: true, woche: L.woche, periode: sicher(() => periodeVon(liga)), saison: L.saison, ruhe: typeof ruhe === 'string' ? ruhe : null,
    hatSb: L.hatSb, sbWoche: scoreboard && !L.hatSb && !L.sbFehler ? scoreboard.week?.number ?? null : null, sbFehler: L.sbFehler,
    nfl: sicher(() => nflSpiele(L)), matchups: sicher(() => matchups(L, meinTeam)),
    teams: Object.fromEntries([...L.teams.keys()].map(tid => [tid, sicher(() => aufstellung(L, tid))])),
    reihenfolge: Array.isArray(reihenfolge) ? reihenfolge : [],
    bewegungen: bew, kader, neuer: (bew.neu || 0) > 0 || (kader.abweichungen || []).length > 0};
}
