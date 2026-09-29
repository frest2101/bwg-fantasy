# Auftrag Session 5 – Luck erklärt, Wochensicht in der App, Smartphone-Prüfung (29.09.2026)

Grundlage: Nachfrage Stephan zu Luck (gloane saubande 0,00 trotz drei Median-Siegen; Hugh Jass +0,44 ohne Sieg unter dem Median) und der Wunsch, All-Play, Coaching und Punkte je Woche zu sehen – handhabbar auf dem iPhone.

## Befund Luck (nach W3, nachgerechnet aus `data/season_2026.json`)
Luck = (W + 0,5·T) − All-Play-Anteil × Spiele ist exakt die Summe von Wochenbeiträgen: Beitrag = Ergebnis (W 1 · T 0,5 · L 0) − pₜ, mit pₜ = All-Play-Anteil der Woche (Siege gegen die neun anderen ÷ 9). Der Median spielt in der Formel keine Rolle.

| Team | W1 | W2 | W3 | Luck |
|---|---|---|---|---|
| gloane saubande | L als Wochen-5. gegen Hugh Jass (4.): 0 − 5/9 = **−0,56** | W als 3.: 1 − 7/9 = **+0,22** | W als 4. gegen cool runnings (5.): 1 − 6/9 = **+0,33** | **0,00** (± 0,80) |
| Hugh Jass | W als 4. gegen gloane (5.): 1 − 6/9 = **+0,33** | W als 2.: 1 − 8/9 = **+0,11** | W als Wochenbester: **0,00** | **+0,44** (± 0,57) |

- Stephans Lesart ist die Median-Sicht (binär: über dem Median = verdienter Sieg). Danach hätte gloane −1 (drei Median-Siege, zwei echte) und Hugh Jass 0.
- Die All-Play-Sicht ist abgestuft: Ein Sieg als Wochen-4. ist zu 3/9 Paarungsglück, weil drei Teams ihn geschlagen hätten. W1 und W3 von gloane sind Spiegelbilder (Rang 5 verliert gegen Rang 4, Rang 4 schlägt Rang 5): einmal die falsche, einmal die richtige Seite der Münze, netto null. Hugh Jass hat in W1 gegen einen der sechs schlagbaren Gegner gespielt, drei waren stärker – mildes Paarungsglück, innerhalb des Zufallsbands.
- Alternativen (Werte nach W3): Median-Luck = W − Median-Siege (ACB +1 · 4DS +1 · GLS −1 · RTZ −1 · Rest 0; grob, Klippe zwischen Rang 5 und 6); Gegner-Punkte Σ (Ligaschnitt − PA) (CRN +77 · SAM +69 · ACB +41 · DYN +29 · HJS +18 · GLS −6 · SGK −17 · 4DS −32 · RTZ −64 · TTY −115; misst Spielplan-Glück in Punkten, nicht Siege); Pythagorean-Luck (nach drei Wochen instabil, Hugh Jass wäre +1,17).
- **Beschluss offen (Stephan):** Formel bleibt (Gelernt 29.09.); Median-Luck oder Gegner-Punkte als Zusatzspalte nur, wenn die Wochenbeiträge die Frage nicht beantworten.

## Umsetzung
1. **Rechenwerk:** je Team-Woche `allplay_pct` (pₜ in %), `luck` (Beitrag), `luck_kum` (laufende Summe), `efficiency` (PF/Optimal der Woche), `projektions_delta`; je Spielwoche `effizienz_liga`. Luck des Teams = Σ Beiträge (eine Quelle); Tests: Beiträge summieren sich zur geschlossenen Formel, je Woche Nullsumme, Hugh Jass W1/W2 = 1 − 6/9 und 1 − 8/9. Rundung ohne „−0,0“.
2. **App-Daten:** `teams.json › wochen` um die Felder ergänzt, `schedule.json › weeks.effizienz_liga`, `meta.effizienz_liga` (Datenvertrag `docs/app_daten.md`).
3. **App – Wochensicht:** Tabelle › All-Play, Punkte, Coaching mit Wochen-Chips „Saison · W1 · W2 …“ (`#tabelle/allplay/w3`), gleich viele Spalten wie die Saisonsicht; All-Play je Woche mit Gegner (Wochenrang) und Luck-Beitrag, Diagramm „Luck-Beitrag Wn“; Saisonsicht mit „Luck-Verlauf“ (kumuliert, Team × Woche als Datentabelle). Teamseite › Wochenliste und Spielplan › Wochentabelle zeigen Luck-Beitrag und Eff. % je Woche. Glossar: Luck-Beitrag, Luck kumuliert, Effizienz (Woche), Wochensicht.
4. **Smartphone (iPhone 390 px):** Scroll-Kante an Tabellen und Chipleisten (Klasse `more`), Kürzel statt Name in allen Rang-Tabellen unter 600 px, Umschalter und Ansichts-Chips brechen um, Erklärungen als eine wischbare Zeile, Kacheln zu dritt, Zeilen 40 px, Score-Regler einzeilig mit „Spitze“-Rückmeldung, Kopfzeile ohne Umbruch, Teamseite: Kader nach oben, Verläufe und Franchise-Historie eingeklappt, H2H-Matrix auch auf dem Handy.
5. **Nicht umgesetzt (Vorschläge der Prüfung):** Spaltenwahl „Kompakt/Alle“ je Tabelle, Spielerliste mit einklappbaren Filtern, `players.json` (240 KB) aufteilen – erst prüfen, was GitHub Pages komprimiert überträgt.
