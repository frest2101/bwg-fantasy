// Spieltag live (#spieltag, #spieltag/<team_id>; erste Ansicht im Bereich Woche): holt beim Öffnen und auf „Aktualisieren“ den laufenden Spieltag direkt
// bei ESPN (nur lesend, ohne Zugangsdaten) und zeigt Paarungen, Aufstellungen und Bewegungen – nach den Regeln des
// Stand-Skripts scripts/claude_stand.py, aber nur, was die öffentliche App zeigt (keine gescheiterten Claims, keine
// Trade-Vorschläge). Gerechnet wird in live_core.js (reine Funktionen); hier nur Abruf und Anzeige.
// Kein Teil des Datenvertrags (docs/app_daten.md): Die Ansicht liest ESPN im Browser, nichts davon wird gespeichert.
// Aus den App-Daten kommen Teamnamen, Kürzel, Spielerseiten, der Stand der Kader laut Tageslauf (waiver.json) und die bekannten
// Transaktionen (transactions.json) für das Kennzeichen „neu“; jeder Abruf holt vorher den Datenstand der App neu
// (ctx.refresh), damit nach einem Tageslauf „Aktualisieren“ genügt.
// Kein Dauerabruf: Je Abruf werden rund 1,1 MB übertragen (4,5 MB entpackt). Die einzigen Zeitgeber hier brechen ab
// (Zeitlimit, Nachlauf), keiner startet einen Abruf – tests/test_live_ansicht.py wacht darüber.
let U, S, h, C;
const LIMIT_LIGA = 30000, LIMIT = 15000;     // Zeitlimit je Abruf in ms (Liga: große Antwort)
const FRISCH = 120000;                       // so lange gilt der letzte Abruf beim Zurückkommen (z. B. von einer Spielerseite)
const NACHLAUF = 3000;                       // so lange läuft ein Abruf weiter, auf den niemand mehr wartet (kurz weg und zurück)
const ART = {WAIVER: 'Waiver', FREEAGENT: 'Free Agent', ROSTER: 'Drop', FUTURE_ROSTER: 'Drop', TRADE_ACCEPT: 'Trade'};
let merk = null;      // letzter guter Abruf: {t, man (Manifest dazu), mine (Mein Team dazu), E (Ergebnis aus live_core), ausfall, seiten, tagesstand}
let offen = null;     // laufender Abruf, von allen Wartenden geteilt: {p, ac, n (wartende Ansichten), aus (Timer)}

// ---------------------------------------------------------------- Abruf (nur GET, nur ESPN-Lese-Endpunkte)
// Fehler mit deutschem Text für die Seite; art: netz (ESPN nicht erreichbar), antwort (Antwort da, aber nicht
// auswertbar), saison (ESPN gibt die Liga nicht heraus), ab (abgebrochen, weil niemand mehr wartet). Texte des
// Browsers und Stücke der Rohantwort kommen nicht in die Seite, nur in die Konsole.
const fehler = (art, text, status) => Object.assign(new Error(text), {art, status});
const TITEL = {netz: 'ESPN ist gerade nicht erreichbar.', antwort: 'Die Antwort von ESPN lässt sich nicht auswerten.',
  saison: 'ESPN gibt die Liga nicht heraus.'};
