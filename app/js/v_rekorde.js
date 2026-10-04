// Bereich Liga: Duelle (#liga/duelle, die direkten Duelle 2026) und Rekorde (#liga/rekorde) mit zweiter Ebene Saison 2026
// (RS und Playoffs getrennt), Positionen, Wochen 2018–2022 (nfl.com-Auskunft), All-Time und Champions (history.json lazy)
let U, S, h;
const SUBS = [['', 'Saison'], ['positionen', 'Positionen'], ['wochen', 'Wochen 2018–2022'], ['alltime', 'All-Time'], ['champions', 'Champions']];
const LABEL = {hoechster_score: 'Höchster Wochenscore', niedrigster_score: 'Niedrigster Wochenscore', groesster_sieg: 'Größter Sieg',
  knappstes_ergebnis: 'Knappstes Ergebnis', hoechster_verlierer: 'Höchster Verlierer-Score',
  niedrigster_sieger: 'Niedrigster Sieger-Score', laengste_siegesserie: 'Längste Siegesserie', laengste_niederlagenserie: 'Längste Niederlagenserie',
  hoechste_bank: 'Meiste Bankpunkte', meiste_verschenkt: 'Meiste verschenkte Punkte', bester_spieler: 'Bester Einzelspieler',
  beste_bilanz: 'Beste Bilanz', meiste_pf: 'Meiste PF je Spiel', beste_pf_plus: 'Beste PF+', wenigste_pf: 'Wenigste PF je Spiel'};
const AERA = {alt: 'Alt-Scoring 2015–17', bwg: 'BWG-Scoring ab 2018'};
// Wochen 2018–2022 (history.json › wochen): Teile, Phasen, Rekorde je Phase (niedrig = besser bei TIEF), Playoff-Runden und
// Herleitung der Paarung auf Deutsch; Reihenfolge der Kategorien der kuratierten Rekorde (All-Time)
const TEILE = [['', 'Spielwochen'], ['rekorde', 'Rekorde'], ['duelle', 'Duelle'], ['allplay', 'All-Play']];
const PHASE = [['RS', 'Regular Season'], ['PO', 'Playoffs']];
const WREK = ['hoechster_score', 'niedrigster_score', 'groesster_sieg', 'knappstes_ergebnis', 'hoechste_bank'];
const TIEF = new Set(['niedrigster_score', 'knappstes_ergebnis']);
const RS_RUNDE = 'Regular Season';
const RUNDE = {Quarterfinal: 'Runde 1', Semifinal: 'Halbfinale', Final: 'Finale'};
const HERL = {Bracket: 'Paarung aus Endplätzen und Punkten', Screenshot: 'Paarung per Screenshot belegt', 'Bestätigt': 'Paarung bestätigt',
  'Seed-Regel': 'Paarung nach der Seed-Regel', Endplatz: 'Paarung aus den Endplätzen'};
const KAT = ['Titel', 'Bilanz', 'Saison', 'Playoffs', 'Woche', 'Serie', 'Rivalry'];
const POS = ['QB', 'RB', 'WR', 'TE', 'K', 'D/ST'], SLOTS = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'OP', 'D/ST', 'K'];

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  if (r.view === 'duelle') {
    U.kopf(box, r, 'Duelle');
    h2h(box, r);
    return;
  }
  const sub = SUBS.some(x => x[0] === r.sub) ? r.sub : '';
  U.kopf(box, r, 'Rekorde – ' + SUBS.find(x => x[0] === sub)[1]);
  U.ap(box, U.chips('Ansichten der Rekorde', SUBS.map(([k, l]) => ['#' + r.base + (k ? '/' + k : ''), l, k]), sub, 'l2'));
  const svg = await ctx.mod('svg');
  if (sub === 'alltime' || sub === 'champions' || sub === 'wochen') {
    const H = await ctx.lazy('history.json', 'Historie', box);
    if (!r.alive()) return;
    ({alltime, champions, wochen})[sub](box, H, r, svg);
  } else ({'': saison, positionen})[sub](box, r, svg);
}

// Rekordlisten: je Rekord eine Liste von Einträgen (Gleichstand = mehrere). Eintrag laut Export:
// {team_id, week, opponent_id, wert} · Duell {week, team_ids: [Sieger, Verlierer], punkte, wert, unentschieden}
// · Serie {team_id, weeks, wert, laufend} · Spieler {player_id, name, pos, team_id, week, slot, wert}
const entries = rec => Object.entries(rec || {});
const filled = rec => entries(rec).some(([, l]) => (l || []).length);
function recTable(cap, rec) {
  const rows = entries(rec).flatMap(([id, list]) => (list || []).map((e, i) => ({id, e, first: i === 0})));
  const tid = e => e.team_id ?? e.team_ids?.[0];
  const serie = e => Array.isArray(e.weeks);
  const wk = e => {
    if (serie(e)) return (e.weeks[0] !== e.weeks.at(-1) ? `W${e.weeks[0]}–W${e.weeks.at(-1)}` : `W${e.weeks[0] ?? '–'}`) + (e.laufend ? ' (läuft)' : '');
    return U.ok(e.week) ? h('a', {href: '#liga/ergebnisse/w' + e.week}, 'W' + e.week) : '–';
  };
  // lab: erste Spalte bricht auf dem Handy um, kurz: Teams als Kürzel – sonst frisst die feste Spalte die Tabelle
  return U.table({cap, cls: 'nr kurz lab', rows, sortable: false, rh: 0, cols: [
    {k: 'r', l: 'Rekord', f: x => x.first ? LABEL[x.id] || x.id.replace(/_/g, ' ') : h('span', {class: 'note'}, 'ebenso')},
    {k: 'v', l: 'Wert', num: 1, f: x => serie(x.e) ? `${x.e.wert} ${x.e.wert === 1 ? 'Spiel' : 'Spiele'}` : U.num(x.e.wert)},
    {k: 't', l: 'Team', f: x => tid(x.e) != null ? U.tl(tid(x.e)) : '–'},
    {k: 'w', l: 'Woche', f: x => wk(x.e)},
    {k: 'd', l: 'Details', f: x => {
      const e = x.e, extra = [e.pos, e.slot && U.slot(e.slot)].filter(Boolean);
      if (e.player_id != null) return [h('a', {href: '#spieler/' + e.player_id}, e.name || 'Spieler'), extra.length ? ` (${extra.join(', ')})` : ''];
      if (e.team_ids) return `${U.kz(e.team_ids[0])} ${U.num(e.punkte?.[0])} : ${U.num(e.punkte?.[1])} ${U.kz(e.team_ids[1])}` + (e.unentschieden ? ' (Unentschieden)' : '');
      if (e.opponent_id != null) return `gegen ${U.kz(e.opponent_id)}`;
      return '';
    }}]});
}

