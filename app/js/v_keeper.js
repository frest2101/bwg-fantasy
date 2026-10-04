// Bereich Keeper (lädt keeper.json): Keeper-Bilanz – woher die Punkte kommen (Keeper, Draft, Zugänge, Trades), Herkunft je
// Kaderspieler mit Vorjahresvergleich und Marktwert, Altersprofil je Team (Stammdaten von nflverse), Marktwert je Team
// (FantasyCalc, nur Summen, kein Spieler-Ranking), Draft 2026 inklusive Keeper mit Ertrag. Alle Zahlen aus Python
// (scripts/keeper.py).
let U, S, h;
export const init = c => { U = c.ui; S = U.S; h = U.h; };
const KEY = 'bwg-team';                  // eigenes Team wie unter Markt, nur Komfort im Browser
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

// ---------------------------------------------------------------- Marktwert (FantasyCalc), gemeinsam mit Markt und Spielerseite
// Nennung laut Nutzungsbedingungen auf jeder Ansicht mit den Werten, nahe bei den Zahlen, mit Link; neutral (keine Partnerschaft)
const extA = (href, text) => h('a', {href, target: '_blank', rel: 'noopener'}, text, h('span', {class: 'vh'}, ' (neues Fenster)'));
export const fcQuelle = () => ['Werte: ', extA('https://fantasycalc.com', 'FantasyCalc')];
// Trade-Rechner von FantasyCalc statt eines eigenen; die Einstellungen stehen dort nicht in der Adresse
export const fcRechner = () => [extA('https://fantasycalc.com/trade-calculator', 'Trade-Rechner von FantasyCalc'), ' (dort Dynasty, Superflex, 10 Teams, PPR wählen)'];
// Wert als ganze Zahl mit Tausenderpunkt; Trend mit Vorzeichen
export const wertTxt = v => U.num(v, 0);
export const wertSgn = v => U.sgn(v, 0);

export async function render(box, ctx, r) {
  const sub = r.view;      // '' Bilanz · herkunft · alter · marktwert · draft · draft-folgejahr (Router)
  // ?team=N gilt, auch 0 = Alle Teams (sonst fiele die Wahl auf dem Rückweg wieder auf das eigene Team); nur ohne
  // Parameter nimmt die Herkunft-Ansicht das gespeicherte Mein Team
  let team = r.q.has('team') ? +r.q.get('team') : sub === 'herkunft' ? +U.store.get(KEY) || 0 : 0;
  if (!S.byId.has(team)) team = 0;
  const next = S.man.season + 1;
  U.kopf(box, r, {draft: `Draft ${S.man.season}`, 'draft-folgejahr': `Draft ${next}`, herkunft: 'Herkunft der Kaderspieler',
    alter: 'Alter der Kader', marktwert: 'Marktwert der Kader'}[sub] || 'Keeper-Bilanz');
  if (!S.man.files?.['keeper.json']) {
    U.ap(box, h('p', {class: 'note'}, 'Noch keine Keeper-Bilanz: Sie erscheint mit dem ersten Wochenabruf nach dem Draft.'));
    return;
  }
  const K = await ctx.lazy('keeper.json', 'Keeper-Bilanz', box);
  if (!r.alive()) return;
  if (sub === 'draft') draft(box, K, team, r);
  else if (sub === 'draft-folgejahr') draftNext(box, K);
  else if (sub === 'herkunft') kader(box, K, team, r);
  else if (sub === 'alter') alter(box, K, await ctx.mod('svg'));
  else if (sub === 'marktwert') wert(box, K, await ctx.mod('svg'));
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
function kader(box, K, team, r) {
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
      // Marktwert (FantasyCalc): Wert, Gesamtrang mit Positionsrang, Trend 30 Tage
      ...(K.marktwert_stand ? [
        {k: 'w', l: 'Wert', num: 1, v: r => r.wert, f: r => U.val(r.wert, wertTxt, ohneWert(r))},
        {k: 'wr', l: 'Wert-Rang', num: 1, d: 1, v: r => r.wert_rang,
          f: r => U.ok(r.wert_rang) ? [String(r.wert_rang), h('small', null, `${r.pos} ${r.wert_posrang}`)] : U.na(ohneWert(r))},
        {k: 'wt', l: 'Trend 30 T.', num: 1, v: r => r.wert_trend, f: r => U.val(r.wert_trend, wertSgn, ohneWert(r))}] : []),
      {k: 'g', l: 'Sp.', num: 1, v: r => r.g, f: r => U.val(r.g, v => v, 'keine Wochendaten')},
      {k: 'a', l: `Ø ${S.man.season}`, num: 1, v: r => r.avg, f: r => U.val(r.avg, U.num, 'ohne Spiel')},
      {k: 'v', l: `Ø ${S.man.season - 1}`, num: 1, v: r => r.vj_avg, f: r => r.rookie ? h('span', {class: 'note'}, 'Rookie') : U.val(r.vj_avg, U.num, 'kein Vorjahreswert')},
      {k: 'd', l: 'Δ', num: 1, v: r => r.vj_delta, f: r => U.val(r.vj_delta, U.sgn, 'kein Vergleich')},
      {k: 'vg', l: `Sp. ${S.man.season - 1}`, num: 1, v: r => r.vj_g, f: r => U.val(r.vj_g, v => v, 'kein Vorjahreswert')}]}),
    U.legend(['herkunft', 'vorjahr', ...(K.alter_stichtag ? ['alter'] : []), ...(K.marktwert_stand ? ['marktwert', 'wert-trend'] : [])]),
    h('p', {class: 'note'}, standTxt(K) + '.', K.alter_stichtag ? quelle(K) : null,
      K.marktwert_stand ? [' ', fcQuelle(), ` (Stand ${U.stamp(K.marktwert_stand)}); Vergleich einzelner Spieler: `, fcRechner(), '.'] : null));
  };
  U.ap(box, h('div', {class: 'row'}, teamSelect(team, v => { team = v; U.setQ(r.base, {team}); draw(); })), wrap);
  draw();
}

