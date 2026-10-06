// Einstieg der App (Baustein 4): Manifest und Erstdaten laden, Hash-Router, Kopf, Hell/Dunkel.
// Alle Pfade relativ (GitHub Pages läuft unter /bwg-fantasy/). Ansichten werden per import() nachgeladen,
// jeweils mit derselben Version (?v=<Build>) wie dieses Modul.
const APP_SCHEMA = 1;
const V = new URL(import.meta.url).search;
const ctx = {};
const mods = {};
const mod = name => mods[name] || (mods[name] = import(`./${name}.js${V}`).then(m => { m.init?.(ctx); return m; })
  .catch(e => { delete mods[name]; throw e; }));
const U = await mod('ui');
const {h, S} = U;
const $ = x => document.getElementById(x);
const main = $('main'), live = $('live');
const say = t => { live.textContent = t; };
// bereiche(): Name, Frage und Satz je Bereich für die Karten der Startseite (aus BEREICHE, eine Quelle für Kopf und Startseite)
Object.assign(ctx, {ui: U, S, mod, load, lazy, say, refresh, onLeave, route: () => route(), meinTeam: btn => meinTeamPop(btn),
  bereiche: () => Object.entries(BEREICHE).map(([k, B]) => ({k, l: B.l, frage: B.frage, text: B.text}))});

// ---------------------------------------------------------------- Laden
const cache = {};
async function getJSON(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) throw new Error(`${url.split('?')[0]}: HTTP ${r.status}`);
  return r.json();
}
const getManifest = () => getJSON('data/manifest.json?t=' + Date.now(), {cache: 'no-store'});
const ver = (man, name) => man.files?.[name]?.v ?? man.through_week;
const dataUrl = (man, name) => `data/${name}?v=${encodeURIComponent(ver(man, name))}`;
function load(name) {
  if (cache[name]) return cache[name];
  const p = cache[name] = getJSON(dataUrl(S.man, name)).catch(e => { if (cache[name] === p) delete cache[name]; throw e; });
  return p;
}
// Datenstand auffrischen, ohne die Seite neu zu laden (Live-Ansicht „Aktualisieren“, Datenstand-Fenster „Daten neu
// laden“): Manifest ohne Cache holen; jede Datei mit neuer Version fällt aus dem Speicher, load() holt sie beim nächsten
// Aufruf neu. Teams und Spielplan (Grundlage aller Ansichten) werden gleich neu gesetzt – erst geladen, dann
// umgeschaltet, damit bei einem Fehler der alte Stand ganz stehen bleibt. Der Datenstand-Chip im Kopf folgt.
// → true, wenn es einen neuen Stand gibt (die offene Ansicht zeichnet der Aufrufer neu); ein laufender Aufruf wird geteilt.
const BASIS = ['teams.json', 'schedule.json'];
let refreshing = null;
function refresh() {
  return refreshing || (refreshing = (async () => {
    const man = await getManifest();
    if (man.schema > APP_SCHEMA) { banner(); return false; }      // neue App-Version nötig: Hinweis „neu laden“
    const alt = S.man, neu = n => ver(alt, n) !== ver(man, n);
    if (JSON.stringify(man) === JSON.stringify(alt)) return false;
    const basis = BASIS.some(neu) ? await Promise.all(BASIS.map(n => getJSON(dataUrl(man, n)))) : null;
    for (const n of Object.keys(cache)) if (neu(n)) delete cache[n];
    if (neu('players.json') || neu('waiver.json')) suchListe = null;    // Suche im Kopf lädt beim nächsten Öffnen neu
    S.man = man;
    if (basis) {
      BASIS.forEach((n, i) => { cache[n] = Promise.resolve(basis[i]); });
      setup(...basis);
      mtChip();                           // Kürzel oder Name des Teams kann sich geändert haben
    }
    standChip();
    return true;
  })().finally(() => { refreshing = null; }));
}
// Lazy-Datei mit sichtbarem Ladehinweis (aria-live); bei Fehler Hinweis mit „Erneut versuchen“
async function lazy(name, label, box) {
  // schon geladen oder unterwegs: nichts ansagen (sonst überschriebe „… geladen“ etwa die Ansage einer Wahl von Mein Team)
  const neu = !cache[name];
  const p = h('p', {class: 'loading'}, `Lade ${label} …`);
  box.append(p);
  if (neu) say(`Lade ${label} …`);
  try {
    const d = await load(name);
    p.remove();
    if (neu) say(`${label} geladen.`);
    return d;
  } catch (e) {
    p.replaceWith(U.errBox(e, () => route()));
    say(`${label} konnten nicht geladen werden.`);
    throw Object.assign(e, {shown: true});
  }
}

async function start() {
  try {
    S.man = await getManifest();
    if (S.man.schema > APP_SCHEMA) banner();
    const [teams, sched] = await Promise.all([load('teams.json'), load('schedule.json')]);
    setup(teams, sched);
  } catch (e) {
    console.error(e);
    main.replaceChildren(U.errBox(e, start));
    addEventListener('hashchange', start, {once: true});   // Tab antippen = neuer Versuch
    return;
  }
  header();
  addEventListener('hashchange', route);
  route();
}