function saison(box) {
  const fin = S.weeks.filter(w => w.status === 'final');
  if (fin.length) {
    const best = fin.reduce((a, w) => (w.high?.pf ?? -1) > (a.high?.pf ?? -1) ? w : a, fin[0]);
    const low = fin.reduce((a, w) => (w.low?.pf ?? 1e9) < (a.low?.pf ?? 1e9) ? w : a, fin[0]);
    const avg = fin.reduce((a, w) => a + w.ligaschnitt, 0) / fin.length;
    U.ap(box, h('div', {class: 'tiles'},
      U.tile(`Saisonbestwert · W${best.week}`, U.num(best.high?.pf), U.tl(best.high?.team_id)),
      U.tile('Saisonschnitt', U.num(avg), `Ø Ligaschnitt W1–${fin.at(-1).week}`),
      U.tile(`Saisontiefstwert · W${low.week}`, U.num(low.low?.pf), U.tl(low.low?.team_id))));
  }
  U.ap(box, recTable(`Rekorde Regular Season 2026 (nach W${S.tw})`, S.sched.records_rs),
    h('h2', {style: 'margin-top:16px'}, 'Playoffs 2026'),
    filled(S.sched.records_po) ? recTable('Rekorde Playoffs 2026', S.sched.records_po) : h('p', {class: 'note'}, 'Playoff-Rekorde ab W15.'),
    U.legend(['rs-po', 'verschenkt', 'bank']));
}

const share = (obj, k) => { const tot = Object.values(obj).reduce((a, x) => a + (x?.anteil || 0), 0); const v = obj[k]?.anteil; return U.ok(v) ? (tot <= 1.5 ? v * 100 : v) : null; };
function positionen(box, r, svg) {
  let key = r.q.get('slot') === '1' ? 'nach_slot' : 'nach_position', wert = ['anteil', 'rang'].includes(r.q.get('wert')) ? r.q.get('wert') : 'pts';
  let sortK = 'rang';   // gewählte Sortierspalte bleibt beim Wechsel der Werte; Richtung nach dem Standard der Spalte
  const COL = {QB: 'o1', RB: 'o2', WR: 'o3', TE: 'o4', K: 'o5', 'D/ST': 'o6', FLEX: 'o7', OP: 'o8'};   // feste Farbe je Position
  const q = () => U.setQ(r.base + '/positionen', {slot: key === 'nach_slot' ? 1 : null, wert: wert !== 'pts' ? wert : null});
  const wrap = h('div'), chart = h('div');
  const draw = () => {
    const keys = key === 'nach_slot' ? SLOTS : POS, P = t => t.positionen?.[key] || {};
    const cell = (t, k) => { const o = P(t)[k]; if (!o) return '–'; return wert === 'pts' ? U.num(o.pts) : wert === 'anteil' ? U.pct(share(P(t), k)) : U.val(o.rang, v => v + '.'); };
    if (sortK !== 'rang' && sortK !== 'team' && !keys.includes(sortK)) sortK = 'rang';
    const dir = sortK === 'rang' || sortK === 'team' || wert === 'rang' ? 1 : -1;
    wrap.replaceChildren(U.table({cap: `PF nach ${key === 'nach_slot' ? 'Slot' : 'Position'} (${wert === 'pts' ? 'Punkte' : wert === 'anteil' ? 'Anteil' : 'Ligarang'})`,
      cls: 'rk', rc: U.meRc, rows: S.teams, sort: [sortK, dir], onSort: k => { sortK = k; }, cols: [
        {k: 'rang', l: '#', v: t => t.rang, d: 1, f: t => t.rang}, {k: 'team', l: 'Team', v: t => t.name.toLowerCase(), d: 1, f: t => U.tl(t.team_id)},
        ...keys.map(k => ({k, l: k, num: 1, d: wert === 'rang' ? 1 : -1, v: t => wert === 'anteil' ? share(P(t), k) : P(t)[k]?.[wert === 'pts' ? 'pts' : 'rang'], f: t => cell(t, k)}))]}));
    const names = keys, cls = j => COL[keys[j]];
    chart.replaceChildren(svg.fig('Anteile je Team', svg.stack({title: `Anteil der PF nach ${key === 'nach_slot' ? 'Slot' : 'Position'} je Team`, total: 100, names, cls,
      fmt: v => U.pct(v), desc: 'Gestapelte 100-%-Balken je Team; genaue Werte in der Tabelle.',
      rows: S.teams.map(t => ({label: t.kuerzel, parts: keys.map(k => share(P(t), k))}))}),
    {heads: ['Team', ...keys], rows: S.teams.map(t => [t.name, ...keys.map(k => U.pct(share(P(t), k)))])}, svg.swatches(names, cls)));
  };
  U.ap(box, h('div', {class: 'row gap'}, U.seg('Aufteilung', [['nach_position', 'Position'], ['nach_slot', 'Slot']], key, v => {
    key = v; q(); draw();
  }), h('span', {class: 'sep', 'aria-hidden': 'true'}), U.seg('Werte', [['pts', 'Punkte'], ['anteil', 'Anteil'], ['rang', 'Ligarang']], wert, v => { wert = v; q(); draw(); }), U.ib('positionen', '')),
  wrap, chart);
  draw();
}

