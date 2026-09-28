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
| 6 | cool runnings | 51 |
| 7 | Rotzleffe | 36 |
| 8 | SaureGurken | 17 |
| 9 | TeamTy | 16 |
| 10 | 4th Down Syndrom | 13 |

Die Quelle nennt nur Reihenfolge und ganzzahlige Scores; der Rang gilt nach ungerundetem Score. Aus den Rohdaten nachgerechnet (Review 28.09.2026): Dynamo 51,35 vor cool runnings 51,27 – kein Gleichstand.

## Plausibilität (beim Anlegen geprüft)

- PF und PA der Saisontabelle sind exakt die Summen der Matchup-Punkte oben.
- All-Play-Bilanzen passen zu den Wochenrängen aus W1 und W2 (Σ 90-90).

## Abgleich mit ESPN (28.09.2026, `espn_fetch.py --summary`)

- Alle 10 Paarungen W1–W2 stimmen, Abweichung jeweils 0,00.
- Die Tabelle oben (aus dem Auftrag) führt bei 6 von 10 Paarungen den Sieger als „Heim“: W1 SaschaM–4th Down, Dynamo–Rotzleffe, cool runnings–SaureGurken, Hugh Jass–gloane; W2 cool runnings–Dynamo, 4th Down–TeamTy (ESPN-Heim jeweils das zweitgenannte Team).
- Die DB Matchups in Notion ist korrekt: Team A = ESPN-Heimteam in 10/10 Paarungen W1–W2, Punkte identisch (gelesen 28.09.2026). Nur die Auftragstabelle war nach Sieger sortiert; Tests in Baustein 2 vergleichen deshalb Paarungen, nicht Seiten.
- `mRoster` mit `scoringPeriodId` liefert die historische Aufstellung der Woche: Σ Ist-Punkte der 13 Starter W1 = `totalPoints` W1 für alle 10 Teams.

## Zweitreferenz G1 – Ränge, Form, Streak, Restspielplan