// ---------------------------------------------------------------- Draft: alle Picks inklusive Keeper mit Ertrag
function draft(box, K, team, r) {
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
  U.ap(box, h('div', {class: 'row'}, teamSelect(team, v => { team = v; U.setQ(r.base, {team: team || null}); draw(); })), wrap);
  draw();
}

// ---------------------------------------------------------------- Draft des Folgejahrs (Stufe 4): umgekehrte Endplatzierung
// Bis zum Saisonende die Simulation (teams.json sim.liga), danach die feste Reihenfolge aus keeper.json draft_folgejahr
function draftNext(box, K) {
  const season = S.man.season, next = season + 1, D = K.draft_folgejahr || {}, fest = D.reihenfolge;
  const po = S.man.datenstand?.playoff_woche, ab = D.abweichung || [];
  const note = h('p', {class: 'note'}, fest
    ? `Fest nach den Playoffs ${season}, aus den Ergebnissen laut ESPN` + (D.espn_bestaetigt ? ' (von ESPNs Endplätzen bestätigt). ' : '; ESPN hat die Endplätze noch nicht gemeldet. ')
    : `Simulation nach W${S.tw}` + (po ? `, Playoffs gespielt bis W${po}` : '') + ', 10 000 Läufe. Die Playoff-Mechanik von ESPN (Spiel um Platz 5, Trostrunde) ist eine Annahme, die nach W15–17 geprüft wird. ',
    'Getauschte Picks sind nicht berücksichtigt.');
  U.ap(box, h('p', null, `Die Draft-Reihenfolge ${next} ist die umgekehrte Endplatzierung ${season}: Der Letzte hat Pick 1, der Meister Pick 10 – in jeder der zwölf Runden gleich (linear, ohne Lotterie). `,
    U.ib('draft-folgejahr', '')));
  // ESPN paart anders als angenommen oder meldet ein Unentschieden: keine Simulation und keine feste Reihenfolge, bis die
  // Annahme angepasst ist (sonst zählten echte Spiele in falschen Rollen)
  if (ab.length && !fest) {
    U.ap(box, h('p', {class: 'warn'}, `ESPN setzt die Playoffs ab W${ab[0]} anders an als angenommen – Endplatz und Draft-Reihenfolge ${next} werden geprüft und erscheinen danach hier.`),
      U.legend(['draft-folgejahr', 'endplatz-sim']), h('p', {class: 'note'}, 'Getauschte Picks sind nicht berücksichtigt.'));
    return;
  }
  if (fest) {
    U.ap(box, U.table({cap: `Draft-Reihenfolge ${next}`, cls: 'nr kurz', rh: 1, sortable: false,
      rows: fest.map((tid, i) => ({pick: i + 1, tid, platz: fest.length - i})), cols: [
        {k: 'p', l: 'Pick', num: 1, f: x => x.pick},
        {k: 't', l: 'Team', f: x => U.tl(x.tid)},
        {k: 'e', l: `Endplatz ${season}`, num: 1, f: x => x.platz + '.'}]}),
    U.legend(['draft-folgejahr', 'endplatz-sim']), note);
    return;
  }
  const rows = S.teams.filter(t => t.sim?.liga?.endplatz), L = t => t.sim.liga, pct = v => U.po(U.sp(v));
  if (!rows.length) {
    U.ap(box, h('p', {class: 'note'}, 'Noch keine Endplatz-Simulation.'));
    return;
  }
  U.ap(box, U.table({cap: `Erwartete Draft-Position ${next} laut Simulation`, cls: 'nr kurz', rh: 0, rows, sort: ['pk', 1], cols: [
    {k: 't', l: 'Team', v: t => U.kz(t.team_id), d: 1, f: t => U.tl(t.team_id)},
    {k: 'pk', l: 'Ø Pick', num: 1, d: 1, v: t => L(t).pick, f: t => U.num(L(t).pick, 1)},
    {k: 'p1', l: 'Pick 1', num: 1, v: t => U.sp(L(t).pick1), f: t => pct(L(t).pick1)},
    {k: 'p3', l: 'Pick 1–3', num: 1, v: t => U.sp(L(t).pick_top3), f: t => pct(L(t).pick_top3)},
    {k: 'me', l: 'Meister', num: 1, v: t => U.sp(L(t).endplatz[0]), f: t => pct(L(t).endplatz[0])},
    {k: 'po', l: 'Playoffs', num: 1, v: t => U.sp(L(t).playoff), f: t => pct(L(t).playoff)}]}),
  U.legend(['draft-folgejahr', 'endplatz-sim', 'simulation']), note);
}

