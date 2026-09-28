# CLAUDE.md – Projekt bwg-fantasy

Fantasy-Football-Rechenwerk für die BWG Fantasy Liga (ESPN, League-ID 1166555857, 10 Teams, PPR, Superflex/OP, 2 D/ST, 12 Keeper). Besitzer: Stephan Freundl (Team Hugh Jass). Stephan lernt Claude Code mit diesem Projekt – erkläre bei jedem Schritt kurz, was du tust und warum.

## Ziel und Bausteine
1. **ESPN-Abruf** – Rohdaten je Woche als JSON ablegen (dieser Baustein zuerst).
2. **Rechenwerk** – Standings, All-Play, optimale Aufstellung/Coaching, Score mit Profilen, Form, Streak, Restspielplan, Spieler-Kennzahlen; Tests gegen die Referenzwerte in `docs/referenz_w1-w2.md`.
3. **Automatisierung** – öffentliches GitHub-Repo; Action dienstags (Abruf → Rechnung → Tests → Commit) und alle zwei Tage als Transaktions-Archiv (`mTransactions2`, `kona_league_communication` – ESPN hält Transaktionen nur rund drei Tage).
4. **App** – statische Web-Seite auf GitHub Pages; ersetzt Saison-Dashboard und Record-Book-Zahlen aus Notion (Tabellen, Regler für Gewichte, Spielplan, H2H, Rekorde, Spieler mit Formkurve und Rest of Season, D/ST-Faktoren, Playoffs).

**Variante C (Entscheidung Stephan 28.09.2026):** Notion ist nur noch Wissensbasis für Regeln, Entscheidungen und Historie (Privat › Fantasy Football). Zahlen und Anzeige kommen aus diesem Repo und der App; das Repo schreibt nicht automatisch nach Notion. Die Cloud-Routinen „BWG Fantasy – Wochenimport (Di)“ und „Transaktions-Sync“ laufen weiter, bis Baustein 3 (Transaktions-Archiv) bzw. Baustein 4 (App v1) sie ablösen. Das Repo ist öffentlich: nur Ligadaten, nie Persönliches (Notizen, Ziele, Keeper-Pläne, Entscheidungslog).

## Arbeitsregeln
- Sprache Deutsch, NFL-Fachbegriffe Englisch. Kommentare und Doku Deutsch.
- Vor neuen Dateien oder Umbauten: Plan in wenigen Sätzen, dann bauen. Stephan gibt Änderungen im Diff frei.
- Nie in ESPN schreiben. Nur lesende Endpoints.
- Notion: nur lesen. Schreiben ausschließlich in den Ausnahmen unter „Gelernt“ und immer erst nach Stephans Freigabe des Textes.
- Keine destruktiven Git-Kommandos (kein force-push, kein reset --hard) ohne Rückfrage. Commit-Messages Deutsch, ein Satz.
- Vor dem Installieren von Paketen fragen. Ziel: Python 3.11+, Standardbibliothek plus `requests`; keine Frameworks, solange es ohne geht.
- Zahlen: ESPN liefert Drittel-Nachkommastellen; auf zwei Stellen runden (round half up), Ausgabe mit Komma nur in der App-Anzeige.
- Jede Korrektur, die Stephan dir gibt, wird eine Zeile in dieser Datei (Abschnitt „Gelernt“).
- Tests laufen mit `pytest`; ein Baustein gilt als fertig, wenn seine Tests grün sind und die Referenzwerte stimmen.

## Repo-Struktur (Vorschlag, Baustein 1 legt sie an)
```
bwg-fantasy/
  CLAUDE.md
  README.md
  scripts/espn_fetch.py      # Baustein 1
  scripts/compute.py         # Baustein 2
  .github/workflows/         # Baustein 3 (Action)
  data/raw/2026/w03/*.json   # Rohdaten je Woche
  data/season_2026.json      # Ergebnis des Rechenwerks
  docs/referenz_w1-w2.md     # Referenzwerte für Tests
  tests/
  app/                       # Baustein 4
```