function h2h(box, r) {
  const E = S.sched.h2h || [];
  // ?team=N, sonst Mein Team, ohne Wahl das erste Team
  let sel = S.byId.has(+r.q.get('team')) ? +r.q.get('team') : U.meinTeam() || S.teams[0]?.team_id;
  const rec = (a, b) => {
    const e = E.find(x => (x.a === a && x.b === b) || (x.a === b && x.b === a));
    if (!e || !e.spiele) return null;
    const me = e.a === a;
    return {n: e.spiele, w: me ? e.w_a : e.l_a, l: me ? e.l_a : e.w_a, t: e.t, d: me ? e.pf_diff : -e.pf_diff};
  };
  const txt = x => `${x.w}-${x.l}` + (x.t ? `-${x.t}` : '');
  const list = h('div');
  const mxRows = new Map();
  const draw = () => {
    const rows = S.teams.filter(t => t.team_id !== sel).map(t => ({t, x: rec(sel, t.team_id)}));
    for (const [tid, tr] of mxRows) tr.classList.toggle('me', tid === sel);
    list.replaceChildren(U.table({cap: `Duelle 2026: ${U.team(sel)?.name}`, cls: 'nr kurz', rh: 0, rows, sort: ['d', -1], cols: [
      {k: 'o', l: 'Gegner', v: x => x.t.name.toLowerCase(), d: 1, f: x => U.tl(x.t.team_id)},
      {k: 'n', l: 'Spiele', num: 1, v: x => x.x?.n ?? null, f: x => x.x ? x.x.n : U.na('noch kein Duell')},
      {k: 'b', l: 'Bilanz', v: x => x.x ? x.x.w - x.x.l : null, f: x => x.x ? txt(x.x) : '–'},
      {k: 'd', l: 'PF-Diff', num: 1, v: x => x.x?.d ?? null, f: x => x.x ? U.sgn(x.x.d) : '–'}]}));
  };
  const mx = U.scrollHint(h('div', {class: 'tw', role: 'region', tabindex: '0', 'aria-label': 'Matrix aller Duelle'},
    h('table', {class: 'mx'}, h('caption', null, 'Alle Duelle 2026 (Zeile gegen Spalte, W-L)'),
      h('thead', null, h('tr', null, h('td', null, ''), S.teams.map(t => h('th', {scope: 'col'}, h('a', {href: '#team/' + t.team_id, 'aria-label': t.name}, t.kuerzel))))),
      h('tbody', null, S.teams.map(a => {
        // Zeilenkopf wählt das Team für die Liste darüber (Spaltenköpfe bleiben Team-Links)
        const tr = h('tr', null, h('th', {scope: 'row'}, h('a', {href: '#' + r.base + '?team=' + a.team_id, 'aria-label': `Duelle von ${a.name} anzeigen`, onclick: e => {
          e.preventDefault(); sel = a.team_id; U.setQ(r.base, {team: sel}); selBox.value = String(sel); draw();
          list.scrollIntoView({block: 'start', behavior: 'smooth'});
        }}, a.kuerzel)),
        S.teams.map(b => {
          if (a === b) return h('td', {class: 'hx'}, '–');
          const x = rec(a.team_id, b.team_id);
          return h('td', {class: !x ? 'h0' : x.w > x.l ? 'hw' : x.w < x.l ? 'hl' : 'he', title: x ? `PF-Diff ${U.sgn(x.d)}` : null}, x ? txt(x) : '');
        }));
        mxRows.set(a.team_id, tr);
        return tr;
      })))));
  const selBox = h('select', {onchange: e => {
    sel = +e.target.value; U.setQ(r.base, {team: sel}); draw();
  }}, S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === sel}, t.name)));
  U.ap(box, h('div', {class: 'row'}, h('label', null, 'Team ', selBox)),
  list, U.legend(['h2h']), h('h2', {style: 'margin-top:16px'}, 'Alle Duelle'), mx,
  h('p', {class: 'note'}, 'Blau = Bilanz positiv, orange = negativ, grau = ausgeglichen, leer = noch kein Duell, – = dasselbe Team; die Bilanz steht immer in der Zelle. Kürzel links wählt das Team für die Liste oben.'));
  draw();
}

