// Gemeinsame Bausteine aller Ansichten: DOM-Helfer, Zahlenformate, sortierbare Tabellen, Chips, i-Knöpfe.
// Zahlen kommen fertig gerundet aus dem Rechenwerk; hier wird nur formatiert (Komma, Minus, Prozent).
export const S = {};                 // gemeinsamer Zustand, füllt app.js (Manifest, Teams, Spielplan …)
const D = document;
let uid = 0;
export const id = p => (p || 'u') + (++uid);

export function h(tag, a, ...kids) {
  const e = D.createElement(tag);
  if (a) for (const k in a) {
    const v = a[k];
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  add(e, kids);
  return e;
}
export const ap = (e, ...kids) => add(e, kids);      // wie append, überspringt aber null/false
export function add(e, kids) {
  for (const c of kids) {
    if (c == null || c === false) continue;
    if (Array.isArray(c)) add(e, c); else e.append(c.nodeType ? c : String(c));
  }
  return e;
}

// ---------------------------------------------------------------- Zahlen und Daten
const NF = {};
const nf = d => NF[d] || (NF[d] = new Intl.NumberFormat('de-DE', {minimumFractionDigits: d, maximumFractionDigits: d}));
export const MINUS = '−', NB = ' ';
export const ok = v => v != null && v !== '' && isFinite(v);
export function num(v, d = 2) {
  if (!ok(v)) return '–';
  v = +v;
  if (Math.abs(v) < 0.5 * 10 ** -d) v = 0;          // kein „−0,00“
  return nf(d).format(v).replace('-', MINUS);
}
export const sgn = (v, d = 2) => ok(v) ? (v > 0 && Math.abs(v) >= 0.5 * 10 ** -d ? '+' : '') + num(v, d) : '–';
export const pct = (v, d = 1) => ok(v) ? num(v, d) + NB + '%' : '–';
export const nn = v => ok(v) ? num(v, Number.isInteger(+v) ? 0 : 1) : '–';   // ganze Zahl oder x,5
// Playoff-%: ganzzahlig, Ränder als „< 1 %“ / „> 99 %“ (Eingabe in Prozent)
export const po = v => !ok(v) ? '–' : v < 1 ? '< 1' + NB + '%' : v > 99 ? '> 99' + NB + '%' : num(v, 0) + NB + '%';
// Simulations-Anteile laut Vertrag 0–1; falls die Daten schon Prozent liefern, erkennt S.simFrac das
export const sp = v => ok(v) ? (S.simFrac === false ? +v : v * 100) : null;

const TZ = 'Europe/Berlin';
const DF = new Intl.DateTimeFormat('de-DE', {weekday: 'short', day: '2-digit', month: '2-digit', timeZone: TZ});
const TF = new Intl.DateTimeFormat('de-DE', {hour: '2-digit', minute: '2-digit', timeZone: TZ});
const toDate = x => typeof x === 'number' ? new Date(x) : x instanceof Date ? x : new Date(x + 'T12:00:00Z');
const parts = d => Object.fromEntries(DF.formatToParts(toDate(d)).map(p => [p.type, p.value]));
export function datum(x) { const p = parts(x); return `${p.weekday.replace('.', '')} ${p.day}.${p.month}.`; }
export const zeit = x => TF.format(toDate(x));
// Abrufzeit des Tageslaufs (manifest.datenstand.pool_stand, waiver.stand) „JJJJ-MM-TTThhmmZ“ oder Anstoß (wetter.json)
// „JJJJ-MM-TTThh:mmZ“ → Date; stamp: Date, Epoch-ms oder eine solche Zeit → „Di 29.09. 23:51 Uhr“ (deutsche Zeit)
export const utc = s => typeof s === 'string' && /^\d{4}-\d\d-\d\dT\d\d:?\d\dZ$/.test(s) ? new Date(s.replace(/T(\d\d):?(\d\d)Z$/, 'T$1:$2:00Z')) : null;
export const stamp = x => { const d = x instanceof Date ? x : typeof x === 'number' ? new Date(x) : utc(x); return d && !isNaN(d) ? `${datum(d)} ${zeit(d)} Uhr` : '–'; };
// Stand des Tageslaufs (App-Konzept 04.10.2026, Grundsatz 6): „Stand heute 09:12 Uhr“, am Vortag „Stand gestern 23:51 Uhr“,
// sonst „Stand Di 29.09. 23:51 Uhr“ – Tage nach deutscher Zeit; x wie bei stamp(); ohne Zeit „Stand –“
const TAG = new Intl.DateTimeFormat('en-CA', {timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit'});
export function standTxt(x) {
  const d = x instanceof Date ? x : typeof x === 'number' ? new Date(x) : utc(x);
  if (!d || isNaN(d)) return 'Stand –';
  const tag = TAG.format(d), heute = TAG.format(new Date());
  const [y, m, t] = heute.split('-').map(Number), gestern = new Date(Date.UTC(y, m - 1, t - 1)).toISOString().slice(0, 10);
  return tag === heute ? `Stand heute ${zeit(d)} Uhr` : tag === gestern ? `Stand gestern ${zeit(d)} Uhr` : `Stand ${stamp(d)}`;
}
export function spanne(iso) {       // Woche Di–Mo, z. B. „08.–14.09.“
  const a = parts(iso), b = parts(new Date(toDate(iso).getTime() + 6 * 864e5));
  return a.month === b.month ? `${a.day}.–${b.day}.${b.month}.` : `${a.day}.${a.month}.–${b.day}.${b.month}.`;
}

// ---------------------------------------------------------------- Teams, fehlende Werte
export const team = tid => S.byId.get(+tid);
export const kz = tid => team(tid)?.kuerzel ?? '–';
export function tl(tid, cls) {       // Team-Link: Name, auf dem Handy in schmalen Tabellen das Kürzel
  const t = team(tid);
  if (!t) return tid === 0 ? 'FA' : '–';
  return h('a', {href: '#team/' + t.team_id, class: 'tl2' + (cls ? ' ' + cls : '')},
    h('span', {class: 'tn'}, t.name), h('span', {class: 'tk', 'aria-hidden': 'true'}, t.kuerzel));
}
export const rec = t => `${t.w}-${t.l}` + (S.hasT ? `-${t.t}` : '');
// Verletzung und Status je Spieler (ESPN-Kennungen → Kürzel und Langtext), gemeinsam für Spielerliste und Markt
export const INJ = {QUESTIONABLE: ['Q', 'fraglich'], DOUBTFUL: ['D', 'zweifelhaft'], OUT: ['O', 'fällt aus'], INJURY_RESERVE: ['IR', 'Injured Reserve'],
  SUSPENSION: ['SSPD', 'gesperrt'], DAY_TO_DAY: ['DTD', 'Day-to-Day']};
export const STAT = {ONTEAM: 'Kader', FREEAGENT: 'Free Agent', WAIVERS: 'Waivers'};
export const inj = s => INJ[s] ? [h('span', {class: 'inj', 'aria-hidden': 'true'}, INJ[s][0]), h('span', {class: 'vh'}, ' ' + INJ[s][1])] : null;
let naSet = null;
export function na(reason) {         // „–“ mit Grund: in Tabellen als Fußnote unter der Tabelle, sonst im Text (für Screenreader)
  if (naSet) { if (reason) naSet.add(reason); return h('span', {class: 'na'}, '–'); }
  return h('span', {class: 'na'}, '–', reason ? h('span', {class: 'vh'}, ` (${reason})`) : null);
}
export const val = (v, f, reason) => ok(v) ? f(v) : na(reason);
// Rang innerhalb der Position mit dem Rang über alle Positionen klein darunter („RB 12“, „Gesamt 38“); 1 = bester
export const rang = (pos, r, ges) => h('span', {class: 'rg'}, `${pos ?? '–'} ${r}`, ok(ges) ? h('small', null, `Gesamt ${ges}`) : null);
// NFL-Team laut Tagesstand (Beschluss Stephan 09.10.2026): waiver.json führt nfl_tag nur bei Spielern, deren NFL-Team laut
// Tageslauf ein anderes ist als laut Wochenstand (Trade, Neuverpflichtung, Entlassung; null = jetzt ohne Team). Die Zeile x
// (Wochenstand, players.json) bekommt dann dieses Team, damit Anstoß, Wetter und Anzeige zum aktuellen Team passen; wechsel =
// {von: NFL-Team laut Wochenstand}. Gegner und Faktoren (mu) und der Bye des Wochenstands gälten für das alte Team und
// entfallen bis zum Wochenabruf (Grund: WECHSEL). Ohne nfl_tag bleibt x unverändert. d = Zeile aus waiver.json
export const WECHSEL = 'NFL-Team gewechselt: Gegner, Faktor und Bye ab dem Wochenabruf';
export function nflTag(x, d) {
  if (!d || !('nfl_tag' in d)) return x;
  return Object.assign(x, {wechsel: {von: x.nfl ?? null}, nfl: d.nfl_tag, mu: null, bye: null});
}
// Expertenrang der Woche (Beschluss Stephan 09.10.2026; waiver.json exp und exp_n je Spieler, im Kopf experten_quellen und
// experten_tiefe): {v: „RB 12,5“ (Median der ESPN-Experten) oder „RB >50“ (höchstens die Hälfte führt ihn in ihren Top 50),
// n: „8/8 Experten“} oder {why: Grund für „–“}. gespielt = Spiel der Woche schon angepfiffen (die Experten nehmen den Spieler
// dann aus ihren Listen; exp_n null = zum Stand des Tageslaufs angepfiffen, ohne NFL-Team laut Tagesstand oder nicht in den
// Wochendaten, undefined = nicht im Tagesstand)
export function expRang(x, W, gespielt) {
  const k = W?.experten_quellen, pos = x.pos ?? '–', tiefe = W?.experten_tiefe?.[x.pos];
  const why = gespielt ? 'Spiel der Woche schon angepfiffen' : !W ? 'keine Tagesdaten' : !ok(k) ? 'ab dem nächsten Tageslauf'
    : !k ? `ESPN hat für W${W.woche} noch keine Expertenränge veröffentlicht`
    : x.exp_n === null ? (!x.nfl ? 'kein NFL-Team' : !x.pos ? 'nicht in den Wochendaten' : 'Spiel der Woche schon angepfiffen')
    : x.exp_n === undefined ? 'nicht im Tagesstand' : !x.exp_n ? 'in keiner Expertenliste' + (tiefe ? ` (Top ${tiefe})` : '') : null;
  if (why) return {why};
  const n = `${x.exp_n}/${k} Experten`;
  return ok(x.exp) ? {v: `${pos} ${num(x.exp, x.exp % 1 ? 1 : 0)}`, n} : {v: `${pos} >${tiefe ?? '?'}`, n};
}
// FantasyPros-Wochenranglisten je Position, dazu Superflex (nur Verweise, keine Werte; Beschluss Stephan 09.10.2026). Alle am
// 09.10.2026 im Browser am Seitentitel „Week 5 … Rankings“ geprüft – FantasyPros beantwortet falsche Adressen mit HTTP 200
export const FP_RANG = {QB: 'qb', RB: 'ppr-rb', WR: 'ppr-wr', TE: 'ppr-te', K: 'k', 'D/ST': 'dst', Superflex: 'ppr-superflex'};
export const fpRangUrl = key => FP_RANG[key] ? `https://www.fantasypros.com/nfl/rankings/${FP_RANG[key]}.php` : null;

// ---------------------------------------------------------------- Speicher (nur Komfort, darf fehlen)
export const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ohne Speicher gilt der Standard */ } },
};

