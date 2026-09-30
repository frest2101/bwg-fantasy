// Waiver (lädt waiver.json und players.json, dazu transactions.json): beste verfügbare Spieler je Position nach ROS über
// Ersatz (Tagesstand), Bedarf je Team, Waiver-Reihenfolge, Claims der letzten 7 Tage. Zahlen kommen aus Python; hier nur
// Anzeige, Filter und die Zusammenführung von Tagesstand (waiver.json) und Wochenstand (players.json) je Spieler-ID.
// Positions-Matchup je Spieler (Feld mu) aus dem Wochenstand; Wetter-Fähnchen aus wetter.json (Prognose der laufenden Woche).
// Horizont (Beschluss 30.09.2026): Woche N+1 (Standard), Σ N+1…N+3 oder ROS – für die Liste und den Bedarf je Team.
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];
const FREE = ['WAIVERS', 'FREEAGENT'];
const ART = {WAIVER: 'Waiver', FREEAGENT: 'Free Agent'};
const DAYS7 = 7 * 864e5;
const KEY = 'bwg-team';                  // eigenes Team (Kürzel-Auswahl), nur Komfort im Browser
const fz = v => 'fz' + (U.ok(v) ? ' ' + U.fcls(v) : '');   // Farbzelle um F = 1,00; ohne Wert ohne Farbe
const HOR = ['woche', 'drei', 'ros'];
const GRUND = {BYE: 'Bye', OUT: 'fällt aus', INJURY_RESERVE: 'IR', SUSPENSION: 'gesperrt', QUESTIONABLE: 'fraglich',
  DOUBTFUL: 'zweifelhaft', DAY_TO_DAY: 'Day-to-Day'};
// Spiel der Woche N+1 schon angepfiffen: Der Spieler bringt in dieser Woche nichts mehr (Anstoß aus waiver.json)
const played = (W, x) => U.ok(W.anstoss?.[x.nfl]) && W.anstoss[x.nfl] <= Date.now();
const span = W => W.horizont?.length ? `W${W.horizont[0]}` + (W.horizont.length > 1 ? `–${W.horizont.at(-1)}` : '') : 'nächste 3';

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
  // Claims und Wetter sind Zugabe: ohne sie bleibt der Tab nutzbar (ohne Wetter keine Fähnchen)
  const [T, WX] = await Promise.all([ctx.load('transactions.json').catch(() => null),
    S.man.files?.['wetter.json'] ? ctx.load('wetter.json').catch(() => null) : null]);
  const wx = WX ? await ctx.mod('v_wetter').catch(() => null) : null;
  if (!r.alive()) return;
  const byId = new Map(P.players.map(p => [p.id, p]));
  // Tagesstand je Spieler, Stammdaten und ROS aus dem Wochenstand; wer dort fehlt, heißt wie im Tagesstand (ohne ROS)
  const rows = W.spieler.map(d => {
    const p = byId.get(d.id) || {};
    return {...p, ...d, name: p.name ?? d.name ?? `Spieler ${d.id}`, pos: p.pos ?? d.pos ?? null, nfl: p.nfl ?? d.nfl ?? null};
  });
  const rowById = new Map(rows.map(x => [x.id, x]));
  const name = id => byId.get(id)?.name ?? rowById.get(id)?.name ?? T?.spieler?.[String(id)] ?? `Spieler ${id}`;
  // Bezugsteam: #waiver?team=N gilt nur für diesen Aufruf (Link von der Team-Seite), sonst das gespeicherte Mein Team
  const qTeam = U.team(r.q.get('team')) ? +r.q.get('team') : 0;
  const me = {mine: qTeam || +U.store.get(KEY) || 0, q: qTeam};
  const mineSel = h('select', {'aria-label': 'Mein Team', onchange: e => {
    me.mine = +e.target.value; me.q = 0; U.store.set(KEY, me.mine); av.rebuild(); draw();
  }}, h('option', {value: 0}, 'Mein Team wählen'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === me.mine}, `${t.kuerzel} · ${t.name}`)));
  U.ap(box, h('p', {class: 'note'}, `Tagesstand ${U.stamp(W.stand)} · Projektion und Bye-Hinweis für W${W.woche}`, ' ', U.ib('tagesstand', '')),
    h('div', {class: 'row'}, h('label', null, qTeam ? 'Sicht von ' : 'Mein Team ', mineSel)));
  const av = available(box, W, P, rows, r, wx && (nfl => wx.flagLink(wx.gameOf(WX, nfl))), me);
  const grid = h('div', {class: 'two'});
  U.ap(box, grid);
  let bsicht = W.bedarf_woche ? 'woche' : 'ros';
  // Wochensicht mit fünf Spalten: Bedarf und Reihenfolge untereinander in voller Breite, ROS-Sicht nebeneinander
  const draw = () => {
    grid.className = bsicht === 'woche' ? 'stack' : 'two';
    grid.replaceChildren(needs(W, P, name, me.mine, bsicht, v => { bsicht = v; draw(); }, rowById), order(W, me.mine));
  };
  draw();
  claims(box, T, name);
}