function alltime(box, H, r) {
  const A = H.alltime || [];
  U.ap(box, U.table({cap: h('span', null, 'All-Time 2015–2025', h('span', {class: 'sub'}, 'Bilanz und PF: Regular Season')), cls: 'nr kurz lab', rh: 0, rows: A, sort: ['ti', -1], cols: [
    {k: 'n', l: 'Franchise', v: a => a.name_2026.toLowerCase(), d: 1, f: a => [U.team(a.slot) ? U.tl(a.slot) : a.name_2026,
      a.namenskette !== a.name_2026 ? h('span', {class: 'sub'}, a.namenskette) : null]},
    {k: 's', l: 'Saisons', num: 1, v: a => a.saisons, f: a => a.saisons},
    {k: 'wl', l: 'W-L', num: 1, v: a => a.w, f: a => `${a.w}-${a.l}`},
    {k: 'wp', l: 'W %', num: 1, x: 1, v: a => a.w_pct, f: a => U.pct(a.w_pct)},
    {k: 'pf', l: 'PF', num: 1, x: 1, v: a => a.pf, f: a => U.num(a.pf)},
    {k: 'pp', l: 'Ø PF+', num: 1, x: 1, v: a => a.pf_plus_avg, f: a => U.num(a.pf_plus_avg, 1)},
    {k: 'ti', l: 'Titel', num: 1, v: a => a.titel, f: a => a.titel},
    {k: 'fi', l: 'Finals', num: 1, v: a => a.finals, f: a => a.finals},
    {k: 'po', l: 'Playoffs', num: 1, v: a => a.playoffs, f: a => a.playoffs},
    {k: 'dv', l: 'Divisionstitel', num: 1, x: 1, v: a => a.divisionssiege, f: a => a.divisionssiege},
    {k: 'sc', l: 'Scoring-Titel', num: 1, x: 1, v: a => a.scoring_titel, f: a => a.scoring_titel},
    {k: 'le', l: 'Letzter Platz', num: 1, x: 1, v: a => a.letzte, f: a => a.letzte},
    {k: 'pl', l: 'Ø Platz', num: 1, x: 1, v: a => a.platz_avg, d: 1, f: a => U.num(a.platz_avg, 1)}]}),
  U.legend(['saisons', 'wpct-alltime', 'pfplus', 'pfplus-avg', 'titel-finals', 'playoffs-alltime', 'div-titel', 'scoring-titel', 'letzter', 'endplatz', 'aera']));
  const R = H.rekorde || {};
  const der = R.abgeleitet || [];
  if (der.length) U.ap(box, U.table({cap: 'Abgeleitete All-Time-Rekorde je Ära', cls: 'nr kurz lab', rh: 0, sortable: false, rows: der, cols: [
    {k: 'r', l: 'Rekord', f: x => LABEL[x.id] || x.id},
    {k: 'a', l: 'Ära', f: x => AERA[x.aera] || x.scoring_era},
    {k: 'v', l: 'Wert', num: 1, f: x => x.kriterium === 'w_pct' ? U.pct(x.wert) : U.num(x.wert, x.kriterium === 'pf_plus' ? 1 : 2)},
    {k: 'h', l: 'Halter', f: x => (x.halter || []).map((t, i) => [i ? ', ' : '', `${t.team_name} ${t.season}`])}]}));
  const top = R.hoechstes_einzelspiel;
  if (top) U.ap(box, U.card('Höchstes Einzelspiel (vor 2026)',
    (top.halter || []).map(t => h('p', null, h('strong', null, U.num(top.wert)), ` – ${t.team_name}, ${t.season} W${t.week} (${RUNDE[t.round] || t.round}) gegen ${t.gegner_name} ${U.num(t.gegner_pts)}`)),
    h('p', {class: 'note'}, `Status: ${top.status}. ${top.hinweis ? top.hinweis[0].toUpperCase() + top.hinweis.slice(1) + '.' : ''}`, U.ib('unverifiziert', ''))));
  kuratiert(box, R.kuratiert || []);
  // Saisontabellen je Jahr; 2018–2022 mit All-Play % aus den Wochen des nfl.com-Exports
  const seasons = (H.seasons || []).map(s => s.season);
  if (!seasons.length) return;
  let yr = seasons.includes(+r.q.get('saison')) ? +r.q.get('saison') : seasons.at(-1);
  const AP = new Map((H.wochen?.allplay || []).map(a => [a.season + '/' + a.slot, a]));
  const out = h('div');
  const draw = () => {
    const f = (H.seasons || []).find(s => s.season === yr) || {};
    const rows = (H.team_seasons || []).filter(t => t.season === yr);
    const ap = t => AP.get(yr + '/' + t.slot);
    const mitAp = rows.some(ap);
    out.replaceChildren(h('p', {class: 'note'}, [f.platform, f.teams && `${f.teams} Teams`, f.rs_games && `${f.rs_games} Spiele Regular Season`, f.scoring_era, f.qb_format, f.playoff_format].filter(Boolean).join(' · ')),
      mitAp ? h('p', {class: 'note'}, 'Wochen, Paarungen und All-Play dieser Saison unter ', h('a', {href: `#${r.base}/wochen?saison=${yr}`}, 'Wochen 2018–2022'), '.') : null,
      U.table({cap: `Saison ${yr}`, cls: 'rk', rows, sort: ['p', 1], cols: [
        {k: 'p', l: '#', v: t => t.final_rank, d: 1, f: t => t.final_rank},
        {k: 'n', l: 'Team', v: t => t.team_name.toLowerCase(), d: 1, f: t => t.team_name},
        {k: 'dv', l: 'Division / Platz', num: 1, x: 1, v: t => t.division * 10 + t.div_rank, d: 1, f: t => `${t.division}/${t.div_rank}.`},
        {k: 'wl', l: 'W-L', num: 1, v: t => t.w_pct, f: t => `${t.w}-${t.l}`},
        {k: 'pf', l: 'PF', num: 1, v: t => t.pf, f: t => U.num(t.pf)},
        {k: 'pp', l: 'PF+', num: 1, v: t => t.pf_plus, f: t => U.num(t.pf_plus, 1)},
        ...mitAp ? [{k: 'ap', l: 'All-Play %', num: 1, v: t => ap(t)?.allplay_pct, f: t => U.val(ap(t)?.allplay_pct, U.pct, 'nicht im Export')}] : [],
        {k: 'po', l: 'Playoffs', v: t => +t.playoffs, f: t => t.playoffs ? h('span', null, '✓', h('span', {class: 'vh'}, ' ja')) : ''},
        {k: 'sc', l: 'Scoring-Titel', x: 1, v: t => +t.scoring_titel, f: t => t.scoring_titel ? h('span', null, '✓', h('span', {class: 'vh'}, ' ja')) : ''}]}));
  };
  U.ap(box, h('h2', {style: 'margin-top:16px'}, 'Saisontabellen'), h('div', {class: 'row'}, h('label', null, 'Saison ', h('select', {onchange: e => {
    yr = +e.target.value; U.setQ(r.base + '/alltime', {saison: yr}); draw();
  }}, seasons.map(y => h('option', {value: y, selected: y === yr}, y))))), out);
  draw();
}