// ---------------------------------------------------------------- Mein Team (App-Konzept 04.10.2026, Abschnitt 6)
// Einmal im Kopf gewählt, gilt überall: Browser-Speicher 'bwg-team' (nur die Team-Nummer, kein Login), 0 = keins.
// setMeinTeam meldet den Wechsel als Ereignis 'bwg-team' am document (der Kopf zeigt dann das neue Kürzel).
// Ohne Browser-Speicher (Privatmodus, Website-Daten gesperrt) gilt die Wahl bis zum Neuladen, wie bei Hell/Dunkel.
const TEAM_KEY = 'bwg-team';
let teamMem = 0;
export const meinTeam = () => { const v = +(store.get(TEAM_KEY) ?? teamMem) || 0; return S.byId?.has(v) ? v : 0; };
export function setMeinTeam(tid) {
  teamMem = S.byId?.has(+tid) ? +tid : 0;
  store.set(TEAM_KEY, teamMem);
  D.dispatchEvent(new CustomEvent('bwg-team'));
}
// ---------------------------------------------------------------- Einfach / Ausführlich (App-Konzept Abschnitt 8, Paket P5)
// Eine Einstellung für alle Tabellen: Spalten mit x (Rechenweg, Nebenwerte) stehen nur in „Ausführlich“; Standard „Einfach“.
// Browser-Speicher 'bwg-spalten' ('einfach' | 'voll'), ohne Speicher bis zum Neuladen; der Wechsel meldet 'bwg-spalten' am
// document, jede Tabelle mit solchen Spalten zeichnet sich dann selbst neu (Sortierung, Filter und Anzahl bleiben).
const SP_KEY = 'bwg-spalten';
let spMem = null;
export const spaltenVoll = () => (store.get(SP_KEY) ?? spMem) === 'voll';
export function setSpaltenVoll(v) {
  spMem = v ? 'voll' : 'einfach';
  store.set(SP_KEY, spMem);
  D.dispatchEvent(new CustomEvent('bwg-spalten'));
}
// ein Empfänger für alle Tabellen: nur die im Dokument stehen, bauen sich neu (abgehängte bleiben nicht angemeldet)
D.addEventListener('bwg-spalten', () => D.querySelectorAll('.tbox').forEach(b => b.spNeu?.()));