// ---------------------------------------------------------------- beste verfügbare Spieler je Position
function available(box, W, P, rows, r, wflag, me) {
  const q = r.q;
  const narrow = matchMedia('(max-width:599px)').matches;
  const hasWeek = !!W.ersatz_woche;
  const st = {pos: POS.includes(q.get('pos')) ? q.get('pos') : '', text: '',
    hor: HOR.includes(q.get('h')) && (hasWeek || q.get('h') === 'ros') ? q.get('h') : (hasWeek ? 'woche' : 'ros'),
    sicht: ['alle', 'ros', 'besitz'].includes(q.get('sicht')) ? q.get('sicht') : (narrow ? 'ros' : 'alle')};
  const free = rows.filter(x => FREE.includes(x.status));
  const rowsNow = () => free.filter(x => (!st.pos || x.pos === st.pos) && (!st.text || x.name.toLowerCase().includes(st.text)));
  const rosWhy = P.ros_nach_woche == null ? `ab Wochenabruf W${S.tw + 1}` : 'keine ROS-Projektion';
  const num = (k, l, f = U.num, why) => ({k, l, num: 1, v: x => x[k], f: x => U.val(x[k], f, why)});
  // Wetter-Fähnchen als eigener Link nach #wetter neben dem Spielerlink (kein Link im Link)
  const spieler = {k: 'name', l: 'Spieler', v: x => x.name.toLowerCase(), d: 1, flt: false, f: x => {
    const a = h('a', {href: '#spieler/' + x.id, class: 'pl'},
      h('span', null, x.name, U.inj(x.inj)), h('span', {class: 'sub'}, `${x.pos ?? '–'} · ${x.nfl ?? '–'} · ${x.status === 'FREEAGENT' ? 'FA' : 'Waivers'}`
        + (played(W, x) ? ` · W${W.woche} gespielt` : '') + ahead(x)));
    const fl = wflag?.(x.nfl);
    return fl ? h('span', {class: 'plw'}, a, fl) : a;
  }};
  // Positions-Matchup (players.json mu, Wochenstand): Gegner in Woche mu_woche mit F als Farbzelle wie im D/ST-Tab, Bye grau
  const hasMu = 'mu_woche' in P, week = new Set(P.players.map(p => p.id));
  const muWhy = x => !hasMu ? 'ab dem nächsten Wochenabruf' : x.mu ? 'keine offene Woche' : !x.nfl ? 'kein NFL-Team'
    : week.has(x.id) ? 'kein Positions-Matchup' : 'nicht im Wochenstand';
  const mu = {k: 'mu', l: U.ok(P.mu_woche) ? `Matchup W${P.mu_woche}` : 'Matchup', num: 1, v: x => x.mu?.n1?.opp ? x.mu.n1.f ?? null : null,
    cls: x => x.mu?.n1 ? (x.mu.n1.opp ? fz(x.mu.n1.f) : 'fz bye') : 'fz',
    f: x => {
      const n = x.mu?.n1;
      if (!n) return U.na(muWhy(x));
      return n.opp ? [n.opp, h('small', null, U.val(n.f, v => U.num(v, 2), 'kein Faktor'))] : ['Bye', h('small', null, '·')];
    }};
  const mu3 = {k: 'mu3', l: 'Ø nächste 3', num: 1, v: x => x.mu?.naechste3 ?? null, cls: x => fz(x.mu?.naechste3),
    f: x => U.val(x.mu?.naechste3, v => U.num(v, 2), x.mu ? 'kein Spiel in den nächsten 3 Wochen' : muWhy(x))};
  const bye = {k: 'bye', l: 'Bye', num: 1, cat: 1, v: x => x.bye, d: 1, f: x => !U.ok(x.bye) ? U.na('kein NFL-Team')
    : x.bye === W.woche ? h('span', {class: 'dn'}, 'W' + x.bye, h('span', {class: 'vh'}, ' – nächste Woche spielfrei')) : 'W' + x.bye};
  const verl = {k: 'inj', l: 'Verletzung', v: x => U.INJ[x.inj] ? x.inj : null, d: 1, f: x => U.INJ[x.inj]?.[1] || (x.inj === 'ACTIVE' ? 'aktiv' : '–')};
  const frist = {k: 'frist', l: 'Frist', v: x => x.status === 'WAIVERS' ? x.waiver_bis : null, d: 1,
    f: x => x.status === 'WAIVERS' ? U.val(x.waiver_bis, U.stamp, 'keine Frist gemeldet') : U.na('Free Agent, sofort')};
  // Zugewinn für das Bezugsteam (waiver.json spieler[].zug, Python): brutto, netto nur, wenn ein Drop etwas kostet
  const gain = x => x.zug?.[st.hor]?.[String(me.mine)] ?? null;
  const lost = x => st.hor !== 'ros' && played(W, x);
  const zugCol = () => ({k: 'zug', l: `Für ${U.kz(me.mine)}`, num: 1, v: x => lost(x) ? null : gain(x)?.b ?? null,
    f: x => {
      const z = gain(x);
      if (lost(x)) return U.na('Spiel der Woche schon angepfiffen');
      if (!z) return U.na('verbessert die beste Aufstellung nicht');
      return z.n !== z.b ? [U.sgn(z.b), h('small', null, `netto ${U.sgn(z.n)}`)] : U.sgn(z.b);
    }});
  // Konkurrenz um den Claim: Teams vor dem Bezugsteam in der Waiver-Reihenfolge, bei denen der Spieler starten würde
  const ahead = x => {
    if (x.status !== 'WAIVERS' || !me.mine || !W.reihenfolge) return '';
    const mineAt = W.reihenfolge.indexOf(me.mine);
    const rivals = W.reihenfolge.slice(0, mineAt < 0 ? W.reihenfolge.length : mineAt)
      .map((tid, i) => [tid, i + 1]).filter(([tid]) => x.zug?.[st.hor]?.[String(tid)]);
    return rivals.length ? ' · vor dir: ' + rivals.map(([tid, i]) => `${i}. ${U.kz(tid)}`).join(', ') : '';
  };
  // Woche N+1: wer schon gespielt hat, bringt in dieser Woche nichts mehr – ohne Sortierwert ans Ende
  const weekWhy = x => x.pos === 'D/ST' || !U.ok(x.pos) ? 'kein freier Spieler der Position' : 'noch keine ESPN-Projektion';
  const projUe = {k: 'proj_ue', l: `W${W.woche} ü. Ersatz`, num: 1, v: x => played(W, x) ? null : x.proj_ue,
    f: x => played(W, x) ? U.na('Spiel der Woche schon angepfiffen') : U.val(x.proj_ue, U.sgn, weekWhy(x))};
  const proj = num('proj', `Proj. W${W.woche}`, U.num, 'noch keine ESPN-Projektion');
  const base = {
    woche: [spieler, projUe, proj],
    drei: [spieler, num('proj3_ue', `Σ ${span(W)} ü. Ersatz`, U.sgn, 'keine ROS-Projektion'),
      num('proj3', `Σ ${span(W)}`, U.num, 'keine ROS-Projektion'), proj],
    ros: [spieler, num('ros_ue', 'ROS ü. Ersatz', U.sgn, rosWhy), proj]};
  const SORT = {woche: 'proj_ue', drei: 'proj3_ue', ros: 'ros_ue'};
  const CAP = {woche: `Verfügbare Spieler nach Projektion W${W.woche} über Ersatz`, drei: `Verfügbare Spieler nach Σ ${span(W)} über Ersatz`,
    ros: 'Verfügbare Spieler nach ROS über Ersatz'};
  const ros = [mu, mu3, bye, verl, num('ros_g', 'ROS/Sp.', U.num, rosWhy)];
  const besitz = [num('own', 'Besitz %', v => U.pct(v)), num('own_d', 'Δ Tag', v => U.sgn(v, 2)), num('started', 'gestartet %', v => U.pct(v))];
  const extra = {alle: [...ros, ...besitz, frist], ros: [...ros, frist], besitz: [...besitz, frist]};
  const count = h('p', {class: 'note', 'aria-live': 'polite'});
  const slot = h('div');
  const fst = {}, filters = [{k: 'nfl', l: 'NFL-Team', v: x => x.nfl, d: 1, cat: 1, f: x => x.nfl},
    {k: 'status', l: 'Status', v: x => x.status, d: 1, cat: 1, f: x => U.STAT[x.status] || x.status}];
  let tbl;
  const build = () => {
    tbl = U.table({cap: CAP[st.hor], cls: 'nr', rh: 0, rows: rowsNow(), sort: [SORT[st.hor], -1], limit: 50, filter: true,
      filters, fstate: fst, cols: [base[st.hor][0], ...(me.mine ? [zugCol()] : []), ...base[st.hor].slice(1), ...extra[st.sicht]],
      rc: x => st.hor !== 'ros' && played(W, x) ? 'gsp' : null,
      note: 'Verfügbar = Waivers oder Free Agent laut Tagesstand.'});
    slot.replaceChildren(tbl);
  };
  const refresh = rebuild => {
    if (rebuild) build(); else tbl.upd(rowsNow());
    count.textContent = `${rowsNow().length} verfügbare Spieler`;
    U.setQ('waiver', {team: me.q || null, pos: st.pos || null, h: st.hor !== (hasWeek ? 'woche' : 'ros') ? st.hor : null,
      sicht: st.sicht !== (narrow ? 'ros' : 'alle') ? st.sicht : null});
    ersNote.replaceChildren(); U.ap(ersNote, ersText());
  };
  let timer;
  // Ersatzniveau passend zum Horizont: Projektion W(N+1), Σ N+1…N+3 oder ROS/Spiel
  const ersText = () => {
    const [lbl, ers, gid] = {woche: [`Projektion W${W.woche}`, W.ersatz_woche, 'proj-ue'], drei: [`Σ ${span(W)}`, W.ersatz_3, 'proj3'],
      ros: ['ROS/Spiel', P.ersatz, 'ersatz']}[st.hor];
    return [`Ersatzniveau (${lbl}): `, POS.map((p, i) => [i ? ' · ' : '', `${p} ${U.ok(ers?.[p]) ? U.num(ers[p]) : '–'}`]),
      ' ', U.ib(gid, '')];
  };
  const ersNote = h('p', {class: 'note'});
  const horSeg = hasWeek ? U.seg('Horizont', [['woche', `W${W.woche}`], ['drei', `Σ ${span(W)}`], ['ros', 'ROS']], st.hor,
    v => { st.hor = v; refresh(true); }) : null;
  U.ap(box, h('h2', null, 'Beste verfügbare Spieler'),
    horSeg && h('div', {class: 'row'}, horSeg, U.ib('horizont', '')),
    ersNote,
    h('div', {class: 'row'}, U.seg('Position', [['', 'Alle'], ...POS.map(p => [p, p])], st.pos, v => { st.pos = v; refresh(); })),
    h('div', {class: 'row'}, h('label', null, h('span', {class: 'vh'}, 'Spieler suchen'),
      h('input', {type: 'search', placeholder: 'Name suchen', oninput: e => {
        clearTimeout(timer);
        timer = setTimeout(() => { st.text = e.target.value.trim().toLowerCase(); refresh(); }, 150);
      }})),
    U.seg('Spalten', [['alle', 'Alle'], ['ros', 'Ausblick'], ['besitz', 'Besitz']], st.sicht, v => { st.sicht = v; refresh(true); })),
    count, slot,
    U.legend(['verfuegbar', 'horizont', 'proj-ue', 'proj3', 'gespielt', 'ros-ue', 'ersatz', 'ros-spiel', 'proj-naechste', 'mu-n1', 'mu-naechste3', 'bye-hinweis', 'besitz-trend', 'frist',
      'wetter-markierung', 'filter', 'projektionen']));
  refresh(true);
  return {rebuild: () => refresh(true)};
}

