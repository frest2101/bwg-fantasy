// Spieler (lädt players.json, dazu waiver.json als Tagesstand; kein Tab, Einstieg über die Suche im Kopf): Liste mit Filtern
// in 50er-Blöcken (#spieler), Detail #spieler/<id> mit Formkurve, Rest der Saison (ROS), Matchup je Position (Feld mu,
// Wetterzeile aus wetter.json), Marktwert (FantasyCalc, aus waiver.json) und News-Kasten (nur Datum der letzten
// ESPN-Meldung und Verweise, nie Text). Namen nach App-Konzept 04.10.2026 (P4).
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];
// Tagesstand je Spieler (waiver.json, stündlich) überlagert diese Wochenwerte: Team, Status, Verletzung, Besitz
const DAILY = ['team', 'status', 'inj', 'own'];
// Marktwert je Spieler (waiver.json, nur bei Spielern mit Wert; täglich von FantasyCalc)
const WERT = ['wert', 'wert_rang', 'wert_posrang', 'wert_trend', 'wert_ue'];
// Rückweg zur Liste: zuletzt geöffneter Spieler und die Spaltenfilter der Liste (Modul bleibt geladen, gilt bis zum Neuladen)
let lastOpened = null, keptFilters = {};
// Spieler ohne NFL-Team (entlassen, vereinslos) heißen „FA“ statt „null“
export const nflTxt = p => p.nfl || 'FA';
// Suche ohne Groß/klein, Akzente, Punkte, Apostrophe und Bindestriche: „aj brown“ findet A.J. Brown, „amon ra“ Amon-Ra St. Brown
export const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .replace(/-/g, ' ').replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
const spiele = n => `${n ?? 0} ${n === 1 ? 'Spiel' : 'Spiele'}`;
// nach der letzten Woche (ROS nach W17, Stufe 4) gibt es keine Restwoche mehr – kein „ab Wochenabruf“, kein Ersatzniveau
const seasonEnd = P => P.ros_nach_woche != null && P.ros_nach_woche >= (S.weeks.at(-1)?.week ?? 17);
// Rückweg-Ziele für den Link oben im Spielerdetail
const BACK = {spieler: 'Spielerliste', team: 'Team', liga: 'Liga', staerke: 'Stärke', woche: 'Woche', markt: 'Markt', keeper: 'Keeper',
  spieltag: 'Spieltag live'};

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const detail = r.sub && r.sub !== '';
  const h1 = h('h1', null, 'Spieler');
  U.ap(box, h1);
  const P = await ctx.lazy('players.json', 'Spielerdaten', box);
  if (!r.alive()) return;
  // Tagesstand ist Zugabe: ohne waiver.json (vor dem ersten Tageslauf, Ladefehler) gilt der Wochenstand
  const W = S.man.files?.['waiver.json'] ? await ctx.load('waiver.json').catch(() => null) : null;
  // Wetter ebenso (nur Spielerseite): ohne wetter.json keine Wetterzeile
  const WX = detail && S.man.files?.['wetter.json'] ? await ctx.load('wetter.json').catch(() => null) : null;
  const wx = WX ? await ctx.mod('v_wetter').catch(() => null) : null;
  // Herkunft (nur Spielerseite): ohne keeper.json fehlt die Zeile; v_keeper liefert auch die Marktwert-Hilfen
  const K = detail && S.man.files?.['keeper.json'] ? await ctx.load('keeper.json').catch(() => null) : null;
  const kp = detail ? await ctx.mod('v_keeper').catch(() => null) : null;
  if (!r.alive()) return;
  const svg = await ctx.mod('svg');
  const rosWhy = P.ros_nach_woche == null ? `ab Wochenabruf W${S.tw + 1}` : seasonEnd(P) ? 'Saison beendet, keine Restwoche' : 'keine Projektion';
  const rows = merge(P, W);
  const wline = wx ? p => { const g = wx.gameOf(WX, p.nfl); return g ? wx.line(g) : null; } : null;
  // Herkunft nur, wenn keeper.json den Spieler beim selben Team führt wie der Tagesstand
  const origin = kp && K ? p => {
    const o = kp.byPlayer(K).get(p.id);
    return o && o.team === p.team ? [kp.herkunft(o, K, true), kp.alterTxt(o)] : null;
  } : null;
  if (detail) one(box, h1, P, W, rows, r, svg, rosWhy, wline, origin, kp);
  else list(box, W, rows, r, rosWhy, P.ersatz || {}, P.ros_nach_woche != null && !seasonEnd(P));
}

