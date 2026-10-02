// Wetter (lädt wetter.json): Prognose der laufenden NFL-Woche und Ist der gespielten Spiele, je Spiel Anstoß in deutscher
// Zeit, Stadion, Dach und die Werte über die Anstoßstunde und drei Stunden danach (Open-Meteo, Modellwerte). Die Markierung
// ⚑ rechnet Python (wetter.markierung); hier nur Anzeige, Sortierung und Filter. Fähnchen im Waiver-Tab und Wetterzeile der
// Spielerseite nutzen die Helfer unten (ctx.mod('v_wetter')).
let U, S, h;
export const init = c => { U = c.ui; S = U.S; h = U.h; };
// Anzeige wie die Markierung in Python: Temperatur, Wind, Böen und Regen ganzzahlig, Niederschlag und Schnee eine Stelle
const FMT = {temp: [0, '°C'], wind: [0, 'km/h'], boeen: [0, 'km/h'], regen_wahrsch: [0, '%'], niederschlag: [1, 'mm'], schnee: [1, 'cm']};
const LAB = {wind: 'Wind', boeen: 'Böen', regen_wahrsch: 'Regen', schnee: 'Schnee'};
const unit = (g, k) => U.num(g[k], FMT[k][0]) + U.NB + FMT[k][1];
const marks = g => g.markierung || [];
const open = g => g.dach === 'offen';
const tbd = g => !!g.tbd || !g.kickoff;
const kick = g => tbd(g) ? 'Anstoß offen' : U.stamp(g.kickoff);
// Anstoß vorbei: die Prognose führt die ganze laufende Woche, bis ihr letztes Spiel vorbei ist – für ein schon
// angepfiffenes Spiel ist sie keine Entscheidungshilfe mehr (kein Fähnchen, Spielerzeile ohne Prognosewerte)
export const played = g => !tbd(g) && (U.utc(g.kickoff)?.getTime() ?? Infinity) <= Date.now();

// ---------------------------------------------------------------- Helfer für Waiver-Tab und Spielerseite
// Spiel eines NFL-Teams in der Prognose (laufende Woche); ohne Spiel (Bye, kein NFL-Team) null
export const gameOf = (W, nfl) => nfl ? (W?.prognose || []).find(g => g.heim === nfl || g.gast === nfl) || null : null;
// Text der markierten Werte, z. B. „Wetter W4: Wind 30 km/h, Böen 54 km/h“; null ohne Markierung (auch Dach, Anstoß offen)
export function flagText(g) {
  const m = g ? marks(g) : [];
  return m.length ? `Wetter W${g.woche}: ` + m.map(k => `${LAB[k] || k} ${FMT[k] ? unit(g, k) : ''}`.trim()).join(', ') : null;
}
// Fähnchen ⚑ als eigener Link nach #wetter (Waiver-Tab, neben dem Spielerlink); nur vor dem Anstoß
export function flagLink(g) {
  const t = g && !played(g) ? flagText(g) : null;
  return t ? h('a', {href: '#wetter', class: 'wf flag', title: t}, h('span', {'aria-hidden': 'true'}, '⚑'), h('span', {class: 'vh'}, t)) : null;
}
// Zeile der Spielerseite: „Spiel W4: PIT @ CLE, Fr 02.10. 02:15 Uhr, 24 °C, Wind 19 km/h (Böen 54 ⚑), Regen 25 %“;
// Dachspiele „…, Dach“ ohne Werte, offener Anstoß „…, Anstoß offen“, nach dem Anstoß „…, gespielt“ (Werte unter „Ist“)
export function line(g) {
  const m = new Set(marks(g));
  const fl = k => m.has(k) ? [' ', h('span', {class: 'flag', 'aria-hidden': 'true'}, '⚑'), h('span', {class: 'vh'}, ' (über der Schwelle)')] : null;
  const out = [`Spiel W${g.woche}: ${g.gast} @ ${g.heim}`, g.neutral ? ` (Auslandsspiel, ${g.ort})` : '', ', ' + kick(g)];
  if (tbd(g)) return out;
  if (played(g)) return [...out, ', gespielt'];
  if (!open(g)) return [...out, ', Dach'];
  out.push(', ' + unit(g, 'temp'), `, Wind ${unit(g, 'wind')}`, fl('wind'), ` (Böen ${U.num(g.boeen, 0)}`, fl('boeen'), ')');
  if (U.ok(g.regen_wahrsch)) out.push(`, Regen ${unit(g, 'regen_wahrsch')}`, fl('regen_wahrsch'));
  if (m.has('schnee')) out.push(`, Schnee ${unit(g, 'schnee')}`, fl('schnee'));
  return out;
}