// ---------------------------------------------------------------- Bedarf je Team
// sicht 'woche': Lücken der Woche N+1 mit Grund und freien Kandidaten, Ausfälle der ROS-Aufstellung, Byes N+2…N+3;
// 'ros': Lücken der ROS-optimalen Aufstellung (Regular Season)
function needs(W, P, name, mine, sicht, onSicht, rowById) {
  const card = U.card('Bedarf je Team');
  if (W.bedarf_woche) U.ap(card, h('div', {class: 'row'}, U.seg('Bedarf', [['woche', `W${W.woche}`], ['ros', 'ROS']], sicht, onSicht)));
  const teams = key => [...S.teams].sort((a, b) => (b.team_id === mine) - (a.team_id === mine) || a.rang - b.rang)
    .map(t => ({t, b: W[key]?.[String(t.team_id)]}));
  const rc = x => x.t.team_id === mine ? 'me' : null;
  const link = id => h('a', {href: '#spieler/' + id}, name(id));
  // Team mit Schwächen laut Profil (waiver.json profil) als Unterzeile, in beiden Sichten
  const teamCell = x => [U.tl(x.t.team_id), weakSub(W, x.t.team_id)];
  if (sicht === 'woche' && W.bedarf_woche) {
    const byId = rowById;
    const cand = all => { const ids = all.filter(id => !played(W, byId.get(id) || {})); return ids.length ? [' → ', ids.map((id, i) => [i ? ', ' : '', link(id), ` ${U.num(byId.get(id)?.proj)}`])] : ' → kein freier Spieler mit mehr'; };
    const gap = g => [`${g.slot}: `, g.id == null ? 'unbesetzt' : [link(g.id), U.inj(byId.get(g.id)?.inj),
      ` ${U.num(g.proj)}` + (g.grund ? ` (${GRUND[g.grund] || g.grund})` : '')], cand(g.kandidaten)];
    const miss = a => [link(a.id), ` ${a.slot}: ${GRUND[a.grund] || a.grund}`];
    const bye = b => [`W${b.woche} `, link(b.id), ` (${b.slot})`];
    const list = (arr, f, none) => arr.length ? arr.map((x, i) => [i ? h('br') : '', f(x)]) : h('span', {class: 'note'}, none);
    U.ap(card, U.table({cap: `Lücken der besten Aufstellung für W${W.woche}`, cls: 'nr', rh: 0, rows: teams('bedarf_woche'), sortable: false, rc, cols: [
      {k: 't', l: 'Team', f: teamCell},
      {k: 'n', l: 'Lücken', num: 1, f: x => x.b ? (x.b.luecken.length || h('span', {class: 'note'}, 'keine')) : '–'},
      {k: 'l', l: `Lücken W${W.woche} → beste freie Spieler`, cls: 'wrap', f: x => x.b ? list(x.b.luecken, gap, '–') : '–'},
      {k: 'a', l: 'Ausfälle und fraglich', cls: 'wrap', f: x => x.b ? list(x.b.ausfaelle, miss, '–') : '–'},
      {k: 'y', l: `Byes ${W.horizont?.length > 1 ? `W${W.horizont[1]}–${W.horizont.at(-1)}` : ''}`, cls: 'wrap', f: x => x.b ? list(x.b.byes, bye, '–') : '–'}]}),
    U.legend(['bedarf-woche', 'proj-ue', 'gespielt', 'profil']));
    return card;
  }
  if (!W.bedarf) {
    U.ap(card, h('p', {class: 'note'}, P.ros_nach_woche == null ? `Bedarf ab dem ersten ROS-Auszug (Wochenabruf W${S.tw + 1}).` : 'Nach W17 gibt es keinen Bedarf mehr.'));
    return card;
  }
  const po = W.bedarf_basis === 'playoffs';   // nach W14: ROS Playoffs/Spiel W15–17 mit dem Ersatzniveau der Playoffs
  const ers = W.bedarf_ersatz || P.ersatz || {};
  const gap = g => g.id == null ? `${g.slot}: unbesetzt`
    : [`${g.slot}: `, link(g.id), ` ${U.num(g.ros_g)}` + (U.ok(ers[g.pos]) ? ` (Ersatz ${U.num(ers[g.pos])})` : '')];
  U.ap(card, U.table({cap: po ? 'Lücken der besten Aufstellung für W15–17' : 'Lücken der ROS-optimalen Aufstellung', cls: 'nr', rh: 0,
    rows: teams('bedarf'), sortable: false, rc, cols: [
    {k: 't', l: 'Team', f: teamCell},
    {k: 'n', l: 'Lücken', num: 1, f: x => x.b ? (x.b.luecken.length || h('span', {class: 'note'}, 'keine')) : '–'},
    {k: 'l', l: 'Starter unter Ersatzniveau', cls: 'wrap', f: x => x.b ? x.b.luecken.map((g, i) => [i ? h('br') : '', gap(g)]) : '–'},
    {k: 'u', l: 'Über Ersatz je Position', cls: 'wrap', f: x => x.b ? POS.map((p, i) => [i ? ' · ' : '', `${p} ${x.b.ueber_ersatz[p] ?? '–'}`]) : '–'}]}),
  U.legend(['bedarf', 'ersatz', 'profil']));
  return card;
}

