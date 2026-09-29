# Vorbereitung Session 6 – Tageslauf, Wetter, Waiver, Positions-Matchup (29.09.2026, Beschlüsse Stephan)

Ausgangspunkt: Patricks Ideen für die App (Matchup-Schwere je Spieler, Witterung, mehr zu Waiver und Free Agents).
Diskussion am 29.09.2026, Beschlüsse Stephan am selben Tag. Nichts davon ist gebaut; diese Seite ist die Grundlage
für den Auftrag `session6.md`.

## 1 Befunde
- **Positions-Matchup liegt schon in den Rohdaten.** `kona_player_info.positionAgainstOpponent.positionalRatings`
  trägt für alle sechs Positionen (QB, RB, WR, TE, K, D/ST) je NFL-Defense den Ø zugelassener Fantasy-Punkte und den
  Rang (ESPNs „OPRK“). Genutzt wird bisher nur die D/ST-Zeile. Team-Level, kein Einzelduell; Dienstag-Abruf trägt den
  Vorwochenstand (wie bei D/ST), selbst gerechnet aus den Spieler-Stats entfällt das.
- **CB-gegen-WR (Shadow Coverage) gibt es nicht als offene Daten.** PFF ist kostenpflichtig ohne Weitergabe,
  FantasyPros hat keine API (Scraping verboten und fragil), nflverse hat keine Coverage-Zuordnung. Nur als
  redaktionelle CSV von Hand möglich – zurückgestellt.
- **ESPN-Spielertexte** (`seasonOutlook`, `outlooksByWeek`) sind Prosa ohne strukturierten Matchup-Wert; sie bleiben
  wie beschlossen (28.09.) aus der App. Ersetzen keine Datenquelle.
- **Waiver/Free Agents:** alles Nötige ist im Pool: Status WAIVERS/FREEAGENT, `waiverProcessDate`, Besitz ESPN-weit
  (`percentOwned`, `percentChange`, `percentStarted`, ADP), Verletzung, Wochenprojektion, ROS, Experten-Ränge; aus
  mTeam `waiverRank`, aus dem Archiv alle Claims. Liga: klassische Waiver-Reihenfolge ohne FAAB, 24 h Waiver,
  Verarbeitungstage Mo/Mi/Do/Fr/Sa/So; ESPN meldet `waiverProcessDate` 07:00 UTC, in der App sind die Ergebnisse
  erfahrungsgemäß erst 10:30–11:00 Uhr deutscher Zeit sichtbar (Stephan).
- **Netz:** Externe Quellen (Open-Meteo, ESPN-Site-API, nflverse) sind nur aus der GitHub-Action erreichbar, nicht
  aus der Claude-Session (Proxy 403, auch für ESPN). Prüfung der Quellen also per Probe-Lauf in der Action.
- **Kein Server, keine Tokens:** Das Rechenwerk ist reines Python; häufigere Läufe kosten im öffentlichen Repo nichts.
  Aktualisierung „bei jedem App-Aufruf“ verworfen (bräuchte Rechenwerk in JS oder einen Server; ESPN-CORS ungeprüft).
- **Privat stellen** verworfen: Pages aus privatem Repo erst ab GitHub Pro, und die Seite bliebe trotzdem öffentlich;
  ESPNs Nutzungsbedingungen ändern sich dadurch nicht.