function setup(teams, sched) {
  S.meta = teams.meta;
  S.teams = teams.teams;
  S.byId = new Map(S.teams.map(t => [t.team_id, t]));
  S.sched = sched;
  S.weeks = sched.weeks || [];
  S.tw = S.man.through_week ?? S.meta.weeks?.at(-1) ?? 0;
  S.hasT = S.teams.some(t => t.t > 0);
  const po = S.teams.map(t => t.sim?.liga?.playoff).filter(U.ok);
  S.simFrac = po.length ? po.every(v => v <= 1) : true;
}

function banner() {
  const b = $('banner');
  b.replaceChildren(h('strong', null, 'Neue Version – bitte neu laden.'),
    h('button', {type: 'button', class: 'btn', onclick: () => location.reload()}, 'Neu laden'));
  b.hidden = false;
}

// ---------------------------------------------------------------- Kopf: Datenstand-Chip, Hell/Dunkel
// Nächster Tageslauf laut tageslauf.yml: Slots in deutscher Zeit (cron mit timezone "Europe/Berlin"), stündlich
// 04:45–16:45 und 17:40–23:40 Uhr = 20 Läufe je Tag; GitHub startet erfahrungsgemäß 10–16 min später.
// DAILY = [Minute, erste Stunde, letzte Stunde] je cron-Zeile – tests/test_zeitplan.py vergleicht mit dem Workflow.
// Gerechnet wird in Berliner Uhrzeit, egal wo der Browser steht: Berlin ist UTC+1 oder UTC+2, es gilt der Kandidat,
// dessen Berliner Uhr den Slot zeigt. Kein Slot liegt in der Umstellungsstunde 02–03 Uhr, also passt immer genau einer.
const DAILY_TZ = 'Europe/Berlin';
const DAILY = [[45, 4, 16], [40, 17, 23]];
const BERLIN = new Intl.DateTimeFormat('en-GB', {timeZone: DAILY_TZ, hourCycle: 'h23', year: 'numeric', month: 'numeric',
  day: 'numeric', hour: 'numeric', minute: 'numeric'});
const berlin = t => Object.fromEntries(BERLIN.formatToParts(t).filter(p => p.type !== 'literal').map(p => [p.type, +p.value]));
export function nextDaily(now = new Date()) {
  const b = berlin(now);
  for (let day = 0; day < 2; day++) for (const [mm, von, bis] of DAILY) for (let hh = von; hh <= bis; hh++) for (const off of [2, 1]) {
    const t = new Date(Date.UTC(b.year, b.month - 1, b.day + day, hh - off, mm));
    const p = berlin(t);
    if (p.hour === hh && p.minute === mm && t > now) return t;
  }
  return null;
}
function header() {
  standChip();
  suche();
  mtChip();
  $('mt').onclick = () => meinTeamPop($('mt'));
  // Wechsel aus einer Ansicht (Auswahl unter Markt): nur der Kopf zieht nach, die Ansicht zeichnet sich selbst
  document.addEventListener('bwg-team', mtChip);
  // Wahl in einem anderen Tab (null = Speicher geleert): Kopf nachziehen, die offene Ansicht neu zeichnen
  addEventListener('storage', e => { if (e.key === 'bwg-team' || e.key === null) { mtChip(); route(); } });
  theme();
}