// Schwächen eines Teams laut Profil als Unterzeile („schwach: WR · RB“); leer ohne Profil oder ohne Schwäche
const PROF_NAME = {QB: 'QB+OP'};
const weakText = (W, tid) => (W.profil?.[String(tid)]?.schwach || []).map(g => PROF_NAME[g] || g).join(' · ');
const weakSub = (W, tid) => weakText(W, tid) ? h('span', {class: 'sub'}, 'schwach: ' + weakText(W, tid)) : null;

// ---------------------------------------------------------------- Waiver-Reihenfolge
function order(W, mine) {
  const card = U.card('Waiver-Reihenfolge');
  const list = W.reihenfolge || [];
  if (!list.length) { U.ap(card, h('p', {class: 'note'}, 'Noch keine Reihenfolge gemeldet.')); return card; }
  const src = W.reihenfolge_quelle === 'tageslauf' ? `Tagesstand ${U.stamp(W.reihenfolge_stand || W.stand)}` : `Stand Wochenabruf (nach W${S.tw}); der Tagesstand kommt mit dem nächsten Tageslauf`;
  U.ap(card, U.table({cap: 'Reihenfolge der Claims', cls: 'nr', rh: 1, rows: list.map((tid, i) => ({i: i + 1, tid})), sortable: false,
    rc: x => x.tid === mine ? 'me' : null, cols: [
      {k: 'p', l: 'Platz', num: 1, f: x => x.i + '.'},
      {k: 't', l: 'Team', f: x => U.tl(x.tid)},
      ...(W.profil ? [{k: 's', l: 'Schwächen', cls: 'wrap', f: x => weakText(W, x.tid) || '–'}] : [])]}),
  h('p', {class: 'note'}, src, '. ESPN verarbeitet Waiver um 07:00 UTC; in der ESPN-App sind die Ergebnisse erfahrungsgemäß erst 10:30–11:00 Uhr sichtbar. Die Reihenfolge rollt: Wer erfolgreich claimt, rückt ans Ende. ', U.ib('waiver-reihenfolge', '')));
  return card;
}

