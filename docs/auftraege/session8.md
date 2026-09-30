# Auftrag Session 8 – Positions-Matchup und Wetteranzeige (Start nach dem 30.09.2026, Cloud oder lokal)

Grundlage: `docs/auftraege/session6_vorbereitung.md` Abschnitt 1 (Befunde: Positions-Matchup, Wetter), Abschnitt 2
(Beschluss: Faktor je Defense und Position analog D/ST, Vorjahr als Prior, ehrlich beschriftet als „Position gegen
Defense“) und Abschnitt 5 (Wetter-Schwellen aus der Literatur); das Ergebnis-Kapitel in `session7.md` (Waiver-Tab ohne
Matchup-Spalte, `wetter.json` liegt seit Session 6 vor); Datenvertrag `docs/app_daten.md`; Rechenregeln in CLAUDE.md
(„D/ST-Faktoren“ als Vorbild). Vorab geprüft am 30.09.2026 (lokal, nur lesend): Die ESPN-Vorjahresantwort
`seasons/2025/segments/0/leaguedefaults/3?view=kona_player_info` trägt **keine** `positionalRatings`, aber je Spieler
das Wochen-Ist W1–18 mit 27 Rohstat-Werten und `proTeamId` je Woche (rund 24 KB je Spieler, also etwa 25 MB für alle
aktiven Spieler); die laufende Saison steht mit Ist je Woche im Liga-Scoring schon in `wNN/kona_player_info.json`.

## Starttext (für die Session, Cloud oder lokal)
Wir starten Session 8 nach `docs/auftraege/session8.md`. Lies zuerst CLAUDE.md, `docs/app_daten.md`,
`docs/auftraege/session6_vorbereitung.md` (Abschnitte 1, 2 und 5) und das Ergebnis-Kapitel in
`docs/auftraege/session7.md`, dann `git pull`, Branch `claude/session8-matchup` anlegen. Reihenfolge:

1. **Vorjahresgrundlage Positionen:** `espn_fetch.py --due` holt einmalig `basis/positionen_2025.json` – ein Auszug
   aus der 2025-Antwort (alle aktiven Spieler, Wochen-Ist mit Rohstats): je NFL-Team, Position (QB, RB, WR, TE, K)
   und Woche die Summe der Punkte im **Liga-Scoring aus den Rohstats** (wie die D/ST-Grundlage, `dst.py` rechnet dort
   94/94 exakt) und die Zahl der Spieler mit Stat 210; Gegner aus `basis/proTeamSchedules_wl_2025.json`. Nur die Summen
   ins Repo (wenige KB), nie die Rohantwort. Ohne die Datei rechnet das Modul mit r25 = 1,00 (Ligamittel), damit die
   App auch vor dem ersten Wochenabruf nach dem Merge läuft. Test mit einem Fake wie in `tests/test_fetch.py`.
2. **Rechenwerk `scripts/matchup.py`** (reine Funktionen, analog `dst.py`): Z(D, P) = Ø je Spiel der Punkte
   (Liga-Scoring, nur Spieler mit Stat 210), die Spieler der Position P gegen die Defense D erzielt haben; laufende
   Saison aus den gespeicherten Wochenpools (`proTeamId` je Wochen-Eintrag, Gegner aus dem NFL-Spielplan). LS_P = Ø Z
   über alle Defenses mit Spiel; r = Z/LS; F = (n·r26 + 5·r25 + 5·1,00)/(n + 10), n = Spiele der Defense 2026. Je
   Position Rang 1 = höchstes F (bestes Matchup für die Position). Je Spieler: F des Gegners in Woche N+1 (Bye →
   null), Ø F der nächsten 3 Kalenderwochen, Rest bis W14, SoS W15–17 (Bye fällt heraus, wie D/ST). ESPNs
   `positionalRatings` nur als Test (Vorwochenstand, siehe CLAUDE.md), nicht als Quelle. D/ST bleibt im D/ST-Modul.
   Auslöser wie D/ST (|ΔF| ≥ 0,10, Rangsprung ≥ 5); der z-Auslöser erst, wenn die Positions-CV gegen die echten
   Wochenwerte geprüft sind.
3. **Export und Datenvertrag:** neue Datei `matchup.json` (lazy): Kopf `through_week`, `ligaschnitt` je Position
   (2025, 2026), `formel`; `defenses`: je NFL-Team und Position `{z25, z26, n, r25, r26, f, f_vorwoche, delta, rang,
   rang_vorwoche, ausloeser}`. Je Spieler in `players.json` ein Feld `mu` = `{n1: {week, opp, f}, naechste3, rest,
   sos_po}` (Wochenstand; die App verknüpft über die Spieler-ID, `waiver.json` bleibt Tagesstand). `claude.json`
   bekommt je Kaderspieler `mu_n1`. Positivliste und Öffentlichkeits-Check bleiben grün.
