// Tab Spieler (lädt players.json): Liste mit Filtern in 50er-Blöcken, Detail #spieler/<id> mit Formkurve und ROS
let U, S, h;
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'];
const INJ = {QUESTIONABLE: ['Q', 'fraglich'], DOUBTFUL: ['D', 'zweifelhaft'], OUT: ['O', 'fällt aus'], INJURY_RESERVE: ['IR', 'Injured Reserve'],
  SUSPENSION: ['SSPD', 'gesperrt'], DAY_TO_DAY: ['DTD', 'Day-to-Day']};
const STAT = {ONTEAM: 'Kader', FREEAGENT: 'Free Agent', WAIVERS: 'Waivers'};

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const detail = r.sub && r.sub !== '';
  const h1 = h('h1', null, 'Spieler');
  U.ap(box, h1, detail ? null : U.spGroup('spieler'));
  const P = await ctx.lazy('players.json', 'Spielerdaten', box);
  if (!r.alive()) return;
  const svg = await ctx.mod('svg');
  const rosWhy = P.ros_nach_woche == null ? `ab Wochenabruf W${S.tw + 1}` : 'keine Projektion';
  if (detail) one(box, h1, P, r.sub, svg, rosWhy); else list(box, P, r, rosWhy);
}

const trendTxt = t => {
  const v = t === 'up' || t === 1 ? '↑' : t === 'down' || t === -1 ? '↓' : t === 'flat' || t === 0 ? '→' : t;
  return v ? h('span', {class: v === '↑' ? 'up' : v === '↓' ? 'dn' : 'eq', title: 'Trend'}, v,
    h('span', {class: 'vh'}, v === '↑' ? ' steigend' : v === '↓' ? ' fallend' : ' stabil')) : null;
};
const inj = s => INJ[s] ? [h('span', {class: 'inj', 'aria-hidden': 'true'}, INJ[s][0]), h('span', {class: 'vh'}, ' ' + INJ[s][1])] : null;
const stand = () => {
  const ds = S.man.datenstand || {}, w = S.weeks.find(x => x.week === (ds.pool_woche ?? S.tw) + 1);
  return h('p', {class: 'note'}, `Besitz und Verletzung: Stand nach W${ds.pool_woche ?? S.tw}` + (w ? ` (${U.datum(w.start)})` : ''), U.ib('besitz', ''));
};