// Wochenwerte je Spieler mit dem Tagesstand überlagern (Schlüssel: Spieler-ID); ohne Tagesstand unverändert.
// Spieler, die nur der Tagesstand kennt, kommen mit „–“ dazu statt zu fehlen: Kaderspieler, die unter der Woche geholt
// wurden, und freie Spieler mit Marktwert, die players.json nicht führt (ohne Einsatz, nicht unter den besten Free Agents).
export function merge(P, W) {
  const daily = new Map((W?.spieler || []).map(x => [x.id, x]));
  const rows = P.players.map(p => {
    const d = daily.get(p.id);
    if (!d) return p;
    const out = {...p, own_d: d.own_d, started: d.started, waiver_bis: d.waiver_bis, proj_n: d.proj, news: d.news};
    for (const k of [...DAILY, ...WERT]) if (d[k] !== undefined) out[k] = d[k];
    return out;
  });
  const known = new Set(P.players.map(p => p.id));
  for (const d of daily.values()) {
    if (known.has(d.id) || !(d.team > 0 || d.wert != null)) continue;
    const out = {id: d.id, name: d.name ?? `Spieler ${d.id}`, pos: d.pos ?? null, nfl: d.nfl ?? null, team: d.team, status: d.status, inj: d.inj,
      own: d.own, own_d: d.own_d, started: d.started, waiver_bis: d.waiver_bis, proj_n: d.proj, news: d.news, fp: d.fp, nur_tag: true};
    for (const k of WERT) if (d[k] !== undefined) out[k] = d[k];
    rows.push(out);
  }
  return rows;
}

const trendTxt = t => {
  const v = t === 'up' || t === 1 ? '↑' : t === 'down' || t === -1 ? '↓' : t === 'flat' || t === 0 ? '→' : t;
  return v ? h('span', {class: v === '↑' ? 'up' : v === '↓' ? 'dn' : 'eq', title: 'Trend'}, v,
    h('span', {class: 'vh'}, v === '↑' ? ' steigend' : v === '↓' ? ' fallend' : ' stabil')) : null;
};
function stand(W) {
  if (W?.stand) return h('p', {class: 'note'}, U.standTxt(W.stand), ' ', U.ib('tagesstand', ''));
  const ds = S.man.datenstand || {}, w = S.weeks.find(x => x.week === (ds.pool_woche ?? S.tw) + 1);
  return h('p', {class: 'note'}, `Besitz und Verletzung: Stand nach W${ds.pool_woche ?? S.tw}` + (w ? ` (${U.datum(w.start)})` : ''), ' ', U.ib('besitz', ''));
}

