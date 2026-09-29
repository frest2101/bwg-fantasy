// Waiver (lädt waiver.json und players.json, dazu transactions.json): beste verfügbare Spieler je Position nach ROS über
// Ersatz (Tagesstand), Bedarf je Team, Waiver-Reihenfolge, Claims der letzten 7 Tage. Zahlen kommen aus Python; hier nur
// Anzeige, Filter und die Zusammenführung von Tagesstand (waiver.json) und Wochenstand (players.json) je Spieler-ID.
// Positions-Matchup folgt in Session 8 (keine Platzhalter-Spalte).
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];
const FREE = ['WAIVERS', 'FREEAGENT'];
const ART = {WAIVER: 'Waiver', FREEAGENT: 'Free Agent'};
const DAYS7 = 7 * 864e5;
const KEY = 'bwg-team';                  // eigenes Team (Kürzel-Auswahl), nur Komfort im Browser

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  U.ap(box, h('h1', null, 'Waiver'));
  if (!S.man.files?.['waiver.json']) {
    U.ap(box, h('p', {class: 'warn'}, 'Noch keine Tagesdaten: Der Waiver-Tab füllt sich mit dem ersten Tageslauf (stündlich vormittags und abends).'),
      h('p', null, h('a', {href: '#spieler?status=frei&sicht=ros'}, 'Freie Spieler nach Wochenstand')));
    return;
  }
  const [W, P] = await Promise.all([ctx.lazy('waiver.json', 'Tagesstand', box), ctx.lazy('players.json', 'Spielerdaten', box)]);
  if (!r.alive()) return;
  const T = await ctx.load('transactions.json').catch(() => null);   // Claims sind Zugabe: ohne sie bleibt der Tab nutzbar
  if (!r.alive()) return;
  const byId = new Map(P.players.map(p => [p.id, p]));
  // Tagesstand je Spieler, Stammdaten und ROS aus dem Wochenstand; wer dort fehlt, heißt wie im Tagesstand (ohne ROS)
  const rows = W.spieler.map(d => {
    const p = byId.get(d.id) || {};
    return {...p, ...d, name: p.name ?? d.name ?? `Spieler ${d.id}`, pos: p.pos ?? d.pos ?? null, nfl: p.nfl ?? d.nfl ?? null};
  });
  const name = id => byId.get(id)?.name ?? rows.find(x => x.id === id)?.name ?? T?.spieler?.[String(id)] ?? `Spieler ${id}`;
  let mine = +U.store.get(KEY) || 0;
  const mineSel = h('select', {'aria-label': 'Mein Team', onchange: e => { mine = +e.target.value; U.store.set(KEY, mine); draw(); }},
    h('option', {value: 0}, 'Mein Team wählen'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === mine}, `${t.kuerzel} · ${t.name}`)));
  U.ap(box, h('p', {class: 'note'}, `Tagesstand ${U.stamp(W.stand)} · Projektion und Bye-Hinweis für W${W.woche}`, ' ', U.ib('tagesstand', '')),
    h('div', {class: 'row'}, h('label', null, 'Mein Team ', mineSel)));
  available(box, W, P, rows, r);
  const grid = h('div', {class: 'two'});
  U.ap(box, grid);
  const draw = () => { grid.replaceChildren(needs(W, P, name, mine), order(W, mine)); };
  draw();
  claims(box, T, name);
}