function list(box, P, r, rosWhy) {
  const q = r.q;
  const st = {pos: POS.includes(q.get('pos')) ? q.get('pos') : '', status: ['kader', 'frei'].includes(q.get('status')) ? q.get('status') : 'alle',
    team: +q.get('team') || 0, sicht: ['ros', 'besitz'].includes(q.get('sicht')) ? q.get('sicht') : 'saison', text: ''};
  const count = h('p', {class: 'note', 'aria-live': 'polite'});
  const slotBox = h('div');
  const rows = () => P.players.filter(p => (!st.pos || p.pos === st.pos)
    && (st.status === 'alle' || (st.status === 'kader' ? p.team > 0 : !(p.team > 0)))
    && (!st.team || p.team === st.team)
    && (!st.text || p.name.toLowerCase().includes(st.text)));
  const num = (k, l, f = U.num, why) => ({k, l, num: 1, v: p => p[k], f: p => U.val(p[k], f, why)});
  const base = [
    {k: 'name', l: 'Spieler', v: p => p.name.toLowerCase(), d: 1, f: p => h('a', {href: '#spieler/' + p.id, class: 'pl'},
      h('span', null, p.name, inj(p.inj)), h('span', {class: 'sub'}, `${p.pos} · ${p.nfl}` + (p.team > 0 ? ' · ' + U.kz(p.team) : '')))},
    num('avg', 'Ø', U.num, 'ohne Spiel'),
    {k: 'form', l: 'Form', num: 1, v: p => p.form, f: p => [U.val(p.form, U.num, 'ohne Spiel'), ' ', trendTxt(p.trend)]},
    num('ros_g', 'ROS/Sp.', U.num, rosWhy)];
  const extra = {
    saison: [num('pts', 'Pkt'), num('g', 'Spiele', v => v), num('floor', 'Floor', U.num, 'ohne Spiel'), num('ceil', 'Ceiling', U.num, 'ohne Spiel'),
      num('sd', 'Konstanz', U.num, 'unter 2 Spielen'), num('starts', 'Starts', v => v), num('bench_pts', 'Bank-Pkt'),
      num('proj_d', 'Proj.-Δ', U.sgn, 'ohne Spiel'), {k: 'spark', l: 'Formkurve', f: p => h('span', {class: 'sp', 'aria-hidden': 'true'}, p.spark || '')}],
    ros: [num('ros', 'ROS', U.num, rosWhy), num('rest_g', 'Restspiele', v => v, rosWhy), num('ros_po', 'ROS PO', U.num, rosWhy),
      num('ros_rang', 'ROS-Rang', v => v + '.', rosWhy), num('ros_ue', 'ROS ü. Ersatz', U.sgn, rosWhy)],
    besitz: [num('own', 'Besitz %', v => U.pct(v)), {k: 'status', l: 'Status', v: p => p.status, d: 1, f: p => STAT[p.status] || p.status || '–'},
      {k: 'inj', l: 'Verletzung', v: p => INJ[p.inj] ? p.inj : null, d: 1, f: p => INJ[p.inj]?.[1] || (p.inj === 'ACTIVE' ? 'aktiv' : '–')},
      {k: 'team', l: 'Team', v: p => U.kz(p.team), d: 1, f: p => p.team > 0 ? U.tl(p.team) : (STAT[p.status] || 'frei')}]};
  const sortKey = {saison: 'pts', ros: 'ros_g', besitz: 'own'};
  let tbl;
  const build = () => {
    tbl = U.table({cap: 'Spielerliste', cls: 'nr', rh: 0, rows: rows(), sort: [sortKey[st.sicht], -1], limit: 50, cols: [...base, ...extra[st.sicht]]});
    slotBox.replaceChildren(tbl);
  };
  const refresh = (rebuild) => {
    if (rebuild) build(); else tbl.upd(rows());
    count.textContent = `${rows().length} Spieler`;
    U.setQ('spieler', {pos: st.pos || null, status: st.status !== 'alle' ? st.status : null, team: st.team || null, sicht: st.sicht !== 'saison' ? st.sicht : null});
  };
  let timer;
  U.ap(box, stand(),
    h('div', {class: 'row'}, U.seg('Position', [['', 'Alle'], ...POS.map(p => [p, p])], st.pos, v => { st.pos = v; refresh(); })),
    h('div', {class: 'row'}, U.seg('Status', [['alle', 'Alle'], ['kader', 'Kader'], ['frei', 'Frei']], st.status, v => { st.status = v; refresh(); }),
      h('label', null, h('span', {class: 'vh'}, 'Fantasy-Team '), h('select', {onchange: e => { st.team = +e.target.value; refresh(); }},
        h('option', {value: 0}, 'Alle Teams'), S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === st.team}, t.name))))),
    h('div', {class: 'row'}, h('label', null, h('span', {class: 'vh'}, 'Spieler suchen'),
      h('input', {type: 'search', placeholder: 'Name suchen', oninput: e => {
        clearTimeout(timer);
        timer = setTimeout(() => { st.text = e.target.value.trim().toLowerCase(); refresh(); }, 150);
      }})),
    U.seg('Spalten', [['saison', 'Saison'], ['ros', 'ROS'], ['besitz', 'Besitz']], st.sicht, v => { st.sicht = v; refresh(true); })),
    count, slotBox,
    U.legend(['avg', 'form-sp', 'trendpfeil', 'ros-spiel', 'spiele', 'floor-ceil', 'konstanz', 'starts', 'proj-delta-sp', 'ros', 'restspiele', 'ros-po', 'ros-rang', 'ros-ue', 'projektionen']));
  refresh(true);
}

