# Referenzwerte Liga-Historie 2015–2025 (Notion, 28.09.2026; nfl.com-Export 24.09.2026)

Grundlage für `tests/test_history.py` (die Abschnitte zum nfl.com-Export am Ende: `tests/test_history_wochen.py`): Die Werte prüfen den einmaligen Export nach `data/history/` gegen die Quelle. Die Summen stammen aus einer SQL-Abfrage auf die Notion-DB Saisondaten (108 Zeilen). Die Champions stehen im Ligaarchiv (View Champions).

## Summen je Franchise
| Slot | Saisons | W | L | PF | PA | Σ Division | Σ Div-Platz | Σ Endplatz | Playoffs | Scoring-Titel |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10 | 73 | 62 | 27101,37 | 26327,85 | 12 | 31 | 50 | 5 | 3 |
| 2 | 11 | 95 | 54 | 30356,10 | 27739,45 | 21 | 19 | 30 | 10 | 3 |
| 3 | 11 | 92 | 57 | 28526,08 | 26647,14 | 19 | 25 | 52 | 9 | 0 |
| 4 | 11 | 95 | 54 | 30316,61 | 27588,96 | 16 | 22 | 44 | 9 | 3 |
| 5 | 11 | 46 | 103 | 24272,90 | 28363,69 | 19 | 48 | 93 | 2 | 0 |
| 6 | 11 | 67 | 82 | 26836,13 | 27666,90 | 14 | 38 | 72 | 5 | 1 |
| 7 | 11 | 65 | 84 | 26821,21 | 27249,32 | 17 | 35 | 60 | 6 | 0 |
| 8 | 11 | 88 | 61 | 29077,72 | 28029,37 | 14 | 27 | 44 | 11 | 1 |
| 9 | 11 | 45 | 104 | 25528,54 | 28305,33 | 15 | 46 | 83 | 3 | 0 |
| 10 | 10 | 65 | 70 | 25194,16 | 26112,81 | 15 | 29 | 58 | 6 | 0 |

## Champions
| Saison | Slot | Team |
|---|---|---|
| 2015 | 4 | cool runnings |
| 2016 | 3 | Elephucks |
| 2017 | 2 | Hugh Jass |
| 2018 | 2 | Hugh Jass |
| 2019 | 2 | Hugh Jass |
| 2020 | 2 | Hugh Jass |
| 2021 | 4 | cool runnings |
| 2022 | 1 | Asse's Cowboys |
| 2023 | 1 | Asse's Cowboys |
| 2024 | 2 | Hugh Jass |
| 2025 | 3 | Elephucks |

## Zähler (Ligaarchiv, per SQL nachgezählt)
| Größe | Wert |
|---|---|
| Titel | 11 |
| Divisionssiege | 22 |
| Scoring-Titel | 11 |
| Letzte | 11 |

## Endstände Screenshot-Spiele 2018–2022 (nfl.com-Export)
Grundlage für `tests/test_history_wochen.py`: Die Screenshot-Spiele aus `data/history/matchups_hist.csv` mit dem Endstand laut DSGVO-Export (Auftrag 03.10.2026). 2018 W16, 2020 W15 und 2020 W16 standen im Archiv zuerst als Zwischenstand bzw. vor einer Stat-Korrektur (233,73 → 233,63 am 31.12.2020); seit 04.10.2026 führen Notion und `matchups_hist.csv` die Endstände.
| Saison | Woche | Runde | Slot A | Slot B | Pkt A | Pkt B |
|---|---|---|---|---|---|---|
| 2018 | 12 | Regular Season | 2 | 3 | 313,33 | 230,40 |
| 2018 | 16 | Final | 2 | 4 | 233,90 | 157,13 |
| 2019 | 15 | Semifinal | 2 | 3 | 268,90 | 263,80 |
| 2020 | 14 | Quarterfinal | 3 | 1 | 206,20 | 204,83 |
| 2020 | 14 | Quarterfinal | 5 | 8 | 232,60 | 220,47 |
| 2020 | 15 | Semifinal | 2 | 3 | 236,16 | 188,20 |
| 2020 | 16 | Final | 2 | 4 | 233,63 | 229,27 |

## All-Play Hugh Jass 2018–2022 (nfl.com-Saisonstand)
Saisonstand der Datei `nfl_fantasy_league_team` (letzter Snapshot je Saison, Felder breakdown_wins/breakdown_losses) – eine andere Exportdatei als die Wochenwerte, also eine unabhängige Gegenprobe der Summe über die Wochen.
| Saison | Slot | W | L |
|---|---|---|---|
| 2018 | 2 | 104 | 13 |
| 2019 | 2 | 63 | 54 |
| 2020 | 2 | 73 | 44 |
| 2021 | 2 | 80 | 46 |
| 2022 | 2 | 73 | 53 |

## Wochen 2018–2022 Zähler (nfl.com-Export)
| Größe | Wert |
|---|---|
| Team-Wochen | 820 |
| Spiele Regular Season | 335 |
| Playoff-Spiele | 35 |
| Playoff-Spiele nach Seed-Regel | 4 |
| Höchster Wochenwert | 338,43 |
| Höchster Wochenwert Saison | 2018 |
| Höchster Wochenwert Woche | 2 |
| Höchster Wochenwert Slot | 2 |
| Gegenprobe Hugh Jass 2020–2022 Wochen | 41 |
| Gegenprobe Hugh Jass 2020–2022 exakt | 38 |