// Zeilenklasse für Tabellen mit einer Zeile je Team (team_id, sonst tid): die eigene Zeile hervorgehoben
export const meRc = x => { const m = meinTeam(); return m && (x?.team_id ?? x?.tid) === m ? 'me' : null; };

// Hash-Parameter ändern, ohne die Ansicht neu zu laden (teilbarer Link)
export function setQ(path, params) {
  const q = new URLSearchParams();
  for (const k in params) if (params[k] != null && params[k] !== '') q.set(k, params[k]);
  const s = q.toString().replace(/%2C/g, ',');
  history.replaceState(history.state, '', '#' + path + (s ? '?' + s : ''));   // state behalten: gesicherte Scrollposition
}

// ---------------------------------------------------------------- Chips, Umschalter, Kacheln
// Waagerecht scrollende Bereiche (Tabellen, Chipleisten): Klasse „sc-more“, solange rechts etwas verborgen ist (CSS
// blendet die Kante aus), „sc-scrolled“ ab dem ersten Wischen (Schatten an der festen Team-Spalte). Auf dem Handy ist sonst nicht
// zu erkennen, dass eine Tabelle weitere Spalten hat.
export function scrollHint(el) {
  const upd = () => {
    el.classList.toggle('sc-more', el.scrollWidth - el.clientWidth - el.scrollLeft > 2);
    el.classList.toggle('sc-scrolled', el.scrollLeft > 2);
  };
  el.addEventListener('scroll', upd, {passive: true});
  new ResizeObserver(upd).observe(el);
  return el;
}
export const chips = (label, items, cur, cls) => scrollHint(h('nav', {class: 'chips' + (cls ? ' ' + cls : ''), 'aria-label': label},
  items.map(([href, text, key, extra]) => h('a', {href, 'aria-current': key === cur ? 'page' : null, class: extra}, text))));
// aktuellen Chip einer scrollenden Chipleiste in die Mitte holen (erst aufrufen, wenn die Leiste im DOM steht)
export function centerChip(nav) {
  const cur = nav.querySelector('[aria-current]');
  if (cur) nav.scrollLeft += cur.getBoundingClientRect().left - nav.getBoundingClientRect().left - (nav.clientWidth - cur.offsetWidth) / 2;
  return nav;
}
// Wochenwahl „Saison · W1 · W2 …“ über die gerechneten Wochen (meta.weeks): Links auf path bzw. path/wN
export function weekChips(path, cur) {
  const start = n => S.weeks.find(w => w.week === n)?.start;
  return chips('Woche wählen', [['#' + path, ['Saison', h('small', null, `bis W${S.tw}`)], 0],
    ...(S.meta.weeks || []).map(w => ['#' + path + '/w' + w, ['W' + w, h('small', null, start(w) ? spanne(start(w)) : '')], w])], cur, 'wk');
}
// All-Play-Bilanz „6-3“, mit Gleichständen „6-2-1“ (showT erzwingt die dritte Zahl, damit eine Spalte einheitlich bleibt)
export const apwl = (w, l, t, showT) => `${nn(w)}-${nn(l)}` + (showT || t ? `-${nn(t)}` : '');

// Kopf einer Ansicht: Überschrift, bei Ansichten eines Bereichs (r.B vom Router) darunter die Bereichs-Zeile mit der Frage des
// Bereichs und die Ansichten als Chips. Spieler-, Team- und Erklärungen-Seite haben keinen Bereich, nur die Überschrift.
// → h1, damit die Ansicht den Titel nach dem Laden noch ändern kann
export function kopf(box, r, titel) {
  const h1 = h('h1', null, titel), B = r.B;
  add(box, [h1, B ? [h('p', {class: 'bereich'}, h('strong', null, B.l), ' – ', B.frage, ' ', B.text),
    chips('Ansichten ' + B.l, B.chips, r.view, 'bv')] : null]);
  return h1;
}
// Zweite Ebene von Woche › Matchups: Übersicht, je Position und D/ST (Offenses aus den D/ST-Faktoren)
export const muChips = cur => chips('Matchups je Position', [['#woche/matchups', 'Übersicht', ''],
  ...['QB', 'RB', 'WR', 'TE', 'K'].map(p => ['#woche/matchups/' + p.toLowerCase(), p, p.toLowerCase()]), ['#woche/matchups/dst', 'D/ST', 'dst']], cur, 'l2');