function champions(box, H) {
  const C = H.champions || [];
  U.ap(box, U.table({cap: 'Champions 2015–2025', cls: 'nr', rh: 1, rows: C, sort: ['s', -1], cols: [
    {k: 's', l: 'Saison', num: 1, v: c => c.season, f: c => c.season},
    {k: 'n', l: 'Champion', v: c => c.team_name.toLowerCase(), d: 1, f: c => [c.team_name, U.team(c.slot) && U.team(c.slot).name !== c.team_name ? h('span', {class: 'sub'}, 'heute ' + U.team(c.slot).name) : null]},
    {k: 'wl', l: 'W-L', num: 1, v: c => c.w, f: c => `${c.w}-${c.l}`},
    {k: 'pf', l: 'PF', num: 1, v: c => c.pf, f: c => U.num(c.pf)},
    {k: 'pp', l: 'PF+', num: 1, v: c => c.pf_plus, f: c => U.num(c.pf_plus, 1)},
    {k: 'sc', l: 'Scoring-Titel', v: c => +c.scoring_titel, f: c => c.scoring_titel ? h('span', null, '✓', h('span', {class: 'vh'}, ' ja')) : ''},
    {k: 'a', l: 'Ära', v: c => c.aera, d: 1, f: c => [AERA[c.aera] || c.scoring_era, c.rs_games ? h('span', {class: 'sub'}, `${c.rs_games} Spiele Regular Season`) : null]}]}),
  U.legend(['pfplus', 'scoring-titel', 'aera']));
  const n = {};
  for (const c of C) n[c.slot] = (n[c.slot] || 0) + 1;
  U.ap(box, U.card('Titel je Franchise', h('ul', null, Object.entries(n).sort((a, b) => b[1] - a[1]).map(([s, k]) =>
    h('li', null, U.team(s) ? U.tl(s) : 'Slot ' + s, `: ${k}`)))));
}

// Kuratierte Rekorde aus dem Ligaarchiv (history.json › rekorde.kuratiert, Spiegel der Notion-DB Rekorde nach Durchsicht):
// je Kategorie ein Aufklapper je Rekord mit Wert, Details und Quelle; Texte wie gepflegt
function kuratiert(box, K) {
  if (!K.length) return;
  const kats = [...KAT, ...new Set(K.map(k => k.kategorie).filter(k => !KAT.includes(k)))];
  const beleg = k => [k.verifiziert ? 'verifiziert' : 'unverifiziert',
    k.ableitbar ? 'aus den Daten der Liga-Historie nachgerechnet' : 'nicht aus den Daten nachrechenbar'].join(', ');
  U.ap(box, U.card(null, h('h2', null, 'Rekorde aus dem Ligaarchiv ', U.ib('ligaarchiv', '')),
    h('p', {class: 'note'}, 'Von Hand gepflegte Rekorde der Ligageschichte 2015–2025, Teamnamen der jeweiligen Saison. Antippen für Details und Quelle.'),
    kats.map(kat => {
      const list = K.filter(k => k.kategorie === kat);
      return list.length ? [h('h3', null, kat), list.map(k => h('details', {class: 'dt'},
        h('summary', null, h('span', null, k.rekord, h('span', {class: 'sub', style: 'white-space:normal'}, k.wert))),   // lange Werte umbrechen
        k.details ? h('p', null, k.details) : null,
        h('p', {class: 'note'}, `Quelle: ${k.quelle} · ${beleg(k)}`)))] : null;
    })));
}

// ---------------------------------------------------------------- Wochen 2018–2022 (#liga/rekorde/wochen)
// nfl.com-Ära aus dem Export vom 24.09.2026 (history.json › wochen): Teile Spielwochen (?saison, ?woche), Rekorde (?phase),
// Duelle (?phase, ?team) und All-Play (?saison). Eigene Statistik – Plattform und Scoring anders als ab 2026, nie mit den
// Rekorden 2026 mischen. Teamnamen der jeweiligen Saison; Duelle je Franchise mit dem Namen von heute.
function wochen(box, H, r) {
  const W = H.wochen || {}, saisons = W.saisons || [];
  if (!saisons.length) { U.ap(box, h('p', {class: 'note'}, 'Keine Wochen 2018–2022 vorhanden.')); return; }
  const names = new Map((H.team_seasons || []).map(t => [t.season + '/' + t.slot, t.team_name]));
  const st = {
    nm: (yr, slot) => names.get(yr + '/' + slot) || U.team(slot)?.name || 'Slot ' + slot,
    teil: TEILE.some(x => x[0] === r.q.get('teil')) ? r.q.get('teil') : '',
    phase: r.q.get('phase') === 'PO' ? 'PO' : 'RS',
    yr: saisons.includes(+r.q.get('saison')) ? +r.q.get('saison') : saisons.at(-1),
    wk: +r.q.get('woche') || 0,
    sel: S.byId.has(+r.q.get('team')) ? +r.q.get('team') : U.meinTeam() || S.teams[0]?.team_id,
  };
  // teilbarer Link: nur die Parameter des gewählten Teils
  st.q = () => U.setQ(r.base + '/wochen', {teil: st.teil || null,
    saison: st.teil === '' || st.teil === 'allplay' ? st.yr : null, woche: st.teil === '' ? st.wk || null : null,
    phase: (st.teil === 'rekorde' || st.teil === 'duelle') && st.phase === 'PO' ? 'PO' : null, team: st.teil === 'duelle' ? st.sel : null});
  const out = h('div');
  const draw = () => {
    out.replaceChildren();
    ({'': spielwochen, rekorde: wRekorde, duelle: wDuelle, allplay: wAllplay})[st.teil](out, W, st, saisons);
  };
  U.ap(box, h('p', {class: 'note'}, 'nfl.com-Ära: Wochenpunkte, Paarungen und Bankpunkte aller Teams 2018–2022 aus dem Datenexport von nfl.com (24.09.2026). ',
    'Eigene Statistik – Plattform und Scoring waren anders als ab 2026, deshalb nicht mit den Rekorden 2026 vergleichbar. Teamnamen der jeweiligen Saison. ', U.ib('wochen-nfl', '')),
  U.seg('Teil der Wochen 2018–2022', TEILE, st.teil, v => { st.teil = v; st.q(); draw(); }), out);
  draw();
}

