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
