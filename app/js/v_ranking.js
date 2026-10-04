// Bereich Stärke: Power Ranking (Stärke μ, Trend, Erwartete All-Play % E, Kernsätze) und Eigener Score mit Profil-Chips,
// sieben Reglern und Normierung. Formelzeichen nur hier im Code und im Glossar, nie im Spaltenkopf (App-Konzept 04.10.2026).
// Der Browser rechnet nur Score = Σ w · norm[kind][m] / Σ w aus den fertigen Normwerten (teams.json), nie selbst normiert.
let U, S, h;
const GID = {pf: 'pfspiel', allplay: 'allplay', win: 'win', coaching: 'effizienz', floor: 'floor', form: 'form'};
// Kurzformen wie im Rest der App (Tabellenkopf und Regler); der volle Name steht im title. Kader heißt hier kurz
// „Kader“, gleich ob Beste Aufstellung Ø oder Projektion Kader zählt (die Zeile unter der Tabelle nennt die Quelle)
const SHORT = m => ({pf: 'PF/Spiel', allplay: 'All-Play', win: 'Win', coaching: 'Coaching', floor: 'Floor', form: 'Form',
  kader: 'Kader'})[m.key] || m.label;
// Standard (z, Profil „Standard“, bis 04.10.2026 „Stärke“) steht in den Erklärungen; ohne „(Standard)“ passen die Chips auf dem Handy in eine Zeile
const NORMS = [['z', 'z-Wert'], ['minmax', 'Min–Max'], ['rank', 'Rangpunkte']];
const slug = s => s.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue');

export async function render(box, ctx, r) {
  U = ctx.ui; S = U.S; h = U.h;
  const score = r.view === 'score';
  U.kopf(box, r, score ? 'Eigener Score' : 'Power Ranking');
  U.ap(box, S.tw <= 4 ? h('p', {class: 'warn'}, `Nach ${S.tw} Wochen sind die Unterschiede noch stark zufallsgeprägt.`) : null);
  const svg = await ctx.mod('svg');
  (score ? scoreView : power)(box, r, svg);
}