async function hole(url, params, limit, signal, headers) {
  const q = new URLSearchParams(params).toString();
  const ac = new AbortController();
  const ab = () => ac.abort();
  const timer = setTimeout(() => ac.abort(), limit);
  signal.addEventListener('abort', ab, {once: true});
  if (signal.aborted) ab();
  try {
    const r = await fetch(url + (q ? '?' + q : ''), {method: 'GET', credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
      headers: headers || {}, signal: ac.signal});
    if (!r.ok) throw fehler('netz', `ESPN antwortet mit HTTP ${r.status}`, r.status);
    return await r.json();
  } catch (e) {
    if (e?.art) throw e;
    if (signal.aborted) throw fehler('ab', 'Abruf abgebrochen');
    if (e?.name === 'AbortError') throw fehler('netz', `Zeitlimit: keine Antwort nach ${limit / 1000} Sekunden`);
    if (e instanceof SyntaxError) throw fehler('antwort', 'ESPN hat keine lesbare Antwort geliefert (kein JSON)');
    if (e instanceof TypeError) throw fehler('netz', 'Abruf vom Browser blockiert oder keine Verbindung');
    console.error(e);
    throw fehler('netz', 'unbekannter Fehler beim Abruf');
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', ab);
  }
}
// Erst Liga (vier Views, laufende Periode) und Scoreboard gleichzeitig; danach nur bei Bedarf das Scoreboard der
// Liga-Woche und kona_player_info für Spieler aus Bewegungen, die weder ein Kader noch die App benennt.
async function abrufen(saison, bekannt, signal) {
  const ausfall = {};
  const [lg, sb] = await Promise.allSettled([hole(C.ligaUrl(saison), C.LIGA_VIEWS.map(v => ['view', v]), LIMIT_LIGA, signal),
    hole(C.SCOREBOARD_URL, [], LIMIT, signal)]);
  if (lg.status === 'rejected') {
    // Nach dem Saisonende gibt ESPN eine vergangene Saison nicht mehr ohne Anmeldung heraus (Liga-Vorjahre: 404)
    if ([401, 403, 404].includes(lg.reason.status)) {
      throw fehler('saison', `ESPN antwortet für die Saison ${saison} mit HTTP ${lg.reason.status} – nach dem Saisonende ist das zu erwarten, `
        + 'dann stellt ESPN die Liga auf die neue Saison um; Liga › Tabelle und Rekorde der App zeigen den Endstand');
    }
    throw lg.reason;
  }
  const liga = lg.value;
  let scoreboard = sb.status === 'fulfilled' ? sb.value : null, kona = null;
  if (sb.status === 'rejected') ausfall.scoreboard = sb.reason.message;
  if (!C.ligaMangel(liga)) {
    const woche = liga.scoringPeriodId, nach = [];
    if (!C.scoreboardPasst(scoreboard, woche)) {
      nach.push(hole(C.SCOREBOARD_URL, {seasontype: 2, week: woche, dates: liga.seasonId ?? saison}, LIMIT, signal)
        .then(d => { scoreboard = d; delete ausfall.scoreboard; }, e => { ausfall.scoreboard = e.message; }));
    }
    // Namen sammeln: Hat die Antwort hier eine unerwartete Form, geht es ohne Nachabruf weiter – stand() meldet dann
    // den betroffenen Abschnitt als nicht auswertbar, statt dass die Ansicht „nicht erreichbar“ behauptet
    let ids = [];
    try { ids = C.unbekannteSpieler(liga, bekannt); } catch (e) { console.warn('Spieler aus Bewegungen nicht lesbar:', e); }
    if (ids.length) {
      nach.push(hole(C.ligaUrl(saison), {view: C.KONA_VIEW}, LIMIT, signal, {'X-Fantasy-Filter': JSON.stringify(C.konaFilter(ids, woche))})
        .then(d => { kona = d; }, e => { ausfall.kona = e.message; }));
    }
    await Promise.all(nach);
    if (signal.aborted) throw fehler('ab', 'Abruf abgebrochen');
  }
  return {liga, scoreboard, kona, ausfall};
}

// Auszug der App-Daten für live_core: Namen je Spieler (players.json, waiver.json, transactions.json), Kader laut
// Stand der App (Tageslauf), bekannte Transaktionen, Expertenrang laut Tagesstand (waiver.json exp und exp_n, nur Spieler
// mit Rang); dazu die Spieler mit eigener Seite in der App (wie merge() in v_spieler.js)
function appAuszug(P, W, T) {
  const spieler = {}, seiten = new Set();
  for (const [id, name] of Object.entries(T?.spieler || {})) if (name) spieler[id] = {name};
  for (const d of W?.spieler || []) {
    if (d.name) spieler[d.id] = {name: d.name, pos: d.pos, nfl: d.nfl};
    if (P && (d.team > 0 || d.wert != null)) seiten.add(d.id);
  }
  for (const p of P?.players || []) { spieler[p.id] = {name: p.name, pos: p.pos, nfl: p.nfl}; seiten.add(p.id); }
  // NFL-Team nach einem Wechsel unter der Woche laut Tagesstand (waiver.json nfl_tag, wie U.nflTag)
  for (const d of W?.spieler || []) if ('nfl_tag' in d && spieler[d.id]) spieler[d.id].nfl = d.nfl_tag;
  let kader = null;
  if (W?.spieler) {
    kader = Object.fromEntries(S.teams.map(t => [t.team_id, []]));
    for (const d of W.spieler) if (d.team > 0) (kader[d.team] ||= []).push(d.id);
  }
  const experten = W?.spieler && W.experten_quellen != null ? {woche: W.woche, quellen: W.experten_quellen, tiefe: W.experten_tiefe || {},
    je: Object.fromEntries(W.spieler.filter(d => d.exp_n > 0).map(d => [d.id, [d.exp ?? null, d.exp_n]]))} : null;
  return {teams: S.teams.map(t => ({id: t.team_id, kz: t.kuerzel, name: t.name})), spieler, kader,
    tx: T?.items ? T.items.map(x => x.id) : null, seiten, experten};
}
// Expertenrang laut App in der Unterzeile eines Spielers: „Experten RB 12,5 (8/8)“ bzw. „Experten RB >50 (3/8)“
const expTxt = e => `Experten${U.NB}${e.pos} ${U.ok(e.wert) ? U.num(e.wert, e.wert % 1 ? 1 : 0) : '>' + (e.tiefe ?? '?')} (${e.n}/${e.k})`;