function list(box, W, all, r, rosWhy, ersatz, hasRos) {
  const q = r.q;
  const st = {pos: POS.includes(q.get('pos')) ? q.get('pos') : '', status: ['kader', 'frei'].includes(q.get('status')) ? q.get('status') : 'alle',
    team: +q.get('team') || 0, sicht: ['ros', 'besitz'].includes(q.get('sicht')) ? q.get('sicht') : 'saison', raw: (q.get('q') || '').trim()};
  st.text = norm(st.raw);
  for (const p of all) p._n ??= norm(p.name);
  // Spaltenfilter bleiben nur auf dem Rückweg (Zurück, „← Spielerliste“) erhalten; ein frischer Aufruf beginnt ohne
  if (!r.back) keptFilters = {};
  const count = h('span', {class: 'note cnt2', 'aria-live': 'polite'});
  const slotBox = h('div'), legBox = h('div');
  // „–“ bei „Vorteil Rest Saison“: ohne freien Spieler der Position gibt es kein Ersatzniveau (z. B. alle D/ST vergeben)
  const ueWhy = p => hasRos && !U.ok(ersatz[p.pos]) ? 'kein freier Spieler der Position' : rosWhy;
  const rows = () => all.filter(p => (!st.pos || p.pos === st.pos)
    && (st.status === 'alle' || (st.status === 'kader' ? p.team > 0 : !(p.team > 0)))
    && (!st.team || p.team === st.team)
    && (!st.text || p._n.includes(st.text)));
  const num = (k, l, f = U.num, why) => ({k, l, num: 1, v: p => p[k], f: p => U.val(p[k], f, why)});
  const base = [
    {k: 'name', l: 'Spieler', v: p => p.name.toLowerCase(), d: 1, flt: false, f: p => h('a', {href: '#spieler/' + p.id, class: 'pl'},
      h('span', null, p.name, U.inj(p.inj)), h('span', {class: 'sub'}, `${p.pos ?? '–'} · ${nflTxt(p)}` + (p.team > 0 ? ' · ' + U.kz(p.team) : '')))},
    num('avg', 'Ø Punkte', U.num, 'ohne Spiel'),
    {k: 'form', l: 'Form', num: 1, v: p => p.form, f: p => [U.val(p.form, U.num, 'ohne Spiel'), ' ', trendTxt(p.trend)]},
    num('ros_g', 'Rest je Spiel', U.num, rosWhy)];
  const extra = {
    saison: [num('pts', 'Pkt'), num('g', 'Spiele', v => v), num('floor', 'Floor', U.num, 'ohne Spiel'), num('ceil', 'Ceiling', U.num, 'ohne Spiel'),
      {...num('sd', 'Schwankung', U.num, 'unter 2 Spielen'), d: 1}, num('starts', 'Starts', v => v), num('bench_pts', 'Bankpunkte'),
      num('proj_d', 'Ist − Projektion', U.sgn, 'ohne Spiel'), {k: 'spark', l: 'Formkurve', f: p => h('span', {class: 'sp', 'aria-hidden': 'true'}, p.spark || '')}],
    ros: [num('ros', 'Rest Saison', U.num, rosWhy), num('rest_g', 'Restspiele', v => v, rosWhy), num('ros_po', 'Rest Playoffs', U.num, rosWhy),
      {...num('ros_rang', 'Rang Rest je Spiel', v => v + '.', rosWhy), d: 1}, {k: 'ros_ue', l: 'Vorteil Rest Saison', num: 1, v: p => p.ros_ue, f: p => U.val(p.ros_ue, U.sgn, ueWhy(p))},
      {k: 'bye', l: 'Bye', num: 1, cat: 1, v: p => p.bye, d: 1, f: p => U.val(p.bye, v => 'W' + v, 'kein NFL-Team')}],
    besitz: [num('own', 'Besitz %', v => U.pct(v)),
      ...(W ? [num('own_d', 'seit gestern', v => U.sgn(v, 2), 'keine Tagesdaten'), num('started', 'aufgestellt %', v => U.pct(v), 'keine Tagesdaten')] : []),
      {k: 'inj', l: 'Verletzung', v: p => U.INJ[p.inj] ? p.inj : null, d: 1, f: p => U.INJ[p.inj]?.[1] || (p.inj === 'ACTIVE' ? 'aktiv' : '–')},
      {k: 'team', l: 'Team', v: p => U.kz(p.team), d: 1, f: p => p.team > 0 ? U.tl(p.team) : (U.STAT[p.status] || 'frei')}]};
  const sortKey = {saison: 'pts', ros: 'ros_g', besitz: 'own'};
  const filters = [{k: 'nfl', l: 'NFL-Team', v: nflTxt, d: 1, cat: 1, f: nflTxt}];
  // Sortierspalte der Sicht direkt hinter den Namen: auf dem Handy sonst erst nach Wischen sichtbar
  const colsFor = sicht => {
    const all = [...base, ...extra[sicht]], key = sortKey[sicht];
    return [all[0], all.find(c => c.k === key), ...all.slice(1).filter(c => c.k !== key)];
  };
  const LEG = {saison: ['spiele', 'floor-ceil', 'konstanz', 'starts', 'proj-delta-sp'], ros: ['ros', 'restspiele', 'ros-po', 'ros-rang', 'ros-ue', 'ersatz', 'projektionen'],
    besitz: [W ? 'besitz-trend' : 'besitz']};
  const setCount = (n, total) => { count.textContent = n < total ? `${n} von ${total} Spielern` : `${total} Spieler`; };
  let tbl, first = true;
  const build = () => {
    const cols = colsFor(st.sicht), rs = rows();
    // Spaltenfilter ohne Spalte in dieser Sicht fallen weg (sonst greifen sie unsichtbar beim Zurückwechseln)
    for (const k in keptFilters) if (k !== 'nfl' && !cols.some(c => c.k === k)) delete keptFilters[k];
    legBox.replaceChildren(U.legend(['filter', 'avg', 'form-sp', 'trendpfeil', 'ros-spiel', ...LEG[st.sicht]]));
    // Rückweg: so viele 50er-Blöcke zeigen, dass der zuletzt geöffnete Spieler dabei ist
    let show = 50;
    if (first && r.back && lastOpened != null) {
      const sc = cols.find(c => c.k === sortKey[st.sicht]);
      const i = U.sortRows(rs, sc.v, -1).findIndex(p => p.id === lastOpened);
      if (i >= 50) show = Math.ceil((i + 1) / 50) * 50;
    }
    first = false;
    tbl = U.table({cap: 'Spielerliste', cls: 'nr', rh: 0, rows: rs, sort: [sortKey[st.sicht], -1], limit: 50, show, filter: true, filters,
      fstate: keptFilters, cols, aside: count, onCount: setCount});
    slotBox.replaceChildren(tbl);
  };
  const refresh = (rebuild) => {
    if (rebuild) build(); else tbl.upd(rows());
    U.setQ('spieler', {pos: st.pos || null, status: st.status !== 'alle' ? st.status : null, team: st.team || null, sicht: st.sicht !== 'saison' ? st.sicht : null, q: st.raw || null});
  };
  let timer;
  U.ap(box, stand(W),
    h('div', {class: 'row'}, U.seg('Position', [['', 'Alle'], ...POS.map(p => [p, p])], st.pos, v => { st.pos = v; refresh(); }, 'tight')),
    h('div', {class: 'row'}, U.seg('Status', [['alle', 'Alle'], ['kader', 'Kader'], ['frei', 'Frei']], st.status, v => { st.status = v; refresh(); }),
      h('label', null, h('span', {class: 'vh'}, 'Fantasy-Team '), h('select', {onchange: e => { st.team = +e.target.value; refresh(); }},
        h('option', {value: 0}, 'Alle Teams'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === st.team}, t.name))))),
    h('div', {class: 'row srch'}, h('label', null, h('span', {class: 'vh'}, 'Spieler suchen'),
      h('input', {type: 'search', placeholder: 'Suchen', value: st.raw || null, oninput: e => {
        clearTimeout(timer);
        timer = setTimeout(() => { st.raw = e.target.value.trim(); st.text = norm(st.raw); refresh(); }, 150);
      }})),
    U.seg('Spalten', [['saison', 'Saison'], ['ros', 'Rest Saison'], ['besitz', 'Besitz']], st.sicht, v => { st.sicht = v; refresh(true); })),
    slotBox, legBox);
  refresh(true);
}