function power(box, r, svg) {
  const rows = S.teams.filter(t => t.pr);
  if (!rows.length) { U.ap(box, h('p', {class: 'note'}, 'Das Power Ranking folgt.')); return; }
  const vorjahr = rows.some(t => t.pr.p_quelle === 'vorjahr');
  const n = S.tw;
  U.ap(box, vorjahr ? h('p', {class: 'warn'}, h('strong', null, 'Projektion Kader aus dem Vorjahr: '),
    'Die Projektion des Kaders liegt noch nicht vor, bis dahin zählt die Vorjahresleistung. ', U.ib('p', '')) : null,
  U.table({cap: `Power Ranking nach W${n}`, cls: 'rk', rc: U.meRc, rows, sort: ['r', 1], cols: [
    {k: 'r', l: '#', v: t => t.pr.rang, d: 1, f: t => t.pr.rang},
    {k: 'team', l: 'Team', v: t => t.name.toLowerCase(), d: 1, f: t => [U.tl(t.team_id), t.pr.p_quelle === 'vorjahr' ? h('span', {class: 'badge', title: 'Projektion Kader aus dem Vorjahr'}, 'Vorjahr') : null]},
    {k: 'tr', l: 'Trend', num: 1, v: t => t.pr.trend, f: t => U.trend(t.pr.trend, 'noch kein Vorwochenvergleich')},
    {k: 'mu', l: 'Stärke', num: 1, v: t => t.pr.mu, f: t => [U.num(t.pr.mu, 1), h('span', {class: 'sub'}, '± ' + U.num(t.pr.se, 1))]},
    {k: 'e', l: 'Erwartete All-Play %', num: 1, v: t => t.pr.e, f: t => U.pct(U.ok(t.pr.e) ? t.pr.e * 100 : null)},
    {k: 'ap', l: 'All-Play % bisher', num: 1, v: t => t.allplay_pct, f: t => U.pct(t.allplay_pct)},
    {k: 'wl', l: S.hasT ? 'W-L-T' : 'W-L', v: t => -t.rang, f: U.rec},
    {k: 'p', l: 'Projektion Kader', num: 1, v: t => t.pr.p, f: t => U.val(t.pr.p, v => U.num(v, 1))},
    {k: 'vw', l: 'Rang Vorwoche', num: 1, v: t => t.pr.rang_vorwoche, d: 1, f: t => U.val(t.pr.rang_vorwoche, v => v + '.', 'noch kein Vorwochenvergleich')}]}),
  U.legend(['mu', 'kader-proj', 'e', 'pr-rang', 'trend', 'kernsatz']));
  // Kernsätze als Liste (auf dem Handy lesbar); ohne Freigabe „folgt“
  const sorted = U.sortRows(rows, t => t.pr.rang, 1);
  const any = rows.some(t => t.pr.kernsatz);
  U.ap(box, U.card('Kernsätze', any
    ? h('ol', {class: 'ksl'}, sorted.map(t => h('li', null, h('strong', null, U.tl(t.team_id)), ' ',
      t.pr.kernsatz ? h('p', {class: 'ks'}, t.pr.kernsatz) : h('span', {class: 'na'}, 'folgt'))))
    : h('p', {class: 'note'}, 'Die Kernsätze folgen nach Freigabe.')));
  U.ap(box, svg.fig('Stärke mit Unsicherheit', svg.dots({title: 'Stärke je Team mit Unsicherheit', fmt: v => U.num(v, 1),
    desc: `${sorted[0].name} vorn mit Stärke ${U.num(sorted[0].pr.mu, 1)}, ${sorted.at(-1).name} hinten mit ${U.num(sorted.at(-1).pr.mu, 1)}; die Striche zeigen die Unsicherheit.`,
    rows: sorted.map(t => ({label: t.kuerzel, v: t.pr.mu, lo: t.pr.mu - t.pr.se, hi: t.pr.mu + t.pr.se}))}),
  {heads: ['Team', 'Stärke', '±', 'Erwartete All-Play %', 'Rang'], rows: sorted.map(t => [t.name, U.num(t.pr.mu, 1), U.num(t.pr.se, 1), U.pct(U.ok(t.pr.e) ? t.pr.e * 100 : null), t.pr.rang])}));
}

