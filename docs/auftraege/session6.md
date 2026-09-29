# Auftrag Session 6 – Tageslauf, Pool-Auszug, Wetter, Probe-Lauf (Start 29.09.2026, lokal)

Grundlage: `docs/auftraege/session6_vorbereitung.md` (Beschlüsse Stephan 29.09.2026). Diese Session baut nur die
Infrastruktur; Waiver-Tab und News-Kasten Stufe 1 folgen in Session 7, Positions-Matchup und Wetteranzeige in Session 8.

## Starttext (für die lokale Session)
Wir starten Session 6 nach `docs/auftraege/session6_vorbereitung.md`, Abschnitt 3, Punkte 1–7. Lies zuerst CLAUDE.md
und die Vorbereitungsdatei, dann `git pull`, Branch `claude/session6-tageslauf` anlegen. Du darfst `pytest` aus
`requirements.txt` installieren, falls es fehlt. Reihenfolge:

1. **Probe-Lauf zuerst:** Workflow `probe.yml` (nur `workflow_dispatch`, ohne Commit), der Open-Meteo (Prognose und
   `past_days`), die ESPN-Site-API (Scoreboard mit `weather`, Athleten-News) abfragt und die Antworten gekürzt ins Log
   schreibt. Starten mit `gh workflow run probe.yml`, Log lesen, dann Wetter- und News-Quelle festlegen. Lokal kannst du
   die Quellen auch direkt anfragen, aber die Probe stellt sicher, dass sie aus der Action erreichbar sind.
2. **Tageslauf:** `transaktionen.yml` umbauen (Name „Tageslauf“, cron `45 6-11 * * *` und `40 15-21 * * *`, Aufruf
   `espn_fetch.py --transactions --pool --wetter`); News bleibt für Stufe 2 vorbereitet, aber noch aus.
3. **Pool-Auszug** `data/raw/2026/pool/latest.json` (Felder laut Vorbereitung, inkl. `lastNewsDate`), Tests.
4. **Stadion-Tabelle** `data/raw/2026/nfl/stadien.json` von Hand (Koordinaten, Dach, Zeitzone) plus Auslandsspiele 2026.
5. **Wetter:** Prognosen `wetter/prognose/wNN_<UTC>.json` nur für die laufende Woche, Ist-Wetter dauerhaft in
   `wetter/ist_2026.json`, nur W1–17, Tests.
6. **compute/app_export:** `manifest.datenstand` um `pool_stand` und `wetter_stand`, Dateien `waiver.json` und
   `wetter.json` nach `docs/app_daten.md` (Positivliste erweitern), `check_public.py` bleibt grün.
7. **CLAUDE.md:** Abschnitt Automatisierung, Repo-Struktur, Gelernt-Zeile zur Waiver-Sichtbarkeit 10:30–11:00 Uhr.

Vor dem Merge: `main` nachziehen, `python scripts/compute.py`, `pytest`, `python scripts/check_public.py`, Pull
Request anlegen und mergen (Beschluss 29.09.). Erkläre bei jedem Schritt kurz, was du tust und warum.