// ---------------------------------------------------------------- Mein Team im Kopf (App-Konzept 04.10.2026, Abschnitt 6, Paket P2)
// Knopf mit dem Kürzel des gewählten Teams (ohne Wahl ein Trikot-Symbol); das Fenster führt zur Team-Seite und wählt das Team.
// Gespeichert wird nur die Team-Nummer im Browser (U.setMeinTeam). Der Knopf ersetzt seit P2 den Chip „Live“ im Kopf: Bei
// 320 px blieben neben sechs Elementen nur 8 px Rand; Spieltag live öffnet während der Saison der Tab Woche.
const TRIKOT = () => {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('width', '22'); s.setAttribute('height', '22');
  s.setAttribute('aria-hidden', 'true'); s.setAttribute('focusable', 'false');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', 'M9 3.5 4.5 5.5 2 10l3 1.8 1.5-1.3V20.5h11V10.5l1.5 1.3L22 10l-2.5-4.5L15 3.5c-.4 1.5-1.6 2.4-3 2.4s-2.6-.9-3-2.4Z');
  p.setAttribute('fill', 'none'); p.setAttribute('stroke', 'currentColor'); p.setAttribute('stroke-width', '2'); p.setAttribute('stroke-linejoin', 'round');
  s.append(p);
  return s;
};
function mtChip() {
  const b = $('mt'), t = U.team(U.meinTeam());
  b.className = t ? 'stand mt' : 'ico mt';
  b.replaceChildren(t ? t.kuerzel : TRIKOT());
  // der zugängliche Name beginnt mit dem sichtbaren Kürzel (Sprachsteuerung: „HJS“ antippen)
  b.setAttribute('aria-label', t ? `${t.kuerzel} – Mein Team: ${t.name}` : 'Mein Team wählen');
  b.title = t ? `Mein Team: ${t.kuerzel}, ${t.name}` : 'Mein Team wählen';
  b.hidden = false;
}
// Fenster „Mein Team“; btn = Knopf, an dem es hängt (Kopf oder Startseite)
function meinTeamPop(btn) {
  const tid = U.meinTeam(), t = U.team(tid);
  const wahl = neu => {
    U.setMeinTeam(neu);
    U.closePop(false);
    // Hervorhebung, Startseite und Voreinstellungen der offenen Ansicht neu; danach Ansage und Fokus zurück auf den auslösenden
    // Knopf (auf der Startseite ist er neu gezeichnet, dann der Knopf im Kopf)
    route().then(() => {
      say(U.meinTeam() ? `Mein Team: ${U.team(U.meinTeam()).name}.` : 'Kein Team gewählt.');
      (btn.isConnected ? btn : $('mt')).focus({preventScroll: true});
    });
  };
  // Link auf die gerade offene Seite: kein hashchange, also schließt das Fenster hier (wie in der Suche)
  const zu = (href, text, cls) => h('a', {href, class: cls || null, onclick: e => { if (href === location.hash) { e.preventDefault(); U.closePop(true); } }}, text);
  const teams = [...S.teams].sort((a, b) => a.name.localeCompare(b.name, 'de'));
  U.showPop(btn, 'Mein Team', [
    t ? h('div', {class: 'row'}, zu('#team/' + tid, `${t.name}: Team-Seite`, 'btn pri'))
      : h('p', null, 'Wähle dein Team: Die App hebt es dann in Tabellen, Diagrammen und Paarungen hervor, Markt, Herkunft und Spieltag live zeigen es zuerst.'),
    t ? h('p', {class: 'note'}, 'Zuerst gezeigt unter ', zu('#spieltag', 'Spieltag live'), ' · ', zu('#markt', 'Markt'), ' · ', zu('#keeper/herkunft', 'Herkunft')) : null,
    h('div', {class: 'mtg', role: 'group', 'aria-label': 'Team wählen'}, teams.map(x => h('button', {type: 'button', class: 'btn',
      'aria-pressed': String(x.team_id === tid), onclick: () => wahl(x.team_id)}, h('b', null, x.kuerzel), h('span', null, x.name)))),
    t ? h('p', null, h('button', {type: 'button', class: 'btn', onclick: () => wahl(0)}, 'Kein Team')) : null,
    h('p', {class: 'note'}, 'Gespeichert wird nur die Team-Nummer in diesem Browser, kein Login. ', zu('#erklaerungen/mein-team', 'Mehr dazu')),
  ]);
}