// ---------------------------------------------------------------- Deep-Links (nur Verweise, keine Texte)
const SUFFIX = /\s+(jr|sr|ii|iii|iv|v)\.?$/i;
// FantasyPros-D/ST-Seiten heißen <stadt>-defense.php (alle 32 geprüft 30.09.2026), Schlüssel = ESPN-Kürzel
const FP_DST = {ARI: 'arizona', ATL: 'atlanta', BAL: 'baltimore', BUF: 'buffalo', CAR: 'carolina', CHI: 'chicago', CIN: 'cincinnati', CLE: 'cleveland',
  DAL: 'dallas', DEN: 'denver', DET: 'detroit', GB: 'green-bay', HOU: 'houston', IND: 'indianapolis', JAX: 'jacksonville', KC: 'kansas-city',
  LAC: 'los-angeles-chargers', LAR: 'los-angeles-rams', LV: 'las-vegas', MIA: 'miami', MIN: 'minnesota', NE: 'new-england', NO: 'new-orleans',
  NYG: 'new-york-giants', NYJ: 'new-york-jets', PHI: 'philadelphia', PIT: 'pittsburgh', SEA: 'seattle', SF: 'san-francisco', TB: 'tampa-bay',
  TEN: 'tennessee', WSH: 'washington'};
// FantasyPros-Adresse fp aus dem Abgleich mit der Sitemap (Wochenabruf, scripts/fantasypros.py): Namensvettern tragen dort die
// Position (josh-allen-qb). null = keine eindeutige Zuordnung → Seitensuche (DuckDuckGo, site:fantasypros.com; die Suche der Seite
// nimmt keinen Begriff aus der Adresse). Fehlt fp (noch kein Auszug), gilt die alte Regel: bei Namenszusatz Suche, sonst der Slug
// aus dem Namen (Kleinbuchstaben ohne Akzente, Apostrophe und Punkte, Bindestriche zwischen den Teilen)
const FP_SUCHE = 'https://duckduckgo.com/?q=';
export const fpUrl = (name, nfl, fp) => FP_DST[nfl] && /D\/ST$/.test(name) ? `https://www.fantasypros.com/nfl/players/${FP_DST[nfl]}-defense.php`
  : fp ? `https://www.fantasypros.com/nfl/players/${fp}.php`
  : fp === null || SUFFIX.test(name) ? FP_SUCHE + encodeURIComponent('site:fantasypros.com ' + name)
  : `https://www.fantasypros.com/nfl/players/${name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/['’.]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}.php`;
