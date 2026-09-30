// Lesart: das Glossar steht als <dl id="glossar"> in index.html (ohne JS lesbar); hier nur Suche und Sprungmarken.
export function render(box, ctx, r) {
  const {h} = ctx.ui;
  const gl = document.getElementById('glossar');
  const items = [...gl.children];
  const areas = items.filter(d => d.dataset.b);
  const count = h('p', {class: 'note', 'aria-live': 'polite'});
  const filter = q => {
    q = q.trim().toLowerCase();
    let n = 0, first = null;
    for (const d of items) {
      const hit = !q || d.textContent.toLowerCase().includes(q);
      d.hidden = !hit; n += hit;
      d.classList.remove('f0');
      if (hit && !first) first = d;
    }
    first?.classList.add('f0');     // Trennlinien nur zwischen sichtbaren Begriffen
    gl.hidden = n === 0;            // kein leerer Rahmen ohne Treffer
    count.textContent = !q ? `${items.length} Begriffe` : n ? `${n} von ${items.length} Begriffen` : 'Kein Begriff gefunden.';
  };
  box.append(h('h1', null, 'Lesart'),
    h('p', null, 'Kurzfassung aller Begriffe der App. Verbindlich sind die Rechenregeln im Repo. Fehlende Werte stehen als „–“, alle Projektionen sind ESPN-Schätzungen.'),
    h('div', {class: 'row'}, h('label', null, 'Begriff suchen ', h('input', {type: 'search', oninput: e => filter(e.target.value)}))),
    count,
    h('nav', {class: 'chips', 'aria-label': 'Bereiche der Lesart'}, areas.map(d => h('a', {href: '#lesart/' + d.querySelector('dt').id.slice(2)}, d.dataset.b))));
  filter('');
  for (const d of items) d.classList.remove('hit');
  const t = r.sub && document.getElementById('g-' + r.sub);
  if (t) { t.parentElement.classList.add('hit'); return t; }
}