// ---------------------------------------------------------------- Alter: Altersprofil je Team
const ohneAlter = r => r.pos === 'D/ST' ? 'D/ST ohne Alter' : 'nicht in den Stammdaten';
const ohneWert = r => r.pos === 'K' || r.pos === 'D/ST' ? 'K und D/ST ohne Marktwert' : 'nicht bei FantasyCalc';
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
  // Gewicht: Restpunkte laut ROS; ohne ROS-Projektion (Offseason) der Marktwert (Stufe 4), ohne beides keins
  const ros = K.alter_gewicht, rosWhy = 'keine ROS-Projektion und kein Marktwert';
  const byWert = ros === 'wert', gw = byWert ? 'Wert' : 'ROS';
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
      {k: 'bereinigt_ros', l: `bereinigt ${gw}`, num: 1, d: 1, v: t => P(t).bereinigt_ros, f: t => U.val(P(t).bereinigt_ros, dev, rosWhy)},
      {k: 'ros', l: `nach ${gw}`, num: 1, d: 1, v: t => P(t).ros, f: t => U.val(P(t).ros, age, rosWhy)},
      {k: 'bereinigt', l: 'bereinigt', num: 1, d: 1, v: t => P(t).bereinigt, f: t => dev(P(t).bereinigt)},
      {k: 'kader', l: 'Ø Alter', num: 1, d: 1, v: t => P(t).kader, f: t => age(P(t).kader)},
      {k: 'jung', l: '< 26', num: 1, v: t => P(t).jung, f: t => P(t).jung},
      {k: 'alt', l: '≥ 30', num: 1, v: t => P(t).alt, f: t => P(t).alt},
      {k: 'rk', l: 'Rookies', num: 1, v: t => P(t).rookies, f: t => P(t).rookies},
      {k: 'zj', l: '2. Jahr', num: 1, v: t => P(t).zweites_jahr, f: t => P(t).zweites_jahr},
      {k: 'n', l: 'Spieler', num: 1, v: t => P(t).n, f: t => P(t).n}]}),
    svg.fig(ros ? `Alter bereinigt, nach ${gw} gewichtet` : 'Alter bereinigt', svg.hbars({title: 'Abstand zum Liga-Schnitt der Positionen je Team, in Jahren',
      desc: 'Balken nach links = jünger als der Schnitt, nach rechts = älter; genaue Werte in der Tabelle.', fmt: dev, rows: bars}),
    {heads: ['Team', 'Jahre zum Schnitt'], rows: bars.map(b => [b.name, dev(b.v)])},
    h('p', {class: 'note'}, 'Links jünger, rechts älter als der Liga-Schnitt der jeweiligen Position.')),
    U.legend(['alter', byWert ? 'alter-wert' : 'alter-ros', 'alter-bereinigt']),
    // nach Wert gewichtet: abgeleitete FantasyCalc-Werte, Nennung mit Link wie in der Ansicht Wert
    h('p', {class: 'note'}, standTxt(K) + '.', quelle(K),
      byWert ? [' Gewichtet mit dem Marktwert; ', fcQuelle(), K.marktwert_stand ? ` (Stand ${U.stamp(K.marktwert_stand)})` : '', '.'] : null));
}