## ESPN-API (lesend, Liga öffentlich, kein Login)
Basis: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/1166555857`
- `?view=mSettings` – Einstellungen (Slots, Scoring, Playoffs, Positionslimits).
- `?view=mTeam` – Teams: id (= Franchise-Slot 1–10), Name, Division, record, waiverRank, transactionCounter.
- `?view=mMatchupScore&scoringPeriodId=N` – alle Matchups; je Matchup home/away mit teamId und totalPoints; W1–W14 Regular Season, 15–17 Playoffs.
- `?view=mRoster&scoringPeriodId=N` – Roster je Team mit Slot je Spieler (lineupSlotId) und Stats.
- `?view=kona_player_info` mit Header `X-Fantasy-Filter` (JSON, z. B. `{"players":{"limit":2000,"filterActive":{"value":true}}}`) – ganzer Spielerpool: id, fullName, defaultPositionId, proTeamId, injuryStatus, ownership (percentOwned, percentStarted, percentChange), stats.
- Stat-Einträge: `statSourceId` 0 = Ist, 1 = Projektion; `statSplitTypeId` 0 = Saison, 1 = Woche; `scoringPeriodId` = Woche; Punkte in `appliedTotal`. Feldnamen im JSON verifizieren, nicht raten.
- Lineup-Slot-IDs: 0 QB · 2 RB · 4 WR · 6 TE · 7 OP · 16 D/ST · 17 K · 20 Bench · 21 IR · 23 FLEX. Positions-IDs: 1 QB · 2 RB · 3 WR · 4 TE · 5 K · 16 D/ST.
- Team-IDs: 1 Asse's Cowboys · 2 Hugh Jass · 3 4th Down Syndrom · 4 cool runnings · 5 TeamTy · 6 SaschaM · 7 Rotzleffe · 8 gloane saubande · 9 Dynamo · 10 SaureGurken.
- Divisionen 2026: Division 1 = Asse's, Dynamo, 4th Down, Rotzleffe, TeamTy · Division 2 = Hugh Jass, cool runnings, SaschaM, gloane, SaureGurken (gegen mTeam prüfen).
- NFL-Wochen: Woche n läuft Dienstag bis Montag, Woche 1 begann Di 08.09.2026. Regular Season W1–14, Playoffs W15–17 (6 Teams, Tiebreak Total Points Scored; Divisionssieger-Bye ungeklärt).

## Rechenregeln (Baustein 2)
- **Starter-Slots:** QB, 2 RB, 3 WR, TE, 2 FLEX (RB/WR/TE), OP (QB/RB/WR/TE), 2 D/ST, K = 13 Starter. IR nicht startfähig.
- **Standings:** W/L aus Matchups; Rang = Siege, dann PF. Rang Division innerhalb der Division.
- **All-Play:** je Woche Vergleich der PF gegen alle neun anderen Teams; All-Play % = Siege / (9 × Spiele). Median-Sieg = PF über dem Wochenmedian. Wochenrang = Platz der PF in der Woche.
- **Optimal:** beste Aufstellung aus allen Rosterspielern außer IR. Basis = QB1 + RB1–2 + WR1–3 + TE1 + D/ST1–2 + K1; Rest = übrige RB/WR/TE absteigend; opt1 = Summe der drei besten Reste; opt2 = QB2 + zwei beste Reste; Optimal = Basis + max(opt1, opt2). Coaching-Effizienz = Σ PF / Σ Optimal; Verschenkt = Optimal − PF; Kader-Potenzial = Σ Optimal / Spiele.
- **Floor** = schwächste Woche. **Form** = Ø PF der letzten drei gespielten Wochen; Form Δ = Form − PF je Spiel. **Streak** = W/L + Länge der jüngsten Serie. **Luck** = W − All-Play % × Spiele. **Restspielplan** = Ø All-Play % der noch offenen Gegner. **Projektions-Delta** = Σ PF − Σ Starter-Projektion.
- **Score („Echter Tabellenführer“):** Kennzahlen PF je Spiel, All-Play %, Win %, Coaching-Effizienz, Kader-Potenzial, Floor, Form. Normierungen nebeneinander: Min–Max 0–100 im Ligavergleich (bei max = min: 50), Rangpunkte 10…1, z-Score (Std-Abw. 0 → 0). Score = Σ Gewicht × normierte Kennzahl / Σ Gewichte. Profile: Stärke (aktiv) PF 30 · All-Play 25 · Win 15 · Coaching 10 · Kader 10 · Floor 10 · Form 0 — Verdienst 20 · 25 · 10 · 30 · 0 · 15 · 0 — Form 20 · 25 · 0 · 10 · 10 · 0 · 35.
- **Spieler:** Pkt Saison, Spiele (ohne Bye), Ø, Floor/Ceiling, Konstanz (Std-Abw.), Form (Ø letzte 3), Form Δ, Trend ↑/→/↓ bei ±15 % vom Ø (mindestens 1 Punkt), Formkurve als Sparkline ▁▂▃▄▅▆▇█ je Woche (Bye „·“, negative Werte auf 0), Starts, Bank-Punkte, Projektions-Delta. **Rest of Season:** ROS/Spiel = (Projektion Saison − Ist Saison) / verbleibende NFL-Spiele des Teams (bis Woche 17, Bye abziehen, falls noch offen); Restspiele Regular Season = Wochen ab der aktuellen bis 14 minus Bye; ROS gesamt = ROS/Spiel × Restspiele; ROS Playoffs = ROS/Spiel × 3; ROS-Rang je Position über alle Spieler (Roster + Pool); Ersatzniveau = Ø ROS/Spiel der drei besten Free Agents der Position; ROS über Ersatz = ROS/Spiel − Ersatzniveau. Alle Projektionen sind ESPN-Input, keine Wahrheit.
- **Kader-Projektion ROS (Team):** Optimal-Logik auf ROS/Spiel des aktuellen Kaders. **Playoff-Simulation (später):** 10 000 Läufe, erwartete PF = (n × PF-Schnitt + 4 × Kader-Projektion) / (n + 4), Streuung aus den gespielten Wochen.

## Notion (nur lesen)
Data-Source-IDs zum Nachschlagen: Matchups `25588fd6-104c-4086-8e03-7680c8c19a6d` · Spieler `b3f55f54-5368-45da-a5de-8de0dd7da2ee` · Lineups `b532da39-983e-47cf-b34a-52fa48eb66dc`. Seit 28.09.2026 auf Stand W2 eingefroren (Rückbau folgt): Team-Wochen 2026 `d7a79f06-b021-4068-8e96-96cdb5dfc43a` · Saisontabelle 2026 `c67bb31a-1828-494b-b459-c36b9a2d5367` · Spielwochen 2026 `6077bf0a-00c7-4bf1-aabb-16616f3b989e`. Umbau-Plan: Page `3c60559b2745815b8460cf00220d6189`.

## Gelernt
- Notion-Ausnahme (28.09.2026): Am Sessionende darf Claude im Umbau-Plan (Kapitel Session G) Haken, Sessionvermerk und Versionsnummer schreiben – nur nach Stephans Freigabe des Textes; alle übrigen Notion-Regeln bleiben.
- Variante C vorgezogen (28.09.2026): Baustein 3 ist Automatisierung statt Notion-Sync; das Repo schreibt nicht automatisch nach Notion.
- Notion-Rückbau (28.09.2026): Claude darf Wissensseiten auf Variante C umstellen, Warnhinweise und 🗑-Markierungen setzen und Entscheidungslog-Einträge anlegen – jeweils nach Stephans Freigabe des Textes; Löschen und Archivieren macht Stephan.
- GitHub-Repo öffentlich (28.09.2026): nur Ligadaten ins Repo, nichts Persönliches.
- Testdaten kennzeichnen (28.09.2026): Erfundene Werte in Temp-Kopien (z. B. ein Testname für eine Umbenennung) im Text sofort als erfunden benennen, damit sie nicht wie echte Ligadaten wirken.