// Ein ganzer Abruf: Datenstand der App auffrischen, ESPN holen, rechnen. Nur ein auswertbares Ergebnis wird gemerkt –
// eine unbrauchbare Antwort überschreibt den letzten guten Stand nicht und gilt nicht als „frisch“.
async function holen(ctx, mine, signal) {
  // Nach einem Tageslauf genügt so „Aktualisieren“: neues Manifest, geänderte Dateien neu, Datenstand-Chip im Kopf.
  // Scheitert das, gilt der geladene Stand der App weiter (die App-Daten sind Zugabe).
  await ctx.refresh().catch(e => console.warn('Datenstand der App nicht aufgefrischt:', e));
  // Das Manifest dieses Abrufs festhalten: Kommt während des Abrufs ein neuer Datenstand („Daten neu laden“), gilt
  // das Ergebnis danach nicht als frisch und wird neu geholt – sonst zeigten „neu“ und Kadervergleich den alten Stand.
  const man = S.man;
  // Ohne App-Daten fehlen nur Spielerlinks, das Kennzeichen „neu“ und der Kadervergleich
  const has = n => man.files?.[n];
  const [P, W, T] = await Promise.all(['players.json', 'waiver.json', 'transactions.json']
    .map(n => has(n) ? ctx.load(n).catch(() => null) : null));
  const app = appAuszug(P, W, T);
  const roh = await abrufen(man.season, Object.keys(app.spieler), signal);
  let E;
  try {
    E = C.stand({liga: roh.liga, scoreboard: roh.scoreboard, kona: roh.kona, app, meinTeam: mine});
  } catch (e) {
    console.error(e);
    throw fehler('antwort', `Antwort nicht auswertbar (${C.FORM})`);
  }
  if (!E.ok) {
    if (E.technik) console.error('ESPN-Antwort nicht auswertbar:', E.technik);
    throw fehler('antwort', E.grund);
  }
  if (E.sbFehler) console.warn('NFL-Scoreboard nicht auswertbar:', E.sbFehler);
  merk = {t: Date.now(), man, mine, E, ausfall: roh.ausfall, seiten: app.seiten,
    tagesstand: W?.stand ?? man.datenstand?.pool_stand ?? null};
  return merk;
}

// Ein laufender Abruf wird geteilt: Wer dazukommt („Erneut versuchen“, Zurückkommen, Mehrfachtippen, Tab „Woche“),
// wartet auf denselben Abruf, statt einen zweiten zu starten. los() meldet eine Ansicht ab; wartet NACHLAUF ms lang
// niemand, wird der Abruf abgebrochen – wer nur kurz weg war, findet ihn noch laufend vor.
function teilen(start) {
  if (!offen) {
    const neu = offen = {ac: new AbortController(), n: 0, p: null, aus: 0};
    neu.p = start(neu.ac.signal).finally(() => { clearTimeout(neu.aus); if (offen === neu) offen = null; });
  }
  const o = offen;
  clearTimeout(o.aus);
  o.n++;
  let da = true;
  return {p: o.p, los() {
    if (!da) return;
    da = false;
    if (--o.n === 0 && offen === o) o.aus = setTimeout(() => { if (!o.n) o.ac.abort(); }, NACHLAUF);
  }};
}