// Laufende Woche nach dem Kalender: die letzte Woche des Spielplans, die (Dienstag, deutsche Zeit) schon begonnen hat; vor W1
// die erste. Eine Woche heißt erst nach dem Wochenabruf „final“, ihr Status sagt deshalb nicht, ob sie gerade läuft.
const ISO = new Intl.DateTimeFormat('en-CA', {timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit'});
export const heute = () => ISO.format(new Date());          // „2026-10-04“, deutscher Kalendertag
export const aktuelleWoche = () => { const t = heute(); return S.weeks.filter(w => w.start <= t).at(-1)?.week ?? S.weeks[0]?.week ?? 1; };
// Saison läuft (Woche öffnet dann mit dem Spieltag live): W1 hat begonnen, die letzte Woche des Spielplans ist nach dem
// Kalender noch nicht vorbei (ihr Montag) und die Playoffs sind nicht bis zur letzten Woche gewertet (manifest ›
// datenstand.playoff_woche, wie „Saison beendet“ im Datenstand-Fenster). Der Status der Woche taugt dafür nicht:
// Playoff-Wochen führt schedule.json nie als „final“.
export const saisonLaeuft = () => {
  const t = heute(), last = S.weeks.at(-1);
  if (!last || S.weeks[0].start > t) return false;
  const ende = new Date(Date.parse(last.start + 'T12:00:00Z') + 7 * 864e5).toISOString().slice(0, 10);
  return t < ende && (S.man.datenstand?.playoff_woche ?? 0) < last.week;
};
// Wochenabruf laut .github/workflows/wochenabruf.yml in Stunden nach Dienstag 00:00 UTC: Di 08:30, Nachläufe Di 16:30 und
// Mi 08:30 UTC (tests/test_zeitplan.py vergleicht mit den cron-Zeilen); wochenabrufe(tag) = die drei Termine ab dem Dienstag
// tag („2026-10-06“, Beginn einer Woche), ohne tag keine
export const WOCHENABRUF_H = [8.5, 16.5, 32.5];
export const wochenabrufe = tag => tag ? WOCHENABRUF_H.map(x => new Date(Date.parse(tag + 'T00:00:00Z') + x * 36e5)) : [];
// Nächster Wochenabruf als Text, gleich im Hinweis „Gespielt, noch nicht gewertet“ und im Datenstand-Fenster („Nächster
// Wochenabruf“): vor dem ersten Termin „geplant …“, danach „fällig seit …“ mit dem nächsten Nachlauf, solange einer aussteht.
// Ob GitHub den Lauf schon gestartet hat (meist 10–16 min nach dem Slot, manchmal deutlich später), weiß die App nicht –
// deshalb nie „verpasst“; ohne tag null
export function wochenabrufTxt(tag) {
  const [erster, ...nach] = wochenabrufe(tag), jetzt = Date.now();
  if (!erster) return null;
  if (erster.getTime() > jetzt) return `geplant ${stamp(erster)}`;
  const nachlauf = nach.find(t => t.getTime() > jetzt);
  return `fällig seit ${stamp(erster)}` + (nachlauf ? `, nächster Nachlauf ${stamp(nachlauf)}` : '');
}
// Dienstags zwischen Wochenwechsel und Wochenabruf (Beschluss Stephan 06.10.2026): Der Tageslauf führt schon die neue Woche
// (waiver.json › woche = N+2), der Wochenstand noch die alte (players.json › mu_woche = N+1, Rest der Saison nach W N).
// Nicht über manifest › datenstand.pool_woche: das ist der Wochen-Pool (= gewertete Woche) und nie größer.
// → {gespielt: N+1, neu: N+2, stand: N} oder null (Montag, nach dem Wochenabruf, ohne Tagesstand, nach W17: mu_woche null)
export const zwischenstand = (W, P) => W && P && ok(W.woche) && ok(P.mu_woche) && W.woche > P.mu_woche
  ? {gespielt: P.mu_woche, neu: W.woche, stand: P.mu_woche - 1} : null;
// Hinweiszeile dazu (Markt, Spielerseite, Team-Seite) mit dem nächsten Wochenabruf (wochenabrufTxt). „endet mit dem
// Montagsspiel“ statt „ist gespielt“: Der Tagesstand wechselt um 00:00 UTC in die neue Woche, beim ersten Tageslauf am
// Dienstag (rund 2 h 40 min nach dem Anstoß) läuft das Montagsspiel oft noch. Gegner nennt der Grundsatz nicht – die Ansichten
// blenden ihn aus und sagen das im zusatz (Satz der Ansicht: was dort bis dahin fehlt)
export function zwischenHinweis(z, zusatz) {
  const wann = wochenabrufTxt(S.weeks?.find(w => w.week === z.neu)?.start);
  return h('p', {class: 'warn'}, `W${z.gespielt} endet mit dem Montagsspiel und wird mit dem Wochenabruf gewertet${wann ? ` (${wann})` : ''}. `
    + `Bis dahin gelten Kader und Projektion schon für W${z.neu}; Faktoren, Rest der Saison sowie Stärken und Schwächen zeigen noch den Stand nach W${z.stand}.`,
  zusatz ? ' ' + zusatz : null, ' ', ib('vor-wochenabruf', ''));
}
// Farbklasse eines Faktors F um 1,00 (D/ST-Faktoren, Positions-Matchup): f1–f3 blau = günstig, g1–g3 orange = ungünstig,
// f0 = um 1,00; die Zahl steht immer dabei. Stufe nach F in den angezeigten Stellen st (2 oder 3), gerundet mit demselben
// Intl-Formatierer wie num() (toFixed rundet 0,985 anders als die Anzeige), gemessen in Tausendsteln: gleiche angezeigte
// Zahl = gleiche Farbe, und die Grenzen der Legende gelten genau (1,15 − 1 ergibt als Gleitkommazahl 0,1499…)
const NFE = {};
const shown = (v, d) => +(NFE[d] || (NFE[d] = new Intl.NumberFormat('en-US', {minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: false}))).format(v);
export const fcls = (f, st = 2) => {
  if (!ok(f)) return 'f0';
  const d = Math.round((shown(+f, st) - 1) * 1000);
  return d >= 150 ? 'f3' : d >= 70 ? 'f2' : d >= 20 ? 'f1' : d > -20 ? 'f0' : d > -70 ? 'g1' : d > -150 ? 'g2' : 'g3';
};

export function seg(label, opts, cur, on, cls) {
  const g = scrollHint(h('div', {class: 'seg' + (cls ? ' ' + cls : ''), role: 'group', 'aria-label': label}));
  const bs = opts.map(([v, text]) => h('button', {type: 'button', 'aria-pressed': String(v === cur), 'data-v': v}, text));
  g.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    bs.forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    on(b.dataset.v);
  });
  g.set = v => bs.forEach(x => x.setAttribute('aria-pressed', String(x.dataset.v === v)));
  add(g, bs);
  return g;
}

