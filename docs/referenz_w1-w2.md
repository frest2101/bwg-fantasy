# Referenzwerte W1–W2 (Saison 2026)

Quelle: Notion Record Book 2.7 / DB Matchups, übernommen aus dem Auftrag Session 1 (28.09.2026). Punkte auf zwei Stellen (round half up), Dezimalkomma wie in der Quelle. Grundlage der Tests in Baustein 2; Toleranz je Wert ≤ 0,01.

## Matchups

| Woche | Heim (ESPN) | Punkte | Gast | Punkte |
|---|---|---|---|---|
| 1 | SaschaM | 288,04 | 4th Down Syndrom | 118,83 |
| 1 | Dynamo | 234,46 | Rotzleffe | 179,23 |
| 1 | cool runnings | 179,24 | SaureGurken | 135,44 |
| 1 | Asse's Cowboys | 307,51 | TeamTy | 184,08 |
| 1 | Hugh Jass | 216,62 | gloane saubande | 203,90 |
| 2 | cool runnings | 217,38 | Dynamo | 194,85 |
| 2 | 4th Down Syndrom | 168,37 | TeamTy | 137,03 |
| 2 | Hugh Jass | 249,73 | SaschaM | 191,54 |
| 2 | Asse's Cowboys | 250,30 | Rotzleffe | 209,00 |
| 2 | gloane saubande | 218,05 | SaureGurken | 200,53 |

Heim/Gast wie in Notion übernommen (Team A = ESPN-Heimteam). Es zählt die Paarung, nicht die Seite – führt ESPN die Seiten anders, ist das keine Abweichung (Abgleich siehe unten).

## Saisontabelle nach W2

| Team | W-L | PF | PA | All-Play | Verschenkt gesamt | davon einzeln |
|---|---|---|---|---|---|---|
| Asse's Cowboys | 2-0 | 557,81 | 393,08 | 18-0 | 67,87 | W1 49,37 |
| Hugh Jass | 2-0 | 466,35 | 395,44 | 14-4 | 33,01 | W2 17,20 |
| cool runnings | 2-0 | 396,62 | 330,29 | 9-9 | 132,54 | W2 82,44 |
| SaschaM | 1-1 | 479,58 | 368,56 | 10-8 | 64,79 | W1 32,40 |
| Dynamo | 1-1 | 429,31 | 396,61 | 10-8 | 152,29 | W1 93,51 |
| gloane saubande | 1-1 | 421,95 | 417,15 | 12-6 | 46,19 | W2 28,31 |
| 4th Down Syndrom | 1-1 | 287,20 | 425,07 | 1-17 | 53,94 | W1 43,44 |
| Rotzleffe | 0-2 | 388,23 | 484,76 | 7-11 | 42,63 | W1 33,43 |
| SaureGurken | 0-2 | 335,97 | 397,29 | 5-13 | 127,45 | W1 87,33 |
| TeamTy | 0-2 | 321,11 | 475,88 | 4-14 | 67,07 | W2 41,87 |

„Verschenkt“ = Optimal − PF (siehe CLAUDE.md, Rechenregeln). Die Spalte „davon einzeln“ nennt den Wert einer der beiden Wochen, die andere Woche ergibt sich als Differenz.

## Score-Probe Profil „Stärke“ (Min–Max)

| Rang | Team | Score |
|---|---|---|
| 1 | Asse's Cowboys | 98 |
| 2 | Hugh Jass | 77 |
| 3 | SaschaM | 62 |
| 4 | gloane saubande | 58 |
| 5 | Dynamo | 51 |
| 5 | cool runnings | 51 |
| 7 | Rotzleffe | 36 |
| 8 | SaureGurken | 17 |
| 9 | TeamTy | 16 |
| 10 | 4th Down Syndrom | 13 |

## Plausibilität (beim Anlegen geprüft)

- PF und PA der Saisontabelle sind exakt die Summen der Matchup-Punkte oben.
- All-Play-Bilanzen passen zu den Wochenrängen aus W1 und W2 (Σ 90-90).

## Abgleich mit ESPN (28.09.2026, `espn_fetch.py --summary`)

- Alle 10 Paarungen W1–W2 stimmen, Abweichung jeweils 0,00.
- ESPN führt Heim/Gast bei 6 von 10 Paarungen andersherum als Notion: W1 SaschaM–4th Down, Dynamo–Rotzleffe, cool runnings–SaureGurken, Hugh Jass–gloane; W2 cool runnings–Dynamo, 4th Down–TeamTy (ESPN-Heim jeweils das zweitgenannte Team).
- Muster: In Notion steht als Team A immer der Sieger, nicht das ESPN-Heimteam. Die Spaltenbezeichnung „Team A = ESPN-Heimteam“ trifft also nicht zu – relevant für den Notion-Sync (Baustein 3).
- `mRoster` mit `scoringPeriodId` liefert die historische Aufstellung der Woche: Σ Ist-Punkte der 13 Starter W1 = `totalPoints` W1 für alle 10 Teams.