function scoreView(box, r) {
  const M = S.meta.metrics, P = S.meta.profiles, PN = Object.keys(P), std = S.meta.profil_standard || PN[0];
  const gid = k => k === 'kader' ? (S.meta.kader_quelle === 'projektion' ? 'kader-proj' : 'kader-pot') : GID[k];
  const clean = w => Object.fromEntries(M.map(m => [m.key, Math.max(0, Math.min(50, Math.round((+w[m.key] || 0) / 5) * 5))]));
  const match = w => PN.find(p => M.every(m => (P[p][m.key] || 0) === w[m.key])) || 'eigene';
  const fromQ = q => {
    if (!q.has('profil') && !q.has('w') && !q.has('norm')) return null;
    // alte Links ?profil=staerke: das Standardprofil hieß bis 04.10.2026 „Stärke“
    const qp = q.get('profil') === 'staerke' ? slug(std) : q.get('profil');
    const p = PN.find(x => slug(x) === qp || x === qp);
    const list = (q.get('w') || '').split(',');
    const w = p ? {...P[p]} : q.has('w') ? Object.fromEntries(M.map((m, i) => [m.key, list[i]])) : {...P[std]};
    return {w, norm: q.get('norm')};
  };
  const saved = U.store.get('bwg-score');
  let st = fromQ(r.q) || saved || {w: {...P[std]}, norm: S.meta.norm_standard};
  // eigene: zuletzt selbst eingestellte Gewichte – „Eigene“ holt sie nach einem Profil-Vergleich zurück (alte Speicherstände ohne das Feld bleiben lesbar)
  const eig = st.eigene || saved?.eigene;
  st = {w: clean(st.w || {}), norm: NORMS.some(n => n[0] === st.norm) ? st.norm : 'z', eigene: eig ? clean(eig) : null};
  if (!st.eigene && match(st.w) === 'eigene') st.eigene = {...st.w};
  let raw = false;
  const rawVal = {pf: 'pf_per_game', allplay: 'allplay_pct', win: 'win_pct', coaching: 'efficiency', floor: 'floor', form: 'form',
    kader: S.meta.kader_quelle === 'projektion' ? 'kader_projektion' : 'kader_potenzial'};
  const sum = () => M.reduce((a, m) => a + st.w[m.key], 0);
  const scoreOf = t => { const sw = sum(); return sw ? M.reduce((a, m) => a + st.w[m.key] * t.norm[st.norm][m.key], 0) / sw : null; };
  const disp = v => v == null ? null : st.norm === 'z' ? 50 + 10 * v : v;
  let sc = new Map(), rk = new Map();
  const calc = () => {
    sc = new Map(S.teams.map(t => [t.team_id, disp(scoreOf(t))]));
    // Rang ungerundet nach Score, bei Gleichstand nach PF/Spiel
    const order = S.teams.filter(t => sc.get(t.team_id) != null)
      .sort((a, b) => sc.get(b.team_id) - sc.get(a.team_id) || b.pf_per_game - a.pf_per_game);
    rk = new Map(order.map((t, i) => [t.team_id, i + 1]));
  };
  const bar = v => {
    if (!U.ok(v)) return U.na('Summe der Gewichte = 0');
    const p = st.norm === 'z' ? (v - 20) / 60 * 100 : st.norm === 'rank' ? (v - 1) / 9 * 100 : v;
    return h('span', {class: 'pb', style: `--p:${Math.max(0, Math.min(100, p)).toFixed(1)}%`}, U.num(v, 1));
  };
  const normTxt = v => st.norm === 'rank' ? U.num(v, 0) : U.num(st.norm === 'z' ? 50 + 10 * v : v, 1);
  const rawTxt = (k, v) => ['allplay', 'win', 'coaching'].includes(k) ? U.pct(v) : U.num(v);
  const cols = [
    {k: 'rk', l: '#', v: t => rk.get(t.team_id), d: 1, f: t => rk.get(t.team_id) ?? '–'},
    {k: 'team', l: 'Team', v: t => t.name.toLowerCase(), d: 1, f: t => U.tl(t.team_id)},
    {k: 'score', l: 'Score', num: 1, v: t => rk.has(t.team_id) ? -rk.get(t.team_id) : null, f: t => bar(sc.get(t.team_id))},
    ...M.map(m => ({k: m.key, l: h('span', {title: m.label}, SHORT(m)), num: 1, v: t => raw ? t[rawVal[m.key]] : t.norm[st.norm][m.key],
      f: t => raw ? U.val(t[rawVal[m.key]], v => rawTxt(m.key, v), 'ab Wochenabruf W' + (S.tw + 1)) : normTxt(t.norm[st.norm][m.key])})),
    {k: 'rg', l: 'Tabelle', num: 1, v: t => t.rang, d: 1, f: t => t.rang + '.'}];
  calc();
  const tbl = U.table({cap: 'Score je Team', cls: 'rk sc', rc: U.meRc, rows: S.teams, sort: ['score', -1], cols});

  // Bedienung: Profile, Normierung, Regler
  const profSeg = U.seg('Profil', [...PN.map(p => [slug(p), p]), ['eigene', 'Eigene']], slug(match(st.w)), v => {
    // „Eigene“ entsteht erst durch einen Regler: Chip auf den tatsächlichen Stand zurück, Regler aufklappen
    if (v === 'eigene') {
      if (st.eigene) { st.w = {...st.eigene}; sync(true); return; }
      // noch keine eigenen Werte: Regler aufklappen und den ersten fokussieren
      profSeg.set(slug(match(st.w))); panel.open = true; ins[M[0].key]?.focus(); return;
    }
    st.w = {...P[PN.find(p => slug(p) === v)]};
    sync(true);
  });
  const normSeg = U.seg('Normierung', NORMS, st.norm, v => { st.norm = v; update(); });
  const outs = {}, ins = {};
  const sliders = M.map(m => {
    const i = 'w-' + m.key;
    ins[m.key] = h('input', {type: 'range', id: i, min: 0, max: 50, step: 5, value: st.w[m.key],
      oninput: e => { st.w[m.key] = +e.target.value; st.eigene = {...st.w}; sync(false); }});
    outs[m.key] = h('output', {for: i});
    return h('div', {class: 'sl'}, h('div', {class: 'row', style: 'margin:0'}, h('label', {for: i, title: m.label}, SHORT(m)), U.ib(gid(m.key), '')), outs[m.key], ins[m.key]);
  });
  const block = h('p', {class: 'note', 'aria-live': 'polite'});
  const top3 = h('p', {class: 'note live', 'aria-live': 'polite'});  // Spitze live im Regler-Feld: auf dem Handy liegt die Tabelle darunter außer Sicht
  const panel = h('details', {class: 'gw', open: matchMedia('(min-width:900px)').matches},
    h('summary', null, 'Gewichte anpassen'), sliders,
    h('div', {class: 'row'}, h('button', {type: 'button', class: 'btn', onclick: () => {
      const p = match(st.w);
      st.w = {...P[p === 'eigene' ? std : p]};
      sync(true);
    }}, 'Zurücksetzen'), U.ib('redundanz', 'Redundanz')), block, top3);
  const rawSeg = U.seg('Werte in der Tabelle', [['norm', 'Normwerte'], ['raw', 'Rohwerte']], 'norm', v => { raw = v === 'raw'; tbl.upd(S.teams); });
  function sync(setSliders) {
    const sw = sum();
    for (const m of M) {
      if (setSliders) ins[m.key].value = st.w[m.key];
      const a = sw ? Math.round(st.w[m.key] / sw * 100) : 0;
      outs[m.key].textContent = `${st.w[m.key]} · ${a}${U.NB}%`;
      ins[m.key].setAttribute('aria-valuetext', `${st.w[m.key]} Punkte, ${a} Prozent`);
    }
    const pb = M.filter(m => ['pf', 'allplay', 'floor', 'form', 'kader'].includes(m.key)).reduce((a, m) => a + st.w[m.key], 0);
    block.textContent = sw ? `Summe der Gewichte ${sw} · davon Punkte-Block (PF, All-Play, Floor, Form, Kader) ${Math.round(pb / sw * 100)}${U.NB}%`
      : 'Summe der Gewichte = 0: kein Score („–“). Mindestens einen Regler hochziehen.';
    profSeg.set(slug(match(st.w)));
    update();
  }
  function update() {
    calc();
    tbl.upd(S.teams);
    const lead = S.teams.filter(t => rk.has(t.team_id)).sort((a, b) => rk.get(a.team_id) - rk.get(b.team_id)).slice(0, 3);
    top3.textContent = lead.length ? 'Spitze: ' + lead.map(t => `${t.kuerzel} ${U.num(sc.get(t.team_id), 1)}`).join(' · ') : '';
    const p = match(st.w);
    U.setQ(r.base, {profil: slug(p), w: p === 'eigene' ? M.map(m => st.w[m.key]).join(',') : null, norm: st.norm !== 'z' ? st.norm : null});
    U.store.set('bwg-score', st);
  }
  // Name der Kader-Kennzahl wie Spaltenkopf und Glossar (das label aus teams.json trägt noch den alten Namen)
  const kader = M.some(m => m.key === 'kader') ? (S.meta.kader_quelle === 'projektion' ? 'Projektion Kader' : 'Beste Aufstellung Ø') : '–';
  // Bedienung im DOM zuerst (Handy: über der Tabelle), ab 900 px rechts daneben
  U.ap(box, h('div', {class: 'two sc2'},
    h('div', {class: 'side'},
      h('div', {class: 'row'}, h('span', {class: 'note'}, 'Profil'), profSeg),
      h('div', {class: 'row'}, h('span', {class: 'note'}, 'Normierung'), normSeg),
      panel),
    h('div', {class: 'm1'}, tbl, h('div', {class: 'row'}, rawSeg),
      h('p', {class: 'note'}, `Kennzahl Kader: ${kader}`, U.ib(gid('kader'), ''),
        ` Anzeige bei z: 50 + 10 · Score; 50 = Ligaschnitt. Voreinstellung: Profil ${std}, z-Wert.`),
      U.legend(['score', 'kennzahlen', 'z', 'minmax', 'rangpunkte', 'profile']))));
  sync(false);
}