4. **App Positions-Matchup:** Waiver-Tab Spalte „Matchup Wn“ (F des Gegners N+1 als Farbzelle wie im D/ST-Tab,
   Bye als „Bye“) und „Ø nächste 3“ in der Sicht ROS; Spielerseite Kachel „Positions-Matchup“ (Gegner Wn, F, Rang der
   Defense für die Position, Ø nächste 3, Rest) mit dem Hinweis „Position gegen Defense, kein Einzelduell“; neue
   Ansicht `#matchup` (Chip in der Spieler-Gruppe neben D/ST-Faktoren, `app/js/v_matchup.js`): Defense × Position
   mit F und Rang, Umschalter Position, Sortierung, Auslöser-Fähnchen wie bei D/ST.
5. **Wetteranzeige** (`wetter.json`, Datenvertrag Session 6): neue Ansicht `#wetter` (Chip in der Spieler-Gruppe,
   `app/js/v_wetter.js`): Spiele der laufenden Woche mit Anstoß in deutscher Zeit, Heim/Gast, Stadion, Dach
   (Dachspiele ohne Werte, „Dach“), Temperatur, Wind mit Böen, Regenwahrscheinlichkeit, Niederschlag, Schnee;
   Markierung ab Wind ≥ 25 km/h, Böen ≥ 40 km/h, Regenwahrscheinlichkeit ≥ 60 % oder Schnee > 0; zweite Sicht „Ist“
   (gespielte Spiele der Saison). Spielerseite: Zeile „Spiel Wn: PIT @ CLE, Fr 02.10. 02:15 Uhr, 24 °C, Wind 19 km/h
   (Böen 54), Regen 25 %“ über das NFL-Team des Spielers; Waiver-Tab: Fähnchen ⚑ in der Spieler-Spalte bei Wetter über
   der Schwelle (nur Prognose der laufenden Woche; Bye oder Dach: nichts). `wetter_stand` steht schon im Datenstand-Kasten.
6. **Lesart und Doku:** Glossar-Blöcke „Matchup“ (Positions-Matchup, Z je Position, r, F, Rang, nächste 3, Rest,
   Auslöser) und „Wetter“ (Prognose und Ist, Schwellen als Faustregel, Dachspiele, Modellwerte statt Stationsmesswert);
   README (App: Matchup und Wetter; Wochenabruf: Vorjahresgrundlage Positionen); CLAUDE.md (Baustein 4, Rechenregel
   „Positions-Matchup“, Repo-Struktur `basis/positionen_2025.json`, `matchup.py`, `matchup.json`, Gelernt-Zeilen für
   Korrekturen dieser Session); `docs/app_daten.md`.
7. **Tests:** Auszug 2025 aus einem Fake (Rohstats → Liga-Scoring, Muster `dst.py`), Z und F von Hand mit Mini-Daten
   (Bye, Spieler ohne NFL-Team, Defense ohne Spiel), Rang und Spielerwerte (N+1, nächste 3, Rest), Export-Vertrag,
   Wetter-Schwellen als Funktion mit Test, Öffentlichkeit, `test_committete_app_daten_sind_aktuell`.

Vor dem Merge: `main` nachziehen, `python scripts/compute.py`, `pytest`, `python scripts/check_public.py app`, Pull
Request anlegen und mergen (Beschluss 29.09.). Danach holt der nächste Wochenabruf (Di 08:30 UTC) die Datei
`basis/positionen_2025.json`; von Hand geht das nur aus einer lokalen Session (`gh workflow run wochenabruf.yml`) oder
durch Stephan unter Actions › Wochenabruf › Run workflow. Erkläre bei jedem Schritt kurz, was du tust und warum.

## Rahmen
- **Cloud-Session:** eigener Klon, Push, Pull Request und Merge über die GitHub-Anbindung; keine `gh`-CLI (Actions von
  Hand startet Stephan oder eine lokale Session). Netzwerk der Cloud-Umgebung „Standard“ steht seit 29.09. auf
  „Vollständig“, ein erster Test gegen ESPN steht aus – Rohdaten holt ohnehin die Action, ESPN-Antworten nur zum
  Erkunden abrufen, nie committen. App-Prüfung im Chromium (390 px und 1100 px, hell und dunkel) wie beim UI-Review.
  `.lokal/` gibt es in der Cloud nicht; dort liegt nichts, was Session 8 braucht.
