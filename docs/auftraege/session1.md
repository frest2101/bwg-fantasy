# Auftrag Session 1 – Setup und ESPN-Abruf (28.09.2026, abends)

Lies zuerst CLAUDE.md. Stell mir Rückfragen, bevor du Dateien anlegst. Ich lerne Claude Code mit dieser Session: erkläre jeden Schritt in zwei, drei Sätzen, keine langen Vorträge.

## Ziel
Am Ende der Session liegt im Ordner ein lauffähiges Skript `scripts/espn_fetch.py`, das die ESPN-Rohdaten der Liga für die Wochen 1–3 als JSON ablegt, plus die Repo-Struktur aus CLAUDE.md, ein erster Git-Commit und die Datei `docs/referenz_w1-w2.md` mit den Werten unten.

## Schritte
1. **Umgebung prüfen:** Ist `python3` (3.11 oder neuer) und `git` vorhanden? Wenn nicht, sag mir genau, was ich installieren soll, und warte.
2. **Struktur anlegen** (Plan zeigen, dann bauen): Ordner laut CLAUDE.md, `README.md` mit drei Sätzen, `.gitignore` (data/raw wird versioniert, `.env` nicht), `requirements.txt` nur mit `requests`.
3. **`scripts/espn_fetch.py`:** holt für eine Saison (2026) und eine Liste von Wochen die Views `mSettings`, `mTeam`, `mMatchupScore` und `mRoster` (jeweils mit `scoringPeriodId`) und speichert sie unverändert unter `data/raw/2026/wNN/<view>.json`. Aufruf: `python scripts/espn_fetch.py --weeks 1 2 3`. Fehler (HTTP ≠ 200, leere Antwort) sauber melden, nichts stillschweigend überschreiben ohne `--force`.
4. **Kurzer Check** in `scripts/espn_fetch.py --summary`: je Woche die fünf Matchups mit Teamnamen und Punkten ausgeben (Namen aus mTeam, Punkte aus mMatchupScore).
5. **Prüfen:** Die Ausgabe für W1 und W2 muss den Referenzwerten unten entsprechen (Abweichung ≤ 0,01). W3 gegen die ESPN-Oberfläche (ich schaue selbst nach).
6. **`docs/referenz_w1-w2.md`** mit der Tabelle unten anlegen (wird die Grundlage der Tests in Baustein 2).
7. **Git:** `git init`, erster Commit „Baustein 1: ESPN-Abruf und Repo-Struktur“. Kein Remote in dieser Session.
8. **CLAUDE.md pflegen:** alles, was ich dir währenddessen korrigiere, unter „Gelernt“ eintragen.

## Nicht in dieser Session
Keine Notion-Zugriffe, keine ESPN-Schreibzugriffe, keine App, keine Berechnungen außer dem Summary. Keine Pakete außer `requests`.

## Referenzwerte W1–W2 (Quelle: Notion Record Book 2.7 / DB Matchups; Punkte auf zwei Stellen)

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

Heim/Gast wie in Notion übernommen (Team A = ESPN-Heimteam); die Paarung zählt, nicht die Seite – falls ESPN die Seiten anders führt, ist das keine Abweichung, nur notieren.

Saisontabelle nach W2 (für Baustein 2): Asse's 2-0, PF 557,81, PA 393,08, All-Play 18-0, Verschenkt 67,87 (W1 49,37) · Hugh Jass 2-0, 466,35, 395,44, 14-4, 33,01 (W2 17,20) · cool runnings 2-0, 396,62, 330,29, 9-9, 132,54 (W2 82,44) · SaschaM 1-1, 479,58, 368,56, 10-8, 64,79 (W1 32,40) · Dynamo 1-1, 429,31, 396,61, 10-8, 152,29 (W1 93,51) · gloane 1-1, 421,95, 417,15, 12-6, 46,19 (W2 28,31) · 4th Down 1-1, 287,20, 425,07, 1-17, 53,94 (W1 43,44) · Rotzleffe 0-2, 388,23, 484,76, 7-11, 42,63 (W1 33,43) · SaureGurken 0-2, 335,97, 397,29, 5-13, 127,45 (W1 87,33) · TeamTy 0-2, 321,11, 475,88, 4-14, 67,07 (W2 41,87). Score-Probe Profil Stärke (Min–Max): Asse's 98 · Hugh Jass 77 · SaschaM 62 · gloane 58 · Dynamo 51 · cool runnings 51 · Rotzleffe 36 · SaureGurken 17 · TeamTy 16 · 4th Down 13.

## Danach
Ich hake Baustein 1 im Notion-Umbau-Plan ab. Session 2 = Rechenwerk (`scripts/compute.py` mit Tests gegen die Referenzwerte).