// ---------------------------------------------------------------- Anzeige
const pkt = v => U.num(C.runden(v));                                   // Punkte: zwei Stellen, round half up
const tag = x => U.datum(x).split(' ')[0];                             // „So“
const alter = ms => ms < 90 * 6e4 ? `vor ${Math.max(0, Math.round(ms / 6e4))} min` : `vor ${U.num(ms / 36e5, 1)} h`;
const wann = t => Date.now() - t > 12 * 36e5 ? U.stamp(t) : `${U.zeit(t)} Uhr`;     // älterer Stand mit Datum
const kzTxt = (tid, E) => U.team(tid)?.kuerzel ?? E.teams[tid]?.kz ?? String(tid);
const teamLink = (tid, E) => U.team(tid) ? U.tl(tid) : kzTxt(tid, E);

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  C = await ctx.mod('live_core');
  if (!r.alive()) return;
  const mine = U.meinTeam();                       // Mein Team (Kopf), 0 = keins
  const st = {team: U.team(r.sub) ? +r.sub : 0};
  const kopf = h('p', {class: 'note'}, 'Live von ESPN: Der Spieltag wird jetzt geladen.');
  const status = h('span', {class: 'note'});       // sichtbarer Ladehinweis; angesagt wird über ctx.say (aria-live)
  const meldung = h('div');                        // Fehlerzeile über dem letzten guten Stand
  const body = h('div');
  const btn = h('button', {type: 'button', class: 'btn', onclick: () => laden(true, btn)}, 'Aktualisieren');
  U.kopf(box, r, 'Spieltag live');
  U.ap(box, kopf, h('div', {class: 'row'}, btn, U.tageslaufKnopf(), status), meldung, body);
  // frisch: letzter Abruf höchstens zwei Minuten alt und zum geladenen Datenstand der App und zu Mein Team gerechnet
  const frisch = () => merk && merk.man === S.man && merk.mine === mine && Date.now() - merk.t < FRISCH;
  let wartet = null;        // los() des Abrufs, auf den diese Ansicht gerade wartet
  let nochmal = null;       // Knopf „Erneut versuchen“ in der Fehlerzeile
  let gezeigt = false;      // steht ein Stand in der Ansicht?
  // Tab „Woche“: In der offenen Live-Ansicht lädt ein Tipp neu wie „Aktualisieren“ (die Tab-Leiste steht immer im Blick,
  // der Knopf nur am Seitenanfang); beim Verlassen ist er wieder ein gewöhnlicher Link. Bis Paket P2 tat das der Chip
  // „Live“ im Kopf, an seiner Stelle steht jetzt Mein Team
  const chip = document.querySelector('.tabs a[data-s="woche"]');
  if (chip) chip.onclick = e => {
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    e.preventDefault();
    laden(true, chip);
  };
  ctx.onLeave(() => {
    wartet?.();
    if (chip) { chip.onclick = null; chip.removeAttribute('aria-busy'); }
  });

  const busy = an => {
    btn.disabled = an;
    if (nochmal) nochmal.disabled = an;
    status.textContent = an ? 'Lade Spieltag von ESPN …' : '';
    if (an) chip?.setAttribute('aria-busy', 'true'); else chip?.removeAttribute('aria-busy');
  };

  // von = Knopf oder Tab „Woche“, der den Abruf ausgelöst hat (null beim Öffnen der Ansicht)
  async function laden(erzwingen, von) {
    if (wartet) return;                                  // diese Ansicht wartet schon (Mehrfachtippen)
    if (!erzwingen && frisch()) return zeichne();
    const {p, los} = teilen(signal => holen(ctx, mine, signal));
    wartet = los;
    busy(true);
    ctx.say('Lade Spieltag von ESPN …');
    let err = null;
    try { await p; } catch (e) { err = e; }
    los();
    if (wartet === los) wartet = null;
    if (!r.alive()) return;
    if (err?.art === 'ab') return laden(true, von);      // der geteilte Abruf wurde gerade abgebrochen: neu holen
    busy(false);
    if (!err) {
      try {
        meldung.replaceChildren();
        nochmal = null;
        zeichne();
        ctx.say('Spieltag geladen.');
      } catch (e) {
        err = e;
      }
    }
    if (err) return scheitern(err, von);
    // Tastaturfokus: Der auslösende Knopf war gesperrt oder ist verschwunden („Erneut versuchen“) – zurück auf „Aktualisieren“
    const f = document.activeElement;
    if (von && von !== chip && (!f || f === document.body || !f.isConnected || f === von)) btn.focus({preventScroll: true});
  }

  // Abruf gescheitert: Fehlerzeile mit Uhrzeit und „Erneut versuchen“; der letzte gute Stand bleibt darunter stehen
  function scheitern(e, von) {
    console.error(e);
    const alt = merk && merk.man.season === S.man.season ? merk : null;
    nochmal = h('button', {type: 'button', class: 'btn', onclick: ev => laden(true, ev.currentTarget)}, 'Erneut versuchen');
    meldung.replaceChildren(h('div', {class: 'err blk', role: 'alert'},
      h('p', null, h('strong', null, `${U.zeit(Date.now())} Uhr: `), TITEL[e.art] || 'Die Live-Ansicht konnte den Abruf nicht verarbeiten.'),
      h('p', {class: 'note'}, `Grund: ${e.art ? e.message : 'unerwarteter Fehler (Einzelheiten in der Konsole des Browsers)'}. `,
        alt ? `Darunter steht weiter der Stand von ${wann(alt.t)}.` : 'Die übrigen Seiten der App zeigen weiter den Stand des letzten Tageslaufs.'),
      nochmal));
    if (alt && !gezeigt) { try { zeichne(); } catch (x) { console.error(x); } }
    if (!gezeigt) kopf.replaceChildren('Live von ESPN – der Abruf ist gescheitert.');
    ctx.say('Der Spieltag konnte nicht geladen werden.');
    if (von) nochmal.focus();        // auch vom Seitenende aus (Tab „Woche“): die Fehlerzeile kommt in den Blick
  }

  function zeichne() {
    const {E, t, tagesstand} = merk;
    const ts = U.utc(tagesstand);
    kopf.replaceChildren();
    U.ap(kopf, h('strong', null, `Stand ${wann(t)}`), ` · W${E.woche} · live von ESPN `, U.ib('live', ''),
      h('br'), 'App: ', ts ? `${U.standTxt(ts)} (${alter(t - ts.getTime())})` : 'noch kein Stand des Tageslaufs');
    body.replaceChildren();
    gezeigt = true;
    if (E.neuer) U.ap(body, h('p', {class: 'warn'}, 'Bewegungen oder Kader sind neuer als der Stand der App. „Tageslauf starten“ holt sie nach; '
      + 'etwa 2 Minuten später genügt hier „Aktualisieren“. ', U.ib('tageslauf-starten', '')));
    if (E.ruhe) {
      U.ap(body, h('p', {class: 'warn'}, E.ruhe === 'nach'
        ? 'Die Saison ist bei ESPN beendet – es läuft kein Spieltag mehr. Liga › Tabelle und Rekorde der App zeigen den Endstand.'
        : 'ESPN meldet für die laufende Woche keine Paarung – zurzeit läuft kein Spieltag.'));
    } else {
      const auf = h('section', {class: 'blk'}, h('h2', null, 'Aufstellung'));
      U.ap(body, nfl(E, merk.ausfall), matchups(E, mine), auf);
      aufstellungen(auf, E, mine);
    }
    U.ap(body, bewegungen(E), kader(E, merk.ausfall),
      U.legend(['live', 'live-punkte', 'live-siegchance', 'live-starter', 'neu-tagesstand', 'tageslauf-starten', 'projektionen', 'experten']));
  }

  // Team-Auswahl (Standard: Mein Team, sonst das erste Team der ersten Paarung) und sein Gegner; ohne neuen Abruf
  function aufstellungen(wrap, E, mine) {
    const ids = Object.keys(E.teams).map(Number);
    let tid = [st.team, mine, E.reihenfolge[0], ids[0]].find(x => x && E.teams[x]);
    const out = h('div', {class: 'two2 lva'});
    const draw = () => {
      const a = E.teams[tid], g = a && !a.fehler && a.gegner != null ? E.teams[a.gegner] : null;
      out.replaceChildren();
      U.ap(out, teamBox(a, E, tid), g ? teamBox(g, E, a.gegner)
        : a && !a.fehler ? h('p', {class: 'note'}, a.paarung === 'freilos' ? 'Kein Gegner in dieser Woche (Freilos).' : 'Keine Paarung für dieses Team in dieser Woche.') : null);
    };
    U.ap(wrap, h('div', {class: 'row'}, h('label', null, 'Team ', h('select', {onchange: e => {
      tid = st.team = +e.target.value;
      U.setQ('spieltag/' + tid, {});
      draw();
    }}, ids.map(i => h('option', {value: i, selected: i === tid}, `${kzTxt(i, E)} · ${U.team(i)?.name ?? E.teams[i]?.name ?? i}`))))), out);
    draw();
  }

  // Rückweg mit frischem Stand: sofort zeichnen, damit die Scrollposition wiedergefunden wird
  if (frisch()) zeichne(); else laden(false, null);
}