## 2 Beschlüsse (Stephan, 29.09.2026)
| Thema | Beschluss |
|---|---|
| Frequenz | Die Läufe werden dichter, keine neue Architektur. Wochenabruf (Di 08:30, Nachläufe Di 16:30, Mi 08:30 UTC) bleibt unverändert, er sichert den finalen Wochenstand. |
| Tageslauf | Der Transaktions-Lauf wird zum **Tageslauf** und läuft **vormittags stündlich** (Beschluss Stephan 29.09.), um den Waiver-Zeitpunkt möglichst zu treffen: cron `45 6-11 * * *` = 08:45–13:45 MESZ bzw. 07:45–12:45 MEZ, also in beiden Zeitregimen der ganze Vormittag bis nach 11:00 Uhr. Der alte Termin 05:17 UTC entfällt. Jeder Lauf holt Transaktionen, **Pool-Auszug** und **Wetter** und committet nur bei Änderung; `concurrency: daten-commit` stellt einen Lauf hinter den Wochenabruf (Di 08:30 UTC), statt ihn abzubrechen. |
| Wetter Do | Donnerstag wegen TNF, **mit Prognose für Sonntag und Montag** im selben Lauf (Open-Meteo liefert 7 Tage; ein Abruf je Spielort deckt die ganze Woche). Die Vormittagsläufe erfüllen das (der letzte um 11:45 UTC ≈ 12,5 h vor TNF-Kickoff), der Nachmittagslauf um 15:40 UTC frischt auf. |
| Wetter Mo | Montag nochmal (MNF) – ebenfalls die beiden Tagesläufe. |
| Wetter-Umfang | Nur W1–17, **kein W18** (Beschluss Stephan 29.09.). |
| Wetter-Ablage | **Prognosen nur für die laufende Woche** behalten (je Lauf eine Datei), beim Wochenwechsel wird der Ordner geleert (Git-Historie bleibt). **Das tatsächliche Wetter je Spiel wird dauerhaft archiviert** – Grundlage für die spätere Frage, welche Positionen wie stark vom Wetter abhängen, und als Hilfe für Aufstellungsentscheidungen (Beschluss Stephan 29.09.). |
| Nachmittagslauf | **Täglich 15:40 UTC** (17:40 MESZ / 16:40 MEZ), Beschluss Stephan 29.09.: frische `injuryStatus`, Pool und Wetter am Nachmittag; sonntags liegt er nach den Inactives (90 min vor dem 1-Uhr-Kickoff) und vor dem Anstoß. Ab der US-Zeitumstellung (01.11.2026) rückt der 1-Uhr-Kickoff auf 18:00 UTC, die Inactives auf 16:30 UTC – deshalb zusätzlich **sonntags 16:40 UTC in den Monaten 11, 12 und 1** (`40 16 * 11,12,1 0`). Jeder Lauf committet nur bei Änderung. |
| Waiver-Tab | Bauen (Session 7): beste verfügbare Spieler je Position nach ROS über Ersatz, Bye, Verletzung, Projektion nächste Woche, Positions-Matchup; Besitz-Trend; Bedarf je Team (Starter unter Ersatzniveau); Waiver-Reihenfolge; Claims der Vorwoche. |
| Positions-Matchup | Bauen (Session 7/8): Faktor je Defense und Position analog D/ST-Faktor (Vorjahr als Prior), Rang nächste Woche und Rest je Spieler. Ehrlich beschriftet als „Position gegen Defense“, nicht als Einzelduell. |
| CB vs WR | Nicht bauen, solange niemand die wöchentliche Pflege einer redaktionellen CSV zusagt. |
| ESPN-Texte | Bleiben aus der App (Öffentlichkeits-Check unverändert). |

## 3 Plan Session 6 (Infrastruktur, eine Session)
1. **Workflow `transaktionen.yml` → Tageslauf:** cron `45 6-11 * * *`, `40 15 * * *` und `40 16 * 11,12,1 0` (7 Läufe je Tag, sonntags im Winter 8), Name „Tageslauf“; Aufruf
   `espn_fetch.py --transactions --pool --wetter`. Commit-Regel bleibt: Rohdaten immer, abgeleitete Dateien nur bei
   grünem Rechenwerk und grünen Tests. `concurrency: daten-commit` bleibt.
2. **Pool-Auszug** `data/raw/2026/pool/latest.json` (überschrieben je Lauf, Historie liegt in Git): je Spieler `id,
   status, onTeamId, injuryStatus, percentOwned, percentChange, percentStarted, waiverProcessDate, proj_naechste_woche`;
   dazu `stand` (UTC des Abrufs) und `woche`. Etwa 80 KB statt 2,8 MB. Quelle: kona mit
   `filterStatsForCurrentSeasonScoringPeriodId` = nächste Woche. Kein `members`-Feld, `check_public.py` bleibt grün.
3. **Stadion-Tabelle** `data/raw/2026/nfl/stadien.json` (einmalig von Hand, aus öffentlichem Wissen): je proTeamId
   Stadion, Breite/Länge, Dach (`offen` / `fest` / `beweglich`), Zeitzone. Dazu eine Liste der Auswärts-Sonderspiele
   2026 (London, Deutschland, Mexiko, Madrid …) mit Woche, Teams und Ort – wenige Einträge, von Hand.
4. **Wetter-Abruf** aus Open-Meteo (frei, ohne Schlüssel): je Spiel der laufenden Woche W1–17 (aus
   `proTeamSchedules_wl.json`: Heimteam, Anstoß) Stundenwert zum Kickoff und für die drei Stunden danach:
   Temperatur, Wind (Mittel und Böen), Niederschlagswahrscheinlichkeit, Niederschlag, Schnee. Dachspiele bekommen
   `dach: true` und keine Wetterwerte in der Anzeige. Ablage der **Prognosen** unter `data/raw/2026/wetter/prognose/
   wNN_<UTC>.json` (je Lauf eine kleine Datei); beim ersten Lauf einer neuen Woche löscht das Script die Dateien der
   Vorwoche (Git-Historie bleibt). **Ist-Wetter:** Für jedes Spiel, dessen Anstoß mindestens vier Stunden zurückliegt,
   holt derselbe Lauf die tatsächlichen Stundenwerte (Open-Meteo `past_days`, Analysewerte, kein Stationsmesswert) und
   schreibt sie einmalig nach `data/raw/2026/wetter/ist_2026.json` (je Spiel: Woche, Teams, Ort, Dach, Kickoff,
   Temperatur, Wind, Böen, Niederschlag, Schnee); vorhandene Einträge werden nie überschrieben. Diese Datei bleibt
   dauerhaft und wächst auf rund 270 Einträge je Saison. **Probe zuerst:** ein `workflow_dispatch`-Lauf, der Open-Meteo
   (Prognose und `past_days`) und als Alternative die ESPN-Site-API (Scoreboard mit `weather`) abfragt; danach Quelle
   festlegen.