// ESPN-Liga: ohne Login lesbar, solange die Saison bei ESPN die laufende ist (eine vergangene Saison verlangt Login, geprüft 30.09.2026)
const LIGA = 1166555857;
// NBC-/Rotoworld-Spielerseiten tragen eine NBC-eigene ID, und die NBC-Suche zeigt über die Adresse keine Treffer; für D/ST (keine
// NBC-Spielerseite) die Rotoworld-Team-News /nfl/<team>/player-news, Schlüssel = ESPN-Kürzel (alle 32 geprüft 30.09.2026)
const NBC_TEAM = {ARI: 'arizona-cardinals', ATL: 'atlanta-falcons', BAL: 'baltimore-ravens', BUF: 'buffalo-bills', CAR: 'carolina-panthers',
  CHI: 'chicago-bears', CIN: 'cincinnati-bengals', CLE: 'cleveland-browns', DAL: 'dallas-cowboys', DEN: 'denver-broncos', DET: 'detroit-lions',
  GB: 'green-bay-packers', HOU: 'houston-texans', IND: 'indianapolis-colts', JAX: 'jacksonville-jaguars', KC: 'kansas-city-chiefs',
  LAC: 'los-angeles-chargers', LAR: 'los-angeles-rams', LV: 'las-vegas-raiders', MIA: 'miami-dolphins', MIN: 'minnesota-vikings',
  NE: 'new-england-patriots', NO: 'new-orleans-saints', NYG: 'new-york-giants', NYJ: 'new-york-jets', PHI: 'philadelphia-eagles',
  PIT: 'pittsburgh-steelers', SEA: 'seattle-seahawks', SF: 'san-francisco-49ers', TB: 'tampa-bay-buccaneers', TEN: 'tennessee-titans',
  WSH: 'washington-commanders'};
// Spieler: Seitensuche wie bei FantasyPros; der volle ESPN-Name mit Zusatz trifft Namensvettern über die Adresse (marvin-harrison-jr),
// „www.“ hält die alte Statistikseite scores.nbcsports.com fern, „news stats bio“ trifft den Titel der Spielerseiten
export const nbcUrl = (name, nfl, dst) => dst ? (NBC_TEAM[nfl] ? `https://www.nbcsports.com/nfl/${NBC_TEAM[nfl]}/player-news` : null)
  : `https://duckduckgo.com/?q=${encodeURIComponent(`site:www.nbcsports.com ${name} news stats bio`)}`;
export function links(p) {
  const dst = p.pos === 'D/ST' || p.id < 0;
  // ESPN hat für die Fantasy-Spielerkarte keine Adresse (Pop-up, football/player gibt 404); sie öffnet sich in den Liga-Kadern
  // per Klick auf den Namen. Nicht die Teamseite football/team: Die öffnet auf dem iPhone laut apple-app-site-association die ESPN-Fantasy-App,
  // und die zeigt so offenbar nur das eigene Team (Test Stephan 30.09.2026). seasonId ist Pflicht (sonst gilt die Saison aus ESPNs Cookie).
  // Nur für Kaderspieler und nur, bis die letzte Woche der Saison final ist.
  const kader = p.team > 0 && S.weeks.at(-1)?.status !== 'final';
  const nbc = nbcUrl(p.name, p.nfl, dst), fp = fpUrl(p.name, p.nfl, p.fp);
  return [
    dst ? [`https://www.espn.com/nfl/team/_/name/${String(p.nfl || '').toLowerCase()}`, 'ESPN-Teamseite']
      : [`https://www.espn.com/nfl/player/_/id/${p.id}`, 'ESPN-Spielerseite'],
    kader ? [`https://fantasy.espn.com/football/league/rosters?leagueId=${LIGA}&seasonId=${S.man.season}`, 'ESPN Fantasy – Liga-Kader'] : null,
    dst && !FP_DST[p.nfl] ? null : [fp, fp.startsWith(FP_SUCHE) ? 'FantasyPros – Suche' : 'FantasyPros'],
    nbc ? [nbc, dst ? 'NBC Rotoworld – Team-News' : 'NBC Rotoworld – Suche'] : null].filter(Boolean);
}
function newsBox(p, W) {
  const last = !W ? U.na('keine Tagesdaten') : U.ok(p.news) ? U.stamp(p.news) : U.na('keine Meldung');
  return U.card('News', h('p', null, 'Letzte ESPN-Meldung: ', h('strong', null, last), ' ', U.ib('news', '')),
    h('div', {class: 'row'}, links(p).map(([href, text]) => h('a', {href, target: '_blank', rel: 'noopener', class: 'btn'}, text, h('span', {class: 'vh'}, ' (neues Fenster)')))),
    h('p', {class: 'note'}, 'Nur Verweise: Die App übernimmt keine Texte. ', W?.stand ? `${U.standTxt(W.stand)}.` : ''));
}

