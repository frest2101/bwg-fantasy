// Markt › Moves (#markt/moves, lädt transactions.json): ausgeführte Moves und angenommene Trades; je Team die Zugänge laut ESPN
// (teams.json › moves, Zähler des Teams zum Wochenabruf; bis 04.10.2026 Spalte „Moves“ unter Playoff-Chancen, Paket P3) und die
// Aufstellungswechsel.
// Der Draft steht unter Keeper › Draft (#keeper/draft, keeper.json); alte Links #moves/draft leitet der Router dorthin.
let U, S, h;
const ART = {WAIVER: 'Waiver', FREEAGENT: 'Free Agent', ROSTER: 'Drop', TRADE_ACCEPT: 'Trade', DRAFT: 'Draft'};

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  let team = S.byId.has(+r.q.get('team')) ? +r.q.get('team') : 0;
  // Verweis auf den Draft mit dem gewählten Team
  const draftLink = h('a', null, `Keeper › Draft ${S.man.season}`);
  const viewLinks = () => draftLink.setAttribute('href', '#keeper/draft' + (team ? '?team=' + team : ''));
  viewLinks();
  U.kopf(box, r, 'Moves');
  U.ap(box, h('p', {class: 'note'}, 'Draft und Keeper stehen unter ', draftLink, '.'));
  const T = await ctx.lazy('transactions.json', 'Transaktionen', box);
  if (!r.alive()) return;
  const name = id => T.spieler?.[String(id)] ?? `Spieler ${id}`;
  // Eintrag laut Export: {id, type, team_id, datum, periode, items: [{type: ADD|DROP, player_id, name, from_team_id, to_team_id}]}
  const typ = x => x.type;
  const part = (x, kind) => (x.items || []).filter(i => i.type === kind);
  // Spieler ohne Seite in der App (in_app false, z. B. gedroppt ohne Einsatz) als Text statt totem Link
  const link = (id, txt, inApp, cls) => inApp === false ? h('span', {class: cls}, txt) : h('a', {href: '#spieler/' + id, class: cls}, txt);
  const pl = list => list.map((i, k) => [k ? ', ' : '', link(i.player_id, i.name || name(i.player_id), i.in_app)]);
  const inTeam = x => !team || x.team_id === team;
  const wrap = h('div');
  const draw = () => {
    const items = (T.items || []).filter(inTeam);
    // Zugang und Abgang direkt nach Datum und Team (auf dem Handy als Kürzel), die Art zuletzt; bei gewähltem Team ohne Team-Spalte
    const tbl = U.table({cap: 'Transaktionen (neueste zuerst)', cls: 'nr kurz', rh: team ? 0 : 1, limit: 50, rows: items, sort: ['d', -1], cols: [
      {k: 'd', l: 'Datum', v: x => x.datum, f: x => U.ok(x.datum) ? `${U.datum(x.datum)} ${U.zeit(x.datum)}` : '–'},
      team ? null : {k: 't', l: 'Team', v: x => U.kz(x.team_id), d: 1, f: x => U.tl(x.team_id)},
      {k: 'z', l: 'Zugang', cls: 'wrap', f: x => typ(x) === 'TRADE_ACCEPT' && !part(x, 'ADD').length ? h('span', {class: 'note'}, 'ohne Spieler (ESPN)') : pl(part(x, 'ADD'))},
      {k: 'b', l: 'Abgang', cls: 'wrap', f: x => pl(part(x, 'DROP'))},
      {k: 'a', l: 'Art', v: x => typ(x), d: 1, f: x => ART[typ(x)] || typ(x)}].filter(Boolean)});
    // je Team: Zugänge laut ESPN (Wochenabruf) und Aufstellungswechsel (Archiv); ohne Eintrag im Archiv 0 Wechsel
    const aw = T.aufstellungswechsel;
    const jeTeam = S.teams.filter(t => !team || t.team_id === team)
      .map(t => ({tid: t.team_id, zu: t.moves ?? null, n: aw ? aw[String(t.team_id)] ?? 0 : null}));
    wrap.replaceChildren(); U.ap(wrap, tbl, U.legend(['transaktionen']),
      h('div', {class: 'card', style: 'margin-top:16px'}, U.table({cap: 'Moves je Team', cls: 'nr', rc: U.meRc, rows: jeTeam, sort: ['zu', -1], cols: [
        {k: 't', l: 'Team', v: x => U.kz(x.tid), d: 1, f: x => U.tl(x.tid)},
        {k: 'zu', l: 'Zugänge (ESPN)', num: 1, v: x => x.zu, f: x => U.val(x.zu, v => v, 'kein Zähler von ESPN')},
        {k: 'n', l: 'Aufstellungswechsel', num: 1, v: x => x.n, f: x => U.val(x.n, v => v, 'kein Archiv der Aufstellungswechsel')}], rh: 0,
        note: `Zugänge: Zähler des Teams laut ESPN, Stand nach W${S.tw}.`}), U.legend(['moves', 'aufstellungswechsel'])));
  };
  U.ap(box, h('div', {class: 'row'}, h('label', null, 'Team ', h('select', {onchange: e => {
    team = +e.target.value;
    U.setQ(r.base, {team: team || null});
    viewLinks();
    draw();
  }}, h('option', {value: 0}, 'Alle Teams'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === team}, t.name))))),
  S.man.datenstand?.transaktionen_bis ? h('p', {class: 'note'}, `Letzte Transaktion ${U.datum(S.man.datenstand.transaktionen_bis)} ${U.zeit(S.man.datenstand.transaktionen_bis)} · Abruf stündlich von etwa 05:00 Uhr bis Mitternacht (deutsche Zeit)`) : null,
  wrap);
  draw();
}