function one(box, h1, P, pid, svg, rosWhy) {
  const p = P.players.find(x => String(x.id) === pid);
  U.ap(box, h('p', null, h('a', {href: '#spieler'}, '← Spielerliste')));
  if (!p) { h1.textContent = 'Spieler nicht gefunden'; U.ap(box, h('p', {class: 'note'}, 'Dieser Spieler steht nicht in den App-Daten (nur Kader, Spieler mit Einsatz und die besten Free Agents).')); return; }
  h1.textContent = p.name;
  const ers = P.ersatz?.[p.pos];
  U.ap(box, h('p', null, `${p.pos} · ${p.nfl} · `, p.team > 0 ? U.tl(p.team) : STAT[p.status] || 'frei',
    p.inj && INJ[p.inj] ? h('span', {class: 'badge'}, INJ[p.inj][1]) : null,
    p.pos === 'D/ST' ? [' · ', h('a', {href: '#dst'}, 'D/ST-Faktoren')] : null), stand(),
  h('div', {class: 'tiles'},
    U.tile('Pkt Saison', U.num(p.pts), `${p.g ?? 0} Spiele`, 'spiele'),
    U.tile('Ø', U.val(p.avg, U.num, 'ohne Spiel'), null, 'avg'),
    U.tile('Floor / Ceiling', `${U.num(p.floor)} / ${U.num(p.ceil)}`, null, 'floor-ceil'),
    U.tile('Konstanz', U.val(p.sd, U.num, 'unter 2 Spielen'), null, 'konstanz'),
    U.tile('Form', [U.val(p.form, U.num, 'ohne Spiel'), ' ', trendTxt(p.trend)], `Form Δ ${U.sgn(p.form_d)}`, 'form-sp'),
    U.tile('Starts', U.val(p.starts, v => v), `Bank-Punkte ${U.num(p.bench_pts)}`, 'starts'),
    U.tile('Proj.-Δ', U.val(p.proj_d, U.sgn, 'ohne Spiel'), null, 'proj-delta-sp'),
    U.tile('Besitz', U.val(p.own, v => U.pct(v)), STAT[p.status] || p.status, 'besitz')));
  const W = P.weeks || [], wk = p.wk || [];
  const vals = wk.map(x => x[2] ? null : x[0]);
  U.ap(box, svg.fig('Formkurve', svg.bars({title: `Formkurve ${p.name}`,
    desc: `Punkte je Woche; ${p.g ?? 0} Spiele, Ø ${U.num(p.avg)}; „·“ = Bye, „–“ = nicht gespielt, Strich = Projektion.`,
    x: W.map(w => 'W' + w), vals, miss: i => wk[i]?.[2] ? '·' : '–', tick: wk.map(x => x[1]),
    cls: i => wk[i]?.[4] == null || U.bench(wk[i][4]) ? 'bN' : 'bA', label: i => U.ok(wk[i]?.[0]) ? U.num(wk[i][0], 1) : null, yfmt: v => U.num(v, 0)}),
  {heads: ['Woche', 'Pkt', 'Proj.', 'Team', 'Slot'], rows: W.map((w, i) => ['W' + w, wk[i]?.[2] ? 'Bye' : U.num(wk[i]?.[0]), U.num(wk[i]?.[1]),
    wk[i]?.[3] ? U.kz(wk[i][3]) : 'frei', U.slot(wk[i]?.[4])])},
  h('p', {class: 'note'}, 'Blau = Starter, grau = Bank oder ohne Team, orange Strich = ESPN-Projektion. ', U.ib('formkurve', ''))));
  U.ap(box, h('h2', null, 'Rest of Season'), P.ros_nach_woche == null ? h('p', {class: 'warn'}, `ROS-Werte ${rosWhy}.`) : null,
    h('div', {class: 'tiles'},
      U.tile('ROS/Spiel', U.val(p.ros_g, U.num, rosWhy), null, 'ros-spiel'),
      U.tile('ROS', U.val(p.ros, U.num, rosWhy), U.ok(p.rest_g) ? `${p.rest_g} Restspiele` : null, 'ros'),
      U.tile('ROS Playoffs', U.val(p.ros_po, U.num, rosWhy), null, 'ros-po'),
      U.tile('ROS-Rang', U.val(p.ros_rang, v => `${p.pos} ${v}`, rosWhy), null, 'ros-rang'),
      U.tile('Ersatzniveau', U.val(ers, U.num, rosWhy), p.pos, 'ersatz'),
      U.tile('ROS über Ersatz', U.val(p.ros_ue, U.sgn, rosWhy), null, 'ros-ue')),
    h('p', {class: 'note'}, 'Alle Projektionen sind ESPN-Schätzungen. ', U.ib('projektionen', '')));
}