// Marktwert (FantasyCalc, Tagesstand waiver.json): Marktwert, Marktwert-Rang, Trend und Abstand zur Keeper-Linie mit Quelle
// nahe bei den Zahlen
function marktwert(p, W, kp) {
  if (!kp || !W?.wert_stand) return null;
  const why = p.pos === 'K' || p.pos === 'D/ST' ? 'K und D/ST ohne Marktwert' : 'nicht bei FantasyCalc';
  if (!U.ok(p.wert)) return [h('h2', null, 'Marktwert'), h('p', {class: 'note'}, `Kein Marktwert: ${why}. `, kp.fcQuelle(), '.')];
  return [h('h2', null, 'Marktwert'), h('div', {class: 'tiles'},
    U.tile('Marktwert', kp.wertTxt(p.wert), 'Dynasty, Superflex', 'marktwert'),
    U.tile('Marktwert-Rang', `${p.wert_rang}.`, `${p.pos} ${p.wert_posrang}.`, 'marktwert'),
    U.tile('Trend 30 Tage', kp.wertSgn(p.wert_trend), null, 'wert-trend'),
    U.tile('über Keeper-Linie', U.val(p.wert_ue, kp.wertSgn, 'keine Keeper-Linie'), U.ok(W.keeper_linie) ? `Linie ${kp.wertTxt(W.keeper_linie)}` : null, 'wert-ue')),
  h('p', {class: 'note'}, kp.fcQuelle(), ` · ${U.standTxt(W.wert_stand)} · Tauschpreis, keine Punktprognose. Vergleich mit anderen Spielern: `, kp.fcRechner(), '.')];
}