const seasonSeg = (st, saisons, on) => U.seg('Saison', saisons.map(y => [String(y), String(y)]), String(st.yr), v => { st.yr = +v; st.q(); on(); });
const platzVon = (v, alle) => 1 + alle.filter(x => x > v).length;   // 1 + Zahl der besseren Werte, Gleichstand teilt den besseren Platz

// Spielwochen: Saison und Woche wählen; Kacheln und Wochentabelle nur in der Regular Season (in den Playoffs spielen nicht
// alle Teams gegeneinander), Paarungen mit Runde und Herleitung, Teams ohne Spiel im Export, Saisonwochen im Überblick
function spielwochen(out, W, st, saisons) {
  const box = h('div'), segBox = h('div');
  const draw = () => {
    const yr = st.yr, nm = slot => st.nm(yr, slot), mein = U.meinTeam();
    const games = (W.spiele || []).filter(g => g.season === yr), free = (W.ohne_gegner || []).filter(g => g.season === yr);
    const weeks = [...new Set([...games.map(g => g.week), ...free.map(g => g.week)])].sort((a, b) => a - b);
    const po = new Set([...games.filter(g => g.round !== RS_RUNDE).map(g => g.week), ...free.filter(g => g.phase === 'PO').map(g => g.week)]);
    if (!weeks.includes(st.wk)) {           // Woche fehlt in der Saison (W17 gab es erst ab 2021): erste Woche, Link nachziehen
      const hatte = st.wk;
      st.wk = weeks[0];
      if (hatte) st.q();
    }
    const wk = st.wk, gs = games.filter(g => g.week === wk), fr = free.filter(g => g.week === wk);
    const sides = gs.flatMap(g => [[g.slot_a, g.pts_a, g.bench_a, g.slot_b], [g.slot_b, g.pts_b, g.bench_b, g.slot_a]].map(([slot, pf, bench, opp]) =>
      ({slot, pf, bench, opp, team_id: slot, res: g.winner_slot == null ? 'T' : g.winner_slot === slot ? 'W' : 'L'})));
    const wseg = U.seg('Woche', weeks.map(w => [String(w), po.has(w) ? `W${w} PO` : `W${w}`]), String(wk), v => { st.wk = +v; st.q(); draw(); }, 'tight');
    segBox.replaceChildren(h('div', {class: 'row gap'}, seasonSeg(st, saisons, draw)), wseg);
    // gewählte Woche in die Mitte der waagerecht scrollenden Leiste (Handy), wie U.centerChip bei den Wochen-Chips
    const b = wseg.querySelector('[aria-pressed="true"]');
    if (b) wseg.scrollLeft += b.getBoundingClientRect().left - wseg.getBoundingClientRect().left - (wseg.clientWidth - b.offsetWidth) / 2;
    const side = (g, slot, pts) => {
      const res = g.winner_slot == null ? 'T' : g.winner_slot === slot ? 'W' : 'L';
      return h('div', {class: 'gl' + (res === 'W' ? ' win' : '')}, h('span', {class: 'res'}, U.res(res)), h('span', {class: 'tl2'}, nm(slot)), h('span', {class: 'pts'}, U.num(pts)));
    };
    const meta = g => [g.round !== RS_RUNDE ? RUNDE[g.round] || g.round : null,
      g.winner_slot == null ? 'Unentschieden' : 'Differenz ' + U.num(Math.abs(g.pts_a - g.pts_b)),
      `Bank ${U.num(g.bench_a)} und ${U.num(g.bench_b)}`, g.round !== RS_RUNDE ? HERL[g.herleitung] || g.herleitung : null].filter(Boolean).join(' · ');
    const liste = gs.length ? h('ul', {class: 'games'}, gs.map(g => h('li', {class: 'game' + (mein && (g.slot_a === mein || g.slot_b === mein) ? ' mine' : '')},
      side(g, g.slot_a, g.pts_a), side(g, g.slot_b, g.pts_b), h('div', {class: 'gm'}, meta(g)))))
      : h('p', {class: 'note'}, 'In dieser Woche gibt es im Export keine Paarung.');
    const rs = !po.has(wk) && sides.length, pfs = sides.map(s => s.pf), kids = [];
    if (rs) {
      const best = (k, hoch) => sides.reduce((a, s) => (hoch ? s[k] > a[k] : s[k] < a[k]) ? s : a);
      const hi = best('pf', true), lo = best('pf', false), bk = best('bench', true);
      kids.push(h('div', {class: 'tiles'}, U.tile('Wochenbestwert', U.num(hi.pf), nm(hi.slot)),
        U.tile('Ligaschnitt', U.num(pfs.reduce((a, x) => a + x, 0) / pfs.length), null),
        U.tile('Tiefstwert', U.num(lo.pf), nm(lo.slot)), U.tile('Meiste Bankpunkte', U.num(bk.bench), nm(bk.slot))));
    }
    kids.push(h('h2', null, `Paarungen ${yr} W${wk}` + (po.has(wk) ? ' (Playoffs)' : '')), liste);
    if (fr.length) kids.push(U.table({cap: 'Ohne Spiel im Export (Bye oder Trostrunde)', cls: 'nr', rh: 0, rows: fr, sort: ['pf', -1], cols: [
      {k: 't', l: 'Team', v: x => nm(x.slot).toLowerCase(), d: 1, f: x => nm(x.slot)},
      {k: 'pf', l: 'PF', num: 1, v: x => x.pts, f: x => U.num(x.pts)},
      {k: 'bk', l: 'Bankpunkte', num: 1, v: x => x.bench, f: x => U.num(x.bench)}],
    note: 'Punkte ohne Gegner zählen für keinen Rekord; die Trostrunde ist nicht abgeleitet.'}));
    if (rs) {
      const apw = s => pfs.filter(x => x < s.pf).length, apl = s => pfs.filter(x => x > s.pf).length, apt = s => pfs.filter(x => x === s.pf).length - 1;
      const anyT = sides.some(s => apt(s) > 0);
      kids.push(U.table({cap: `Wochentabelle ${yr} W${wk}`, cls: 'rk', rc: U.meRc, rows: sides, sort: ['wr', 1], cols: [
        {k: 'wr', l: '#', v: s => platzVon(s.pf, pfs), d: 1, f: s => platzVon(s.pf, pfs)},
        {k: 't', l: 'Team', v: s => nm(s.slot).toLowerCase(), d: 1, f: s => nm(s.slot)},
        {k: 'pf', l: 'PF', num: 1, v: s => s.pf, f: s => U.num(s.pf)},
        {k: 'e', l: 'Erg.', v: s => s.res, f: s => U.res(s.res)},
        {k: 'o', l: 'Gegner', x: 1, v: s => nm(s.opp).toLowerCase(), d: 1, f: s => nm(s.opp)},
        {k: 'bk', l: 'Bankpunkte', num: 1, v: s => s.bench, f: s => U.num(s.bench)},
        {k: 'ap', l: anyT ? 'All-Play W-L-T' : 'All-Play W-L', num: 1, x: 1, v: apw, f: s => U.apwl(apw(s), apl(s), apt(s), anyT)}]}),
      U.legend(['wochenrang', 'bank', 'ap-wl']));
    }
    kids.push(saisonWochen(yr, weeks, po, games, nm, wk, w => {
      st.wk = w; st.q(); draw(); segBox.scrollIntoView({block: 'start', behavior: 'smooth'});
    }));
    box.replaceChildren(...kids.filter(Boolean));
  };
  U.ap(out, segBox, box);
  draw();
}

