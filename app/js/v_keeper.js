// Tab Keeper (lädt keeper.json): Keeper-Bilanz – woher die Punkte kommen (Keeper, Draft, Zugänge, Trades), Herkunft je
// Kaderspieler mit Vorjahresvergleich, Altersprofil je Team (Stammdaten von nflverse), Draft 2026 inklusive Keeper mit
// Ertrag. Alle Zahlen aus Python (scripts/keeper.py).
let U, S, h;
export const init = c => { U = c.ui; S = U.S; h = U.h; };
const KEY = 'bwg-team';                  // eigenes Team wie im Waiver-Tab, nur Komfort im Browser
const ARTEN = ['keeper', 'draft', 'waiver', 'free_agent', 'trade'];
const ART = {keeper: 'Keeper', draft: 'Draft', waiver: 'Waiver', free_agent: 'Free Agent', trade: 'Trade'};
// Gruppen der Punkte (Python: keeper.GRUPPEN) mit Anzeige und fester Farbe
const GRP = [['keeper', 'Keeper', 'o4'], ['draft', 'Draft', 'o1'], ['zugang', 'Zugänge', 'o3'], ['trade', 'Trades', 'o8']];

// Herkunft eines Kaderspielers (Zeile aus keeper.json kader) als Text; kurz für Tabellen, lang für die Spielerseite.
// K = keeper.json (für die Frage, ob der Pick eines getauschten Spielers ein Keeper-Pick war)
export function herkunft(r, K, lang) {
  if (!r) return null;
  const was = () => {
    if (!U.ok(r.pick)) return '';
    const kp = (K.picks || []).find(p => p.pick === r.pick)?.keeper;
    return kp ? 'Keeper' : `Draft Rd ${r.runde}`;
  };
  if (r.art === 'keeper') return lang ? `Keeper ${S.man.season}` : 'Keeper';
  if (r.art === 'draft') return lang ? `Draft ${S.man.season}, Runde ${r.runde} (Pick ${r.pick})` : `Draft Rd ${r.runde}`;
  if (r.art === 'trade') {
    const vor = was();
    if (!lang) return 'Trade';
    return 'Trade' + (U.ok(r.seit) ? ` am ${U.datum(r.seit)}` : '') + (vor ? `, zuvor ${vor} bei ${U.kz(r.von)}` : '');
  }
  const txt = ART[r.art] || r.art;
  return lang && U.ok(r.seit) ? `${txt}, geholt am ${U.datum(r.seit)}` : txt;
}
// Sortierwert der Spalte Herkunft: nach Art, Draft-Picks dazu nach Runde (Keeper-Runden sagen nichts, Trades tragen die alte)
export const herkunftOrd = r => { const i = ARTEN.indexOf(r?.art); return i < 0 ? null : i * 100 + (r.art === 'draft' ? r.runde : 0); };
export const byPlayer = K => new Map((K?.kader || []).map(r => [r.id, r]));
// Alter und NFL-Jahr eines Kaderspielers als Text („26,8 Jahre, 5. NFL-Jahr“); null ohne Stammdaten
export const alterTxt = r => r && U.ok(r.alter) ? `${U.num(r.alter, 1)} Jahre` + (r.rookie ? ', Rookie' : U.ok(r.nfl_jahr) ? `, ${r.nfl_jahr}. NFL-Jahr` : '') : null;
const POS = ['QB', 'RB', 'WR', 'TE', 'K'];

export async function render(box, ctx, r) {
  const sub = ['kader', 'alter', 'draft'].includes(r.sub) ? r.sub : '';
  // ?team=N gilt, auch 0 = Alle Teams (sonst fiele die Wahl auf dem Rückweg wieder auf das eigene Team); nur ohne
  // Parameter nimmt die Kader-Ansicht das gespeicherte Mein Team
  let team = r.q.has('team') ? +r.q.get('team') : sub === 'kader' ? +U.store.get(KEY) || 0 : 0;
  if (!S.byId.has(team)) team = 0;
  if (!S.man.files?.['keeper.json']) {
    U.ap(box, h('h1', null, 'Keeper'), h('p', {class: 'note'}, 'Noch keine Keeper-Bilanz: Sie erscheint mit dem ersten Wochenabruf nach dem Draft.'));
    return;
  }
  const views = U.chips('Ansichten Keeper', [['#keeper', 'Bilanz', ''], ['#keeper/kader', 'Kader', 'kader'], ['#keeper/alter', 'Alter', 'alter'],
    ['#keeper/draft', 'Draft', 'draft']], sub);
  U.ap(box, h('h1', null, {draft: `Draft ${S.man.season}`, kader: 'Keeper und Kader', alter: 'Alter der Kader'}[sub] || 'Keeper'), views);
  const K = await ctx.lazy('keeper.json', 'Keeper-Bilanz', box);
  if (!r.alive()) return;
  if (sub === 'draft') draft(box, K, team);
  else if (sub === 'kader') kader(box, K, team);
  else if (sub === 'alter') alter(box, K, await ctx.mod('svg'));
  else bilanz(box, K, await ctx.mod('svg'));
}

