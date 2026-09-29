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
Object.assign(ctx, {ui: U, S, mod, load, lazy, say, route: () => route()});

// ---------------------------------------------------------------- Laden
const cache = {};
async function getJSON(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) throw new Error(`${url.split('?')[0]}: HTTP ${r.status}`);
  return r.json();
}
function load(name) {
  const v = S.man.files?.[name]?.v ?? S.man.through_week;
  return cache[name] || (cache[name] = getJSON(`data/${name}?v=${encodeURIComponent(v)}`)
    .catch(e => { delete cache[name]; throw e; }));
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
    S.man = await getJSON('data/manifest.json?t=' + Date.now(), {cache: 'no-store'});
    if (S.man.schema > APP_SCHEMA) banner();
    const [teams, sched] = await Promise.all([load('teams.json'), load('schedule.json')]);
    setup(teams, sched);
  } catch (e) {
    console.error(e);
    main.replaceChildren(U.errBox(e, start));
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
function header() {
  const ds = S.man.datenstand || {};
  const btn = $('stand');
  const wk = n => S.weeks.find(w => w.week === n);
  // nächster Wochenabruf: Dienstag nach der laufenden Woche, 08:30 UTC
  const nxt = wk(S.tw + 2)?.start;
  const due = nxt ? new Date(nxt + 'T08:30:00Z') : null;
  const alt = due && Date.now() > due.getTime() + 27.5 * 36e5;     // Mittwoch 12:00 UTC ohne neue Woche
  btn.textContent = S.tw ? `nach W${S.tw}` : 'vor W1';
  btn.classList.toggle('alt', !!alt);
  btn.setAttribute('aria-label', `Datenstand: nach Woche ${S.tw}${alt ? ', Daten älter als erwartet' : ''}`);
  btn.hidden = false;
  const pool = ds.pool_woche != null ? wk(ds.pool_woche + 1)?.start : null;
  btn.onclick = () => U.showPop(btn, 'Datenstand', [
    alt ? h('p', {class: 'warn'}, 'Daten älter als erwartet – der Wochenabruf ist noch nicht durchgelaufen.') : null,
    h('dl', null,
      h('dt', null, 'Wertung'), h('dd', null, `nach W${ds.woche_final ?? S.tw} (final)`),
      h('dt', null, 'Projektionen'), h('dd', null, ds.ros_nach_woche != null ? `Stand nach W${ds.ros_nach_woche}` : `ab Wochenabruf W${S.tw + 1}`),
      h('dt', null, 'Besitz, Verletzung'), h('dd', null, ds.pool_woche != null ? `nach W${ds.pool_woche}` + (pool ? ` (${U.datum(pool)})` : '') : '–'),
      h('dt', null, 'Transaktionen'), h('dd', null, ds.transaktionen_bis ? `bis ${U.datum(ds.transaktionen_bis)} ${U.zeit(ds.transaktionen_bis)}` : '–'),
      h('dt', null, 'Nächster Abruf'), h('dd', null, due ? `${U.datum(due)} ${U.zeit(due)} Uhr` : '–')),
    h('p', {class: 'note'}, 'Alle Zahlen rechnen nur mit abgeschlossenen Wochen. ', h('a', {href: '#lesart/aktualisierung'}, 'Mehr zur Aktualisierung')),
  ]);
  const tb = $('theme');
  const dark = () => document.documentElement.dataset.theme === 'dark' ||
    (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  const sync = () => tb.setAttribute('aria-pressed', String(dark()));
  tb.onclick = () => {
    const t = dark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('bwg-theme', t); } catch { /* Umschalter gilt dann nur bis zum Neuladen */ }
    sync();
  };
  sync();
}

// ---------------------------------------------------------------- Router
const VIEWS = {tabelle: 'v_tabelle', ranking: 'v_ranking', spielplan: 'v_spielplan', team: 'v_team', spieler: 'v_spieler',
  dst: 'v_dst', moves: 'v_moves', rekorde: 'v_rekorde', lesart: 'v_lesart'};
const NAV = {team: 'tabelle', dst: 'spieler', moves: 'spieler'};
let seq = 0, cur = null;
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
  const my = ++seq;
  r.alive = () => my === seq;
  document.documentElement.dataset.route = r.sec;
  const navSec = NAV[r.sec] || r.sec;
  for (const a of document.querySelectorAll('.tabs a')) {
    if (a.dataset.s === navSec) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  const same = cur === r.sec;
  cur = r.sec;
  const box = h('div', {class: 'view'}, h('p', {class: 'loading'}, 'Lade …'));
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
  const h1 = box.querySelector('h1');
  document.title = (h1 ? h1.textContent + ' · ' : '') + 'BWG Fantasy 2026';
  const f = target || h1;
  if (f) {
    f.tabIndex = -1;
    f.focus({preventScroll: same || !!target});
    if (target) target.scrollIntoView({block: 'start'});
  }
}

// ---------------------------------------------------------------- globale Ereignisse
document.addEventListener('click', e => {
  const t = e.target;
  const b = t.closest?.('button[data-g]');
  if (b) { U.infoPop(b); return; }
  if (t.closest?.('a.skip')) { e.preventDefault(); main.focus(); return; }
  const p = $('pop');
  if (!p.hidden && !p.contains(t) && !t.closest?.('#stand')) U.closePop(false);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('pop').hidden) { e.preventDefault(); U.closePop(true); }
});

start();