// ---------------------------------------------------------------- Suche im Kopf: Spieler und Teams (statt eines Spieler-Tabs)
// Teams sofort aus teams.json; Spieler beim ersten Öffnen aus players.json und dem Stand des Tageslaufs (waiver.json), zusammengeführt
// wie in der Spielerliste – jeder Treffer hat damit eine Spielerseite. Reihenfolge: Namensanfang, dann Anfang des Vor- oder
// Nachnamens, dann Teiltreffer; bei Gleichstand nach Besitz % (ESPN-weit).
let suchListe = null;
const spielerListe = () => suchListe || (suchListe = (async () => {
  const [P, W, sp] = await Promise.all([load('players.json'),
    S.man.files?.['waiver.json'] ? load('waiver.json').catch(() => null) : null, mod('v_spieler')]);
  return {sp, rows: sp.merge(P, W).map(p => ({p, n: sp.norm(p.name)}))};
})().catch(e => { suchListe = null; throw e; }));
function suche() {
  const btn = $('such');
  btn.hidden = false;
  btn.onclick = () => {
    const inp = h('input', {type: 'search', placeholder: 'Spieler oder Team', 'aria-label': 'Spieler oder Team suchen', autocomplete: 'off',
      autocapitalize: 'off', spellcheck: 'false', enterkeyhint: 'go'});
    const out = h('ul', {class: 'such'});
    const info = h('p', {class: 'note', role: 'status'});
    const alle = h('a', {href: '#spieler'}, 'Alle Spieler mit Filtern');
    let liste = null, fehler = false;
    const eintrag = (href, name, sub, extra) => h('li', null, h('a', {href, class: 'pl'}, h('span', null, name, extra), h('span', {class: 'sub'}, sub)));
    const zeig = () => {
      const raw = inp.value.trim();
      // wie die Spielerliste: ohne Groß/klein, Akzente, Apostrophe („asses“ findet Asse's Cowboys); bis v_spieler geladen ist, einfach
      const nm = s => liste ? liste.sp.norm(s) : String(s).toLowerCase();
      const q = nm(raw);
      alle.setAttribute('href', '#spieler' + (raw ? '?q=' + encodeURIComponent(raw) : ''));
      // Teams: leer alle zehn nach Tabellenplatz, sonst Treffer im Namen oder am Anfang des Kürzels
      const teams = [...S.teams].sort((a, b) => a.rang - b.rang).filter(t => !q || nm(t.name).includes(q) || nm(t.kuerzel).startsWith(q));
      const rang = x => x.n.startsWith(q) ? 0 : x.n.includes(' ' + q) ? 1 : 2;
      const treffer = liste && q ? U.sortRows(liste.rows.filter(x => x.n.includes(q)), x => rang(x) * 1000 - (x.p.own ?? 0), 1).slice(0, 8) : [];
      out.replaceChildren(...teams.map(t => eintrag('#team/' + t.team_id, t.name, `Team · ${t.kuerzel} · ${t.rang}. · ${U.rec(t)}`)),
        ...treffer.map(({p}) => eintrag('#spieler/' + p.id, p.name, `${p.pos ?? '–'} · ${p.nfl || 'FA'} · ${p.team > 0 ? U.kz(p.team) : U.STAT[p.status] || 'frei'}`, U.inj(p.inj))));
      info.textContent = fehler ? 'Spieler konnten nicht geladen werden – nur Teams.' : !q ? 'Name eingeben, z. B. „allen“ oder „HJS“.'
        : !liste ? 'Lade Spieler …' : teams.length + treffer.length ? '' : 'Kein Treffer.';
    };
    inp.addEventListener('input', zeig);
    // Ziel ist die gerade offene Seite: kein hashchange, also schließt nicht route() das Fenster, sondern dies hier (Fokus
    // zurück auf die Lupe); sonst schließt route() und setzt den Fokus auf die neue Überschrift
    const offen = href => href === location.hash && (U.closePop(true), true);
    // Enter öffnet den ersten Treffer
    inp.addEventListener('keydown', e => {
      const a = e.key === 'Enter' && out.querySelector('a');
      if (a) { e.preventDefault(); if (!offen(a.getAttribute('href'))) location.hash = a.getAttribute('href'); }
    });
    const fuss = h('p', {class: 'note'}, alle);
    for (const x of [out, fuss]) x.addEventListener('click', e => { const a = e.target.closest('a'); if (a && offen(a.getAttribute('href'))) e.preventDefault(); });
    U.showPop(btn, 'Spieler und Teams', [h('div', {class: 'row srch'}, h('label', null, h('span', {class: 'vh'}, 'Suchen'), inp)), info, out, fuss]);
    if ($('pop').hidden) return;              // zweiter Klick auf die Lupe schließt das Fenster
    inp.focus({preventScroll: true});
    zeig();
    spielerListe().then(x => { liste = x; if (inp.isConnected) zeig(); })
      .catch(e => { console.error(e); fehler = true; if (inp.isConnected) zeig(); });
  };
}
// Datenstand-Chip und sein Fenster; läuft nach refresh() erneut und zeigt dann den neuen Stand
function standChip() {
  const ds = S.man.datenstand || {};
  const btn = $('stand');
  const wk = n => S.weeks.find(w => w.week === n);
  // Stand-Woche: in den Playoffs die letzte finale Playoff-Woche (Stufe 4), sonst die letzte gewertete Woche
  const po = ds.playoff_woche ?? null, sw = po ?? S.tw;
  // nach W17 holt der Wochenabruf keine Woche mehr (Stat-Korrekturen noch drei Wochen, Glossar „Aktualisierung“)
  const fertig = po != null && po >= (S.weeks.at(-1)?.week ?? 17);
  // Dienstag, an dem Woche n beginnt; nach der letzten Woche des Spielplans eine Woche weiter (Abruf nach W17)
  const start = n => wk(n)?.start ?? (wk(n - 1) ? new Date(Date.parse(wk(n - 1).start + 'T12:00:00Z') + 7 * 864e5).toISOString().slice(0, 10) : null);
  // nächster Wochenabruf: Dienstag nach der laufenden Woche, Termine laut U.wochenabrufe (WOCHENABRUF_H, erster 08:30 UTC); der
  // Text im Fenster kommt aus U.wochenabrufTxt wie im Hinweis „Gespielt, noch nicht gewertet“, „alt“ zählt ab dem ersten Termin
  const nxt = fertig ? null : start(sw + 2);
  const due = U.wochenabrufe(nxt)[0];
  const alt = due && Date.now() > due.getTime() + 27.5 * 36e5;     // Mittwoch 12:00 UTC ohne neue Woche
  // „W4 gewertet“ (App-Konzept, Abschnitt 7); auf schmalen Handys nur „W4 ✓“, der Rest steht im aria-label
  btn.replaceChildren(...(sw ? [`W${sw}`, h('span', {class: 'stw'}, ' gewertet'), h('span', {class: 'stk', 'aria-hidden': 'true'}, ' ✓')] : ['vor W1']));
  btn.classList.toggle('alt', !!alt);
  btn.setAttribute('aria-label', `Datenstand: Woche ${sw} gewertet${alt ? ', Daten älter als erwartet' : ''}`);
  btn.hidden = false;
  const pool = ds.pool_woche != null ? wk(ds.pool_woche + 1)?.start : null;
  // Stand des Tageslaufs: Besitz, Verletzung, Projektion der nächsten Woche und Wetter; davor nur der Wochenstand
  const tag = ds.pool_stand ? U.standTxt(ds.pool_stand) : ds.pool_woche != null ? `nach W${ds.pool_woche}` + (pool ? ` (${U.datum(pool)})` : '') : '–';
  btn.onclick = () => {
    // „Daten neu laden“: holt den Datenstand ohne Neuladen der Seite (refresh). Gibt es einen neuen, wird die offene
    // Ansicht neu gezeichnet und das Fenster mit dem neuen Stand wieder geöffnet (über den dann neuen Klick-Handler).
    const info = h('span', {class: 'note', role: 'status'});
    const neu = h('button', {type: 'button', class: 'btn', onclick: async () => {
      neu.disabled = true;
      info.textContent = 'Lade Datenstand …';
      try {
        if (await refresh()) {
          say('Neuer Datenstand geladen.');
          await route();
          btn.onclick();
          return;
        }
        info.textContent = `Kein neuer Stand (geprüft ${U.zeit(Date.now())} Uhr).`;
      } catch (e) {
        console.error(e);
        info.textContent = 'Datenstand nicht erreichbar – später erneut versuchen.';
      }
      neu.disabled = false;
    }}, 'Daten neu laden');
    // Einfach (Paket P5): Wertung, Stand heute und nächster Tageslauf; Ausführlich: alle Zeilen. Der Schalter unten ist derselbe
    // wie an den Tabellen (U.spaltenVoll) und baut nur den Inhalt neu – der Knopf bleibt im Fenster, das Fenster offen
    const knopf = h('dd', {class: 'full'}, U.tageslaufKnopf(), neu, info);
    const inhalt = h('div');
    const fuellen = () => {
      const voll = U.spaltenVoll();
      inhalt.replaceChildren();
      U.ap(inhalt, h('dl', null,
        h('dt', null, 'Wertung'), h('dd', null, `W${voll ? ds.woche_final ?? S.tw : sw} gewertet`),
        voll && po ? [h('dt', null, 'Playoffs'), h('dd', null, `W${po} gewertet`)] : null,
        voll ? [h('dt', null, 'Projektionen Rest der Saison'), h('dd', null, ds.ros_nach_woche != null ? `Stand nach W${ds.ros_nach_woche}` : `ab Wochenabruf W${sw + 1}`)] : null,
        h('dt', null, ds.pool_stand ? 'Besitz, Verletzung, Projektion nächste Woche' : 'Besitz, Verletzung'), h('dd', null, tag),
        voll ? [h('dt', null, 'Wetter'), h('dd', null, ds.wetter_stand ? U.standTxt(ds.wetter_stand) : '–'),
          h('dt', null, 'Letzter Move'), h('dd', null, ds.transaktionen_bis ? U.stamp(ds.transaktionen_bis) : '–')] : null,
        // „ab“: geplanter Slot, GitHub startet meist rund 15 min später (Glossar „Aktualisierung“)
        h('dt', null, 'Nächster Tageslauf'), h('dd', null, `ab ${U.stamp(nextDaily())}`),
        // Tageslauf von Hand: nur ein Knopf zur Workflow-Seite, kein Start aus der App (kein Token im Browser)
        knopf,
        voll ? [h('dt', null, 'Nächster Wochenabruf'), h('dd', null, fertig ? '– (Saison beendet; Stat-Korrekturen übernimmt er noch drei Wochen lang)' : U.wochenabrufTxt(nxt) ?? '–')] : null),
      h('p', {class: 'note'}, '„Tageslauf starten“ öffnet GitHub: dort „Run workflow“ (GitHub-Anmeldung nötig). Etwa 2 Minuten später holt „Daten neu laden“ den neuen Stand. ',
        h('a', {href: '#erklaerungen/tageslauf-starten'}, 'Mehr dazu')),
      voll ? h('p', {class: 'note'}, 'Wertung und Projektionen rechnen nur mit abgeschlossenen Wochen; der Tageslauf frischt Besitz, Verletzung, Transaktionen und Wetter stündlich von etwa 05:00 Uhr bis Mitternacht (deutsche Zeit) auf. ', h('a', {href: '#erklaerungen/aktualisierung'}, 'Mehr zur Aktualisierung')) : null);
    };
    fuellen();
    const anzeige = U.seg('Anzeige', [['einfach', 'Einfach'], ['voll', 'Ausführlich']], U.spaltenVoll() ? 'voll' : 'einfach',
      v => { U.setSpaltenVoll(v === 'voll'); fuellen(); anzeige.scrollIntoView({block: 'nearest'}); }, 'tight');
    U.showPop(btn, 'Datenstand', [
      alt ? h('p', {class: 'warn'}, 'Daten älter als erwartet – der Wochenabruf ist noch nicht durchgelaufen.') : null,
      inhalt,
      // Link statt i-Knopf: ein Erklärfenster ersetzte dieses Fenster, der Fokus ginge danach verloren
      h('div', {class: 'row'}, h('span', {class: 'note'}, 'Anzeige'), anzeige, h('a', {href: '#erklaerungen/spalten'}, 'Mehr dazu')),
    ]);
  };
}
function theme() {
  const tb = $('theme'), de = document.documentElement, mq = matchMedia('(prefers-color-scheme: dark)');
  const dark = () => de.dataset.theme === 'dark' || (!de.dataset.theme && mq.matches);
  const sync = () => {
    tb.setAttribute('aria-pressed', String(dark()));
    // Browserleiste (iPhone) passend zum gewählten Design, nicht nur zum System
    for (const m of document.querySelectorAll('meta[name=theme-color]')) {
      if (de.dataset.theme) m.setAttribute('content', dark() ? '#161a20' : '#ffffff');
      else m.setAttribute('content', m.media.includes('dark') ? '#161a20' : '#ffffff');
    }
  };
  tb.onclick = () => {
    const t = dark() ? 'light' : 'dark';
    // stimmt die Wahl mit dem System überein, nichts festhalten: dann folgt die App wieder dem Tag-Nacht-Wechsel
    if ((t === 'dark') === mq.matches) {
      delete de.dataset.theme;
      try { localStorage.removeItem('bwg-theme'); } catch { /* ohne Speicher */ }
    } else {
      de.dataset.theme = t;
      try { localStorage.setItem('bwg-theme', t); } catch { /* Umschalter gilt dann nur bis zum Neuladen */ }
    }
    sync();
  };
  mq.addEventListener?.('change', sync);
  sync();
}