const standTxt = K => K.stand ? `Kader: Tagesstand ${U.stamp(K.stand)}` : `Kader: Stand nach W${K.through_week}`;
const teamSelect = (team, on) => h('label', null, 'Team ', h('select', {onchange: e => on(+e.target.value)},
  h('option', {value: 0}, 'Alle Teams'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === team}, t.name))));
const player = (id, name, inApp, sub, extra) => {
  const kids = [h('span', null, name ?? `Spieler ${id}`, extra), sub ? h('span', {class: 'sub'}, sub) : null];
  return inApp === false ? h('span', {class: 'pl'}, kids) : h('a', {href: '#spieler/' + id, class: 'pl'}, kids);
};

// ---------------------------------------------------------------- Bilanz: Punkte nach Herkunft je Team
function bilanz(box, K, svg) {
  const L = K.liga, wk = `W1–W${K.through_week}`;
  let key = 'pf', srt = ['keeper', -1];   // gewählte Sortierung bleibt beim Umschalten der Positionen
  const wrap = h('div'), chart = h('div');
  const draw = () => {
    const kern = key === 'kern';
    wrap.replaceChildren(U.table({cap: `Punkte nach Herkunft (${wk}${kern ? ', ohne K und D/ST' : ''})`, cls: 'nr kurz', rh: 0, rows: K.teams, sort: srt,
      onSort: (k, d) => { srt = [k, d]; }, cols: [
      {k: 't', l: 'Team', v: x => U.kz(x.team_id), d: 1, f: x => U.tl(x.team_id)},
      ...GRP.map(([g, l]) => ({k: g, l: l + ' %', num: 1, v: x => x[key].anteil[g], f: x => U.val(x[key].anteil[g], U.pct, 'noch keine Punkte')})),
      {k: 's', l: kern ? 'Pkt Kern' : 'PF', num: 1, v: x => x[key].summe, f: x => U.num(x[key].summe)},
      {k: 'kd', l: 'Keeper im Kader', num: 1, v: x => x.keeper_da, f: x => `${x.keeper_da} von ${x.keeper}`},
      {k: 'pd', l: 'Draft im Kader', num: 1, v: x => x.picks_da, f: x => `${x.picks_da} von ${x.picks}`},
      {k: 'zg', l: 'Zugänge', num: 1, v: x => x.kader.waiver + x.kader.free_agent, f: x => x.kader.waiver + x.kader.free_agent},
      {k: 'tr', l: 'Trades', num: 1, v: x => x.kader.trade, f: x => x.kader.trade}]}));
    const by = new Map(K.teams.map(t => [t.team_id, t]));
    const names = GRP.map(g => g[1]), cls = j => GRP[j][2];
    chart.replaceChildren(svg.fig('Anteile je Team', svg.stack({title: `Anteil der Punkte nach Herkunft je Team${kern ? ' (ohne K und D/ST)' : ''}`, total: 100, names, cls,
      fmt: v => U.pct(v), desc: 'Gestapelte 100-%-Balken je Team; genaue Werte in der Tabelle.',
      rows: S.teams.map(t => ({label: t.kuerzel, parts: GRP.map(([g]) => by.get(t.team_id)?.[key].anteil[g])}))}),
    {heads: ['Team', ...names], rows: S.teams.map(t => [t.name, ...GRP.map(([g]) => U.pct(by.get(t.team_id)?.[key].anteil[g]))])}, svg.swatches(names, cls)));
  };
  U.ap(box, h('p', null, `${K.keeper_zahl} von ${K.kader_plaetze} Kaderplätzen bleiben über den Winter. Die Bilanz zeigt, wie viel der Punkte ${wk} von diesen Keepern kam und wie viel aus dem Draft ${S.man.season} oder von späteren Zugängen. `, U.ib('keeper-bilanz', '')),
  h('div', {class: 'tiles'},
    U.tile('Keeper', U.pct(L.pf.anteil.keeper), `${U.num(L.pf.pts.keeper, 0)} von ${U.num(L.pf.summe, 0)} Pkt`, 'keeper-bilanz'),
    U.tile('ohne K, D/ST', U.pct(L.kern.anteil.keeper), 'Keeper bei QB, RB, WR, TE', 'keeper-kern'),
    U.tile(`Draft ${S.man.season}`, U.pct(L.pf.anteil.draft), `${L.picks_da} von ${L.picks} Picks im Kader`, 'draft'),
    U.tile('Zugänge', U.pct(L.pf.anteil.zugang), `Trades ${U.pct(L.pf.anteil.trade)}`, 'herkunft'),
    U.tile('Keeper heute', `${L.keeper_da} von ${L.keeper}`, 'noch im Kader', 'herkunft')),
  h('div', {class: 'row'}, U.seg('Positionen', [['pf', 'Alle Positionen'], ['kern', 'ohne K und D/ST']], key, v => { key = v; draw(); }), U.ib('keeper-kern', '')),
  wrap, chart, U.legend(['keeper-bilanz', 'herkunft', 'keeper-kern']),
  h('p', {class: 'note'}, `Punkte nach W${K.through_week} (final). ${standTxt(K)}.`));
  draw();
}