// Saisonwochen der Regular Season: Ligaschnitt, Hoch und Tief je Woche; die gewählte Woche hervorgehoben, Woche antippen wählt sie
function saisonWochen(yr, weeks, po, games, nm, cur, pick) {
  const rows = weeks.filter(w => !po.has(w)).map(w => {
    const s = games.filter(g => g.week === w).flatMap(g => [[g.slot_a, g.pts_a], [g.slot_b, g.pts_b]]);
    if (!s.length) return null;
    const hi = s.reduce((a, x) => x[1] > a[1] ? x : a), lo = s.reduce((a, x) => x[1] < a[1] ? x : a);
    return {w, schnitt: s.reduce((a, x) => a + x[1], 0) / s.length, hi, lo};
  }).filter(Boolean);
  if (!rows.length) return null;
  const who = x => h('span', null, U.num(x[1]), h('span', {class: 'sub'}, nm(x[0])));
  return U.table({cap: `Saisonwochen ${yr} (Regular Season)`, cls: 'nr', rh: 0, rows, sort: ['w', 1], rc: x => x.w === cur ? 'me' : null, cols: [
    {k: 'w', l: 'Woche', v: x => x.w, d: 1, f: x => h('a', {href: `#liga/rekorde/wochen?saison=${yr}&woche=${x.w}`, class: 'tl2',
      onclick: e => { e.preventDefault(); pick(x.w); }}, 'W' + x.w)},
    {k: 's', l: 'Ligaschnitt', num: 1, v: x => x.schnitt, f: x => U.num(x.schnitt)},
    {k: 'hi', l: 'Hoch', num: 1, v: x => x.hi[1], f: x => who(x.hi)},
    {k: 'lo', l: 'Tief', num: 1, v: x => x.lo[1], f: x => who(x.lo)}]});
}

// Wochenrekorde je Phase: je Rekord die Top 5 (Gleichstand an der Grenze kommt mit), Platz mit geteiltem Rang
function wRekorde(out, W, st) {
  const box = h('div');
  const wann = e => `${e.season} W${e.week}` + (e.round !== RS_RUNDE ? ` · ${RUNDE[e.round] || e.round}` : '');
  const draw = () => {
    const R = W.rekorde?.[st.phase] || {};
    box.replaceChildren(...WREK.map(id => {
      const list = R[id] || [], tief = TIEF.has(id), spiel = id === 'groesster_sieg' || id === 'knappstes_ergebnis';
      const platz = e => 1 + list.filter(x => tief ? x.wert < e.wert : x.wert > e.wert).length;
      const det = e => {
        if (e.team_ids) return (e.unentschieden ? 'Unentschieden ' : '') + `${U.num(e.punkte[0])} : ${U.num(e.punkte[1])} gegen ${e.namen[1]}`;
        return id === 'hoechste_bank' ? `PF ${U.num(e.pf)} gegen ${e.opponent_name}` : `gegen ${e.opponent_name} (${U.num(e.pa)})`;
      };
      return list.length ? U.table({cap: LABEL[id] + (st.phase === 'PO' ? ' (Playoffs)' : ''), cls: 'nr', rh: 2, sortable: false, rows: list,
        rc: e => U.meinTeam() && (e.team_id ?? e.team_ids?.[0]) === U.meinTeam() ? 'me' : null, cols: [
          {k: 'p', l: '#', f: e => platz(e) + '.'},
          {k: 'v', l: spiel ? 'Differenz' : 'Wert', num: 1, f: e => U.num(e.wert)},
          {k: 't', l: spiel ? 'Sieger' : 'Team', f: e => e.team_name ?? e.namen?.[0] ?? '–'},
          {k: 'w', l: 'Woche', f: wann},
          {k: 'd', l: 'Details', f: det}]}) : null;
    }).filter(Boolean));
  };
  U.ap(out, U.seg('Phase', PHASE, st.phase, v => { st.phase = v; st.q(); draw(); }), box,
    h('p', {class: 'note'}, 'Nur Spiele mit bekanntem Gegner; Playoffs mit Spiel um Platz 3 und 5, ohne Byes und Trostrunde.'), U.legend(['rs-po', 'bank']));
  draw();
}