// ---------------------------------------------------------------- Ansicht #wetter, #wetter/ist
export async function render(box, ctx, r) {
  init(ctx);
  const ist = r.sub === 'ist';
  U.ap(box, h('h1', null, ist ? 'Wetter – Ist' : 'Wetter – Prognose'), U.spGroup('wetter'));
  if (!S.man.files?.['wetter.json']) {
    U.ap(box, h('p', {class: 'warn'}, 'Noch keine Wetterdaten: Die Seite füllt sich mit dem ersten Tageslauf (stündlich von etwa 05:00 Uhr bis Mitternacht deutscher Zeit).'));
    return;
  }
  // Umschalter erst nach dem Laden (die Woche der Prognose steht in der Datei); der Platzhalter hält die Stelle
  const slot = h('span');
  U.ap(box, slot);
  const W = await ctx.lazy('wetter.json', 'Wetterdaten', box);
  if (!r.alive()) return;
  slot.replaceWith(U.chips('Ansichten Wetter', [['#wetter', U.ok(W.woche) ? `Prognose W${W.woche}` : 'Prognose', ''], ['#wetter/ist', 'Ist', 'ist']], ist ? 'ist' : ''));
  const s = W.schwellen;
  U.ap(box, h('p', {class: 'note'}, `Stand ${U.stamp(W.stand)} · Modellwerte von Open-Meteo, kein Stationsmesswert; Werte über Anstoßstunde und drei Stunden danach`,
    s ? `; Markierung ⚑ ab Wind ≥ ${U.num(s.wind, 0)} km/h, Böen ≥ ${U.num(s.boeen, 0)} km/h, Regen ≥ ${U.num(s.regen_wahrsch, 0)} %, Schnee > ${U.num(s.schnee, 0)} (Faustregel)` : '',
    ist ? '. Ist ohne Regenwahrscheinlichkeit. ' : '. ', U.ib('wetter-markierung', '')));
  games(box, W, ist);
}

function games(box, W, ist) {
  const rows = (ist ? W.ist : W.prognose) || [];
  if (!rows.length) {
    U.ap(box, h('p', {class: 'note'}, ist ? 'Noch kein gespieltes Spiel.' : 'Keine offenen Spiele mehr: Die Saison ist gespielt, alle Spiele stehen unter „Ist“. ',
      ist ? null : h('a', {href: '#wetter/ist'}, 'Zu „Ist“')));
    return;
  }
  const t0 = g => tbd(g) ? null : U.utc(g.kickoff)?.getTime() ?? null;
  const shown = g => open(g) && !tbd(g);
  // markierte Werte in Warnfarbe; welcher Wert markiert ist, steht als Text in der Spalte „Markierung“ (Farbe nie allein)
  const mk = (g, k) => marks(g).includes(k) ? h('strong', {class: 'flag'}, U.num(g[k], FMT[k][0])) : U.num(g[k], FMT[k][0]);
  // Dachspiele zeigen „Dach“ statt Werten (Open-Meteo rechnet sie trotzdem), offener Anstoß „–“ mit Grund
  const cell = (g, k, f) => !open(g) ? h('span', {class: 'na'}, 'Dach') : tbd(g) ? U.na('Anstoß offen') : !U.ok(g[k]) ? U.na('kein Wert') : f();
  const vcol = (k, l) => ({k, l, num: 1, v: g => shown(g) ? g[k] : null, f: g => cell(g, k, () => mk(g, k))});
  const cols = [
    {k: 'sp', l: 'Spiel', v: t0, d: 1, flt: false, f: g => h('span', {class: 'pl'}, h('span', null, `${g.gast} @ ${g.heim}`),
      h('span', {class: 'sub'}, kick(g)), g.neutral ? h('span', {class: 'sub'}, 'Auslandsspiel') : null,
      !ist && played(g) ? h('span', {class: 'sub'}, 'gespielt – Ist-Werte unter „Ist“') : null)},
    ist ? {k: 'w', l: 'Woche', num: 1, cat: 1, v: g => g.woche, d: 1, f: g => 'W' + g.woche} : null,
    {k: 'm', l: 'Markierung', v: g => marks(g).length || null, f: g => marks(g).length
      ? h('span', {class: 'flag'}, h('span', {'aria-hidden': 'true'}, '⚑ '), marks(g).map(k => LAB[k] || k).join(', ')) : '–'},
    vcol('temp', 'Temp. °C'),
    {k: 'wind', l: 'Wind (Böen) km/h', num: 1, v: g => shown(g) ? g.wind : null, f: g => cell(g, 'wind', () => [mk(g, 'wind'), ' (', mk(g, 'boeen'), ')'])},
    ist ? null : vcol('regen_wahrsch', 'Regen %'),
    vcol('niederschlag', 'Niederschlag mm'),
    vcol('schnee', 'Schnee cm'),
    {k: 'dach', l: 'Dach', v: g => g.dach, d: 1, cat: 1, f: g => g.dach || '–'},
    {k: 'st', l: 'Stadion', v: g => g.stadion, d: 1, flt: false, f: g => [g.stadion || '–', h('span', {class: 'sub'}, g.ort || '')]}].filter(Boolean);
  U.ap(box, U.table({cap: ist ? 'Gespielte Spiele: Wetter zur Anstoßzeit' : `Spiele W${W.woche ?? ''}: Wetterprognose zur Anstoßzeit`, cls: 'nr', rh: 0, rows,
    sort: ['sp', ist ? -1 : 1], filter: true, stick: ist, limit: ist ? 50 : 0, cols}),
  U.legend(['wetter', 'wetter-werte', 'wetter-markierung', 'wetter-dach', 'wetter-anstoss', 'filter']));
}