// ---------------------------------------------------------------- Kader: Herkunft und Vorjahresvergleich je Spieler
function kader(box, K, team) {
  const wrap = h('div');
  const all = [...K.kader].sort((a, b) => (b.avg ?? -1) - (a.avg ?? -1));
  const draw = () => {
    const rows = all.filter(r => !team || r.team === team);
    wrap.replaceChildren(U.table({cap: `Kader nach Herkunft (${rows.length} Spieler)`, cls: 'nr', rh: 0, limit: 50, rows, sort: ['h', 1], filter: true, cols: [
      {k: 'n', l: 'Spieler', v: r => (r.name || '').toLowerCase(), d: 1, flt: false,
        f: r => player(r.id, r.name, r.in_app, `${r.pos ?? '–'} · ${r.nfl || 'FA'}` + (team ? '' : ' · ' + U.kz(r.team)))},
      {k: 'h', l: 'Herkunft', v: herkunftOrd, d: 1, cat: 1, f: r => herkunft(r, K)},
      {k: 's', l: 'seit', v: r => r.seit, flt: false, f: r => U.val(r.seit, U.datum, r.art === 'keeper' ? 'Keeper: vor dem Draft' : 'Datum folgt mit dem Tageslauf')},
      ...(K.alter_stichtag ? [
        {k: 'al', l: 'Alter', num: 1, v: r => r.alter, f: r => U.val(r.alter, v => U.num(v, 1), ohneAlter(r))},
        {k: 'nj', l: 'NFL-Jahr', num: 1, d: 1, v: r => r.nfl_jahr, f: r => U.val(r.nfl_jahr, v => v, ohneAlter(r))}] : []),
      {k: 'g', l: 'Sp.', num: 1, v: r => r.g, f: r => U.val(r.g, v => v, 'keine Wochendaten')},
      {k: 'a', l: `Ø ${S.man.season}`, num: 1, v: r => r.avg, f: r => U.val(r.avg, U.num, 'ohne Spiel')},
      {k: 'v', l: `Ø ${S.man.season - 1}`, num: 1, v: r => r.vj_avg, f: r => r.rookie ? h('span', {class: 'note'}, 'Rookie') : U.val(r.vj_avg, U.num, 'kein Vorjahreswert')},
      {k: 'd', l: 'Δ', num: 1, v: r => r.vj_delta, f: r => U.val(r.vj_delta, U.sgn, 'kein Vergleich')},
      {k: 'vg', l: `Sp. ${S.man.season - 1}`, num: 1, v: r => r.vj_g, f: r => U.val(r.vj_g, v => v, 'kein Vorjahreswert')}]}),
    U.legend(['herkunft', 'vorjahr', ...(K.alter_stichtag ? ['alter'] : [])]),
    h('p', {class: 'note'}, standTxt(K) + '.', K.alter_stichtag ? quelle(K) : null));
  };
  U.ap(box, h('div', {class: 'row'}, teamSelect(team, v => { team = v; U.setQ('keeper/kader', {team}); draw(); })), wrap);
  draw();
}