// ---------------------------------------------------------------- Router
// Fünf Bereiche nach Fragen (App-Konzept 04.10.2026, Paket P1): Tab, Frage und Satz der Bereichs-Zeile unter jeder Überschrift,
// Ansichten als Chips. Je Ansicht [Pfad im Bereich, Chip, Modul]; der Router gibt dem Modul den Chip-Pfad als r.view, den Rest
// des Hashs (Woche w3, Position qb, zweite Ebene) als r.sub und den Pfad der Ansicht als r.base (für eigene Links und setQ).
// Chip null: eigene Route ohne eigenen Chip (bis P3 Matchups › D/ST, seit P3 Teil der Ansicht Matchups); ein Chip als Funktion liest
// die Daten.
const BEREICHE = {
  liga: {l: 'Liga', frage: 'Wo stehen wir?', text: 'Tabelle nach Siegen, Ergebnisse, Playoff-Chancen, Duelle und Rekorde.', v: [
    ['', 'Tabelle', 'v_tabelle'], ['division', 'Division', 'v_tabelle'], ['ergebnisse', 'Ergebnisse', 'v_spielplan'],
    ['playoffs', 'Playoff-Chancen', 'v_tabelle'], ['duelle', 'Duelle', 'v_rekorde'], ['rekorde', 'Rekorde', 'v_rekorde']]},
  staerke: {l: 'Stärke', frage: 'Wer ist wirklich wie gut?', text: 'Rangfolgen nach Punkten statt nach Siegen.', v: [
    ['', 'Power Ranking', 'v_ranking'], ['allplay', 'All-Play & Glück', 'v_tabelle'], ['punkte', 'Punkte & Form', 'v_tabelle'],
    ['coaching', 'Coaching', 'v_tabelle'], ['score', 'Eigener Score', 'v_ranking']]},
  woche: {l: 'Woche', frage: 'Was zählt diese Woche?', text: 'Live-Punkte, Paarungen mit Siegchance, Matchups je Position und Wetter.', v: [
    ['live', 'Spieltag live', 'v_spieltag'], ['paarungen', () => `Paarungen W${U.aktuelleWoche()}`, 'v_spielplan'],
    ['matchups', 'Matchups', 'v_matchup'], ['wetter', 'Wetter', 'v_wetter']]},
  markt: {l: 'Markt', frage: 'Wen holen, wen abgeben?', text: 'Beste freie Spieler, Bedarf je Team, Waiver-Reihenfolge und alle Moves.', v: [
    ['', 'Freie Spieler', 'v_waiver'], ['bedarf', 'Bedarf je Team', 'v_waiver'], ['reihenfolge', 'Reihenfolge & Claims', 'v_waiver'],
    ['moves', 'Moves', 'v_moves']]},
  keeper: {l: 'Keeper', frage: 'Wie ist der Kader langfristig aufgestellt?', text: 'Woher die Punkte kommen, Alter, Marktwert und Draft.', v: [
    ['', 'Bilanz', 'v_keeper'], ['herkunft', 'Herkunft', 'v_keeper'], ['alter', 'Alter', 'v_keeper'], ['marktwert', 'Marktwert', 'v_keeper'],
    ['draft', () => `Draft ${S.man.season}`, 'v_keeper'], ['draft-folgejahr', () => `Draft ${S.man.season + 1}`, 'v_keeper']]},
};
// Seiten ohne Tab: Startseite (Marke im Kopf, leerer Hash; Paket P2), Spielerliste und -seite (Suche im Kopf), Team-Seite,
// Erklärungen (Glossar). spieltag = Live-Ansicht (erste Ansicht der Woche, während der Saison auch der Tab Woche); „#live“ ist
// die aria-live-Region
const VIEWS = {start: 'v_start', spieler: 'v_spieler', team: 'v_team', spieltag: 'v_spieltag', erklaerungen: 'v_lesart'};
const IN_BEREICH = {spieltag: ['woche', 'live']};
// Alte Hashes (bis 04.10.2026) → neue Routen. Es gilt der längste passende Anfang; der Rest des Pfads (Woche, Position) und
// die Parameter (?team=, ?seeding= …) bleiben, damit Lesezeichen, README, Aufträge und das Claude-Projekt weiter funktionieren.
// tests/test_routen.py prüft, dass jedes Ziel eine Route ist und die App selbst keine alten Hashes mehr verlinkt.
const ALT = {tabelle: 'liga', 'tabelle/allplay': 'staerke/allplay', 'tabelle/punkte': 'staerke/punkte', 'tabelle/coaching': 'staerke/coaching',
  'tabelle/ausblick': 'liga/playoffs', ranking: 'staerke', spielplan: 'liga/ergebnisse', rekorde: 'liga/rekorde', 'rekorde/h2h': 'liga/duelle',
  matchup: 'woche/matchups', dst: 'woche/matchups/dst', 'dst/offense': 'woche/matchups/dst', wetter: 'woche/wetter', 'woche/live': 'spieltag',
  waiver: 'markt', moves: 'markt/moves', 'moves/draft': 'keeper/draft', 'keeper/kader': 'keeper/herkunft', 'keeper/wert': 'keeper/marktwert',
  lesart: 'erklaerungen'};       // „Lesart“ heißt seit Paket P4 (04.10.2026) „Erklärungen“
