// Bereich Liga: Duelle (#liga/duelle, die direkten Duelle 2026) und Rekorde (#liga/rekorde) mit zweiter Ebene Saison 2026
// (RS und Playoffs getrennt), Positionen, All-Time und Champions (history.json lazy)
let U, S, h;
const SUBS = [['', 'Saison'], ['positionen', 'Positionen'], ['alltime', 'All-Time'], ['champions', 'Champions']];
const LABEL = {hoechster_score: 'Höchster Wochenscore', niedrigster_score: 'Niedrigster Wochenscore', groesster_sieg: 'Größter Sieg',
  knappstes_ergebnis: 'Knappstes Ergebnis', hoechster_verlierer: 'Höchster Verlierer-Score',
  niedrigster_sieger: 'Niedrigster Sieger-Score', laengste_siegesserie: 'Längste Siegesserie', laengste_niederlagenserie: 'Längste Niederlagenserie',
  hoechste_bank: 'Meiste Bankpunkte', meiste_verschenkt: 'Meiste verschenkte Punkte', bester_spieler: 'Bester Einzelspieler',
  beste_bilanz: 'Beste Bilanz', meiste_pf: 'Meiste PF je Spiel', beste_pf_plus: 'Beste PF+', wenigste_pf: 'Wenigste PF je Spiel'};
const AERA = {alt: 'Alt-Scoring 2015–17', bwg: 'BWG-Scoring ab 2018'};
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
  if (sub === 'alltime' || sub === 'champions') {
    const H = await ctx.lazy('history.json', 'Historie', box);
    if (!r.alive()) return;
    (sub === 'alltime' ? alltime : champions)(box, H, r, svg);
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
      cls: 'rk', rows: S.teams, sort: [sortK, dir], onSort: k => { sortK = k; }, cols: [
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
  let sel = S.byId.has(+r.q.get('team')) ? +r.q.get('team') : S.teams[0]?.team_id;
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
    {k: 'wp', l: 'W %', num: 1, v: a => a.w_pct, f: a => U.pct(a.w_pct)},
    {k: 'pf', l: 'PF', num: 1, v: a => a.pf, f: a => U.num(a.pf)},
    {k: 'pp', l: 'Ø PF+', num: 1, v: a => a.pf_plus_avg, f: a => U.num(a.pf_plus_avg, 1)},
    {k: 'ti', l: 'Titel', num: 1, v: a => a.titel, f: a => a.titel},
    {k: 'fi', l: 'Finals', num: 1, v: a => a.finals, f: a => a.finals},
    {k: 'po', l: 'Playoffs', num: 1, v: a => a.playoffs, f: a => a.playoffs},
    {k: 'dv', l: 'Divisionstitel', num: 1, v: a => a.divisionssiege, f: a => a.divisionssiege},
    {k: 'sc', l: 'Scoring-Titel', num: 1, v: a => a.scoring_titel, f: a => a.scoring_titel},
    {k: 'le', l: 'Letzter Platz', num: 1, v: a => a.letzte, f: a => a.letzte},
    {k: 'pl', l: 'Ø Platz', num: 1, v: a => a.platz_avg, d: 1, f: a => U.num(a.platz_avg, 1)}]}),
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
    (top.halter || []).map(t => h('p', null, h('strong', null, U.num(top.wert)), ` – ${t.team_name}, ${t.season} W${t.week} (${t.round}) gegen ${t.gegner_name} ${U.num(t.gegner_pts)}`)),
    h('p', {class: 'note'}, `Status: ${top.status}. ${top.hinweis ? top.hinweis[0].toUpperCase() + top.hinweis.slice(1) + '.' : ''}`, U.ib('unverifiziert', ''))));
  // Saisontabellen je Jahr
  const seasons = (H.seasons || []).map(s => s.season);
  if (!seasons.length) return;
  let yr = seasons.includes(+r.q.get('saison')) ? +r.q.get('saison') : seasons.at(-1);
  const out = h('div');
  const draw = () => {
    const f = (H.seasons || []).find(s => s.season === yr) || {};
    const rows = (H.team_seasons || []).filter(t => t.season === yr);
    out.replaceChildren(h('p', {class: 'note'}, [f.platform, f.teams && `${f.teams} Teams`, f.rs_games && `${f.rs_games} Spiele Regular Season`, f.scoring_era, f.qb_format, f.playoff_format].filter(Boolean).join(' · ')),
      U.table({cap: `Saison ${yr}`, cls: 'rk', rows, sort: ['p', 1], cols: [
        {k: 'p', l: '#', v: t => t.final_rank, d: 1, f: t => t.final_rank},
        {k: 'n', l: 'Team', v: t => t.team_name.toLowerCase(), d: 1, f: t => t.team_name},
        {k: 'dv', l: 'Division / Platz', num: 1, v: t => t.division * 10 + t.div_rank, d: 1, f: t => `${t.division}/${t.div_rank}.`},
        {k: 'wl', l: 'W-L', num: 1, v: t => t.w_pct, f: t => `${t.w}-${t.l}`},
        {k: 'pf', l: 'PF', num: 1, v: t => t.pf, f: t => U.num(t.pf)},
        {k: 'pp', l: 'PF+', num: 1, v: t => t.pf_plus, f: t => U.num(t.pf_plus, 1)},
        {k: 'po', l: 'Playoffs', v: t => +t.playoffs, f: t => t.playoffs ? h('span', null, '✓', h('span', {class: 'vh'}, ' ja')) : ''},
        {k: 'sc', l: 'Scoring-Titel', v: t => +t.scoring_titel, f: t => t.scoring_titel ? h('span', null, '✓', h('span', {class: 'vh'}, ' ja')) : ''}]}));
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