// ---------------------------------------------------------------- Claims der letzten 7 Tage
function claims(box, T, name) {
  U.ap(box, h('h2', null, 'Claims der letzten 7 Tage'));
  if (!T) { U.ap(box, h('p', {class: 'note'}, 'Transaktionen konnten nicht geladen werden. ', h('a', {href: '#moves'}, 'Zu den Moves'))); return; }
  const since = Date.now() - DAYS7;
  const items = (T.items || []).filter(x => ART[x.type] && U.ok(x.datum) && x.datum >= since);
  const part = (x, kind) => (x.items || []).filter(i => i.type === kind);
  // Spieler ohne Seite in der App (in_app false, z. B. gedroppt ohne Einsatz) nur als Name, wie unter Moves
  const pl = list => list.length ? list.map((i, k) => {
    const txt = i.name || name(i.player_id);
    return [k ? ', ' : '', i.in_app === false ? h('span', null, txt) : h('a', {href: '#spieler/' + i.player_id}, txt)];
  }) : '–';
  if (!items.length) { U.ap(box, h('p', {class: 'note'}, 'Keine ausgeführten Claims oder Free-Agent-Zugänge in den letzten 7 Tagen. ', h('a', {href: '#moves'}, 'Alle Moves'))); return; }
  U.ap(box, U.table({cap: 'Ausgeführte Waiver-Claims und Free-Agent-Zugänge (neueste zuerst)', cls: 'nr', rh: 1, limit: 50, rows: items, sort: ['d', -1], cols: [
    {k: 'd', l: 'Datum', v: x => x.datum, f: x => U.stamp(x.datum)},
    {k: 't', l: 'Team', v: x => U.kz(x.team_id), d: 1, f: x => U.tl(x.team_id)},
    {k: 'a', l: 'Art', v: x => x.type, d: 1, f: x => ART[x.type] || x.type},
    {k: 'z', l: 'Zugang', f: x => pl(part(x, 'ADD'))},
    {k: 'b', l: 'Abgang', f: x => pl(part(x, 'DROP'))}]}),
  h('p', {class: 'note'}, h('a', {href: '#moves'}, 'Alle Moves und der Draft'), ' ', U.ib('claims', '')));
}