Quelle: Notion › Saisontabelle 2026 (Import-Spalten und N/R/Z), von Session G1 am 28.09.2026 aus denselben ESPN-Daten gerechnet und am 28.09. gelesen – keine Record-Book-Werte, sondern eine Zweitreferenz für die Werte, die Baustein 3 nach Notion schreibt. Bestätigt durch `compute.py` und zwei unabhängige Nachrechnungen (je 270/270 in Rundungstoleranz). Rundung in Notion: Form 2 Stellen (Asse's 278,9 = 278,905 mit Float-Rundung; round half up ergibt 278,91), Restspielplan in % und N mit 1 Stelle, Z mit 2 Stellen. Spaltenreihenfolge der Kennzahlen: PF · All-Play · Win · Coaching · Kader · Floor · Form.

| Team | Rang | Rang Division | Rang Score | Form | Streak | Restspielplan |
|---|---|---|---|---|---|---|
| Asse's Cowboys | 1 | 1 | 1 | 278,9 | W2 | 44,0 |
| Hugh Jass | 2 | 1 | 2 | 233,18 | W2 | 43,5 |
| cool runnings | 3 | 2 | 6 | 198,31 | W2 | 54,2 |
| SaschaM | 4 | 3 | 3 | 239,79 | L1 | 49,1 |
| Dynamo | 5 | 2 | 5 | 214,66 | L1 | 47,7 |
| gloane saubande | 6 | 4 | 4 | 210,98 | W1 | 53,2 |
| 4th Down Syndrom | 7 | 3 | 10 | 143,6 | W1 | 57,4 |
| Rotzleffe | 8 | 4 | 7 | 194,12 | L2 | 43,1 |
| SaureGurken | 9 | 5 | 8 | 167,99 | L2 | 53,7 |
| TeamTy | 10 | 5 | 9 | 160,56 | L2 | 54,2 |

## Zweitreferenz G1 – Min–Max (N)

| Team | PF | All-Play | Win | Coaching | Kader | Floor | Form |
|---|---|---|---|---|---|---|---|
| Asse's Cowboys | 100 | 100 | 100 | 79,7 | 100 | 100 | 100 |
| Hugh Jass | 66,2 | 76,5 | 100 | 100 | 55,6 | 74,4 | 66,2 |
| cool runnings | 40,4 | 47,1 | 100 | 11,8 | 66,1 | 45,9 | 40,4 |
| SaschaM | 71,1 | 52,9 | 50 | 74,7 | 71,4 | 55,3 | 71,1 |
| Dynamo | 52,5 | 52,9 | 50 | 6,3 | 84,5 | 57,8 | 52,5 |
| gloane saubande | 49,8 | 64,7 | 50 | 84,4 | 44,6 | 64,7 | 49,8 |
| 4th Down Syndrom | 0 | 0 | 50 | 56 | 0 | 0 | 0 |
| Rotzleffe | 37,3 | 35,3 | 0 | 84,3 | 31,5 | 45,9 | 37,3 |
| SaureGurken | 18 | 23,5 | 0 | 0 | 43 | 12,6 | 18 |
| TeamTy | 12,5 | 17,6 | 0 | 48,9 | 16,5 | 13,8 | 12,5 |

## Zweitreferenz G1 – Rangpunkte (R)

| Team | PF | All-Play | Win | Coaching | Kader | Floor | Form |
|---|---|---|---|---|---|---|---|
| Asse's Cowboys | 10 | 10 | 10 | 7 | 10 | 10 | 10 |
| Hugh Jass | 8 | 9 | 10 | 10 | 6 | 9 | 8 |
| cool runnings | 5 | 5 | 10 | 3 | 7 | 5 | 5 |
| SaschaM | 9 | 7 | 7 | 6 | 8 | 6 | 9 |
| Dynamo | 7 | 7 | 7 | 2 | 9 | 7 | 7 |
| gloane saubande | 6 | 8 | 7 | 9 | 5 | 8 | 6 |
| 4th Down Syndrom | 1 | 1 | 7 | 5 | 1 | 1 | 1 |
| Rotzleffe | 4 | 4 | 3 | 8 | 3 | 4 | 4 |
| SaureGurken | 3 | 3 | 3 | 1 | 4 | 2 | 3 |
| TeamTy | 2 | 2 | 3 | 4 | 2 | 3 | 2 |

## Zweitreferenz G1 – z-Score (Z)

| Team | PF | All-Play | Win | Coaching | Kader | Floor | Form |
|---|---|---|---|---|---|---|---|
| Asse's Cowboys | 1,94 | 1,89 | 1,29 | 0,72 | 1,67 | 1,81 | 1,94 |
| Hugh Jass | 0,75 | 1,05 | 1,29 | 1,31 | 0,15 | 0,93 | 0,75 |
| cool runnings | -0,15 | 0 | 1,29 | -1,23 | 0,51 | -0,04 | -0,15 |
| SaschaM | 0,92 | 0,21 | 0 | 0,58 | 0,69 | 0,28 | 0,92 |
| Dynamo | 0,27 | 0,21 | 0 | -1,39 | 1,14 | 0,37 | 0,27 |
| gloane saubande | 0,18 | 0,63 | 0 | 0,86 | -0,23 | 0,6 | 0,18 |
| 4th Down Syndrom | -1,57 | -1,68 | 0 | 0,04 | -1,76 | -1,61 | -1,57 |
| Rotzleffe | -0,26 | -0,42 | -1,29 | 0,86 | -0,68 | -0,04 | -0,26 |
| SaureGurken | -0,94 | -0,84 | -1,29 | -1,57 | -0,29 | -1,18 | -0,94 |
| TeamTy | -1,13 | -1,05 | -1,29 | -0,16 | -1,2 | -1,14 | -1,13 |