// ---------------------------------------------------------------- beste verfügbare Spieler je Position
function available(box, W, P, rows, r) {
  const q = r.q;
  const narrow = matchMedia('(max-width:599px)').matches;
  const st = {pos: POS.includes(q.get('pos')) ? q.get('pos') : '', text: '',
    sicht: ['alle', 'ros', 'besitz'].includes(q.get('sicht')) ? q.get('sicht') : (narrow ? 'ros' : 'alle')};
  const free = rows.filter(x => FREE.includes(x.status));
  const rowsNow = () => free.filter(x => (!st.pos || x.pos === st.pos) && (!st.text || x.name.toLowerCase().includes(st.text)));
  const rosWhy = P.ros_nach_woche == null ? `ab Wochenabruf W${S.tw + 1}` : 'keine ROS-Projektion';
  const num = (k, l, f = U.num, why) => ({k, l, num: 1, v: x => x[k], f: x => U.val(x[k], f, why)});
  const spieler = {k: 'name', l: 'Spieler', v: x => x.name.toLowerCase(), d: 1, flt: false, f: x => h('a', {href: '#spieler/' + x.id, class: 'pl'},
    h('span', null, x.name, U.inj(x.inj)), h('span', {class: 'sub'}, `${x.pos ?? '–'} · ${x.nfl ?? '–'} · ${x.status === 'FREEAGENT' ? 'FA' : 'Waivers'}`))};
  const bye = {k: 'bye', l: 'Bye', num: 1, cat: 1, v: x => x.bye, d: 1, f: x => !U.ok(x.bye) ? U.na('kein NFL-Team')
    : x.bye === W.woche ? h('span', {class: 'dn'}, 'W' + x.bye, h('span', {class: 'vh'}, ' – nächste Woche spielfrei')) : 'W' + x.bye};
  const verl = {k: 'inj', l: 'Verletzung', v: x => U.INJ[x.inj] ? x.inj : null, d: 1, f: x => U.INJ[x.inj]?.[1] || (x.inj === 'ACTIVE' ? 'aktiv' : '–')};
  const frist = {k: 'frist', l: 'Frist', v: x => x.status === 'WAIVERS' ? x.waiver_bis : null, d: 1,
    f: x => x.status === 'WAIVERS' ? U.val(x.waiver_bis, U.stamp, 'keine Frist gemeldet') : U.na('Free Agent, sofort')};
  const base = [spieler, num('ros_ue', 'ROS ü. Ersatz', U.sgn, rosWhy), num('proj', `Proj. W${W.woche}`, U.num, 'noch keine ESPN-Projektion')];
  const ros = [bye, verl, num('ros_g', 'ROS/Sp.', U.num, rosWhy)];
  const besitz = [num('own', 'Besitz %', v => U.pct(v)), num('own_d', 'Δ Tag', v => U.sgn(v, 2)), num('started', 'gestartet %', v => U.pct(v))];
  const extra = {alle: [...ros, ...besitz, frist], ros: [...ros, frist], besitz: [...besitz, frist]};
  const count = h('p', {class: 'note', 'aria-live': 'polite'});
  const slot = h('div');
  const fst = {}, filters = [{k: 'nfl', l: 'NFL-Team', v: x => x.nfl, d: 1, cat: 1, f: x => x.nfl},
    {k: 'status', l: 'Status', v: x => x.status, d: 1, cat: 1, f: x => U.STAT[x.status] || x.status}];
  let tbl;
  const build = () => {
    tbl = U.table({cap: 'Verfügbare Spieler nach ROS über Ersatz', cls: 'nr', rh: 0, rows: rowsNow(), sort: ['ros_ue', -1], limit: 50, filter: true,
      filters, fstate: fst, cols: [...base, ...extra[st.sicht]],
      note: 'Verfügbar = Waivers oder Free Agent laut Tagesstand. Positions-Matchup folgt in Session 8.'});
    slot.replaceChildren(tbl);
  };
  const refresh = rebuild => {
    if (rebuild) build(); else tbl.upd(rowsNow());
    count.textContent = `${rowsNow().length} verfügbare Spieler`;
    U.setQ('waiver', {pos: st.pos || null, sicht: st.sicht !== (narrow ? 'ros' : 'alle') ? st.sicht : null});
  };
  let timer;
  const ers = P.ersatz || {};
  U.ap(box, h('h2', null, 'Beste verfügbare Spieler'),
    h('p', {class: 'note'}, 'Ersatzniveau (ROS/Spiel): ', POS.map((p, i) => [i ? ' · ' : '', `${p} ${U.num(ers[p])}`]), ' ', U.ib('ersatz', '')),
    h('div', {class: 'row'}, U.seg('Position', [['', 'Alle'], ...POS.map(p => [p, p])], st.pos, v => { st.pos = v; refresh(); })),
    h('div', {class: 'row'}, h('label', null, h('span', {class: 'vh'}, 'Spieler suchen'),
      h('input', {type: 'search', placeholder: 'Name suchen', oninput: e => {
        clearTimeout(timer);
        timer = setTimeout(() => { st.text = e.target.value.trim().toLowerCase(); refresh(); }, 150);
      }})),
    U.seg('Spalten', [['alle', 'Alle'], ['ros', 'ROS'], ['besitz', 'Besitz']], st.sicht, v => { st.sicht = v; refresh(true); })),
    count, slot,
    U.legend(['verfuegbar', 'ros-ue', 'ersatz', 'ros-spiel', 'proj-naechste', 'bye-hinweis', 'besitz-trend', 'frist', 'filter', 'positions-matchup', 'projektionen']));
  refresh(true);
}

