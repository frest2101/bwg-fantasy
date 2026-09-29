# Auftrag Session 7 – Waiver-Tab, News-Kasten Stufe 1, Datenstand (Start 30.09.2026, lokal)

Grundlage: `docs/auftraege/session6_vorbereitung.md` Abschnitt 2 (Beschluss Waiver-Tab; Positions-Matchup Session 7/8)
und Abschnitt 6 (News-Kasten Stufe 1), das Ergebnis-Kapitel in `session6.md` und der Datenvertrag `docs/app_daten.md`
(`waiver.json`, `wetter.json`, `manifest.datenstand`). Der Tageslauf liefert seit 29.09.2026 stündlich den Tagesstand
je Spieler; diese Session baut die Anzeige dazu. Wetteranzeige und Positions-Matchup folgen in Session 8.

## Starttext (für die lokale Session)
Wir starten Session 7 nach `docs/auftraege/session7.md`. Lies zuerst CLAUDE.md, `docs/app_daten.md` und
`docs/auftraege/session6_vorbereitung.md` (Abschnitte 2 und 6), dann `git pull`, Branch `claude/session7-waiver`
anlegen. Reihenfolge:

1. **Datenstand in der App:** Der Kasten im Kopf (`app/js/app.js`, `header()`) zeigt `pool_stand` („Besitz, Verletzung,
   Projektion nächste Woche: Stand <Datum Uhrzeit>“) und `wetter_stand`; „Nächster Abruf“ nennt den nächsten Tageslauf
   (stündlich 06:45–11:45 und 15:40–21:40 UTC) statt nur den Wochenabruf. Der Hinweis im Spieler-Tab („Besitz und
   Verletzung: Stand nach W…“) wechselt auf den Tagesstand, sobald `waiver.json` vorliegt.
2. **Export erweitern** (`scripts/app_export.py`, `scripts/espn_fetch.py`, `docs/app_daten.md`, Tests):
   - `players.json`: je Spieler `bye` (Bye-Woche des NFL-Teams; liegt in `players.py` schon als `bye_week` vor).
   - Tageslauf: `--pool` holt zusätzlich `mTeam` (ein Aufruf) und legt `waiverRank` je Team als `waiver_reihenfolge`
     im Kopf von `pool/latest.json` ab; `waiver.json` bekommt daraus `reihenfolge` (Liste der team_ids, 1 = zuerst).
     Der Wochenwert `waiver_prio` in `teams.json` bleibt, die App zeigt den Tagesstand.
   - `waiver.json`: `bedarf` je Team – Python rechnet, die App zeigt: ROS-optimale Aufstellung des aktuellen Kaders
     (Tagesstand `team` aus `waiver.json`, ROS/Spiel aus `players.json`, Aufstellungsregel `lineup.optimal_points`);
     Starter mit ROS/Spiel unter dem Ersatzniveau ihrer Position sind der Bedarf. Dazu je Position die Zahl der
     Kaderspieler über Ersatzniveau. Nur Regular-Season-ROS.
   - Positivliste und Öffentlichkeits-Check bleiben grün, `test_committete_app_daten_sind_aktuell` bleibt.
3. **Waiver-Tab** (`#waiver`, neuer Eintrag in der Navigation zwischen Spieler und Rekorde; lädt `waiver.json` und
   `players.json`, neue Datei `app/js/v_waiver.js`):
   - **Beste verfügbare Spieler je Position:** Status `WAIVERS` oder `FREEAGENT` laut Tagesstand, sortiert nach ROS über
     Ersatz; Spalten Name (Link zur Spielerseite), NFL, Bye (die Bye der nächsten Woche hervorheben), Verletzung
     (Tagesstand), Projektion nächste Woche, ROS/Spiel, ROS über Ersatz, Besitz % mit Δ, gestartet %, Frist
     (`waiver_bis` in deutscher Zeit, `–` bei Free Agents). Spaltenfilter und Chips wie im Spieler-Tab; Positionschips
     QB · RB · WR · TE · K · D/ST. Die Spalte Positions-Matchup entfällt bis Session 8 (Hinweis in der Lesart).
   - **Bedarf je Team:** aus `bedarf`; das eigene Team (Kürzel-Auswahl wie im Moves-Tab) zuerst.
   - **Waiver-Reihenfolge:** aus `reihenfolge`, mit Hinweis „ESPN verarbeitet 07:00 UTC; in der App sichtbar erst
     10:30–11:00 Uhr“.
   - **Claims der letzten 7 Tage:** aus `transactions.json` (`WAIVER` und `FREEAGENT` mit Drops), Link auf `#moves`.
   - Smartphone: Spalten reduzieren wie im Spieler-Tab, Tabellen scrollbar.