// Abschnitt, der an einer unerwarteten Form der Antwort scheitert: deutscher Satz in der Seite, Einzelheiten in der Konsole
function abschnittFehler(titel, x) {
  if (x.technik) console.warn(`${titel}:`, x.technik);
  return h('p', {class: 'warn'}, `${titel}: nicht auswertbar (${x.fehler}).`);
}

// NFL-Spiele der Woche kompakt nach Status; Anstoß in deutscher Zeit wie überall in der App
function nfl(E, ausfall) {
  if (!E.hatSb) {
    const warum = E.sbFehler ? C.FORM : E.sbWoche != null ? `zeigt Woche ${E.sbWoche} statt ${E.woche}` : ausfall.scoreboard || 'kein Abruf';
    return h('p', {class: 'warn'}, `NFL-Scoreboard nicht nutzbar (${warum}): Spielstatus, Gegner und Anstoßzeiten fehlen; gesperrt/offen je Spieler stammt aus dem ESPN-Kader, Byes sind so nicht erkennbar.`);
  }
  const n = E.nfl;
  if (n.fehler) return abschnittFehler('NFL-Spiele', n);
  const dl = h('dl', {class: 'lvn'});
  const add = (dt, dd) => U.ap(dl, h('dt', null, dt), h('dd', null, dd));
  if (n.final.length) add('final', n.final.map(s => `${s.paarung} ${s.stand}`).join(', '));
  if (n.laeuft.length) add('läuft', n.laeuft.map(s => `${s.paarung} ${s.stand}` + (s.detail ? ` (${s.detail})` : '')).join(', '));
  for (const o of n.offen) add(o.anstoss == null ? 'Anstoß offen' : U.stamp(o.anstoss), o.spiele.join(', '));
  if (n.verschoben.length) add('verschoben', n.verschoben.map(s => `${s.paarung} (${s.detail || 'ohne Angabe'})`).join(', '));
  if (n.bye.length) add('Bye', n.bye.join(', '));
  return U.card(`NFL-Spiele W${E.woche}`, h('p', {class: 'note'}, `${n.final.length} final · ${n.laeuft.length} läuft · ${n.offenZahl} offen`
    + (n.verschoben.length ? ` · ${n.verschoben.length} verschoben` : '')), dl,
  // unlesbares Spiel: übersprungen, aber benannt – seine Teams stehen sonst still als „Bye“ da
  n.defekt ? h('p', {class: 'warn'}, `Spielstatus unvollständig: ${n.defekt === 1 ? 'Ein Spiel' : `${n.defekt} Spiele`} im NFL-Scoreboard `
    + `${n.defekt === 1 ? 'lässt' : 'lassen'} sich nicht lesen. Spieler dieser Teams zeigen „Status ?“ statt Gegner und Anstoß.`) : null);
}