export const tile = (label, value, sub, gid) => h('div', {class: 'tile' + (gid ? ' hi' : '')},
  h('div', {class: 'tl'}, h('span', null, label), gid ? ib(gid, '') : null),
  h('div', {class: 'tv'}, value), sub ? h('div', {class: 'ts'}, sub) : null);

export const card = (title, ...kids) => h('section', {class: 'card'}, title ? h('h2', null, title) : null, kids);

// ---------------------------------------------------------------- i-Knöpfe (Text aus dem Glossar in index.html)
const term = gid => D.getElementById('g-' + gid);
export function ib(gid, label, extra) {
  const name = term(gid)?.textContent || gid;
  const text = label === '' ? null : label || name;
  return h('button', {type: 'button', class: text ? 'it' : 'i', 'aria-expanded': 'false', 'aria-controls': 'pop',
    'aria-haspopup': 'dialog', 'data-g': gid, 'data-x': extra || null, 'aria-label': 'Erklärung: ' + name},
  text ? [text, h('span', {class: 'i', 'aria-hidden': 'true'}, 'i')] : 'i');
}
export const legend = (ids, extra) => scrollHint(h('div', {class: 'lg'}, h('span', null, 'Erklärungen:'),
  ids.map(g => Array.isArray(g) ? ib(g[0], g[1], g[2]) : ib(g, null, extra?.[g]))));

let popBtn = null;
const pop = () => D.getElementById('pop');
export function showPop(btn, title, nodes) {
  const p = pop();
  if (popBtn === btn && !p.hidden) return closePop(true);
  closePop(false);
  p.replaceChildren(h('div', {class: 'ph'}, h('strong', {id: 'pop-t'}, title),
    h('button', {type: 'button', class: 'x', 'aria-label': 'Schließen', onclick: () => closePop(true)}, '×')), ...nodes.filter(Boolean));
  p.hidden = false;
  popBtn = btn;
  btn.setAttribute('aria-expanded', 'true');
  const r = btn.getBoundingClientRect(), w = Math.min(380, innerWidth - 32);
  p.style.width = w + 'px';
  p.style.left = Math.max(16, Math.min(r.left, innerWidth - w - 16)) + scrollX + 'px';
  p.style.top = r.bottom + scrollY + 6 + 'px';
  p.focus({preventScroll: true});
  const pr = p.getBoundingClientRect();
  if (pr.bottom > innerHeight) scrollBy({top: pr.bottom - innerHeight + 12});
}
export function closePop(refocus) {
  const p = pop();
  if (!p || p.hidden) return;
  p.hidden = true;
  if (popBtn) { popBtn.setAttribute('aria-expanded', 'false'); if (refocus) popBtn.focus(); }
  popBtn = null;
}
export function infoPop(btn) {        // i-Knopf: Begriff und Erklärung aus dem Glossar, dazu ggf. der Grund
  const dt = term(btn.dataset.g);
  showPop(btn, dt ? dt.textContent : btn.dataset.g, [
    h('p', null, dt ? dt.nextElementSibling.textContent : 'Keine Erklärung gefunden.'),
    btn.dataset.x ? h('p', {class: 'warn'}, btn.dataset.x) : null,
    h('p', null, h('a', {href: '#erklaerungen/' + btn.dataset.g}, 'In den Erklärungen ansehen')),
  ]);
}