// Duelle 2018–2022 je Franchise (Name von heute): Liste für ein Team und Matrix aller Paare, Regular Season und Playoffs getrennt
function wDuelle(out, W, st) {
  const list = h('div'), mxBox = h('div');
  const rec = (a, b) => {
    const e = (W.h2h?.[st.phase] || []).find(x => (x.a === a && x.b === b) || (x.a === b && x.b === a));
    if (!e || !e.spiele) return null;
    const me = e.a === a;
    return {n: e.spiele, w: me ? e.w_a : e.l_a, l: me ? e.l_a : e.w_a, t: e.t, d: me ? e.pf_diff : -e.pf_diff};
  };
  const txt = x => `${x.w}-${x.l}` + (x.t ? `-${x.t}` : '');
  const ph = () => st.phase === 'PO' ? 'Playoffs' : 'Regular Season';
  const selBox = h('select', {onchange: e => { st.sel = +e.target.value; st.q(); draw(); }},
    S.teams.map(t => h('option', {value: t.team_id, selected: t.team_id === st.sel}, t.name)));
  const draw = () => {
    const rows = S.teams.filter(t => t.team_id !== st.sel).map(t => ({t, x: rec(st.sel, t.team_id)}));
    list.replaceChildren(U.table({cap: `Duelle 2018–2022 (${ph()}): ${U.team(st.sel)?.name}`, cls: 'nr kurz', rh: 0, rows, sort: ['d', -1], cols: [
      {k: 'o', l: 'Gegner', v: x => x.t.name.toLowerCase(), d: 1, f: x => U.tl(x.t.team_id)},
      {k: 'n', l: 'Spiele', num: 1, v: x => x.x?.n ?? null, f: x => x.x ? x.x.n : U.na('kein Duell')},
      {k: 'b', l: 'Bilanz', v: x => x.x ? x.x.w - x.x.l : null, f: x => x.x ? txt(x.x) : '–'},
      {k: 'd', l: 'PF-Diff', num: 1, v: x => x.x?.d ?? null, f: x => x.x ? U.sgn(x.x.d) : '–'}]}));
    mxBox.replaceChildren(U.scrollHint(h('div', {class: 'tw', role: 'region', tabindex: '0', 'aria-label': 'Matrix aller Duelle 2018–2022'},
      h('table', {class: 'mx'}, h('caption', null, `Alle Duelle 2018–2022, ${ph()} (Zeile gegen Spalte, W-L)`),
        h('thead', null, h('tr', null, h('td', null, ''), S.teams.map(t => h('th', {scope: 'col'}, h('a', {href: '#team/' + t.team_id, 'aria-label': t.name}, t.kuerzel))))),
        h('tbody', null, S.teams.map(a => h('tr', {class: a.team_id === st.sel ? 'me' : null},
          h('th', {scope: 'row'}, h('a', {href: '#liga/rekorde/wochen?teil=duelle&team=' + a.team_id, 'aria-label': `Duelle von ${a.name} anzeigen`, onclick: e => {
            e.preventDefault(); st.sel = a.team_id; st.q(); selBox.value = String(st.sel); draw();
            list.scrollIntoView({block: 'start', behavior: 'smooth'});
          }}, a.kuerzel)),
          S.teams.map(b => {
            if (a === b) return h('td', {class: 'hx'}, '–');
            const x = rec(a.team_id, b.team_id);
            return h('td', {class: !x ? 'h0' : x.w > x.l ? 'hw' : x.w < x.l ? 'hl' : 'he', title: x ? `PF-Diff ${U.sgn(x.d)}` : null}, x ? txt(x) : '');
          }))))))));
  };
  U.ap(out, h('div', {class: 'row gap'}, U.seg('Phase', PHASE, st.phase, v => { st.phase = v; st.q(); draw(); }), h('label', null, 'Team ', selBox)),
    h('p', {class: 'note'}, 'Je Franchise mit dem Namen von heute, alle fünf Saisons zusammen; Playoffs mit Spiel um Platz 3 und 5. PF-Diff = Summe der Punktdifferenz.'), list,
    h('h2', {style: 'margin-top:16px'}, 'Alle Duelle'), mxBox,
    h('p', {class: 'note'}, 'Blau = Bilanz positiv, orange = negativ, grau = ausgeglichen, leer = kein Duell, – = dasselbe Team; die Bilanz steht immer in der Zelle. Kürzel links wählt das Team für die Liste oben.'));
  draw();
}

// All-Play je Saison (nur Regular Season): Bilanz gegen alle neun anderen je Woche, daneben die echte Bilanz
function wAllplay(out, W, st, saisons) {
  const box = h('div');
  const draw = () => {
    const rows = (W.allplay || []).filter(a => a.season === st.yr).map(a => ({...a, team_id: a.slot}));
    const pcts = rows.map(a => a.allplay_pct), anyT = rows.some(a => a.allplay_t);
    box.replaceChildren(U.table({cap: `All-Play ${st.yr} (Regular Season)`, cls: 'rk', rc: U.meRc, rows, sort: ['p', -1], cols: [
      {k: 'r', l: '#', v: a => platzVon(a.allplay_pct, pcts), d: 1, f: a => platzVon(a.allplay_pct, pcts)},
      {k: 't', l: 'Team', v: a => a.team_name.toLowerCase(), d: 1, f: a => a.team_name},
      {k: 'ap', l: anyT ? 'All-Play W-L-T' : 'All-Play W-L', num: 1, v: a => a.allplay_w, f: a => U.apwl(a.allplay_w, a.allplay_l, a.allplay_t, anyT)},
      {k: 'p', l: 'All-Play %', num: 1, v: a => a.allplay_pct, f: a => U.pct(a.allplay_pct)},
      {k: 'wl', l: 'Bilanz', num: 1, v: a => a.w / ((a.w + a.l) || 1), f: a => `${a.w}-${a.l}`}]}));
  };
  U.ap(out, h('div', {class: 'row gap'}, seasonSeg(st, saisons, draw)), box,
    h('p', {class: 'note'}, 'Nur 2018–2022: Für die Saisons danach enthält der Export keine Wochenpunkte aller Teams.'), U.legend(['ap-wl', 'allplay']));
  draw();
}