// Starter eines Teams nach Spielstatus als Text: „3/1/9“, dazu Bye, ohne Team, verschoben, Status ?; ohne Scoreboard gesperrt/offen
function starterTxt(s, hatSb) {
  if (!hatSb) return `${s.zu}/${s.auf}`;
  return `${s.post}/${s.in}/${s.pre}` + [['bye', 'Bye'], ['ohne', 'ohne Team'], ['verschoben', 'verschoben'], ['unklar', 'Status ?']]
    .filter(([k]) => s[k]).map(([k, w]) => ` +${s[k]} ${w}`).join('');
}

// Paarungen: je Paarung beide Teams mit Punkten live, Live-Projektion, Siegchance (ESPN) und Starterzahlen
function matchups(E, mine) {
  const ms = E.matchups;
  if (ms.fehler) return abschnittFehler('Paarungen', ms);
  const side = (m, s) => {
    const ich = s.teamId === mine;
    return h('div', {class: 'gl' + (m.sieger === s.teamId ? ' win' : '')},
      h('div', {class: 'lvt'}, teamLink(s.teamId, E),
        h('span', {class: 'sub'}, `${s.w}-${s.l}` + (s.t ? `-${s.t}` : '') + ` · Projektion ${pkt(s.proj)} · Siegchance${U.NB}${U.ok(s.chance) ? U.num(C.runden(s.chance, 0, 2), 0) + U.NB + '%' : '–'}`),
        ich ? h('span', {class: 'sub lvi'}, 'Mein Team') : null),
      h('span', {class: 'pts'}, pkt(s.punkte)));
  };
  const meta = m => [E.hatSb ? 'Starter final/läuft/offen: ' : 'Starter gesperrt/offen: ',
    m.seiten.map(s => `${s.kz} ${starterTxt(s.starter, E.hatSb)}`).join(' · '),
    m.freilos ? ' · Freilos' : '', m.unentschieden ? ' · Unentschieden' : m.sieger != null ? ` · Sieger ${kzTxt(m.sieger, E)}` : '',
    m.runde ? ` · ${m.runde}` : ''];
  return h('section', {class: 'blk'}, h('h2', null, `Paarungen W${E.woche}`),
    E.periode !== E.woche ? h('p', {class: 'note'}, `Paarungsperiode ${E.periode}; Starterzahlen und Aufstellungen gelten für die ESPN-Woche ${E.woche}.`) : null,
    h('ul', {class: 'games lvm'}, ms.map(m => h('li', {class: 'game' + (m.seiten.some(s => s.teamId === mine) ? ' mine' : '')},
      m.seiten.map(s => side(m, s)), h('div', {class: 'gm'}, meta(m))))),
    h('p', {class: 'note'}, 'Punkte laufender Spiele sind Zwischenstände; Projektion und Siegchance stammen von ESPN. ', U.ib('live-siegchance', '')));
}