5. **compute/app_export:** `manifest.datenstand` bekommt `pool_stand` und `wetter_stand`; neue Dateien `waiver.json`
   und `wetter.json` nach `docs/app_daten.md` (Positivliste erweitern). Anzeige kommt in Session 7.
6. **Tests:** Pool-Auszug (Felder, Anzahl, D/ST 32/32), Wetter (jedes Spiel der Woche hat einen Eintrag, Dach ohne
   Werte, Bye-Teams ohne Spiel), `test_committete_app_daten_sind_aktuell` bleibt.
7. **CLAUDE.md:** Abschnitt Automatisierung (Tageslauf statt Transaktions-Archiv), Repo-Struktur (`pool/`, `wetter/`,
   `stadien.json`), Gelernt-Zeile zu Waiver-Sichtbarkeit 10:30–11:00 Uhr.

## 4 Antworten Stephan (29.09.2026)
- **Zweiter Lauf:** ja, und zwar **jeden Tag** um 15:40 UTC, nicht nur sonntags (Sommer-/Winterzeit siehe Tabelle).
- **W18:** kein Wetter für W18.
- **Wetter-Rohdaten:** Prognosen nur für die laufende Woche behalten, danach überschrieben. Das tatsächliche Wetter
  jedes Spiels wird dokumentiert und dauerhaft behalten – gibt später Aufschluss, welche Positionen vom Wetter
  beeinflusst werden, und hilft bei Aufstellungsentscheidungen.

## 5 Später (nicht Session 6)
- **Wetter-Auswertung:** sobald genug Ist-Spiele vorliegen (frühestens nach einer Saison), Punkte je Position gegen
  Wind, Niederschlag und Temperatur auswerten (z. B. Ø Punkte Passing-Positionen bei Wind ≥ 25 km/h gegen ohne Wind).
  Bis dahin zeigt die App nur die Prognose mit Schwellen aus der Literatur (Wind ab etwa 25 km/h relevant für QB, WR, K).

## 6 News-Kasten auf der Spielerseite (Frage Stephan 29.09.2026, Einschätzung)
Gewünscht: ein Kasten mit den neuesten Nachrichten zu einem Spieler von ESPN, FantasyPros usw., notfalls als Link.

**Stufe 1 – nur Links und Datum (kein Risiko, kein Abruf, halbe Session, passt in Session 7):**
- Aus den vorhandenen Daten: `player.lastNewsDate` und `lastVideoDate` (kona) – „Letzte ESPN-News: 28.09.“ zeigt, ob
  es etwas Neues gibt, ohne einen Text zu übernehmen.
- Deep-Links je Spieler: ESPN-Spielerseite (`espn.com/nfl/player/_/id/<ESPN-ID>`, unsere Spieler-ID ist die
  ESPN-Athleten-ID; D/ST gesondert), ESPN-Fantasy-Spielerkarte (`fantasy.espn.com/football/player?playerId=<ID>`,
  öffnet auf dem Handy die App), FantasyPros-Spielerseite (Slug aus dem Namen, klappt bei den meisten, Sonderfälle
  wie „Jr.“ prüfen), Rotoworld/NBC per Suche. Links sind Verweise, keine Weiterverbreitung von Inhalten.

**Stufe 2 – ESPN-Schlagzeilen (eine Session, nach Probe-Lauf, Entscheidung Stephan nötig):**
- ESPNs Site-API liefert je Athlet News (Schlagzeile, Datum, Link); Zugriff undokumentiert, aus der Action erreichbar,
  aus der Claude-Session nicht – Probe im selben `workflow_dispatch`-Lauf wie das Wetter.
- Abruf nur im letzten Vormittagslauf (11:45 UTC) für Kaderspieler und die 20 besten Free Agents je Position, also rund
  300 Anfragen je Tag, nicht stündlich.
- In die App nur **Schlagzeile, Datum und Link**, nie der Text. Das ist das Muster von Nachrichten-Aggregatoren; ein
  Restrisiko bei ESPNs Nutzungsbedingungen bleibt, kleiner als bei den Outlook-Texten. Stephan entscheidet.
- **FantasyPros nur als Link:** keine API, das Auslesen der Seite verbieten deren Bedingungen. Rotoworld/NBC ebenso,
  sofern der Probe-Lauf keinen offenen RSS-Feed findet.

**Empfehlung:** Stufe 1 in Session 7 mit dem Spieler-Tab bauen, Stufe 2 nach dem Probe-Lauf entscheiden.