// ---------------------------------------------------------------- sortierbare Tabelle
// o = {cap, cols: [{k, l, v: Zeile → Sortierwert, f: Zeile → Inhalt, num, d (1 auf-, −1 absteigend), cls}],
//      rows, sort: [key, dir], cls (z. B. 'rk': Rang und Team fest, auf dem Handy Kürzel), rh (Index der Zeilenkopf-Spalte), rc (Zeile → Klasse), limit,
//      filter (true: Knopf „Filter“ öffnet ein Blatt mit einem Dropdown je Spalte – Zahlen als Stufen „≥ 15“ bzw. „≤ 5“ bei d = 1,
//      Texte und Spalten mit cat als Werteliste; flt: false nimmt eine Spalte heraus), filters (zusätzliche Filter ohne Spalte,
//      z. B. {k, l, v, cat}), fstate (Objekt des Aufrufers, in dem die Auswahl über einen Neuaufbau hinweg erhalten bleibt),
//      show (anfangs so viele Zeilen statt limit, z. B. auf dem Rückweg bis zur zuletzt geöffneten Zeile)}
//      Spalte mit x: true steht nur in „Ausführlich“ (spaltenVoll); dann trägt die Tabelle den Schalter „Einfach · Ausführlich“.
//      def: feste Voreinstellung der Sortierung, wenn sort eine mitgeführte Wahl ist (Rückfall, wenn deren Spalte ausgeblendet ist);
//      note darf eine Funktion sein (wird bei jedem Zeichnen gelesen, etwa je nach Einfach / Ausführlich).
export function table(o) {
  const capId = id('c');
  const alle = o.cols, hatX = alle.some(c => c.x);
  let cols = [], heads = [];
  let sk = o.sort?.[0], sd = o.sort?.[1] ?? -1, limit = o.show || o.limit || 1e9;
  const thead = h('thead');
  // Kopfzeile aus den sichtbaren Spalten; ist die Sortierspalte nicht mehr sichtbar, gilt wieder die Voreinstellung
  function kopf() {
    cols = alle.filter(c => !c.x || spaltenVoll());
    if (!cols.some(c => c.k === sk)) {
      const d = [o.def, o.sort].find(s => s && cols.some(c => c.k === s[0]));
      sk = d?.[0] ?? null; sd = d?.[1] ?? -1;
      o.onSort?.(sk, sd);
    }
    heads = cols.map(c => {
      // lange Namen (ab 13 Zeichen) dürfen zweizeilig umbrechen (CSS thead th.wr)
      const th = h('th', {scope: 'col', class: [c.num && 'n', typeof c.l === 'string' && c.l.length > 12 && 'wr'].filter(Boolean).join(' ') || null});
      if (c.v && o.sortable !== false) th.append(h('button', {type: 'button', onclick: () => {
        if (sk === c.k) sd = -sd; else { sk = c.k; sd = c.d ?? -1; }
        o.onSort?.(sk, sd);
        draw();
      }}, c.l, h('span', {class: 'si', 'aria-hidden': 'true'})));
      else th.append(c.l);
      return th;
    });
    thead.replaceChildren(h('tr', null, heads));
  }
  kopf();
  const tb = h('tbody'), fn = h('p', {class: 'fn', id: id('f')}), more = h('div');
  // Filter: ein Dropdown je Spalte in einem Blatt (Handy: von unten, Desktop: Karte unter der Leiste); Auswahl als Chips über der Tabelle.
  // Auch Spalten nur für „Ausführlich“ bleiben filterbar; ein aktiver Filter steht immer als Chip da, auch wenn die Spalte fehlt
  const flt = o.fstate || {};
  const fdefs = o.filter ? [...(o.filters || []), ...alle.filter(c => c.v && c.flt !== false)] : [];
  let fbar = null, fpan = null, fbtn = null, fchips = null, fback = null;
  const cellText = (c, r) => c.f ? h('td', null, c.f(r, 0)).textContent.trim() : String(c.v(r) ?? '');
  const isNum = c => c.num && !c.cat;
  // Optionen je Filter aus den aktuellen Zeilen: Zahlen als „schöne“ Stufen, sonst die vorkommenden Werte (bis 40, danach kein Filter)
  const options = c => {
    if (isNum(c)) {
      const vals = o.rows.map(c.v).filter(ok);
      const asc = c.d === 1, st = steps(vals, asc);
      if (!st.length) return null;       // alle Werte gleich (z. B. Schnee überall 0): kein Filter statt eines leeren Dropdowns
      return st.map(x => ({key: String(x), label: (asc ? '≤ ' : '≥ ') + fmtStep(x, st), test: r => ok(c.v(r)) && (asc ? c.v(r) <= x : c.v(r) >= x)}));
    }
    const seen = new Map();
    o.rows.forEach(r => { const s = cellText(c, r); if (s && s !== '–' && !seen.has(s)) seen.set(s, c.v(r)); });
    if (seen.size > 40 || seen.size < 2) return null;
    return sortRows([...seen], x => x[1], c.d ?? 1).map(([s]) => ({key: s, label: s, test: r => cellText(c, r) === s}));
  };
  const active = () => fdefs.filter(c => flt[c.k]?.key);
  if (o.filter) {
    fchips = h('div', {class: 'fcs', role: 'group', 'aria-label': 'Aktive Filter'});
    fbtn = h('button', {type: 'button', class: 'btn fb', 'aria-expanded': 'false', onclick: () => openPanel()},
      h('span', {'aria-hidden': 'true'}, '⚲'), 'Filter', h('span', {class: 'cnt'}));
    fbar = h('div', {class: 'fbar'}, fbtn, fchips, o.aside || null);
  }
  // Schalter „Einfach · Ausführlich“: gilt für alle Tabellen (spaltenVoll), steht an jeder Tabelle mit Spalten nur für „Ausführlich“
  const spSeg = hatX ? seg('Spalten', [['einfach', 'Einfach'], ['voll', 'Ausführlich']], spaltenVoll() ? 'voll' : 'einfach',
    v => setSpaltenVoll(v === 'voll'), 'tight') : null;
  const spRow = spSeg ? h('div', {class: 'tsw'}, spSeg, ib('spalten', '')) : null;
  if (spRow && fbar) fbar.append(spRow);
  function openPanel() {
    if (fpan) return closePanel();
    const rowsEl = fdefs.map(c => {
      const opts = options(c);
      if (!opts) return null;
      const cur = flt[c.k]?.key || '';
      const label = typeof c.l === 'string' ? c.l : `Spalte ${alle.indexOf(c) + 1}`;
      const sel = h('select', {'aria-label': label, onchange: e => {
        const op = opts.find(x => x.key === e.target.value);
        if (op) flt[c.k] = {key: op.key, label: `${label} ${isNum(c) ? op.label : '· ' + op.label}`, test: op.test}; else delete flt[c.k];
        draw();
      }}, h('option', {value: ''}, 'Alle'), opts.map(x => h('option', {value: x.key, selected: x.key === cur}, x.label)));
      return h('label', {class: 'fr'}, h('span', null, label), sel);
    }).filter(Boolean);
    fpan = h('div', {class: 'fp', role: 'dialog', 'aria-label': 'Filter', tabindex: '-1'},
      h('div', {class: 'ph'}, h('strong', null, 'Filter'), h('button', {type: 'button', class: 'x', 'aria-label': 'Schließen', onclick: closePanel}, '×')),
      rowsEl.length ? h('div', {class: 'fg'}, rowsEl) : h('p', {class: 'note'}, 'Keine filterbaren Spalten.'),
      h('div', {class: 'row fa'}, h('button', {type: 'button', class: 'btn', onclick: () => { clearAll(); closePanel(); }}, 'Zurücksetzen'),
        h('button', {type: 'button', class: 'btn pri', onclick: closePanel}, 'Fertig')));
    fback = h('div', {class: 'fbd', onclick: closePanel});
    fbar.after(fpan);
    D.body.append(fback);
    D.body.classList.add('fp-open');
    fbtn.setAttribute('aria-expanded', 'true');
    fpan.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });
    fpan.focus({preventScroll: true});
  }
  function closePanel() {
    if (!fpan) return;
    fpan.remove(); fback.remove(); fpan = fback = null;
    D.body.classList.remove('fp-open');
    fbtn.setAttribute('aria-expanded', 'false');
    fbtn.focus({preventScroll: true});
  }
  function clearAll() { for (const k in flt) delete flt[k]; draw(); }
  const tbl = h('table', {class: o.cls}, h('caption', {id: capId}, o.cap), thead, tb);
  const wrap = scrollHint(h('div', {class: 'tw' + (o.stick ? ' stick' : ''), role: 'region', tabindex: '0', 'aria-labelledby': capId}, tbl));
  const box = h('div', {class: 'tbox'}, fbar || (spRow ? h('div', {class: 'fbar'}, spRow) : null), wrap, fn, more);
  const rh = o.rh ?? 1;
  function draw() {
    let rows = o.rows;
    const act = active();
    let fdrop = 0;
    if (act.length) {
      const all = rows.length;
      rows = rows.filter(r => act.every(c => flt[c.k].test(r)));
      fdrop = all - rows.length;
    }
    if (fbtn) {
      fbtn.querySelector('.cnt').textContent = act.length ? ` ${act.length}` : '';
      fbtn.classList.toggle('on', act.length > 0);
      fchips.replaceChildren(...act.map(c => h('button', {type: 'button', class: 'fc', onclick: () => { delete flt[c.k]; draw(); },
        'aria-label': `Filter entfernen: ${flt[c.k].label}`}, flt[c.k].label, h('span', {'aria-hidden': 'true'}, ' ×'))),
      ...(act.length > 1 ? [h('button', {type: 'button', class: 'fc all', onclick: clearAll}, 'Alle löschen')] : []));
    }
    const c = alle.find(x => x.k === sk);
    if (c?.v) rows = sortRows(rows, c.v, sd);
    heads.forEach((th, i) => {
      if (cols[i].k === sk) th.setAttribute('aria-sort', sd > 0 ? 'ascending' : 'descending'); else th.removeAttribute('aria-sort');
    });
    naSet = new Set();
    const shown = rows.slice(0, limit);
    tb.replaceChildren(...shown.map((r, i) => h('tr', {class: o.rc?.(r)}, cols.map((col, j) => h(j === rh ? 'th' : 'td',
      {scope: j === rh ? 'row' : null, class: [col.num && 'n', typeof col.cls === 'function' ? col.cls(r) : col.cls].filter(Boolean).join(' ') || null},
      col.f(r, i))))));
    const reasons = [...naSet];
    naSet = null;
    // leere Auswahl (z. B. Filter ohne Treffer) sichtbar machen, statt nur einen leeren Tabellenkörper zu zeigen
    const txt = [rows.length ? '' : 'Keine Einträge für diese Auswahl.', fdrop ? `Filter: ${rows.length} von ${rows.length + fdrop}.` : '',
      reasons.length ? '„–“: ' + reasons.join(' · ') : ''].filter(Boolean).join(' ');
    fn.replaceChildren(txt);
    const note = typeof o.note === 'function' ? o.note() : o.note;
    fn.hidden = !txt && !note;
    if (note) fn.append(txt ? ' · ' : '', note);
    if (fn.hidden) tbl.removeAttribute('aria-describedby'); else tbl.setAttribute('aria-describedby', fn.id);
    more.replaceChildren(rows.length > shown.length ? h('button', {type: 'button', class: 'btn more', onclick: () => {
      const n0 = limit;
      limit += o.limit;
      draw();
      // Fokus auf die erste neue Zeile, sonst springt er (Tastatur, VoiceOver) an den Seitenanfang
      const f = tb.children[n0]?.querySelector('a,button');
      (f || tb.children[n0])?.focus?.({preventScroll: true});
    }}, `Weitere ${Math.min(o.limit, rows.length - shown.length)} anzeigen (${shown.length} von ${rows.length})`) : '');
    o.onCount?.(rows.length, o.rows.length);
  }
  box.upd = rows => { o.rows = rows; if (o.limit) limit = o.limit; draw(); };
  // Wechsel Einfach / Ausführlich (auch an einer anderen Tabelle der Seite): neu aufbauen; der Rahmen behält seine Größe, deshalb
  // den Scroll-Hinweis (sc-more) von Hand neu messen
  if (hatX) box.spNeu = () => {
    spSeg.set(spaltenVoll() ? 'voll' : 'einfach');
    kopf();
    draw();
    wrap.dispatchEvent(new Event('scroll'));
  };
  draw();
  return box;
}
// „Schöne“ Stufen für Zahlenfilter: Spanne der Werte in etwa zehn Schritte (1 · 2 · 2,5 · 5 × 10ⁿ); die Stufe, die nichts
// herausfiltern würde (Minimum bei „≥“, Maximum bei „≤“), entfällt.
export function steps(vals, asc) {
  if (vals.length < 2) return [];
  const lo = Math.min(...vals), hi = Math.max(...vals);
  if (!(hi > lo)) return [];
  const raw = (hi - lo) / 10, p = 10 ** Math.floor(Math.log10(raw)), m = raw / p;
  let step = (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  if (vals.every(Number.isInteger)) step = Math.max(1, Math.round(step));   // Spiele, Starts, Ränge: nur ganze Stufen
  const out = [];
  for (let x = Math.ceil(lo / step) * step; x <= hi + 1e-9; x += step) out.push(+x.toFixed(6));
  return out.filter(x => asc ? x < hi - 1e-9 : x > lo + 1e-9).slice(0, 12);
}
const fmtStep = (x, st) => {
  const d = Math.max(0, ...st.map(s => (String(s).split('.')[1] || '').length));
  return num(x, Math.min(d, 3));
};
export function sortRows(rows, fn, dir) {
  const miss = x => x == null || x === '' || Number.isNaN(x);
  return rows.map((r, i) => [fn(r), i, r]).sort((a, b) => {
    const ma = miss(a[0]), mb = miss(b[0]);
    if (ma || mb) return (ma - mb) || a[1] - b[1];        // fehlende Werte immer ans Ende
    if (a[0] < b[0]) return -dir;
    if (a[0] > b[0]) return dir;
    return a[1] - b[1];
  }).map(x => x[2]);
}

// Playoff-%-Zelle mit dünnem 0–100-Balken
export const pbar = v => ok(v) ? h('span', {class: 'pb', style: `--p:${Math.max(0, Math.min(100, v)).toFixed(1)}%`}, po(v)) : na('Simulation folgt');
// Trendpfeil mit Zahl (Farbe nie allein)
export function trend(v, reason) {
  if (!ok(v)) return na(reason);
  const pl = Math.abs(v) === 1 ? 'Platz' : 'Plätze';
  if (v > 0) return h('span', {class: 'up'}, '↑' + v, h('span', {class: 'vh'}, ` ${pl} besser`));
  if (v < 0) return h('span', {class: 'dn'}, '↓' + -v, h('span', {class: 'vh'}, ` ${pl} schlechter`));
  return h('span', {class: 'eq'}, '→', h('span', {class: 'vh'}, 'unverändert'));
}
export const res = r => r ? h('span', {class: r}, r) : '–';
// ESPN-lineupSlotId → Kürzel (falls der Export schon Text liefert, bleibt er)
const SLOTS = {0: 'QB', 2: 'RB', 4: 'WR', 6: 'TE', 7: 'OP', 16: 'D/ST', 17: 'K', 20: 'Bank', 21: 'IR', 23: 'FLEX'};
export const slot = v => v == null ? '–' : typeof v === 'number' ? SLOTS[v] ?? String(v) : v;
export const bench = v => v === 20 || v === 21 || v === 'Bank' || v === 'IR' || v === 'BE';
// Paarung als Karte; full = mit Teamnamen und Wochenrängen, sonst Kürzel (Woche kompakt)
export function game(g, full) {
  const fin = g.winner != null, st = S.weeks.find(w => w.week === g.week)?.status, wi = S.meta.weeks.indexOf(g.week);
  // offene Woche mit Siegchance: Prozent mit Balken in der Punkte-Spalte, der Favorit fett
  const chance = !fin && st !== 'laeuft' && ok(g.p_home) ? sp(g.p_home) : null;
  const side = (tid, pts, p) => {
    const r = fin ? (g.winner === 'T' ? 'T' : g.winner === tid ? 'W' : 'L') : null;
    return h('div', {class: 'gl' + (r === 'W' || (p != null && p > 50) ? ' win' : '')}, h('span', {class: 'res'}, r ? res(r) : ''),
      full ? tl(tid) : h('a', {href: '#team/' + tid, class: 'tl2', 'aria-label': team(tid)?.name}, kz(tid)),
      h('span', {class: 'pts'}, fin ? num(pts) : p != null ? pbar(p) : ''));
  };
  let meta, info = null;
  if (fin) {
    meta = g.winner === 'T' ? 'Unentschieden' : 'Differenz ' + num(Math.abs(g.home_pf - g.away_pf));
    if (full && wi >= 0) meta += ` · Wochenrang ${team(g.home).wochen.wochenrang[wi]}. und ${team(g.away).wochen.wochenrang[wi]}.`;
  } else if (st === 'laeuft') meta = ['läuft – Ergebnis nach dem Wochenabruf · ', h('a', {href: '#spieltag'}, 'Spieltag live')];
  else if (chance != null) {
    meta = 'Siegchance';
    info = full ? ib('siegchance', '') : null;
  } else meta = 'offen';
  // Spiel von Mein Team mit Randstrich (wie in Spieltag live)
  const mine = meinTeam() && (g.home === meinTeam() || g.away === meinTeam());
  return h('li', {class: 'game' + (mine ? ' mine' : '')}, side(g.home, g.home_pf, chance), side(g.away, g.away_pf, chance == null ? null : 100 - chance),
    h('div', {class: 'gm row'}, h('span', null, meta), info));
}
// Tageslauf von Hand: Die App startet nichts selbst (kein Token im Browser). Der Knopf ist ein Link im Aussehen der
// übrigen Knöpfe (Datenstand-Fenster und Live-Ansicht) und öffnet die Workflow-Seite bei GitHub in einem neuen Tab;
// dort „Run workflow“ (GitHub-Anmeldung mit Schreibrecht nötig). tests/test_live_ansicht.py prüft Adresse und Aufrufe.
export const TAGESLAUF_URL = 'https://github.com/frest2101/bwg-fantasy/actions/workflows/tageslauf.yml';
export const tageslaufKnopf = () => h('a', {href: TAGESLAUF_URL, target: '_blank', rel: 'noopener', class: 'btn'}, 'Tageslauf starten (GitHub)');
export const errBox = (e, retry) => h('div', {class: 'err', role: 'alert'},
  h('p', null, 'Die Daten konnten nicht geladen werden.'),
  h('p', {class: 'note'}, e instanceof TypeError ? 'Keine Verbindung – bitte später erneut versuchen.' : String(e?.message || e)),
  retry ? h('button', {type: 'button', class: 'btn', onclick: retry}, 'Erneut versuchen') : null);