// Gegner und Spielstatus eines Spielers: „vs DEN So 22:25“, „@ CLE final“, „Bye“; ohne Scoreboard gesperrt/offen
function spielTxt(z, hatSb) {
  if (!hatSb) return z.state === 'zu' ? 'gesperrt' : 'offen';
  if (z.state === 'bye') return 'Bye';
  if (z.state === 'unklar') return 'Status ?';       // Spiel des Teams im Scoreboard nicht lesbar
  if (z.state === 'ohne' || !z.spiel) return 'ohne NFL-Team';
  const g = z.spiel.gegner.replace(' ', U.NB);       // „vs DEN“ und Anstoß brechen als Ganzes um
  if (z.state === 'post') return `${g} final`;
  if (z.state === 'verschoben') return `${g} verschoben (${z.spiel.detail || 'ohne Angabe'})`;
  if (z.state === 'in') return `${g} läuft` + (z.spiel.detail ? ` (${z.spiel.detail})` : '');
  return z.spiel.anstoss == null ? `${g} (Zeit offen)` : `${g} ${tag(z.spiel.anstoss)}${U.NB}${U.zeit(z.spiel.anstoss)}`;
}
const zielTxt = s => `${s.name} (${s.slot} ${C.SPIELFREI.includes(s.state) ? (s.state === 'bye' ? 'Bye' : 'ohne NFL-Team') : pkt(s.wert) + (s.state === 'verschoben' ? ' verschoben' : '')})`;

// Aufstellung eines Teams: Starter, dann Bank und IR vollständig
function teamBox(a, E, tid) {
  if (!a || a.fehler) return abschnittFehler(`Aufstellung ${kzTxt(tid, E)}`, a || {fehler: 'Team fehlt'});
  const seite = id => merk.seiten.has(id);
  const verl = z => U.inj(z.inj) ?? (z.inj ? h('span', {class: 'inj'}, z.inj) : null);
  const cols = [
    {k: 's', l: 'Slot', f: z => z.slot},
    {k: 'n', l: 'Spieler', f: z => h(seite(z.id) ? 'a' : 'span', {href: seite(z.id) ? '#spieler/' + z.id : null, class: 'pl'},
      h('span', null, z.name, verl(z)), h('span', {class: 'sub'}, `${z.pos} · ${z.nfl} · ${spielTxt(z, E.hatSb)}` + (z.exp ? `${U.NB}· ${expTxt(z.exp)}` : '')),
      z.hinweis ? h('span', {class: 'sub'}, `→ mehr Projektion als ${zielTxt(z.hinweis)}`) : null)},
    {k: 'i', l: 'Pkt', num: 1, f: z => U.ok(z.ist) ? pkt(z.ist) : U.na(z.state === 'unklar' ? 'Spielstatus unklar' : C.OFFEN.includes(z.state) ? 'noch nicht gespielt' : 'kein Wert von ESPN')},
    {k: 'p', l: 'Projektion', num: 1, f: z => U.ok(z.proj) ? pkt(z.proj) : U.na(C.SPIELFREI.includes(z.state) ? 'spielfrei: keine Projektion' : 'keine ESPN-Projektion')}];
  const g = a.gegner != null ? kzTxt(a.gegner, E) : null;
  return h('div', {class: 'blk'}, h('h3', null, teamLink(a.id, E), g ? h('small', {class: 'note'}, ` gegen ${g}`) : null),
    U.table({cap: `Starter ${a.kz}`, cls: 'nr lvz', rh: 1, sortable: false, rows: a.starter, cols}),
    a.besetzt < a.soll ? h('p', {class: 'warn'}, `Nur ${a.besetzt} von ${a.soll} Starter-Slots besetzt.`) : null,
    a.reserve.length ? U.table({cap: `Bank und IR ${a.kz}`, cls: 'nr lvz', rh: 1, sortable: false, rows: a.reserve, cols})
      : h('p', {class: 'note'}, 'Bank und IR: leer.'),
    a.sammel.map(s => h('p', {class: 'note'}, `→ ${s.spieler.length} Bankspieler mit mehr Projektion als Starter ${zielTxt(s.starter)}: `,
      s.spieler.map(x => `${x.name} ${pkt(x.proj)}`).join(', '))));
}

