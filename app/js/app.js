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
Object.assign(ctx, {ui: U, S, mod, load, lazy, say, refresh, onLeave, route: () => route()});

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
    S.man = man;
    if (basis) {
      BASIS.forEach((n, i) => { cache[n] = Promise.resolve(basis[i]); });
      setup(...basis);
    }
    standChip();
    return true;
  })().finally(() => { refreshing = null; }));
}
// Lazy-Datei mit sichtbarem Ladehinweis (aria-live); bei Fehler Hinweis mit „Erneut versuchen“
async function lazy(name, label, box) {
  const p = h('p', {class: 'loading'}, `Lade ${label} …`);
  box.append(p);
  say(`Lade ${label} …`);
  try {
    const d = await load(name);
    p.remove();
    say(`${label} geladen.`);
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
  theme();
}
// Datenstand-Chip und sein Fenster; läuft nach refresh() erneut und zeigt dann den neuen Stand
function standChip() {
  const ds = S.man.datenstand || {};
  const btn = $('stand');
  const wk = n => S.weeks.find(w => w.week === n);
  // Stand-Woche: in den Playoffs die letzte finale Playoff-Woche (Stufe 4), sonst die letzte gewertete Woche
  const po = ds.playoff_woche ?? null, sw = po ?? S.tw;
  const fertig = po != null && po >= (S.weeks.at(-1)?.week ?? 17);   // nach W17 kein Wochenabruf bis zum Saisonwechsel
  // Dienstag, an dem Woche n beginnt; nach der letzten Woche des Spielplans eine Woche weiter (Abruf nach W17)
  const start = n => wk(n)?.start ?? (wk(n - 1) ? new Date(Date.parse(wk(n - 1).start + 'T12:00:00Z') + 7 * 864e5).toISOString().slice(0, 10) : null);
  // nächster Wochenabruf: Dienstag nach der laufenden Woche, 08:30 UTC
  const nxt = fertig ? null : start(sw + 2);
  const due = nxt ? new Date(nxt + 'T08:30:00Z') : null;
  const alt = due && Date.now() > due.getTime() + 27.5 * 36e5;     // Mittwoch 12:00 UTC ohne neue Woche
  btn.textContent = sw ? `nach W${sw}` : 'vor W1';
  btn.classList.toggle('alt', !!alt);
  btn.setAttribute('aria-label', `Datenstand: nach Woche ${sw}${alt ? ', Daten älter als erwartet' : ''}`);
  btn.hidden = false;
  const pool = ds.pool_woche != null ? wk(ds.pool_woche + 1)?.start : null;
  // Tagesstand (Tageslauf): Besitz, Verletzung, Projektion der nächsten Woche und Wetter; davor nur der Wochenstand
  const tag = ds.pool_stand ? `Tagesstand ${U.stamp(ds.pool_stand)}` : ds.pool_woche != null ? `nach W${ds.pool_woche}` + (pool ? ` (${U.datum(pool)})` : '') : '–';
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
    U.showPop(btn, 'Datenstand', [
      alt ? h('p', {class: 'warn'}, 'Daten älter als erwartet – der Wochenabruf ist noch nicht durchgelaufen.') : null,
      h('dl', null,
        h('dt', null, 'Wertung'), h('dd', null, `nach W${ds.woche_final ?? S.tw} (final)`),
        po ? [h('dt', null, 'Playoffs'), h('dd', null, `nach W${po} (final)`)] : null,
        h('dt', null, 'Projektionen ROS'), h('dd', null, ds.ros_nach_woche != null ? `Stand nach W${ds.ros_nach_woche}` : `ab Wochenabruf W${sw + 1}`),
        h('dt', null, ds.pool_stand ? 'Besitz, Verletzung, Projektion nächste Woche' : 'Besitz, Verletzung'), h('dd', null, tag),
        h('dt', null, 'Wetter'), h('dd', null, ds.wetter_stand ? `Tagesstand ${U.stamp(ds.wetter_stand)}` : '–'),
        h('dt', null, 'Letzter Move'), h('dd', null, ds.transaktionen_bis ? U.stamp(ds.transaktionen_bis) : '–'),
        // „ab“: geplanter Slot, GitHub startet meist rund 15 min später (Glossar „Aktualisierung“)
        h('dt', null, 'Nächster Tageslauf'), h('dd', null, `ab ${U.stamp(nextDaily())}`),
        // Tageslauf von Hand: nur ein Knopf zur Workflow-Seite, kein Start aus der App (kein Token im Browser)
        h('dd', {class: 'full'}, U.tageslaufKnopf(), neu, info),
        h('dt', null, 'Nächster Wochenabruf'), h('dd', null, fertig ? '– (Saison beendet, erst wieder nach dem Saisonwechsel)' : U.stamp(due))),
      h('p', {class: 'note'}, '„Tageslauf starten“ öffnet GitHub: dort „Run workflow“ (GitHub-Anmeldung nötig). Etwa 2 Minuten später holt „Daten neu laden“ den neuen Stand. ',
        h('a', {href: '#lesart/tageslauf-starten'}, 'Mehr dazu')),
      h('p', {class: 'note'}, 'Wertung und Projektionen rechnen nur mit abgeschlossenen Wochen; der Tageslauf frischt Besitz, Verletzung, Transaktionen und Wetter stündlich von etwa 05:00 Uhr bis Mitternacht (deutsche Zeit) auf. ', h('a', {href: '#lesart/aktualisierung'}, 'Mehr zur Aktualisierung')),
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
const VIEWS = {tabelle: 'v_tabelle', ranking: 'v_ranking', spielplan: 'v_spielplan', team: 'v_team', spieler: 'v_spieler',
  dst: 'v_dst', matchup: 'v_matchup', wetter: 'v_wetter', moves: 'v_moves', waiver: 'v_waiver', keeper: 'v_keeper', rekorde: 'v_rekorde',
  spieltag: 'v_spieltag', lesart: 'v_lesart'};       // spieltag = Live-Ansicht (Chip „Live“ im Kopf); „#live“ ist die aria-live-Region
const NAV = {team: 'tabelle', dst: 'spieler', matchup: 'spieler', wetter: 'spieler', moves: 'spieler'};
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
// Seiten mit eigenem Inhalt je Unterpfad (Team, Spielerdetail) beginnen oben; Wochen- und Ansichts-Chips derselben
// Ansicht behalten die Scrollposition
const viewKey = r => r.sec === 'team' || (r.sec === 'spieler' && r.sub) ? r.path : r.sec;
function parse() {
  let raw = location.hash.slice(1);
  try { raw = decodeURIComponent(raw); } catch { /* unverändert */ }
  const [path, qs] = raw.split('?');
  const [sec, ...rest] = path.split('/');
  return {sec, sub: rest.join('/'), q: new URLSearchParams(qs || ''), path};
}
async function route() {
  const r = parse();
  if (!VIEWS[r.sec]) {
    if (r.sec === 'main' && cur) return;     // Sprungmarke „Zum Inhalt“ ohne JS-Klick
    history.replaceState(null, '', '#tabelle');
    return route();
  }
  U.closePop(false);
  for (const fn of leaving.splice(0)) { try { fn(); } catch (e) { console.error(e); } }
  const my = ++seq;
  r.alive = () => my === seq;
  // Rückweg (Zurück/Vor): der Eintrag trägt eine gesicherte Position; neue Einträge nicht
  const backY = Number.isFinite(history.state?.y) ? history.state.y : null;
  r.back = backY != null;
  S.prevHash = curHash;
  curHash = location.hash;
  document.documentElement.dataset.route = r.sec;
  const navSec = NAV[r.sec] || r.sec;
  for (const a of document.querySelectorAll('.tabs a')) {
    if (a.dataset.s === navSec) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  // Live-Ansicht: kein Tab, der Chip im Kopf zeigt, dass sie offen ist
  if (r.sec === 'spieltag') $('lv')?.setAttribute('aria-current', 'page'); else $('lv')?.removeAttribute('aria-current');
  const key = viewKey(r), same = cur === key;
  cur = key;
  const box = h('div', {class: 'view'}, h('p', {class: 'loading'}, 'Lade …'));
  // gleiche Ansicht: Höhe halten, sonst verkürzt der Ladehinweis die Seite kurz und der Browser springt nach oben
  if (same) main.style.minHeight = main.offsetHeight + 'px';
  main.replaceChildren(box);
  main.setAttribute('aria-busy', 'true');
  if (!same) scrollTo(0, 0);
  let target;
  try {
    const m = await mod(VIEWS[r.sec]);
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
  document.title = (h1 ? h1.textContent + ' · ' : '') + 'BWG Fantasy 2026';
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
  if (!p.hidden && !p.contains(t) && !t.closest?.('#stand')) U.closePop(false);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('pop').hidden) { e.preventDefault(); U.closePop(true); }
});

start();