// ---------------------------------------------------------------- Draft: alle Picks inklusive Keeper mit Ertrag
function draft(box, K, team) {
  const wrap = h('div');
  const bleib = p => p.da ? 'im Kader' : p.team_jetzt ? `bei ${U.kz(p.team_jetzt)}` : 'frei';
  const draw = () => {
    // rk + nr: Pick und Spieler bleiben beim Wischen stehen (mit den Ertragsspalten ist die Tabelle doppelt so breit wie das Handy)
    wrap.replaceChildren(U.table({cap: `Draft ${S.man.season} (inklusive Keeper)`, cls: 'rk nr kurz', rh: 1, limit: 50, rows: K.picks.filter(p => !team || p.team_id === team),
      sort: ['p', 1], filter: true, cols: [
        {k: 'p', l: 'Pick', num: 1, v: p => p.pick, d: 1, flt: false, f: p => p.pick},
        {k: 's', l: 'Spieler', v: p => (p.name || '').toLowerCase(), d: 1, flt: false,
          f: p => player(p.player_id, p.name, p.in_app, p.pos, p.keeper ? h('span', {class: 'kp', title: 'Keeper'}, 'K', h('span', {class: 'vh'}, ' Keeper')) : null)},
        {k: 't', l: 'Team', v: p => U.kz(p.team_id), d: 1, f: p => U.tl(p.team_id)},
        {k: 'b', l: 'Verbleib', v: bleib, d: 1, cat: 1, f: bleib},
        {k: 'pt', l: 'Pkt', num: 1, v: p => p.pts, f: p => U.val(p.pts, U.num, 'keine Wochendaten')},
        {k: 'a', l: 'Ø', num: 1, v: p => p.avg, f: p => U.val(p.avg, U.num, 'ohne Spiel')},
        {k: 'g', l: 'Sp.', num: 1, v: p => p.g, f: p => U.val(p.g, v => v, 'keine Wochendaten')},
        {k: 'st', l: 'Starts', num: 1, v: p => p.starts, f: p => p.starts},
        {k: 'pf', l: 'PF fürs Team', num: 1, v: p => p.pf, f: p => U.num(p.pf)},
        // Art und Runde zuletzt: die Art zeigt schon das K am Namen, beide bleiben als Filter erreichbar
        {k: 'k', l: 'Art', v: p => p.keeper ? 'Keeper' : 'Draft', d: 1, cat: 1, f: p => p.keeper ? 'Keeper' : 'Draft'},
        {k: 'r', l: 'Runde', num: 1, cat: 1, v: p => p.runde, d: 1, f: p => p.runde}]}),
    U.legend(['draft', 'draft-ertrag']), h('p', {class: 'note'}, `Punkte nach W${K.through_week} (final). ${standTxt(K)}.`));
  };
  U.ap(box, h('div', {class: 'row'}, teamSelect(team, v => { team = v; U.setQ('keeper/draft', {team: team || null}); draw(); })), wrap);
  draw();
}

// ---------------------------------------------------------------- Alter: Altersprofil je Team
const ohneAlter = r => r.pos === 'D/ST' ? 'D/ST ohne Alter' : 'nicht in den Stammdaten';
const ext = (href, text) => h('a', {href, target: '_blank', rel: 'noopener'}, text, h('span', {class: 'vh'}, ' (neues Fenster)'));
// Namensnennung laut CC BY 4.0: Quelle, Lizenz und der Hinweis, dass es ein Auszug ist
const nflverse = () => [ext('https://github.com/nflverse/nflverse-data', 'nflverse'), ' (', ext('https://creativecommons.org/licenses/by/4.0/', 'CC BY 4.0'), ', Auszug)'];
const quelle = K => [` Alter am ${U.datum(K.alter_stichtag)}; Geburtsdaten und Rookie-Saison: `, nflverse(), '.'];