// ---------------------------------------------------------------- Wert: Marktwert je Team (FantasyCalc), nur Summen
// Keine Liste der wertvollsten Spieler je Team (Beschluss 01.10.2026): Kern-Wert, Wert über der Linie und Alter als Zahlen
function wert(box, K, svg) {
  const L = K.liga.marktwert;
  if (!L) {
    U.ap(box, h('p', {class: 'note'}, 'Noch keine Marktwerte: Der Tageslauf holt sie einmal am Tag. ', fcQuelle(), '.'));
    return;
  }
  const rows = K.teams.filter(t => t.marktwert), M = t => t.marktwert, line = U.ok(K.keeper_linie);
  const n = K.keeper_zahl, total = n * S.teams.length;
  const by = new Map(rows.map(t => [t.team_id, t]));
  const bars = S.teams.filter(t => by.has(t.team_id)).map(t => ({label: t.kuerzel, name: t.name, v: M(by.get(t.team_id)).kern - L.kern}))
    .sort((a, b) => b.v - a.v);
  const noLine = 'keine Keeper-Linie', noAge = 'keine Altersdaten';
  U.ap(box, h('p', null, `Was die Kader auf dem Tauschmarkt wert sind: je Team die Summe der ${n} wertvollsten Spieler – so viele bleiben über den Winter – und wie viel Wert über der Keeper-Linie liegt. Tauschpreise aus Dynasty-Ligen, keine Punktprognose; K und D/ST haben keinen Wert. `, U.ib('marktwert', '')),
    h('p', {class: 'note'}, fcQuelle(), ` · Stand ${U.stamp(K.marktwert_stand)}`),
    h('div', {class: 'tiles'},
      U.tile('Keeper-Linie', U.val(K.keeper_linie, wertTxt, `weniger als ${total} Kaderspieler mit Wert`), `Wert des ${total}. Kaderspielers`, 'keeper-linie'),
      U.tile('Ø Kern-Wert', wertTxt(L.kern), `${n} wertvollste je Team`, 'kern-wert'),
      U.tile('Alter nach Wert', U.val(L.alter, v => U.num(v, 1), noAge), `Liga, ${L.n} Spieler mit Wert`, 'alter-wert')),
    U.table({cap: 'Marktwert je Team', cls: 'nr kurz', rh: 0, rows, sort: ['kern', -1], cols: [
      {k: 't', l: 'Team', v: t => U.kz(t.team_id), d: 1, f: t => U.tl(t.team_id)},
      {k: 'kern', l: 'Kern-Wert', num: 1, v: t => M(t).kern, f: t => wertTxt(M(t).kern)},
      {k: 'ab', l: 'zum Schnitt', num: 1, v: t => M(t).kern - L.kern, f: t => wertSgn(M(t).kern - L.kern)},
      {k: 'ue', l: 'ü. Linie', num: 1, v: t => M(t).ueber_linie, f: t => U.val(M(t).ueber_linie, wertTxt, noLine)},
      {k: 'nl', l: 'ab Linie', num: 1, v: t => M(t).n_linie, f: t => U.val(M(t).n_linie, v => v, noLine)},
      {k: 'al', l: 'Alter nach Wert', num: 1, d: 1, v: t => M(t).alter, f: t => U.val(M(t).alter, v => U.num(v, 1), noAge)},
      {k: 'n', l: 'mit Wert', num: 1, v: t => M(t).n, f: t => M(t).n}]}),
    svg.fig('Kern-Wert zum Ligaschnitt', svg.hbars({title: `Summe der ${n} wertvollsten Spieler je Team, Abstand zum Ligaschnitt`,
      desc: 'Balken nach rechts = mehr Wert als der Schnitt, nach links = weniger; genaue Werte in der Tabelle.', fmt: wertSgn, rows: bars}),
    {heads: ['Team', 'Kern-Wert zum Schnitt'], rows: bars.map(b => [b.name, wertSgn(b.v)])},
    h('p', {class: 'note'}, `Ligaschnitt ${wertTxt(L.kern)}.`)),
    U.legend(['marktwert', 'keeper-linie', 'kern-wert', 'wert-ue', 'alter-wert']),
    h('p', {class: 'note'}, standTxt(K) + '. ', fcQuelle(), line ? ` · ${L.n_linie} Kaderspieler liegen auf oder über der Linie.` : '', ' Einzelne Spieler vergleichen: ', fcRechner(), '.'));
}
