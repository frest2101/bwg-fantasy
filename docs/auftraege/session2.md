# Auftrag Session 2 – Rechenwerk (Entwurf Claude 28.09.2026, Freigabe Stephan)

Grundlage: CLAUDE.md (Rechenregeln Baustein 2), Umbau-Plan 2.2 in Notion (Kapitel Session G: Definitionen, Prüfpunkte 1–4), `docs/referenz_w1-w2.md`. Stell mir die Rückfragen unten, bevor du Dateien anlegst. Erkläre jeden Schritt in zwei, drei Sätzen.

## Ziel
Am Ende der Session liegt `scripts/compute.py`, das aus `data/raw/2026` die Team-Kennzahlen aller gespielten Wochen berechnet und nach `data/season_2026.json` schreibt, dazu `tests/test_compute.py` (pytest), das gegen `docs/referenz_w1-w2.md` grün läuft, und ein Commit.

## Umfang (Team-Ebene, Umbau-Plan Baustein 2)
- **Je Team-Woche:** PF, PA, Sieg, Starter-Projektion, Bank-Punkte, Optimal, Verschenkt, Wochenrang, All-Play W/L, Median-Sieg.
- **Saisontabelle:** Spiele, W-L, PF, PA, Win %, PF je Spiel, All-Play W-L und %, Median-Bilanz, Σ Optimal, Coaching-Effizienz, Verschenkt, Kader-Potenzial, Floor, Form, Form Δ, Streak, Luck, Restspielplan, Projektions-Delta, Rang, Rang Division, Waiver-Prio und Moves (aus mTeam).
- **Score:** sieben Kennzahlen × drei Normierungen (Min–Max, Rangpunkte, z) × drei Profile (Stärke, Verdienst, Form), dazu Rang Score.
- **Je Spielwoche:** Top-Team, Ligaschnitt, Höchst- und Tiefstwert.

Die Ausgabe ist so geschnitten, dass Baustein 3 die „(Import)“-Spalten in Team-Wochen, Saisontabelle und Spielwochen direkt daraus füllen kann.

## Schritte
1. **Umgebung:** Stephan installiert pytest im normalen PowerShell-Fenster (`python -m pip install --user pytest`); `requirements.txt` bekommt `pytest` dazu.
2. **Rückfragen klären** (unten), dann Plan für `compute.py` in wenigen Sätzen: Funktionen, Datenfluss, Aufbau der JSON-Datei.
3. **`scripts/compute.py`:** liest die Rohdaten über `espn_fetch.load_week_matchups` und `mRoster`; rechnet nur Wochen, deren Matchups alle abgeschlossen sind (W3 fließt erst nach dem Neuholen ein); optional `--through N`. Aufstellung nach CLAUDE.md (Optimal = Basis + max(opt1, opt2), IR ausgeschlossen, Spieler ohne Stat-Eintrag = 0). Ausgabe: `data/season_2026.json` plus kurze Tabelle im Terminal (Rang, Team, W-L, PF, All-Play, Effizienz, Score).
4. **`tests/test_compute.py`:** liest die Tabellen direkt aus `docs/referenz_w1-w2.md` (eine Quelle, keine abgeschriebenen Zahlen) und prüft mit `--through 2`: W-L, PF, PA, All-Play, Verschenkt gesamt und je Woche, Score-Probe Stärke (Min–Max, ganzzahlig) samt Reihenfolge. Dazu Prüfpunkt 1 (Starter-Summe = PF, 20/20) und Regeln ohne Referenzwert: Min–Max in 0–100 (50 bei max = min), Rangpunkte 10…1, z-Mittelwert 0, Gewichtssumme je Profil 100.
5. **Unabhängige Gegenrechnung:** ein zweiter Rechenweg rechnet Optimal und Score nach, ohne `compute.py` zu kennen; Abweichungen klären.
6. **Git:** Commit „Baustein 2: Rechenwerk mit Tests gegen Record Book 2.7.“
7. **Abschluss:** Haken Baustein 2 und Sessionvermerk im Umbau-Plan (nach Freigabe, CLAUDE.md „Gelernt“), Todoist-Aufgabe abhaken, Korrekturen unter „Gelernt“ eintragen.

## Rückfragen vor dem Bauen (Vorschlag in Klammern)
1. **z-Score:** Standardabweichung über die zehn Teams als Grundgesamtheit (÷ n) oder als Stichprobe (÷ n − 1)? (÷ n; vorher lesend gegen die N/R/Z-Werte prüfen, die Session G1 in die Saisontabelle geschrieben hat)
2. **Rang Score:** nach welchem Score? (Min–Max im aktiven Profil Stärke, wie die Score-Probe)
3. **Restspielplan:** Durchschnitt je offenem Spiel (ein Gegner, der zweimal kommt, zählt doppelt) oder je Gegner? (je offenem Spiel)
4. **Form bei weniger als drei Spielen:** Durchschnitt der vorhandenen Spiele? (ja)
5. **Rundung:** Spielerpunkte unverändert summieren und erst das Ergebnis round half up auf zwei Stellen runden? (ja – so entstehen die ESPN-Totals)

## Nicht in dieser Session
Spieler-Kennzahlen, Rest of Season und Ersatzniveau (brauchen `kona_player_info`, das Baustein 1 noch nicht abruft), Kader-Projektion ROS, Playoff-Simulation, Playoff-Seed (Regel offen, Todoist-Aufgabe „Playoff-Format in ESPN prüfen“). Keine ESPN-Abrufe, keine Notion-Writes außer Haken und Sessionvermerk, keine Pakete außer pytest.

## Referenz
`docs/referenz_w1-w2.md` (Record Book 2.7): Toleranz 0,01, Score-Probe ganzzahlig. W3 prüft Stephan nach dem Neuholen gegen die ESPN-Oberfläche.

## Danach
Session 3 = Notion-Sync (Baustein 3): vor dem ersten Write das DB-Schema per API lesen und die Spaltennamen bestätigen lassen.