function alter(box, K, svg) {
  const L = K.liga.altersprofil;
  if (!L) {
    U.ap(box, h('p', {class: 'note'}, 'Noch keine Altersdaten: Geburtsdatum und Rookie-Saison holt der nächste Wochenabruf von ', nflverse(), '.'));
    return;
  }
  const rows = K.teams.filter(t => t.altersprofil), P = t => t.altersprofil;
  const ros = K.alter_gewicht, rosWhy = 'keine ROS-Projektion';
  const age = v => U.num(v, 1), dev = v => U.sgn(v, 1);
  const by = new Map(rows.map(t => [t.team_id, t]));
  const key = ros ? 'bereinigt_ros' : 'bereinigt';
  const bars = S.teams.filter(t => by.has(t.team_id)).map(t => ({label: t.kuerzel, name: t.name, v: P(by.get(t.team_id))[key]}))
    .sort((a, b) => (a.v ?? 0) - (b.v ?? 0));
  U.ap(box, h('p', null, 'Wie alt sind die Kader – und die Spieler, von denen die Punkte kommen sollen? Alter sagt wenig über die laufende Saison, aber einiges über die nächsten Jahre. ', U.ib('alter-bereinigt', '')),
    h('div', {class: 'tiles'},
      U.tile('Ø Alter Liga', age(L.kader), `${L.n} Spieler ohne D/ST`, 'alter'),
      U.tile('unter 26', L.jung, `ab 30: ${L.alt}`, 'alter'),
      U.tile('Rookies', L.rookies, `2. NFL-Jahr: ${L.zweites_jahr}`, 'alter')),
    h('p', {class: 'note'}, 'Liga-Schnitt je Position: ', POS.filter(p => L.positionen[p]).map(p => `${p} ${age(L.positionen[p].alter)}`).join(' · '), '.'),
    U.table({cap: 'Altersprofil je Team', cls: 'nr kurz', rh: 0, rows, sort: [key, 1], cols: [
      {k: 't', l: 'Team', v: t => U.kz(t.team_id), d: 1, f: t => U.tl(t.team_id)},
      // die gewichteten Werte zuerst: auf dem Handy sind nur drei bis vier Spalten ohne Wischen zu sehen
      {k: 'bereinigt_ros', l: 'bereinigt ROS', num: 1, d: 1, v: t => P(t).bereinigt_ros, f: t => U.val(P(t).bereinigt_ros, dev, rosWhy)},
      {k: 'ros', l: 'nach ROS', num: 1, d: 1, v: t => P(t).ros, f: t => U.val(P(t).ros, age, rosWhy)},
      {k: 'bereinigt', l: 'bereinigt', num: 1, d: 1, v: t => P(t).bereinigt, f: t => dev(P(t).bereinigt)},
      {k: 'kader', l: 'Ø Alter', num: 1, d: 1, v: t => P(t).kader, f: t => age(P(t).kader)},
      {k: 'jung', l: '< 26', num: 1, v: t => P(t).jung, f: t => P(t).jung},
      {k: 'alt', l: '≥ 30', num: 1, v: t => P(t).alt, f: t => P(t).alt},
      {k: 'rk', l: 'Rookies', num: 1, v: t => P(t).rookies, f: t => P(t).rookies},
      {k: 'zj', l: '2. Jahr', num: 1, v: t => P(t).zweites_jahr, f: t => P(t).zweites_jahr},
      {k: 'n', l: 'Spieler', num: 1, v: t => P(t).n, f: t => P(t).n}]}),
    svg.fig(ros ? 'Alter bereinigt, nach ROS gewichtet' : 'Alter bereinigt', svg.hbars({title: 'Abstand zum Liga-Schnitt der Positionen je Team, in Jahren',
      desc: 'Balken nach links = jünger als der Schnitt, nach rechts = älter; genaue Werte in der Tabelle.', fmt: dev, rows: bars}),
    {heads: ['Team', 'Jahre zum Schnitt'], rows: bars.map(b => [b.name, dev(b.v)])},
    h('p', {class: 'note'}, 'Links jünger, rechts älter als der Liga-Schnitt der jeweiligen Position.')),
    U.legend(['alter', 'alter-ros', 'alter-bereinigt']),
    h('p', {class: 'note'}, standTxt(K) + '.', quelle(K)));
}
