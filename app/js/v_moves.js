// Moves (lädt transactions.json): ausgeführte Moves und angenommene Trades, Aufstellungswechsel je Team, Draft 2026
let U, S, h;
const ART = {WAIVER: 'Waiver', FREEAGENT: 'Free Agent', ROSTER: 'Drop', TRADE_ACCEPT: 'Trade', DRAFT: 'Draft'};

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const draft = r.sub === 'draft';
  let team = S.byId.has(+r.q.get('team')) ? +r.q.get('team') : 0;
  const views = U.chips('Ansichten Moves', [['#moves', 'Transaktionen', ''], ['#moves/draft', 'Draft', 'draft']], draft ? 'draft' : '');
  const viewLinks = () => views.querySelectorAll('a').forEach((a, i) => a.setAttribute('href', (i ? '#moves/draft' : '#moves') + (team ? '?team=' + team : '')));
  viewLinks();
  U.ap(box, h('h1', null, draft ? 'Draft 2026' : 'Moves'), U.spGroup('moves'), views);
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
    if (draft) {
      wrap.replaceChildren(U.table({cap: 'Draft 2026 (inklusive Keeper)', cls: 'nr kurz', rh: 1, limit: 50, rows: (T.draft || []).filter(inTeam), sort: ['p', 1], filter: true, cols: [
        {k: 'p', l: 'Pick', num: 1, v: d => d.pick, d: 1, flt: false, f: d => d.pick},
        {k: 's', l: 'Spieler', v: d => d.name || name(d.player_id), d: 1, flt: false, f: d => [link(d.player_id, d.name || name(d.player_id), d.in_app, 'tl2'),
          d.keeper ? h('span', {class: 'kp', title: 'Keeper'}, 'K', h('span', {class: 'vh'}, ' Keeper')) : null]},
        {k: 'k', l: 'Art', v: d => d.keeper ? 'Keeper' : 'Draft', d: 1, cat: 1, f: d => d.keeper ? 'Keeper' : 'Draft'},
        {k: 'r', l: 'Runde', num: 1, cat: 1, v: d => d.runde, d: 1, f: d => d.runde},
        {k: 't', l: 'Team', v: d => U.kz(d.team_id), d: 1, f: d => U.tl(d.team_id)}]}),
      U.legend(['draft']));
      return;
    }
    const items = (T.items || []).filter(inTeam);
    // Zugang und Abgang direkt nach Datum und Team (auf dem Handy als Kürzel), die Art zuletzt; bei gewähltem Team ohne Team-Spalte
    const tbl = U.table({cap: 'Transaktionen (neueste zuerst)', cls: 'nr kurz', rh: team ? 0 : 1, limit: 50, rows: items, sort: ['d', -1], cols: [
      {k: 'd', l: 'Datum', v: x => x.datum, f: x => U.ok(x.datum) ? `${U.datum(x.datum)} ${U.zeit(x.datum)}` : '–'},
      team ? null : {k: 't', l: 'Team', v: x => U.kz(x.team_id), d: 1, f: x => U.tl(x.team_id)},
      {k: 'z', l: 'Zugang', cls: 'wrap', f: x => typ(x) === 'TRADE_ACCEPT' && !part(x, 'ADD').length ? h('span', {class: 'note'}, 'ohne Spieler (ESPN)') : pl(part(x, 'ADD'))},
      {k: 'b', l: 'Abgang', cls: 'wrap', f: x => pl(part(x, 'DROP'))},
      {k: 'a', l: 'Art', v: x => typ(x), d: 1, f: x => ART[typ(x)] || typ(x)}].filter(Boolean)});
    const aw = Object.entries(T.aufstellungswechsel || {}).map(([k, v]) => ({tid: +k, n: v})).filter(x => !team || x.tid === team);
    wrap.replaceChildren(); U.ap(wrap, tbl, U.legend(['transaktionen']),
      aw.length ? h('div', {class: 'card', style: 'margin-top:16px'}, U.table({cap: 'Aufstellungswechsel je Team', cls: 'nr', rows: aw, sort: ['n', -1], cols: [
        {k: 't', l: 'Team', v: x => U.kz(x.tid), d: 1, f: x => U.tl(x.tid)},
        {k: 'n', l: 'Wechsel', num: 1, v: x => x.n, f: x => x.n}], rh: 0}), U.legend(['aufstellungswechsel'])) : null);
  };
  U.ap(box, h('div', {class: 'row'}, h('label', null, 'Team ', h('select', {onchange: e => {
    team = +e.target.value;
    U.setQ(draft ? 'moves/draft' : 'moves', {team: team || null});
    viewLinks();
    draw();
  }}, h('option', {value: 0}, 'Alle Teams'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === team}, t.name))))),
  !draft && S.man.datenstand?.transaktionen_bis ? h('p', {class: 'note'}, `Letzte Transaktion ${U.datum(S.man.datenstand.transaktionen_bis)} ${U.zeit(S.man.datenstand.transaktionen_bis)} · Abruf stündlich vormittags und abends`) : null,
  wrap);
  draw();
}