// Bewegungen der Woche wie unter Markt › Moves (ausgeführte Moves, angenommene Trades ohne Spieler, Aufstellungswechsel je
// Team gezählt) – keine gescheiterten Claims, keine Trade-Vorschläge. „neu“ = steht noch nicht in transactions.json.
// Anders als unter Markt › Moves stehen Zugang (+) und Abgang (−) in einer Spalte und die Art unter der Zeit: So ist jede
// Bewegung auf dem Handy ohne Wischen lesbar (drei statt fünf Spalten).
function bewegungen(E) {
  const b = E.bewegungen;
  if (b.fehler) return abschnittFehler('Bewegungen', b);
  const pl = (x, vz, wort) => h('span', {class: 'lvb'}, h('span', {'aria-hidden': 'true'}, vz + U.NB), h('span', {class: 'vh'}, wort + ' '),
    merk.seiten.has(x.id) ? h('a', {href: '#spieler/' + x.id}, x.name) : x.name);
  const gez = list => list.map(x => `${kzTxt(x.teamId, E)} ${x.n}`).join(' · ');
  const sec = h('section', {class: 'blk'}, h('h2', null, `Bewegungen der Woche (W${E.woche})`));
  if (b.zeilen.length) {
    U.ap(sec, U.table({cap: 'Zu- und Abgänge seit dem Wochenwechsel (neueste zuerst)', cls: 'nr kurz lvw', rh: 1, rows: b.zeilen, sort: ['d', -1],
      rc: x => x.neu ? 'me' : null, cols: [
        {k: 'd', l: 'Zeit', v: x => x.zeit, f: x => [U.ok(x.zeit) ? `${U.datum(x.zeit)} ${U.zeit(x.zeit)}` : '–',
          h('span', {class: 'sub'}, ART[x.typ] || 'Bewegung', x.neu ? h('span', {class: 'badge'}, 'neu', h('span', {class: 'vh'}, ' seit Stand der App')) : null)]},
        {k: 't', l: 'Team', v: x => kzTxt(x.teamId, E), d: 1, f: x => teamLink(x.teamId, E)},
        {k: 'z', l: `Zugang (+) / Abgang (${U.MINUS})`, cls: 'lvc', f: x => x.typ === 'TRADE_ACCEPT' ? h('span', {class: 'note'}, 'Trade ohne Spieler (ESPN)')
          : h('div', {class: 'lvs'}, x.zu.map(p => pl(p, '+', 'Zugang')), x.ab.map(p => pl(p, U.MINUS, 'Abgang')))}]}),
    h('p', {class: 'note'}, !b.marken ? 'Die Transaktionen der App sind nicht geladen – „neu“ lässt sich nicht bestimmen.'
      : b.neu ? `${b.neu} ${b.neu === 1 ? 'Bewegung ist' : 'Bewegungen sind'} neu seit dem Stand der App.` : 'Alle Bewegungen stehen schon in der App.',
    ' ', U.ib('neu-tagesstand', '')));
  } else U.ap(sec, h('p', {class: 'note'}, 'Keine Zu- oder Abgänge seit dem Wochenwechsel.'));
  U.ap(sec, b.lineup.length ? h('p', {class: 'note'}, `Aufstellungswechsel je Team (nur gezählt, zusammen ${b.lineupSumme}): ${gez(b.lineup)} `, U.ib('aufstellungswechsel', '')) : null,
    h('p', {class: 'note'}, h('a', {href: '#markt/moves'}, 'Alle Moves der Saison (Stand der App)')));
  return sec;
}

// Kader live gegen den Stand der App (waiver.json): je Team die Abweichungen
function kader(E, ausfall) {
  const k = E.kader;
  if (k.fehler) return abschnittFehler('Kadervergleich', k);
  const sec = h('section', {class: 'blk'}, h('h2', null, 'Kader live gegen Stand der App'));
  const pl = (list, vz) => list.map(x => [' ', vz, merk.seiten.has(x.id) ? h('a', {href: '#spieler/' + x.id}, x.name) : x.name]);
  if (!k.moeglich) U.ap(sec, h('p', {class: 'note'}, 'Kein Vergleich: Der Stand der App ist nicht geladen.'));
  else if (!k.abweichungen.length) U.ap(sec, h('p', null, `Kader live = Stand der App (alle ${k.teams} Teams).`));
  else U.ap(sec, h('ul', {class: 'lvk'}, k.abweichungen.map(x => h('li', null, teamLink(x.teamId, E), ':', pl(x.plus, '+'), pl(x.minus, U.MINUS)))),
    h('p', {class: 'note'}, '+ steht live im Kader, aber noch nicht in der App; − steht in der App, live nicht mehr.'));
  if (ausfall.kona) U.ap(sec, h('p', {class: 'note'}, `Spielernamen ohne Kader teils nur als Nummer (Nachabruf bei ESPN gescheitert: ${ausfall.kona}).`));
  return sec;
}