const qs = q => { const s = q.toString(); return s ? '?' + s : ''; };
// Ziel einer Umleitung als Hash ohne „#“, sonst null
function umleitung(r) {
  const seg = r.path.split('/');
  for (let n = seg.length; n > 0; n--) {
    let neu = ALT[seg.slice(0, n).join('/')];
    if (neu == null) continue;
    // D/ST-Streaming „nur freie D/ST“ (Entscheidung 6: Streaming entfällt) → freie D/ST unter Markt › Freie Spieler
    if (seg[0] === 'dst' && r.q.get('frei') === '1') return 'markt?pos=' + encodeURIComponent('D/ST');
    if (!neu.startsWith('woche/matchups/dst')) neu = [neu, ...seg.slice(n)].join('/');
    return neu + qs(r.q);
  }
  // Woche ohne Ansicht: während der Saison der Spieltag live, davor und danach die Paarungen der laufenden Woche
  if (r.sec === 'woche' && !r.sub) return U.saisonLaeuft() ? 'spieltag' : 'woche/paarungen';
  return null;
}
// Route → Modul und Bereich; null bei leerer oder unbekannter Route (dann die Startseite) bzw. unbekannter Ansicht (dann die
// erste des Bereichs)
function resolve(r) {
  if (VIEWS[r.sec]) {
    const [k, view] = IN_BEREICH[r.sec] || [];
    return {mod: VIEWS[r.sec], k, view, sub: r.sub, base: r.sec};
  }
  const B = BEREICHE[r.sec];
  if (!B) return null;
  // längster Ansichtspfad, mit dem der Hash beginnt (ein Pfad wie a/b vor a); die Ansicht '' nur ohne Unterpfad
  let e = null;
  for (const x of B.v) {
    const passt = x[0] ? r.sub === x[0] || r.sub.startsWith(x[0] + '/') : !r.sub;
    if (passt && (!e || x[0].length > e[0].length)) e = x;
  }
  if (!e) return {k: r.sec, fehlt: true};
  const view = e[0].split('/')[0];
  return {mod: e[2], k: r.sec, view, sub: r.sub.slice(view.length).replace(/^\//, ''), base: r.sec + (view ? '/' + view : '')};
}
const chipHref = (k, p) => k === 'woche' && p === 'live' ? '#spieltag' : '#' + k + (p ? '/' + p : '');
// Was beim Wechsel zwischen Ansichten eines Bereichs mitgeht: die Einzelwoche zwischen All-Play, Punkte und Coaching (wie vor
// P1 in der Tabelle) und die Sicht eines Teams (?team= von der Team-Seite) zwischen den drei Markt-Ansichten mit Stand des Tageslaufs
const MIT_WOCHE = ['allplay', 'punkte', 'coaching'], MIT_TEAM = ['', 'bedarf', 'reihenfolge'];
// Bereich für U.kopf: Name, Frage, Satz und die Chips der Ansichten (Funktionen erst hier ausgewertet, die Daten stehen dann)
function bereich(k, r) {
  const B = BEREICHE[k];
  const woche = k === 'staerke' && MIT_WOCHE.includes(r.view) && /^w\d+$/.test(r.sub) ? '/' + r.sub : '';
  const team = k === 'markt' && MIT_TEAM.includes(r.view) && U.team(r.q.get('team')) ? '?team=' + r.q.get('team') : '';
  const mit = p => k === 'staerke' && MIT_WOCHE.includes(p) ? woche : k === 'markt' && MIT_TEAM.includes(p) ? team : '';
  return {k, l: B.l, frage: B.frage, text: B.text,
    chips: B.v.filter(x => x[1]).map(([p, l]) => [chipHref(k, p) + mit(p), typeof l === 'function' ? l() : l, p])};
}
let seq = 0, cur = null, curHash = null;
// Aufräumen einer Ansicht: fn läuft einmal beim nächsten Routenwechsel (auch wenn dieselbe Ansicht neu gezeichnet wird)
const leaving = [];
function onLeave(fn) { leaving.push(fn); }
// Scrollposition je Verlaufseintrag: beim Verlassen (Link-Klick) und nach jedem Scrollen in history.state.y sichern,
// damit „Zurück“ die alte Stelle wiederfindet. Neue Einträge haben keinen state – daran erkennt der Router den Rückweg.
try { history.scrollRestoration = 'manual'; } catch { /* ältere Browser: Standardverhalten */ }
function saveY() {
  try { history.replaceState({...(history.state || {}), y: Math.round(scrollY)}, ''); } catch { /* Safari begrenzt replaceState */ }
}
let saveT = 0;
addEventListener('scroll', () => { clearTimeout(saveT); saveT = setTimeout(saveY, 250); }, {passive: true});
// Nach dem Rendern zur gesicherten Stelle; nachgeladene Teile (Kader, Historie) machen die Seite erst nach und nach hoch genug
function restore(y, my) {
  const t0 = performance.now();
  const step = () => {
    if (my !== seq) return;
    const max = document.documentElement.scrollHeight - innerHeight;
    if (max >= y - 2 || performance.now() - t0 > 2000) { scrollTo(0, Math.max(0, Math.min(y, max))); return; }
    requestAnimationFrame(step);
  };
  step();
}
// Seiten mit eigenem Inhalt je Unterpfad (Team, Spielerdetail) beginnen oben, ebenso jede andere Ansicht eines Bereichs;
// Wochen-, Positions- und Unteransichts-Chips derselben Ansicht behalten die Scrollposition
const viewKey = (r, res) => res.k ? res.k + '/' + res.view : r.sec === 'team' || (r.sec === 'spieler' && r.sub) ? r.path : r.sec;
function parse() {
  let raw = location.hash.slice(1);
  try { raw = decodeURIComponent(raw); } catch { /* unverändert */ }
  const [path, q] = raw.split('?');
  const [sec, ...rest] = path.split('/');
  return {sec, sub: rest.join('/'), q: new URLSearchParams(q || ''), path};
}
async function route() {
  const r = parse();
  // alte Hashes und „#woche“ umschreiben, ohne einen Verlaufseintrag anzulegen
  const ziel = umleitung(r);
  if (ziel != null) {
    history.replaceState(history.state, '', '#' + ziel);
    return route();
  }
  const res = resolve(r);
  if (!res || res.fehlt) {
    if (r.sec === 'main' && cur) return;     // Sprungmarke „Zum Inhalt“ ohne JS-Klick
    history.replaceState(null, '', '#' + (res ? res.k : 'start'));
    return route();
  }
  Object.assign(r, {view: res.view, sub: res.sub, base: res.base});
  r.B = res.k ? bereich(res.k, r) : null;
  U.closePop(false);
  for (const fn of leaving.splice(0)) { try { fn(); } catch (e) { console.error(e); } }
  const my = ++seq;
  r.alive = () => my === seq;
  // Rückweg (Zurück/Vor): der Eintrag trägt eine gesicherte Position; neue Einträge nicht
  const backY = Number.isFinite(history.state?.y) ? history.state.y : null;
  r.back = backY != null;
  // Rückweg der Spielerseite: nur bei einem echten Seitenwechsel neu setzen; ein Neuzeichnen derselben Seite (Mein Team, Daten
  // neu laden, Erneut versuchen) behält ihn. perLink: per Link gekommen, nicht über Zurück/Vor
  if (curHash !== location.hash) { S.prevHash = curHash; S.perLink = !r.back; }
  curHash = location.hash;
  document.documentElement.dataset.route = r.sec;
  // Tab des Bereichs (Spieltag live: Woche); Startseite, Spieler, Team und Erklärungen gehören zu keinem Bereich
  for (const a of document.querySelectorAll('.tabs a')) {
    if (a.dataset.s === res.k) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  const key = viewKey(r, res), same = cur === key;
  cur = key;
  const box = h('div', {class: 'view'}, h('p', {class: 'loading'}, 'Lade …'));
  // gleiche Ansicht: Höhe halten, sonst verkürzt der Ladehinweis die Seite kurz und der Browser springt nach oben
  if (same) main.style.minHeight = main.offsetHeight + 'px';
  main.replaceChildren(box);
  main.setAttribute('aria-busy', 'true');
  if (!same) scrollTo(0, 0);
  let target;
  try {
    const m = await mod(res.mod);
    if (!r.alive()) return;
    box.replaceChildren();
    target = await m.render(box, ctx, r);
  } catch (e) {
    console.error(e);
    if (r.alive() && !e.shown) box.append(U.errBox(e, () => route()));
  }
  if (!r.alive()) return;
  main.removeAttribute('aria-busy');
  main.style.minHeight = '';
  const h1 = box.querySelector('h1');
  document.title = (h1 && r.sec !== 'start' ? h1.textContent + ' · ' : '') + 'BWG Fantasy 2026';
  const f = target || h1;
  if (f) {
    f.tabIndex = -1;
    f.focus({preventScroll: same || !!target || r.back});
    if (target && !r.back) target.scrollIntoView({block: 'start'});
  }
  if (r.back) restore(backY, my);
}

// ---------------------------------------------------------------- globale Ereignisse
document.addEventListener('click', e => {
  const t = e.target;
  const b = t.closest?.('button[data-g]');
  if (b) { U.infoPop(b); return; }
  if (t.closest?.('a.skip')) { e.preventDefault(); main.focus(); return; }
  if (t.closest?.('a[href^="#"]')) saveY();     // Position des alten Eintrags vor dem Wechsel sichern
  const p = $('pop');
  // Knöpfe, die selbst ein Fenster öffnen (Kopf, „Mein Team wählen“ auf der Startseite), schließen es nicht gleich wieder
  if (!p.hidden && !p.contains(t) && !t.closest?.('#stand,#such,#mt,[data-pop]')) U.closePop(false);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('pop').hidden) { e.preventDefault(); U.closePop(true); }
});

start();