- **Seit Session 7 gemerged:** UI-Pakete aus `docs/auftraege/ui_review_2026-09-29.md` (PR #24–#26: Seitenwechsel oben,
  Zurück mit Scrollposition, feste Spalten auf dem Handy, `in_app`-Kennung für Spieler ohne Seite). Neue Ansichten
  übernehmen diese Muster – nach `git pull` zuerst `app/js/app.js`, `ui.js`, `v_dst.js` und `v_waiver.js` lesen.
- **Nicht in Session 8:** CB-gegen-WR (keine offenen Daten), Wetter-Auswertung nach Positionen (erst nach einer
  Saison, Abschnitt 5), News Stufe 2 (Beschluss Stephan 30.09.2026: bleibt aus, siehe CLAUDE.md „Gelernt“).
- **Regeln:** Rohdaten nie von Hand committen; öffentlich nur Ligadaten; Zahlen kommen aus Python, die App rechnet nur
  Anzeige und Filter; alle Projektionen und Prognosen sind Input, keine Wahrheit.

## Entscheidungen vorab (Vorschlag Claude – Stephan kann sie beim Start ändern)
1. **Prior 2025** aus den Rohstats aller Spieler im Liga-Scoring (exakt wie D/ST) statt aus ESPN-Ratings – die
   2025-Antwort trägt keine `positionalRatings`. Nur Summen je Team, Position und Woche ins Repo.
2. **Formel und Gewichte wie D/ST** (5 Spiele Vorjahr, 5 Spiele Ligamittel 1,00); K wie die anderen Positionen; D/ST
   bleibt im D/ST-Modul.
3. **Anzeige** als „Position gegen Defense“ mit Farbzellen wie im D/ST-Tab; keine Einzelduelle, keine Übernahme von
   ESPNs OPRK.
4. **Wetter-Schwellen** als Faustregel aus der Literatur (Wind ≥ 25 km/h, Böen ≥ 40 km/h, Regen ≥ 60 %, Schnee);
   Dachspiele ohne Werte; Modellwerte, kein Stationsmesswert – die Lesart sagt das.
5. **Eine Session für beides;** wird es eng, zuerst Positions-Matchup mit der Waiver-Spalte, Wetter danach.