// ---------------------------------------------------------------- Bedarf je Team
function needs(W, P, name, mine) {
  const card = U.card('Bedarf je Team');
  if (!W.bedarf) {
    U.ap(card, h('p', {class: 'note'}, P.ros_nach_woche == null ? `Bedarf ab dem ersten ROS-Auszug (Wochenabruf W${S.tw + 1}).` : 'Nach W14 gibt es keinen Regular-Season-Bedarf mehr.'));
    return card;
  }
  const ers = P.ersatz || {};
  const teams = [...S.teams].sort((a, b) => (b.team_id === mine) - (a.team_id === mine) || a.rang - b.rang)
    .map(t => ({t, b: W.bedarf[String(t.team_id)]}));
  const gap = g => g.id == null ? `${g.slot}: unbesetzt`
    : [`${g.slot}: `, h('a', {href: '#spieler/' + g.id}, name(g.id)), ` ${U.num(g.ros_g)}` + (U.ok(ers[g.pos]) ? ` (Ersatz ${U.num(ers[g.pos])})` : '')];
  U.ap(card, U.table({cap: 'Lücken der ROS-optimalen Aufstellung', cls: 'nr', rh: 0, rows: teams, sortable: false, rc: x => x.t.team_id === mine ? 'me' : null, cols: [
    {k: 't', l: 'Team', f: x => U.tl(x.t.team_id)},
    {k: 'n', l: 'Lücken', num: 1, f: x => x.b ? (x.b.luecken.length || h('span', {class: 'note'}, 'keine')) : '–'},
    {k: 'l', l: 'Starter unter Ersatzniveau', cls: 'wrap', f: x => x.b ? x.b.luecken.map((g, i) => [i ? h('br') : '', gap(g)]) : '–'},
    {k: 'u', l: 'Über Ersatz je Position', cls: 'wrap', f: x => x.b ? POS.map((p, i) => [i ? ' · ' : '', `${p} ${x.b.ueber_ersatz[p] ?? '–'}`]) : '–'}]}),
  U.legend(['bedarf', 'ersatz']));
  return card;
}

// ---------------------------------------------------------------- Waiver-Reihenfolge
function order(W, mine) {
  const card = U.card('Waiver-Reihenfolge');
  const list = W.reihenfolge || [];
  if (!list.length) { U.ap(card, h('p', {class: 'note'}, 'Noch keine Reihenfolge gemeldet.')); return card; }
  const src = W.reihenfolge_quelle === 'tageslauf' ? `Tagesstand ${U.stamp(W.stand)}` : `Stand Wochenabruf (nach W${S.tw}); der Tagesstand kommt mit dem nächsten Tageslauf`;
  U.ap(card, U.table({cap: 'Reihenfolge der Claims', cls: 'nr', rh: 1, rows: list.map((tid, i) => ({i: i + 1, tid})), sortable: false,
    rc: x => x.tid === mine ? 'me' : null, cols: [
      {k: 'p', l: 'Platz', num: 1, f: x => x.i + '.'},
      {k: 't', l: 'Team', f: x => U.tl(x.tid)}]}),
  h('p', {class: 'note'}, src, '. ESPN verarbeitet Waiver um 07:00 UTC; in der ESPN-App sind die Ergebnisse erfahrungsgemäß erst 10:30–11:00 Uhr sichtbar. ', U.ib('waiver-reihenfolge', '')));
  return card;
}

// ---------------------------------------------------------------- Claims der letzten 7 Tage
function claims(box, T, name) {
  U.ap(box, h('h2', null, 'Claims der letzten 7 Tage'));
  if (!T) { U.ap(box, h('p', {class: 'note'}, 'Transaktionen konnten nicht geladen werden. ', h('a', {href: '#moves'}, 'Zu den Moves'))); return; }
  const since = Date.now() - DAYS7;
  const items = (T.items || []).filter(x => ART[x.type] && U.ok(x.datum) && x.datum >= since);
  const part = (x, kind) => (x.items || []).filter(i => i.type === kind);
  const pl = list => list.length ? list.map((i, k) => [k ? ', ' : '', h('a', {href: '#spieler/' + i.player_id}, i.name || name(i.player_id))]) : '–';
  if (!items.length) { U.ap(box, h('p', {class: 'note'}, 'Keine ausgeführten Claims oder Free-Agent-Zugänge in den letzten 7 Tagen. ', h('a', {href: '#moves'}, 'Alle Moves'))); return; }
  U.ap(box, U.table({cap: 'Ausgeführte Waiver-Claims und Free-Agent-Zugänge (neueste zuerst)', cls: 'nr', rh: 1, limit: 50, rows: items, sort: ['d', -1], cols: [
    {k: 'd', l: 'Datum', v: x => x.datum, f: x => U.stamp(x.datum)},
    {k: 't', l: 'Team', v: x => U.kz(x.team_id), d: 1, f: x => U.tl(x.team_id)},
    {k: 'a', l: 'Art', v: x => x.type, d: 1, f: x => ART[x.type] || x.type},
    {k: 'z', l: 'Zugang', f: x => pl(part(x, 'ADD'))},
    {k: 'b', l: 'Abgang', f: x => pl(part(x, 'DROP'))}]}),
  h('p', {class: 'note'}, h('a', {href: '#moves'}, 'Alle Moves und der Draft'), ' ', U.ib('claims', '')));
}