4. **News-Kasten Stufe 1** auf der Spielerseite (`#spieler/<id>`, `app/js/v_spieler.js`): „Letzte ESPN-Meldung:
   <Datum>“ aus `waiver.json` `news` (Tagesstand; „–“ ohne Meldung, „keine Tagesdaten“ ohne `waiver.json`) und
   Deep-Links, nur Verweise, nie Text: ESPN-Spielerseite (`https://www.espn.com/nfl/player/_/id/<id>`), ESPN-Fantasy-
   Spielerkarte (`https://fantasy.espn.com/football/player?playerId=<id>`), FantasyPros-Spielerseite (Slug aus dem
   Namen: Kleinbuchstaben, Bindestriche, ohne Apostroph und Punkte; Sonderfälle Jr./Sr./II/III und D/ST prüfen –
   bei Zweifel Suche statt Slug), Rotoworld/NBC als Suche. D/ST (negative ESPN-ID) bekommen die ESPN-Teamseite.
   Links mit `target="_blank"` und `rel="noopener"`.
5. **Lesart und Doku:** Glossar-Einträge Tagesstand, Ersatzniveau, ROS über Ersatz, Frist, Besitz-Trend, Bedarf,
   Waiver-Reihenfolge, Letzte ESPN-Meldung; README (App-Abschnitt: Waiver-Tab, News-Links); CLAUDE.md: Baustein 4 um
   den Waiver-Tab ergänzen, Gelernt-Zeilen für Korrekturen dieser Session.
6. **Tests:** Export (`bye`, `reihenfolge`, `bedarf` gegen eine Handrechnung, Datenvertrag), Tageslauf mit `mTeam`
   (Fake wie in `tests/test_fetch.py`), Öffentlichkeit (Links mit Spielernamen sind erlaubt, Manager-Namen nicht).

Vor dem Merge: `main` nachziehen, `python scripts/compute.py`, `pytest`, `python scripts/check_public.py app`, Pull
Request anlegen und mergen (Beschluss 29.09.). Nach dem Merge einen Tageslauf per `gh workflow run tageslauf.yml`
starten und prüfen, dass `waiver.json` `reihenfolge` und `bedarf` trägt. Erkläre bei jedem Schritt kurz, was du tust
und warum.

## Rahmen
- **Nicht in Session 7:** Positions-Matchup (Session 8: Faktor je Defense und Position mit Vorjahres-Prior, dann die
  Spalte im Waiver-Tab und je Spieler), Wetteranzeige (Session 8), News Stufe 2 (Entscheidung Stephan; einschalten wäre
  `--news` in `tageslauf.yml`).
- **Datenquellen der App:** `waiver.json` = Tagesstand (stündlich): Status, Team, Verletzung, Besitz, Frist, Projektion,
  letzte Meldung; `players.json` = Wochenstand: Name, Position, NFL, ROS, Ersatzniveau (`ersatz`); `transactions.json`
  = Claims; `teams.json` = Wochenwerte. Ein Spieler kann im Tagesstand stehen, aber nicht in `players.json` (dann trägt
  `waiver.json` `name, pos, nfl` selbst, ohne ROS) – die App zeigt ihn mit „–“ statt ihn zu verstecken.
- **Regeln:** Der Tageslauf committet 13-mal täglich auf `main` – vor lokaler Arbeit `git pull`, Rohdaten nie von Hand
  abrufen oder committen; Änderungen am Abruf nur im Code mit Tests. Öffentlich sind nur Ligadaten: keine Manager-Namen,
  keine ESPN-Texte; Links sind Verweise. Zahlen kommen aus Python, die App rechnet nur Anzeige und Filter.

## Entscheidungen vorab (Vorschlag Claude – Stephan kann sie beim Start ändern)
1. **Bedarf-Regel:** Starter der ROS-optimalen Aufstellung (Regular Season) mit ROS/Spiel unter dem Ersatzniveau der
   Position; Ersatzniveau wie bisher Ø der drei besten verfügbaren Spieler je Position (`players.json` `ersatz`).
2. **Waiver-Reihenfolge als Tagesstand** über `mTeam` im Tageslauf (ein zusätzlicher Aufruf je Lauf, `waiverRank`).
3. **„Verfügbar“** = Status `WAIVERS` oder `FREEAGENT` laut Tagesstand; nach dem Wochenwechsel stehen alle freien
   Spieler bis zur nächsten Verarbeitung auf `WAIVERS` (CLAUDE.md, Gelernt).
4. **Frist** in deutscher Zeit (Europe/Berlin) mit Datum und Uhrzeit; ESPN meldet 07:00 UTC.
5. **Positions-Matchup:** keine Platzhalter-Spalte; die Lesart nennt Session 8.
