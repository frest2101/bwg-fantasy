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
   **Achtung:** `pages.yml` hört unter `workflow_run` auf den Workflow-Namen „Transaktions-Archiv“; beim Umbenennen in
   „Tageslauf“ dort mit umbenennen, sonst baut Pages nach den Tagesläufen nicht mehr.
3. **Pool-Auszug** `data/raw/2026/pool/latest.json` (Felder laut Vorbereitung, inkl. `lastNewsDate`), Tests.
4. **Stadion-Tabelle** `data/raw/2026/nfl/stadien.json` von Hand (Koordinaten, Dach, Zeitzone) plus Auslandsspiele 2026.
5. **Wetter:** Prognosen `wetter/prognose/wNN_<UTC>.json` nur für die laufende Woche, Ist-Wetter dauerhaft in
   `wetter/ist_2026.json`, nur W1–17, Tests.
6. **compute/app_export:** `manifest.datenstand` um `pool_stand` und `wetter_stand`, Dateien `waiver.json` und
   `wetter.json` nach `docs/app_daten.md` (Positivliste erweitern), `check_public.py` bleibt grün.
7. **CLAUDE.md:** Abschnitt Automatisierung, Repo-Struktur, Gelernt-Zeile zur Waiver-Sichtbarkeit 10:30–11:00 Uhr.

Vor dem Merge: `main` nachziehen, `python scripts/compute.py`, `pytest`, `python scripts/check_public.py`, Pull
Request anlegen und mergen (Beschluss 29.09.). Erkläre bei jedem Schritt kurz, was du tust und warum.

## Ergebnis (29.09.2026, lokale Session)
- **Probe-Lauf:** `probe.yml` und `scripts/probe.py` kamen über einen eigenen Pull Request nach `main`, weil `gh workflow run` einen Workflow nur findet, wenn seine Datei auf `main` liegt. Der Lauf (16 s) bestätigt aus der Action: Open-Meteo antwortet (Prognose und Ist-Werte über `start_hour`/`end_hour`, erlaubt rund drei Monate zurück bis gut zwei Wochen voraus), die ESPN-Scoreboard-API liefert je Spiel Spielort, `indoor` und `neutralSite`, aber Wetter nur als AccuWeather-Stichwort in °F und nur für wenige Spiele; der Fantasy-News-Endpunkt je Spieler liefert Rotowire-Meldungen und ESPN-Stories mit Schlagzeile, Datum und Link (`lastNewsDate` im Pool entspricht der jüngsten Meldung).
- **Entscheidung Quellen:** Wetter aus Open-Meteo mit eigener Stadion-Tabelle (`scripts/wetter.py`); News aus dem ESPN-Fantasy-Endpunkt, als `--news` in `scripts/news.py` vorbereitet, im Tageslauf aus (Stufe 2 nach Stephans Entscheidung). Abweichung zur Vorbereitung §6: Der News-Teil vergleicht `lastNewsDate` nicht mit dem vorigen Pool-Auszug (der ist zu dem Zeitpunkt schon überschrieben, Fehlschläge gingen verloren), sondern mit einem eigenen Stand je Spieler in `news/lastNewsDate.json`; der Erstlauf ist damit „Stand leer“, Fehlschläge und über die Obergrenze zurückgestellte Spieler werden nachgeholt (Fund der Gegenprüfung).
- **Tageslauf:** `transaktionen.yml` ist zu `tageslauf.yml` geworden (Name „Tageslauf“, 13 Läufe je Tag, `--transactions --pool --wetter`); `pages.yml` hört auf „Tageslauf“. Commit-Meldung mit Uhrzeit, weil es mehrere Läufe je Tag gibt.
- **Pool-Auszug:** `pool/latest.json` mit den Feldern der Vorbereitung plus `lastNewsDate`; geschrieben nur, wenn sich außer `stand` etwas ändert (`stand` = letzte Änderung). Echt gemessen: 1050 Spieler, rund 236 KB (die Schätzung 80 KB war zu knapp; die ESPN-Feldnamen sind lang, Git speichert Deltas).
- **Stadion-Tabelle:** 32 Heimstadien und neun Auslandsspiele mit ESPN-Spiel-IDs, Spielorte gegen die ESPN-Scoreboard-API und die NFL-Liste 2026 geprüft, alle 41 Einträge zusätzlich durch unabhängige Prüfer gegen Wikipedia bestätigt (Koordinaten ±2 km, Dach, Zeitzone).
- **Wetter:** Prognose je Lauf (`wNN_<UTC>.json`, nur bei Änderung, Vorwoche wird beim ersten gelungenen Lauf der neuen Woche gelöscht; die Woche kommt aus dem NFL-Spielplan – erste Woche mit einem noch nicht beendeten Spiel –, damit die Montagnacht zur MNF-Woche gehört und nach dem letzten Spiel der W17 der Ordner geleert wird), Ist-Wetter dauerhaft (`ist_2026.json`, ab vier Stunden nach Anstoß, nie überschrieben, ohne Regenwahrscheinlichkeit). Spiele mit offenem Anstoß (ESPN `startTimeTBD`, Platzhalter So 08:01 UTC) tragen `tbd: true` und keine Werte. Probelauf gegen ein Scratch-Verzeichnis: W4-Prognose mit 16 Spielen (8 KB), Ist-Wetter W1–3 mit 48 Spielen (24 KB). Open-Meteo-Ausfälle sind Warnungen, fehlende Grundlagen (Stadion-Tabelle, Spielplan) Fehler.
- **App-Daten:** `manifest.datenstand.pool_stand` und `wetter_stand`; `waiver.json` (Tagesstand je Spieler der App plus aktuelle Kaderspieler) und `wetter.json` (Prognose und Ist, je Spiel verdichtet) nach `docs/app_daten.md`. Beide entstehen erst mit dem ersten Tageslauf nach dem Merge; die Anzeige folgt in Session 7 (Waiver) und 8 (Wetter).
- **Gegenprüfung:** unabhängige Prüfer über sieben Blickwinkel (Abruf, Wetter, Export, Workflows, News, Tests/Doku, Stadion-Tabelle/Öffentlichkeit), jeder Fund von zwei Skeptikern geprüft. Behoben: News-Stand je Spieler statt Vergleich mit dem vorigen Pool-Auszug (Erstlauf, Fehlschläge, Obergrenze, Meldung zu zwei Spielern), Fehlerbehandlung in `update_pool` (unbekannter Kalender, falsch strukturierte Datei), Prognosewoche aus dem Spielplan, `tbd`-Kennzeichnung, Absturz bei leerer Ist-Datei, Stammdaten für Kaderspieler außerhalb von `players.json` in `waiver.json`, App-Texte „täglich“ → stündlich, Testlücken (D/ST 32/32, Bye-Teams, Tageslauf mit `--news`). Stadion-Tabelle und Öffentlichkeit ohne Fund.
- **Tests:** rund 400 grün (über 30 neu: Pool-Auszug, Tageslauf, Wetter, News, Stadion-Tabelle, Datenvertrag); Zeitzonen-Prüfung ohne Abhängigkeit von `tzdata` (auf Windows fehlt es).
- **Offen:** Stufe 2 News (Entscheidung Stephan); erster echter Tageslauf nach dem Merge per `gh workflow run tageslauf.yml` prüfen; ESPN liefert die Projektion der neuen Woche dienstags vermutlich erst im Lauf des Tages, bis dahin steht `proj_naechste_woche` auf `null`.