function one(box, h1, P, W, rows, r, svg, rosWhy, wline, origin, kp) {
  const pid = r.sub;
  const p = rows.find(x => String(x.id) === pid);
  // Rückweg: kam man per Link aus der App, führt „← zurück“ per Verlauf dorthin (mit Filtern und Scrollposition)
  const prev = S.prevHash?.slice(1).split(/[/?]/)[0];
  const back = S.perLink && BACK[prev] && S.prevHash !== location.hash;
  U.ap(box, h('p', null, back
    ? h('a', {href: S.prevHash, onclick: e => { e.preventDefault(); history.back(); }}, '← ' + (prev === 'team' ? 'zurück zum Team' : 'zurück: ' + BACK[prev]))
    : h('a', {href: '#spieler'}, '← Spielerliste')));
  if (p) lastOpened = p.id;
  if (!p) { h1.textContent = 'Spieler nicht gefunden'; U.ap(box, h('p', {class: 'note'}, 'Dieser Spieler steht nicht in den App-Daten (nur Kader, Spieler mit Einsatz, die besten Free Agents und Spieler mit Marktwert).')); return; }
  h1.textContent = p.name;
  const ers = P.ersatz?.[p.pos];
  U.ap(box, h('p', null, `${p.pos ?? '–'} · ${nflTxt(p)} · `, p.team > 0 ? U.tl(p.team) : U.STAT[p.status] || 'frei',
    p.inj && U.INJ[p.inj] ? h('span', {class: 'badge'}, U.INJ[p.inj][1]) : null,
    U.ok(p.bye) ? ` · Bye W${p.bye}` : null,
    p.pos === 'D/ST' ? [' · ', h('a', {href: '#woche/matchups/dst'}, 'Matchups D/ST')] : null), stand(W),
  p.team > 0 && origin?.(p) ? h('p', {class: 'note'}, 'Herkunft: ', h('strong', null, origin(p)[0]), ' · ',
    origin(p)[1] ? [origin(p)[1], ' ', U.ib('alter', ''), ' · '] : null,   // i-Text nennt Stichtag, Quelle und Lizenz
    h('a', {href: '#keeper/herkunft?team=' + p.team}, 'Keeper › Herkunft'), ' ', U.ib('herkunft', '')) : null,
  h('div', {class: 'tiles'},
    U.tile('Pkt Saison', U.num(p.pts), spiele(p.g), 'spiele'),
    U.tile('Ø Punkte', U.val(p.avg, U.num, 'ohne Spiel'), null, 'avg'),
    U.tile('Floor / Ceiling', `${U.num(p.floor)} / ${U.num(p.ceil)}`, null, 'floor-ceil'),
    U.tile('Schwan­kung', U.val(p.sd, U.num, 'unter 2 Spielen'), null, 'konstanz'),     // weiches Trennzeichen: schmale Kachel
    U.tile('Form', [U.val(p.form, U.num, 'ohne Spiel'), ' ', trendTxt(p.trend)], `Form zu Saison ${U.sgn(p.form_d)}`, 'form-sp'),
    U.tile('Starts', U.val(p.starts, v => v), `Bankpunkte ${U.num(p.bench_pts)}`, 'starts'),
    U.tile('Ist − Projektion', U.val(p.proj_d, U.sgn, 'ohne Spiel'), null, 'proj-delta-sp'),
    U.tile('Besitz', U.val(p.own, v => U.pct(v)), [U.STAT[p.status] || p.status, W && U.ok(p.own_d) ? ` · seit gestern ${U.sgn(p.own_d, 2)}` : ''], W ? 'besitz-trend' : 'besitz'),
    W ? U.tile(`Projektion W${W.woche}`, U.val(p.proj_n, U.num, 'noch keine ESPN-Projektion'),
      p.status === 'WAIVERS' && U.ok(p.waiver_bis) ? `Frist ${U.stamp(p.waiver_bis)}` : null, 'proj-naechste') : null),
  newsBox(p, W), marktwert(p, W, kp));
  if (p.nur_tag) {
    U.ap(box, h('p', {class: 'warn'}, p.team > 0
      ? 'Noch keine Wochendaten: Der Spieler steht laut Tageslauf im Kader, Saisonwerte und Projektionen für den Rest der Saison kommen mit dem nächsten Wochenabruf.'
      : 'Keine Wochendaten: Saisonwerte und Projektionen für den Rest der Saison führt die App für Kaderspieler, Spieler mit Einsatz und die besten Free Agents; dieser Spieler steht wegen seines Marktwerts hier.'));
    return;
  }
  const Wk = P.weeks || [], wk = p.wk || [];
  const vals = wk.map(x => x[2] ? null : x[0]);
  if (!(p.g > 0)) U.ap(box, h('p', {class: 'note'}, 'Noch kein Spiel 2026 – die Formkurve erscheint mit dem ersten Einsatz.'));
  // kleine Werte: Achse mit einer Nachkommastelle, sonst stehen dort „0 0 1 1 1“
  else U.ap(box, svg.fig('Formkurve', svg.bars({title: `Formkurve ${p.name}`,
    desc: `Punkte je Woche; ${spiele(p.g)}, Ø Punkte ${U.num(p.avg)}; „·“ = Bye, „–“ = nicht gespielt, Strich = Projektion.`,
    x: Wk.map(w => 'W' + w), vals, miss: i => wk[i]?.[2] ? '·' : '–', tick: wk.map(x => x[1]),
    cls: i => wk[i]?.[4] == null || U.bench(wk[i][4]) ? 'bN' : 'bA', label: i => U.ok(wk[i]?.[0]) ? U.num(wk[i][0], 1) : null, yfmt: v => U.num(v, Number.isInteger(v) ? 0 : 1)}),
  {heads: ['Woche', 'Pkt', 'Projektion', 'Team', 'Slot'], rows: Wk.map((w, i) => ['W' + w, wk[i]?.[2] ? 'Bye' : U.num(wk[i]?.[0]), U.num(wk[i]?.[1]),
    wk[i]?.[3] ? U.kz(wk[i][3]) : 'frei', U.slot(wk[i]?.[4])])},
  h('p', {class: 'note'}, 'Blau = Starter, grau = Bank oder ohne Team, orange Strich = ESPN-Projektion. ', U.ib('formkurve', ''))));
  U.ap(box, h('h2', null, 'Rest der Saison'), P.ros_nach_woche == null ? h('p', {class: 'warn'}, `Werte für den Rest der Saison ${rosWhy}.`) : null,
    h('div', {class: 'tiles'},
      U.tile('Rest je Spiel', U.val(p.ros_g, U.num, rosWhy), null, 'ros-spiel'),
      U.tile('Rest Saison', U.val(p.ros, U.num, rosWhy), U.ok(p.rest_g) ? `${p.rest_g} Restspiele` : null, 'ros'),
      U.tile('Rest Playoffs', U.val(p.ros_po, U.num, rosWhy), null, 'ros-po'),
      U.tile('Rang Rest je Spiel', U.val(p.ros_rang, v => `${p.pos} ${v}`, rosWhy), null, 'ros-rang'),
      U.tile('Ersatzniveau', U.val(ers, U.num, P.ros_nach_woche != null && !seasonEnd(P) ? 'kein freier Spieler der Position' : rosWhy), p.pos, 'ersatz'),
      U.tile('Vorteil Rest Saison', U.val(p.ros_ue, U.sgn, P.ros_nach_woche != null && !seasonEnd(P) && !U.ok(ers) ? 'kein freier Spieler der Position' : rosWhy), null, 'ros-ue')),
    h('p', {class: 'note'}, 'Alle Projektionen sind ESPN-Schätzungen. ', U.ib('projektionen', '')));
  matchup(box, p, P, wline?.(p));
}