## Ergebnis (30.09.2026, lokale Session)
- **Vorjahresgrundlage Positionen:** `espn_fetch.py --due` holt einmalig `basis/positionen_2025.json` (Job nach der D/ST-Grundlage; Fehler nur Warnung, der nächste Lauf versucht es erneut). Quelle `seasons/2025/segments/0/leaguedefaults/3?view=kona_player_info` mit `filterStatsForSourceIds [0]` und `filterStatsForSplitTypeIds [1]` (1090 Spieler, 4,4 MB, nur Wochen-Ist W1–18). Neu: `scoring_table` und `league_points` rechnen die Rohstats im Liga-Scoring aus `mSettings` nach (`pointsOverrides` nur für Slot 16 = D/ST) – exakt geprüft an allen Ist-Einträgen W1–W3 2026 sowie 2025 an 544/544 D/ST-Spielen (`basis/kona_dst_2025.json`) und 3852/3852 Offensivwochen (Liga-Endpunkt). Der Auszug trägt je NFL-Team (Team des Spiels laut Stat-Eintrag), Position und Woche Punktsumme und Zahl der Spieler mit Einsatz, dazu das verwendete Scoring (rund 25 KB). `check_positions` verlangt 32 Teams mit je 17 QB-Wochen. Abdeckung 2025: alle 544 Team-Spiele mit QB/RB/WR/TE, K fehlt einmal (NYJ W18).
- **Rechenwerk `scripts/matchup.py`:** Formel der D/ST-Faktoren je Defense und Position, Funktionen aus `dst.py` wiederverwendet. Team eines Spielers = `proTeamId` des Ist-Eintrags (`rawdata.PoolRow.game_team`, W1–W3: 10 Ist-Einträge von 8 Spielern weichen vom Team im Pool derselben Woche ab, 2 mit Einsatz). Z26 bis W2 = ESPN `positionalRatings` der W3-Datei (160/160, Test). Ohne Auszug r25 = 1,00 (`vorjahr_quelle` „ligamittel“, Hinweis in der App); weicht das Scoring im Auszug ab, Warnung. Auslöser |ΔF| ≥ 0,10 und Rangsprung ≥ 5 (nicht gegen den Gleichstand vor der Saison ohne Vorjahr), kein z-Auslöser. `player_mu` je Spieler (N+1 mit Gegner, F, Rang; nächste 3, Rest, SoS); D/ST aus den D/ST-Faktoren. Nach W3 ohne Vorjahr: LS26 QB 27,15 · RB 20,94 · WR 33,08 · TE 13,79 · K 8,22; mit dem echten Auszug (Probe, nicht im Repo) LS25 QB 25,61 · RB 22,90 · WR 31,82 · TE 13,36 · K 8,20.
- **Export:** `matchup.json` (lazy, 25 KB), `players.json` je Spieler `mu` und Kopf `mu_woche`, `claude.json` Spalten `gegner_n1`, `mu_n1` und `stand.matchup_woche` (29,7 KB), `wetter.json` je Spiel `markierung` und Kopf `schwellen` (`wetter.markierung`: wie angezeigt gerundet; Dach und offener Anstoß ohne Markierung). Datenvertrag `docs/app_daten.md` nachgezogen.
- **App:** `#matchup` (Übersicht Defense × Position, `#matchup/qb` … `/k` wie D/ST-Offenses), `#wetter` und `#wetter/ist` (Chips in der Spieler-Gruppe), Waiver-Spalten „Matchup Wn“ und „Ø nächste 3“ und Wetter-⚑ (nur vor dem Anstoß), Spielerseite mit Kacheln „Positions-Matchup“ bzw. „Matchup D/ST“ und Wetterzeile („Spiel W4: PIT @ CLE, Fr 02.10. 02:15 Uhr, 25 °C, Wind 19 km/h (Böen 53 ⚑), Regen 25 %“), Glossar-Blöcke „Matchup“ und „Wetter“. Farbstufe `U.fcls` jetzt gemeinsam (auch D/ST) und nach der angezeigten Zahl (2 oder 3 Stellen, gleicher Formatierer): vorher bekam „1,15“ wegen Gleitkomma die Stufe „leicht günstig“; geprüft an 2834 echten Werten ohne Abweichung zwischen Zahl und Farbe.
- **Tests:** 451 grün (40 neu: Abruf mit Fake-Session und echtem Scoring, Z/F von Hand mit Attrappe, Spielerwerte, Vertrag, Wetter-Schwellen, Rangsprung ohne Vorjahr). Mit dem echten Auszug als Repo-Kopie laufen alle Tests und `compute.py` ohne Warnung – der Zustand nach dem ersten Wochenabruf ist also geprüft.
- **Gegenprüfung:** sieben Blickwinkel (Rechenwerk mit unabhängiger Nachrechnung, Abruf, Export, App Matchup, App Wetter, Doku/Tests, Auftragsabgleich), je Fund zwei Skeptiker, 35 Agenten. Unabhängig nachgerechnet ohne Abweichung: alle 160 Zellen mit und ohne Vorjahr, alle 576 Spieler-`mu`, D/ST-`mu` gegen `dst.json`. Bestätigt und behoben: falsche Zahl in CLAUDE.md (10 Spieler → 10 Einträge von 8 Spielern), erfundenes Override-Beispiel im Docstring von `scoring_table`, Farbstufe widersprach bei drei Stellen der Legende. Aus strittigen Funden übernommen: kein Rangsprung gegen den Gleichstand vor der Saison (ohne Vorjahr hätte W1 fast alle Zellen markiert), kein Wetter-⚑ und keine Prognosewerte für schon angepfiffene Spiele.
- **Zwischenfall:** Eine parallele Session im selben Arbeitsordner hat um 10:26 Uhr die noch nicht committeten Grundlagen-Zeilen dieser Session (`season_files`, `PoolRow.game_team`, `Season.prior_positions`) in ihren Commit für PR #28 übernommen und den Ordner auf `main` gewechselt. Inhaltlich harmlos (rein additiv, Tests grün), die Arbeit wurde danach sofort auf den Branch committet.
- **Offen:** Auslöser-Dichte (nach W3 je Position 10–19 von 32 Defenses mit ⚑, mit Vorjahr 5–14, fast nur Rangsprünge bei n = 3; D/ST: 4) – Schwelle mit Stephan klären; z-Auslöser nach Prüfung der Positions-CV; `players.json` wächst (W3: 53 KB gzip, mit `mu` +8 KB), Budget im Blick behalten; `basis/positionen_2025.json` holt der nächste Wochenabruf.