// Matchup je Position der nächsten Wochen (players.json mu, Wochenstand; D/ST: Faktor der gegnerischen Offense aus
// Matchups › D/ST) und die Wetterzeile des nächsten Spiels (wetter.json, Prognose der laufenden Woche)
function matchup(box, p, P, wl) {
  const dst = p.pos === 'D/ST', m = p.mu, n1 = m?.n1;
  const why = !('mu_woche' in P) ? 'ab dem nächsten Wochenabruf' : !p.nfl ? 'kein NFL-Team' : 'kein Matchup-Wert für diese Position';
  const n1Why = !n1 ? 'keine offene Woche' : 'Bye';
  const cell = (v, reason) => U.val(v, x => h('span', {class: 'fz ' + U.fcls(x)}, U.num(x, 2)), reason);
  U.ap(box, h('h2', null, dst ? 'Matchup D/ST' : p.pos ? `Matchup ${p.pos}` : 'Matchup'),
    !m ? h('p', {class: 'note'}, `Kein Matchup-Wert: ${why}.`) : h('div', {class: 'tiles'},
      // 32 NFL-Teams: Rang 1 = höchster Faktor (F), also das günstigste Matchup
      U.tile(n1 ? `Gegner W${n1.week}` : 'Gegner', n1 ? n1.opp || 'Bye' : U.na(n1Why), n1?.opp ? (dst ? 'Offense' : 'Defense') : null, 'mu-n1'),
      U.tile('Faktor', n1?.opp ? cell(n1.f, 'kein Faktor') : U.na(n1Why), null, dst ? 'f' : 'mu-f'),
      U.tile('Rang', n1?.opp ? U.val(n1.rang, v => `${v}. von 32`, 'kein Faktor') : U.na(n1Why), '1 = günstigstes Matchup', dst ? 'f' : 'mu-rang'),
      U.tile('Faktor nächste 3', cell(m.naechste3, 'kein Spiel in den nächsten 3 Wochen'), null, dst ? 'naechste3' : 'mu-naechste3'),
      U.tile('Rest Regular Season', cell(m.rest, 'keine Regular-Season-Woche mehr'), null, dst ? 'rest' : 'mu-rest'),
      U.tile('Playoffs W15–17', cell(m.sos_po, 'kein Playoff-Spiel'), null, dst ? 'sos' : 'mu-sos')),
    !m ? null : h('p', {class: 'note'}, ...(dst
      ? ['Faktor der gegnerischen Offense, über 1,00 = günstig für die D/ST. ', h('a', {href: '#woche/matchups/dst'}, 'Matchups D/ST')]
      : ['Position gegen Defense, kein Einzelduell: Ein Faktor über 1,00 heißt, Spieler der Position holen gegen diese Defense mehr Punkte als im Schnitt. ',
        h('a', {href: '#woche/matchups/' + String(p.pos).toLowerCase()}, `Alle Defenses gegen ${p.pos}`)])),
    wl ? h('p', null, wl, ' · ', h('a', {href: '#woche/wetter'}, 'Wetter aller Spiele')) : null);
}
