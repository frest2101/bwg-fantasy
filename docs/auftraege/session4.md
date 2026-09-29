# Auftrag Session 4 – App (Baustein 4) und Methodik-Umbau (Entwurf Claude, Rückfragen beantwortet Stephan 29.09.2026)

Grundlage:
- CLAUDE.md und `docs/auftraege/session4_vorbereitung.md` (Beschlüsse Stephan vom 28.09.)
- Todoist-Aufgabe „Claude Code – Session 4“
- vier unabhängige Analysen vom 29.09.: Gewichte-Simulation, Bauplan, App-Aufbau, Deploy/Öffentlichkeit
- eine Gegenprüfung dieses Entwurfs: 59 Befunde, jeder von einem zweiten Agenten geprüft; 48 bestätigt und eingearbeitet

Berichte, Hilfsskripte und Prototypen liegen lokal unter `.lokal/session4/analysen_2909/`. Der Ordner ist gitignored, weil die Prüf-Attrappen echte Namen aus mTeam enthalten.

Erst die Rückfragen klären, dann bauen. Jeden Schritt in zwei, drei Sätzen erklären.

## Ziel
Am Ende der Session läuft App v1 öffentlich unter `https://frest2101.github.io/bwg-fantasy/`. Sie ersetzt Saison-Dashboard und Record-Book-Zahlen aus Notion:
- Tabellen und Score mit Reglern
- Power Ranking und Playoff-Simulation
- Spielplan und Record Book
- D/ST-Faktoren, Spieler mit Formkurve und ROS, Liga-Historie

Das Rechenwerk rechnet nach den Beschlüssen vom 28.09. und den Antworten auf die Rückfragen unten. Wochenabruf und Transaktions-Archiv halten die App ohne Rechner aktuell. Die Tests sind grün, und CLAUDE.md „Rechenregeln“ ist nachgezogen.

Damit sind zwei der drei Ablösekriterien der Routine „Wochenimport (Di)“ erfüllt: Die App zeigt Tabellen, Record Book und Spielplan, und die D/ST-Faktoren rechnet das Repo. Das dritte Kriterium (wer den Power-Ranking-Text schreibt) klärt Frage 3.

## Befund 29.09. (00:00 MESZ, nur lesend)
- **W3:**
  - Der Wochenabruf läuft erst heute um 08:30 UTC (10:30 MESZ), das MNF von W3 heute Nacht.
  - `w03/` hat nur die vier Kern-Views von gestern (nicht final).
  - `ros.json`, `mStandings.json` und der Spielerpool W3 entstehen erst mit diesem Lauf. ROS, Ersatzniveau, Kader-Projektion und die Projektion im Power Ranking lassen sich deshalb erst danach an echten Daten prüfen.
- **Repo:** `main` = `dfd1e86`, 156 Tests grün (Python 3.13.15).
- **GitHub:**
  - Pages ist aus (`has_pages: false`, API 404), es gibt keine Environment und keine Secrets. Die Standardrechte der Workflows stehen auf `read`.
  - Aktuelle Releases: `upload-pages-artifact` v5.0.0, `deploy-pages` v5.0.1, `checkout` v7.0.1, `setup-python` v7.0.0.
  - Bei `workflow_run` ist `GITHUB_SHA` der neueste Stand von `main`, also mit dem Bot-Commit. Der `head_sha` des auslösenden Laufs wäre der Stand davor (belegt: Lauf 36488744399, head `85183ff`, Commit `dfd1e86`). Deshalb `checkout` ohne `ref`.
- **D/ST:**
  - Die alte Formel reproduziert `referenz_dst.md` (LV exakt, sonst ≤ 0,001).
  - ESPNs `positionalRatings` stimmt nach W2 32/32 mit dem eigenen „Off. zugelassen 2026“ überein. Die nachgeholte W1-Datei trägt schon den Stand W2.
  - Neue Formel nach W2: LV 1,200 · ATL 1,181 · SF 0,812 · CAR 0,994.
- **Spieler:**
  - W1 hat 665 Ist-Einträge, davon 498 mit `stats["210"] == 1`. Kein Eintrag ohne 210 hat Punkte ≠ 0.
  - Den Verletzungsstatus trägt `player.injuryStatus`, in `kona_player_info` und in `mRoster` (`playerPoolEntry.player`), jeweils als Stand des Abrufs. Nur `entry.injuryStatus` in `mRoster` steht immer auf „NORMAL“.
- **Power Ranking nach W2** (Vorjahres-Prior, noch ohne Projektion): σ gepoolt 36,5; μ von 235,8 (Asse's) bis 178,9 (TeamTy); Σ Eᵢ = 5.
- **Playoff-Simulation:** 10 000 Läufe dauern in reinem Python 0,44 s. Mit festem Seed ist das Ergebnis byte-gleich.
- **Transaktions-Archiv:** Der bisher einzige Trade steht nur als `TRADE_ACCEPT` ohne `items`, `status` und `processDate` im Archiv. Der zugehörige Vorschlag fehlt.
- **App-Daten** (Prototypen aus echten Daten):
  - Erstaufruf (manifest, teams, schedule) nach W2 ≈ 4 KB gzip, bis W14 ≈ 5–9 KB (Ziel < 20 KB).
  - `players.json` lädt erst mit dem Tab (≈ 15–45 KB gzip).
  - `claude.json` ≈ 20 KB roh (Ziel < 50 KB).
- **Öffentlichkeit:**
  - In den Rohdaten stehen Felder, die nie in die App dürfen: `members`, `owners` und `primaryOwner` (mTeam), `memberId` (Transaktionen), `outlooks` und `seasonOutlook` (ESPN-Texte).
  - Ein Prüfskript-Prototyp erkennt alle diese Testfälle, auch einen eingeschmuggelten vollen Namen. Bei 1050 NFL-Spielernamen gibt es keinen Fehlalarm.

## Die 15 Gewichtspunkte im Stärke-Profil (Frage 1)
**Vorab:** Der Score teilt durch Σ Gewichte. Win auf 0 zu setzen und sonst nichts zu ändern, ist deshalb dasselbe wie eine proportionale Umverteilung (Option A). Die Frage ist also, ob sich das Verhältnis verschieben soll.

**Methode:**
- 10 000 simulierte Saisons mit dem echten Spielplan 2026 und den gemessenen Streuungen (σ ≈ 35 je Woche, echte Stärkeunterschiede τ ≈ 17,5).
- Gemessen wird, wie gut der Score die **wahre** Stärke der Teams trifft (Rangkorrelation, 1 = perfekt; n = gespielte Wochen).
- Alle Optionen sind mit z-Normierung gerechnet.
- Sensitivität über 9 Szenarien: schwächere oder bessere ESPN-Projektion, mehr oder weniger echtes Coaching-Können, k von 3 bis 6. Das ergibt mit je 5 Zeitpunkten 45 Vergleiche.

| Option | PF · All-Play · Win · Coaching · Kader · Floor · Form | n = 2 | n = 4 | n = 10 | mind. so gut wie A (von 45) |
|---|---|---|---|---|---|
| heute | 30 · 25 · 15 · 10 · 10 · 10 · 0 | 0,531 | 0,647 | 0,779 | 0 |
| A proportional | 30 · 25 · 0 · 10 · 10 · 10 · 0 | 0,541 | 0,655 | 0,784 | – |
| **B Kader +15** | **30 · 25 · 0 · 10 · 25 · 10 · 0** | **0,597** | **0,695** | **0,801** | **43** |
| F Kader +10, All-Play +5 | 30 · 30 · 0 · 10 · 20 · 10 · 0 | 0,577 | 0,682 | 0,797 | 44 |
| E Kader +10, Coaching +5 | 30 · 25 · 0 · 15 · 20 · 10 · 0 | 0,570 | 0,674 | 0,788 | 41 |
| C Coaching +15 | 30 · 25 · 0 · 25 · 10 · 10 · 0 | 0,505 | 0,618 | 0,744 | 5 |
| Floor +15 | 30 · 25 · 0 · 10 · 10 · 25 · 0 | 0,534 | 0,649 | 0,776 | 0 |
| zum Vergleich: Power Ranking μ | – | 0,664 | 0,722 | 0,809 | – |

**Lesart:**
- **Kein Mehrwert durch mehr Punkte-Gewicht:** PF, All-Play, Floor und Form messen fast dasselbe. Mehr Gewicht auf PF, All-Play oder Form bringt ±0.
- **Coaching und Floor verschlechtern:** Coaching schwankt stark und ist als dauerhaftes Können nicht belegt. Floor ist die eine schlechteste Woche.
- **Kader-Projektion ist die einzige neue Information:** Sie bildet den Kader heute ab, mit Verletzungen und Byes, unabhängig vom Wochenglück. B ist früh in der Saison so viel wert wie zusätzliche Spielwochen: bei n = 4 so gut wie A nach 5,3 Wochen. Der Vorsprung ist moderat. In einer einzelnen echten Saison kann der Zufall ihn überdecken.
- **Wirkung nach W2:** B tauscht nur gloane und Dynamo (4 ↔ 5). Ab W3 ersetzt die Kader-Projektion das Kader-Potenzial, dann können sich weitere Ränge verschieben.
- **Rollenteilung mit dem Power Ranking:** B ordnet die Teams sehr ähnlich wie μ (Rangkorrelation 0,95). Nach W2 stehen trotzdem 5 von 10 Teams einen bis zwei Plätze anders. Das Power Ranking ist die **Prognose** in Punkten, ihr Projektionsanteil fällt mit jeder Woche. Der Score ist die **Zerlegung**: feste Gewichte, dazu Coaching und Floor, die μ nicht enthält. Den rein rückblickenden Blick liefert weiter das Profil Verdienst.

## Umfang
1. **Rechenwerk in Modulen.** `compute.py` bleibt der einzige Einstieg der Action. Neu kommen reine Funktionen mit eigenen Tests:
   - `rawdata.py`: lädt jede Rohdatei einmal und verdichtet je Woche. Bis W14 lägen sonst ≈ 270 MB geparste Rohdaten im Speicher.
   - `lineup.py`: `optimal_points`, unverändert verschoben.
   - `records.py`: H2H, Rekorde RS und Playoffs getrennt, Serien, Positions-Breakdown nach `defaultPositionId` mit Slot-Umschalter, Transaktionsliste.
   - `players.py`: Spiele über Stat 210, Kennzahlen, Trend mit Rauschschwelle, ROS aus `ros.json`, Ersatzniveau, ROS über Ersatz, Kader-Projektion je Restwoche.
   - `dst.py`: „Off. zugelassen“, Faktor F nach neuer Formel (alte als Test), Restspielplan, nächste 3, SoS W15–17, Auslöser, Faktorreihe je Woche.
   - `powerranking.py`: σ gepoolt, P, μ, Eᵢ, Rang und Trend, Playoff-Simulation mit Seeding-Schalter. Ausgabe je Seeding: Playoff-, Division-, Bye-% und erwartete Restsiege. Die Restsiege ersetzen den Team-Restspielplan (Beschluss).
   - `history.py`: All-Time mit W % und Ø PF+, Champions, Ära, abgeleitete Rekorde.
   - `app_export.py`: App-Dateien nach einer Positivliste von Feldern, deterministisch.
   - In `compute.py` selbst:
     - Unentschieden 0,5 (Win %, All-Play, Luck, Ränge)
     - z-Score als Standard
     - neues Stärke-Profil
     - Form Δ mit ±-Band σ·√(1/3 − 1/n); das Band gibt es erst ab n ≥ 4, vorher ist es leer
     - Der Team-Restspielplan entfällt.
   - Jede Wochenreihe wird bei jedem Lauf neu aus den Rohdaten gerechnet; es gibt keinen gespeicherten Zwischenstand. `--through N` nimmt nie einen jüngeren Stand als Woche N.
   - `data/season_2026.json` bleibt die interne Gesamtausgabe.
2. **App-Daten `app/data/`,** von den Actions committet (Frage 4):
   - `manifest.json`: Schema, Woche, Datenstand, Hash je Datei; ohne Zeitstempel, damit nur echte Änderungen einen Commit auslösen.
   - `teams.json`, `schedule.json`: Erstaufruf.
   - `players.json`, `dst.json`, `history.json`, `transactions.json`: laden erst beim Öffnen ihres Bereichs.
   - `claude.json`: kompakte Datei unter 50 KB für Claude-Sessions unterwegs.
   - Zahlen im JSON mit Punkt als Dezimalzeichen, Stellen nach Frage 11 (a). Das Komma setzt erst die App.
3. **App `app/`:**
   - Aufbau: `index.html`, `style.css`, `app.js`. Kein Framework, kein Build-Schritt, Diagramme als Inline-SVG ohne Bibliothek.
   - Datenschutz: keine Drittanbieter-Requests, also keine Webfonts, kein CDN, keine Analytics, keine ESPN-Bilder.
   - Mobil zuerst, Hell/Dunkel.
   - Bereiche:
     - **Tabelle:** Gesamt, Division, All-Play/Luck, Punkte, Coaching (mit Kader-Potenzial), Ausblick mit Playoff-, Division-, Bye-% und erwarteten Restsiegen.
     - **Ranking:** Power Ranking; Score mit Profil-Chips, sieben Reglern und Normierungsumschalter. Angezeigt wird der Score als 50 + 10·z mit einer Stelle, dazu ein Redundanz-Hinweis im i-Knopf.
     - **Spielplan:** je Woche Kacheln, Paarungen, Wochentabelle, Top-Scorer; dazu die Saisonwochen.
     - **Spieler:** Liste, Detail mit Formkurve, D/ST-Faktoren.
     - **Rekorde:** Saison RS und Playoffs, Positionen, H2H, All-Time, Champions.
     - **Teamseite** `#team/N` und **Lesart** `#lesart`: Glossar mit allen Definitionen, i-Knöpfe statt Maus-Tooltips.
   - Deep Links per Hash (`#tabelle/coaching`, `#spieler/<id>`, `#ranking/score?w=…`).
   - Der Browser rechnet nur den Score aus den vorberechneten Normwerten neu. Alle übrigen Zahlen rechnet Python, und sie werden getestet.
4. **Veröffentlichung:**
   - Neuer Workflow `.github/workflows/pages.yml`:
     - zwei Jobs; `build` darf nur lesen, `deploy` bekommt `pages: write` und `id-token: write`
     - Auslöser: Push auf `app/**`, `workflow_run` nach Wochenabruf und Transaktions-Archiv (nur bei Erfolg und nur aus diesem Repo), `workflow_dispatch`
     - hochgeladen wird nur `app/`, nie Rohdaten
   - Cache-Busting:
     - `manifest.json` wird immer frisch geladen, jede Datendatei mit `?v=<Hash>`.
     - `app.js` und `style.css` stehen in `index.html` mit `?v=<Build-SHA>`; `pages.yml` setzt den SHA ein.
     - Ist das Manifest-Schema neuer als die App, zeigt sie „Neue Version – bitte neu laden“.
5. **Öffentlichkeits-Check:**
   - `scripts/check_public.py` (nur Standardbibliothek, lauffähig mit Python 3.12) und `tests/test_oeffentlich.py`.
   - Geprüft wird: keine verbotenen Schlüssel (`members`, `owners`, `memberId`, `outlooks`, …), keine vollen Namen oder Anzeigenamen der Manager, keine überlangen Texte, nur erlaubte Dateitypen.
   - Die Namen liest der Check zur Laufzeit aus mTeam; im Test-Code steht kein Name. Gefundene Namen gibt er nie aus, nur Datei und Art des Fundes, weil Action-Logs öffentlich sind.
   - Er läuft vor jedem Commit (pytest in beiden Actions und lokal) und noch einmal in `pages.yml`.
6. **Actions:**
   - `wochenabruf.yml`: Rohdaten immer committen, die abgeleiteten Dateien (`season_2026.json`, `app/data`) nur bei grünem Rechenwerk und grünen Tests (Frage 11 e). So gehen `ros.json` und die Dienstags-Stände nicht verloren, wenn das Rechenwerk scheitert.
   - `transaktionen.yml`: dazu `compute.py` und `pytest`, damit die Transaktionsliste in der App täglich stimmt.
7. **Tests:**
   - neu: `test_records`, `test_dst`, `test_players`, `test_powerranking`, `test_app_export`, `test_oeffentlich`
   - `test_compute` und `test_history` werden erweitert
   - Referenzen:
     - `referenz_w1-w2.md` bleibt unverändert. Score-Probe und G1-„Rang Score“ werden mit den eingefrorenen W2-Gewichten (Min–Max) geprüft, die G1-Spalte Restspielplan nicht mehr.
     - `referenz_dst.md`: alte Formel als Test der Datenkette.
     - ESPN `positionalRatings`: 32/32, nur für N ≥ 2; das Feld `average` nicht verwenden.
     - `referenz_historie.md`
   - `test_app_export` rechnet die Browserformel aus den gerundeten Normwerten nach und vergleicht mit dem Python-Score (± 0,05, gleicher Rang).
   - Invarianten: Starter-Summe = PF, Σ All-Play 45 je Woche, Σ Positionen = PF, Σ Eᵢ = 5. Für die Simulation: Σ Playoff-% = 600, Σ Division-% = 200, Σ Bye-% = 200, Σ erwartete Restsiege = Zahl der offenen Spiele.
8. **Doku:**
   - CLAUDE.md: „Rechenregeln“ mit allen Beschlüssen und Antworten (auch D/ST-Methodik, ROS, Stat 210, σ-Formel), dazu Struktur, Takt, „Gelernt“.
   - Checkliste „Saisonwechsel“ ergänzen: Saison 2026 in `data/history` übernehmen (Prior des Folgejahres), D/ST-Grundlage des Vorjahrs neu holen, neue `data/redaktion/power_ranking_<Saison>.csv`.
   - README: App-URL, lokale Vorschau.
   - Nachtrag in diesem Auftrag.

## Schritte
**Wichtig:**
- Code, der das Rechenwerk ändert, wird erst **nach** dem Wochenabruf W3 (heute 10:30 MESZ) gepusht. Der erste Lauf soll mit bekanntem Code auf die ungesehene `ros.json` treffen.
- Lokale Läufe von `compute.py` in Teil A ändern die getrackte `data/season_2026.json`, und der W3-Lauf committet dieselbe Datei. Vor dem `git pull` in B1 setze ich die lokale Fassung deshalb zurück. Sie wird danach ohnehin neu gerechnet; weil das ein Verwerfen ist, frage ich einmal vorher. `app/data/` ist bis dahin untracked und stört nicht.

1. Rückfragen klären (unten).
2. **Teil A: sofort, mit W1–W2 (`--through 2`)**
   - A1 `rawdata.py` und `lineup.py`, `compute.py` darauf umstellen; die 156 Tests bleiben unverändert grün.
   - A2 Unentschieden, z-Standard, Stärke-Profil (Frage 1), Restspielplan raus, Tests anpassen.
   - A3 `records.py` · A4 `dst.py` · A5 `history.py` · A6 `powerranking.py` mit Vorjahres-Prior · A7 `players.py` Teil 1 (Wochenreihen, Kennzahlen, Trend).
   - A8 `app_export.py` und der Öffentlichkeits-Check.
   - A9 App-Oberfläche. Das ist der größte Schritt; lokale Vorschau im Browser-Fenster der App. `app/.gitkeep` löschen, sobald `index.html` existiert, denn der Check lehnt Punkt-Dateien ab.
   - A10 `pages.yml` und die Anpassungen an Wochenabruf und Transaktions-Archiv.
3. **Teil B: nach dem Wochenabruf W3**
   - B1 Lauf prüfen (`gh run list`, Commit „bis W3“), dann `git pull`. Die Felder in `w03/ros.json`, `w03/kona_player_info.json` und `w03/mStandings.json` am JSON verifizieren.
   - B1 ebenso prüfen: Wie projiziert ESPN verletzte Spieler (OUT/IR) über die Restwochen? Davon hängt Frage 8 ab.
   - B1 Abschluss: Todoist-Aufgabe „Wochenabruf W3 prüfen“ mit Kommentar abhaken.
   - B2 ROS, Restspiele, Ersatzniveau, ROS über Ersatz, ROS-Rang.
   - B3 Kader-Projektion je Restwoche; damit „Kader“ im Score, P im Power Ranking und die Wochenabweichungen der Simulation.
   - B4 Vergleich mit der ESPN-Simulation (`mStandings`); `players.json` und `claude.json` mit ROS.
4. **Unabhängige Prüfung** durch getrennte Prüf-Agenten: Rechenlogik gegen die Beschlüsse, App (Bedienung, Barrierefreiheit, Handy), Öffentlichkeit und Workflows. Jeden Befund prüft ein zweiter Agent und versucht, ihn zu widerlegen.
5. **Freigabe und Veröffentlichung:**
   - Stephan gibt den Diff frei. Er umfasst Code, Tests, CLAUDE.md „Rechenregeln“ sowie die nach dem Pull neu gerechneten Dateien `data/season_2026.json` und `app/data/`.
   - Danach: gh-Schritte aus Frage 6, Commit, Push, erster Deploy.
   - Prüfung der Seite: HTTP 200, Manifest, Handy-Ansicht.
   - Erst nach je einem grünen Lauf der drei gepinnten Workflows folgt die Härtung aus Frage 5.
6. **Abschluss:**
   - Wochenabruf per `workflow_dispatch` als Gegenprobe der neuen Action: erwartet grün und kein neuer Commit.
   - Erste Power-Ranking-Kernsätze für W3 nach Frage 3, zur Freigabe.
   - CLAUDE.md „Gelernt“ mit Freigabe.
   - Todoist-Aufgaben mit Kommentar abhaken.
   - Haken Baustein 4 und Sessionvermerk im Umbau-Plan (nach Freigabe des Textes).

## Rückfragen vor dem Bauen (Vorschlag in Klammern)
**Hauptfragen:**
1. **15 Gewichtspunkte im Stärke-Profil:** (B: alle 15 auf die Kader-Projektion, also PF 30 · All-Play 25 · Win 0 · Coaching 10 · Kader 25 · Floor 10 · Form 0. Zweitbeste und robusteste Wahl ist F mit PF 30 · All-Play 30 · Win 0 · Coaching 10 · Kader 20 · Floor 10 · Form 0; F passt, wenn der Score etwas mehr „Ergebnis“ und weniger „ESPN“ sein soll.)
   - Die Gewichte von Verdienst und Form bleiben.
   - Die Kennzahl Kader wechselt ab W3 in **allen** Profilen auf die Kader-Projektion. Damit enthält auch das Profil Form 10 Punkte ESPN-Projektion; Verdienst (Kader 0) bleibt rein rückblickend.
   - Kader-Potenzial bleibt als Spalte unter Coaching sichtbar.
   - Alternative: Das Profil Form behält Kader-Potenzial. Das kostet eine achte Kennzahl.
2. **Umfang dieser Session:** (Teil A und Teil B, also App v1 mit Spieler-Tab und ROS.)
   - Wird es zu lang, wird nach Teil A veröffentlicht, denn Teil A allein erfüllt die Ablösekriterien 1 und 2. Teil B folgt dann als Session 5.
   - In diesem Rückfall trägt das Power Ranking das Kennzeichen „P aus Vorjahr“, ohne Trend und ohne Kernsätze. Mit Teil B wird W3 mit der Projektion neu gerechnet, und die Ränge können sich noch ändern.
3. **Redaktionelle Texte: Power-Ranking-Kernsätze und D/ST-„Kontext Warum“.** Beide schreibt heute die Cloud-Routine bzw. Claude in Notion. Nach dem Pausieren der Routine darf Claude Code ohne neue Ausnahme in „Gelernt“ nicht in Notion schreiben.
   - (Kernsätze ins Repo, „Kontext Warum“ entfällt vorerst.)
   - **Kernsätze:**
     - Rang, μ, erwartete All-Play-Quote und Trend rechnet das Repo.
     - Du startest dienstags nach dem Wochenabruf eine Claude-Code-Session am Rechner. Claude entwirft die Kernsätze aus `claude.json` und der App, nur mit Teamnamen, ohne Manager-Namen und ohne Absichten; du gibst frei.
     - Danach folgen Eintrag in `data/redaktion/power_ranking_2026.csv` (woche, slot, kernsatz), `git pull`, Rechnen, pytest mit Check, ein Commit, Push. Im Repo steht nur freigegebener Text; ohne Freigabe zeigt die App „folgt“.
     - Die App-Wertung beginnt mit W3; die ersten Kernsätze entstehen am Ende dieser Session. W0–W2 bleiben in Notion, weil sie anders zustande kamen. Der erste Trendpfeil kommt W3 → W4, weil erst dann beide Wochen die Projektion als Grundlage haben.
     - Damit entfällt der Power-Ranking-Entwurf der Routine.
   - **„Kontext Warum“:** Die App zeigt in v1 die Auslöser ohne Kontext. Mit dem Pausieren der Routine endet die Pflege in Notion.
   - Alternative (b): eine neue Notion-Ausnahme in „Gelernt“, nach der Claude den Kontext in der Dienstags-Session nach Freigabe einträgt.
   - Alternative (c): keine Kernsätze in App v1; die Routine schreibt den Power-Ranking-Entwurf weiter nach Notion. Dann ist das dritte Ablösekriterium noch nicht erfüllt.

**Voreinstellungen (Sammelfreigabe möglich, Einspruch einzeln):**

4. **App-Daten:** (Die Actions committen `app/data/`.)
   - Jede Änderung an öffentlichen Daten ist im Diff prüfbar, und Tests und Check laufen vor dem Commit.
   - `pages.yml` braucht kein setup-python und kein pip; der Check läuft mit dem System-Python des Runners.
   - Claude unterwegs erreicht `claude.json` über `raw.githubusercontent.com`.
   - Die Alternative, die Daten erst beim Deploy zu erzeugen, verliert all das.
5. **Actions absichern:** (Alle drei Workflows auf Commit-SHA mit Versionskommentar pinnen, `.github/dependabot.yml` für Actions monatlich in einem PR.)
   - Nach dem ersten grünen Lauf setzt Claude per gh: nur GitHub-eigene Actions zulassen und SHA-Pinning erzwingen. Tags lassen sich umhängen, SHAs nicht.
   - Nachteil: Updates und Sicherheitskorrekturen kommen nur noch über den monatlichen Dependabot-PR. Du gibst ihn frei, Claude liest vorher die Release Notes und merged per gh.
6. **gh-Schritte nach der Diff-Freigabe:** (Claude führt direkt vor dem ersten Push per gh aus:)
   - Pages mit `build_type=workflow` einschalten
   - Environment `github-pages` nur für `main` zulassen
   - ersten Deploy beobachten
   - Repo-Link auf die Seite setzen
   - Im Browser musst du bei GitHub nichts tun.
7. **Darstellung:**
   - Startansicht ist die Tabelle.
   - Eigene Kürzel ACB · HJS · 4DS · CRN · TTY · SAM · RTZ · GLS · DYN · SGK, weil die ESPN-Kürzel uneinheitlich sind.
   - Keine ESPN-Logos (Fremdbilder, jeder Aufruf ginge an ESPN) und keine Manager-Namen.
   - `noindex`, damit die Seite nicht in Suchmaschinen auftaucht. Das schützt nichts, macht die Seite aber schwerer auffindbar.
8. **Simulation und Power Ranking:**
   - Seeding-Standard ESPN (W, dann PF) mit Schalter „Divisionssieger auf 1–2“. Das war Tradition bis 2025 und ist bei ESPN 2026 unbelegt.
   - σ gepoolt mit Startwert: σ² = (Σ Quadratsummen innerhalb der Teams + 20·35²)/(Σ(nᵢ − 1) + 20). Nach W2 ergibt das 35,5 statt 36,5; der Anteil des Startwerts fällt von 67 % nach W2 auf 13 % nach W14.
   - Der Ligafaktor (Σ PF/Σ Starter-Projektion, nach W2 0,977) wird laufend gemessen, für die Kader-Projektion und für P. Für die Kader-Projektion ist das beschlossen. Für P ist es eine **Änderung** gegenüber dem Beschluss „Pᵢ = 0,98 × …“, damit beide gleich rechnen.
   - Spieler mit OUT oder IR zählen in der nächsten Woche 0, danach gilt die ESPN-Wochenprojektion. Das beruht auf einer Annahme: Belegt ist nur, dass ESPNs Saisonprojektion für OUT-Spieler > 0 bleibt. Geprüft wird in B1 an `w03/ros.json`; passt es nicht, lege ich die Regel neu vor.
9. **D/ST-Auslöser:**
   - Auslöser 1 bleibt (|ΔF| ≥ 0,10).
   - Auslöser 2 wird z = (Ø Z der letzten 3 Spiele − Z26)/(0,55 · LS26 · √(1/3 − 1/n)), Auslöser bei |z| ≥ 2, erst ab n ≥ 4 (vorher ist die Formel nicht definiert). Der Beschluss nennt zwei Varianten, Schwelle oder die drei größten z. Vorschlag: die Schwelle als Auslöser, die drei größten |z| nur als „beobachten“.
   - Auslöser 3 (Rangsprung ≥ 5, aus Notion) bleibt.
10. **Transaktionen in der App:**
    - Gezeigt werden nur ausgeführte Moves (`status == EXECUTED`) und angenommene Trades (`TRADE_ACCEPT`).
    - Ein Trade erscheint in v1 als „Trade angenommen (Team, Datum)“ ohne Spieler, weil das Archiv keinen Inhalt dazu hat. Der Inhalt folgt mit Record Book §8.
    - Aufstellungswechsel erscheinen nur als Zahl je Team.
    - Keine gescheiterten Claims und keine Trade-Vorschläge. Die Rohdaten bleiben unverändert.
11. **Kleinkram:**
    - (a) **Stellen im JSON:** Punkte 2; `norm.z` 3, weil bei 2 Stellen die Score-Anzeige nach W2 in 1–3 von 10 Teams um 0,1 abweicht; `norm.minmax` 2; Rangpunkte ganzzahlig; F, r und E 3.
    - (a) **Anzeige:** Quoten mit 1 Stelle, Playoff-% ganzzahlig („< 1 %“, „> 99 %“). Die Regel „zwei Stellen“ aus CLAUDE.md gilt weiter für Punkte.
    - (b) Die Positions-CV für die Trendschwelle ist eine feste Tabelle (QB 0,45 · RB 0,60 · WR 0,75 · TE 0,75 · K 0,55 · D/ST 0,55), am Saisonende neu gemessen.
    - (c) **Abweichung vom Beschluss** (beide Doppelwerte kennzeichnen): 338,43 liegt nicht im Repo und kommt erst mit den kuratierten Rekorden. Bis dahin zeigt v1 bei 313,33 „verifiziert (Screenshot)“ und den Hinweis „ein höherer, unverifizierter Wert ist bekannt“.
    - (d) Verbindlich stehen die Definitionen in CLAUDE.md „Rechenregeln“; die App-Lesart ist die öffentliche Kurzfassung. Die Notion-Lesart verweist künftig auf die App; den Text dafür gibt Stephan frei.
    - (e) Rohdaten auch bei rotem Rechenwerk committen, abgeleitete Dateien nur bei Grün.

**Nur du** (Owner-Einstellungen und Handgriffe, die Claude nicht kann):
- **Netzwerk-Freigabe für Claude unterwegs:**
  - In claude.ai unter Organization settings › Capabilities › „Additional allowed domains“ `raw.githubusercontent.com` und `frest2101.github.io` ergänzen. Das gilt für alle Mitglieder der Organisation. Die Liste nicht auf „All domains“ stellen.
  - Für die Cloud-Umgebung (auch die der laufenden Routinen) unter „Network access: Custom“ `lm-api-reads.fantasy.espn.com` und `frest2101.github.io` eintragen. Bestehende Einträge nicht entfernen, und „Also include default list of common package managers“ anhaken; darüber bleiben `raw.githubusercontent.com` und pip erreichbar. Die laufenden Routinen brauchen weiter ESPN.
  - Test nach dem ersten Deploy: Eine neue Unterhaltung liest `claude.json`. Vorher gilt 404 mit `server: GitHub.com` als erreichbar, 403 oder `host_not_allowed` heißt „nicht freigegeben“.
- **Dienstags** nach dem Wochenabruf die Claude-Code-Session für die Kernsätze starten (falls Frage 3 wie vorgeschlagen).
- **Pausieren der Routinen:**
  - „Wochenimport (Di)“, sobald alle drei Ablösekriterien erfüllt sind
  - „Transaktions-Sync“, nachdem Claude um den 06.10. das Archiv lesend mit Notion abgeglichen hat

**Antwort Stephan 29.09.2026:** alles wie vorgeschlagen.
1. Option B: Stärke = PF 30 · All-Play 25 · Win 0 · Coaching 10 · Kader 25 · Floor 10 · Form 0. Kader wechselt ab W3 in allen Profilen auf die Kader-Projektion.
2. Teil A und Teil B in dieser Session.
3. Kernsätze ins Repo (`data/redaktion/power_ranking_2026.csv`, nur freigegeben, Dienstags-Session). „Kontext Warum“ entfällt vorerst, die App zeigt nur die Auslöser.
4.–11. Sammelfreigabe wie vorgeschlagen, inklusive der gekennzeichneten Abweichungen vom Beschluss (Ligafaktor für P gemessen, D/ST-Auslöser 2 als Schwelle, 338,43 später).

## Nachtrag 29.09.2026: Bau und Prüfung Teil A
**Bau:**
- **Aufteilung:** Das Fundament (`rawdata`, `lineup`, `zahlen`) und der Umbau von `compute.py` kommen von Claude. Die Module `records`, `dst`, `history`, `powerranking` und `players` haben fünf parallele Agenten gebaut, je mit einem Prüfer. Die Prüfer haben Testlücken per absichtlich eingebautem Fehler gefunden und geschlossen. Rechenfehler fanden sie nicht.
- **App:** Ein Agent hat die Oberfläche gegen den Datenvertrag `docs/app_daten.md` gebaut, ein zweiter hat sie im Browser geprüft (40 Routen, Handy und Desktop, hell und dunkel).
- **Nachgerechnet:** σ nach W2 35,52; Ligafaktor 0,977; neue D/ST-Faktoren wie im Befund. Die alte D/ST-Formel trifft `referenz_dst.md`, und ESPNs `positionalRatings` stimmt 32/32 mit dem eigenen Wert.
- **Laufzeit:** Das ganze Rechenwerk samt Simulation und Export braucht 1,2 s.
- **Größen:** Der Erstaufruf der Daten hat 9 KB gzip, `claude.json` 23 KB.

**Unabhängige Schlussprüfung** (drei Blickwinkel, jeder Befund gegengeprüft): 32 Befunde, 29 bestätigt oder teilweise bestätigt, alle eingearbeitet außer den unten genannten.
- **Hoch (zwei Prüfer unabhängig):**
  - **Befund:** Waren Rechenwerk grün und Tests rot, lagen die abgeleiteten Dateien ungestaged herum. `git pull --rebase` brach dann ab, und die Rohdaten des Dienstags (ROS-Auszug, mStandings) wären verloren gegangen.
  - **Behebung:** In beiden Actions `git pull --rebase --autostash`, in einem Test-Repo nachgewiesen. Der Wochenabruf rechnet und sichert jetzt auch nach einem Teilfehler beim Abruf.
- **Mittel:**
  - **Zeilenenden:** `.gitattributes` hält generierte JSON-Dateien auf LF (Windows-Pull).
  - **Spielplan:** Er nimmt Ergebnisse aus derselben Wochendatei wie die Tabelle; eine Stat-Korrektur im jüngeren Spielplan meldet `compute.py` als Warnung.
  - **Kader-Projektion:** Nach W14 rechnet sie über W15–17, damit die Schlusstabelle nicht auf den Vorjahres-Prior zurückfällt.
  - **Vorsaison:** Nach dem Saisonwechsel endet `compute.py` grün, bis W1 final ist.
  - **Playoff-Wochen:** Mit Bye gelten sie nicht dauerhaft als „läuft“.
  - **D/ST:** Das Auslöser-Fähnchen gehört an den Gegner (die Offense), nicht an die D/ST.
- **Niedrig:**
  - Anteile mit 1 Stelle gegen doppeltes Runden, Stellenregel auch in `claude.json`, genau 20 Free Agents je Position.
  - Test für Manager-Namen in `data/redaktion/`.
  - Lesart-Texte (Trendpfeil, Siegchance, D/ST-Rang, Redundanz), E in Prozent und weitere Kleinigkeiten in der App.
- **Bewusst nicht geändert:**
  - `pages.yml` deployt nach jedem grünen Datenlauf, auch ohne Änderung (kostenlos).
  - `persist-credentials: false` und Dependabot-Alerts für pip bleiben eine spätere Härtung.
  - `teams()` liest Namen, Divisionen, Waiver-Prio und Moves bewusst immer aus dem jüngsten mTeam, auch bei `--through`.

## Nachtrag 29.09.2026: Teil B mit den echten W3-Daten
- **W3 geholt:** W3 war um 09:30 MESZ bei ESPN final. Auf Stephans Wunsch hat Claude den Wochenabruf per `workflow_dispatch` gestartet, statt auf 10:30 zu warten, und W3 nicht lokal geholt. Lauf 36537064098 grün, Commit `71a32e0` („Rechenwerk bis W3“) mit `ros.json`, `mStandings.json` und dem Spielerpool W3.
- **Annahmen am JSON geprüft:**
  - `ros.json` hat nach W3 die Wochen 4–17 für 636 Spieler.
  - ESPN projiziert 31 von 32 D/ST auch in der Bye-Woche; Bye = 0 aus dem Spielplan ist also nötig.
  - Verletzte: 17 OUT-Spieler haben für W4 trotzdem Punkte projiziert; die Regel „OUT/IR in N+1 = 0“ (Frage 8) greift dort. Rückkehrer projiziert ESPN ab der Rückkehrwoche.
  - `mStandings` liefert `playoffPct` und `divisionWinPct`, wie angenommen.
- **ESPN-Ratings:** Die D/ST-Ratings in der Datei vom Dienstagmorgen tragen noch den Stand der Vorwoche (32/32 = eigenes Z26 nach W2). Der Test vergleicht deshalb mit N oder N−1.
- **Ergebnis nach W3:**
  - Kader-Projektion zwischen 191 und 217 Punkten; der Score nutzt sie, die Kennzahl heißt „Kader-Projektion ROS“.
  - Power Ranking mit P aus der Projektion, alle Trends „neu“ (der erste Pfeil kommt W3 → W4); der Vorwochenrang wird ohne gültigen Vergleich nicht gezeigt.
  - Die eigene Simulation ist entschiedener als die von ESPN (z. B. 4th Down 18 % gegen 46 % Playoff-Chance). Das ist Methodik; ESPN steht als Vergleich daneben.
- **Tests:** 361 grün, keiner übersprungen.

## Nachtrag 29.09.2026: Veröffentlichung
- **Freigabe und Veröffentlichung:** Stephan hat den Diff freigegeben (52 Dateien). Danach Pages eingeschaltet (`build_type=workflow`), die Environment `github-pages` auf `main` beschränkt, Commit `b78a38d`, Push. Der erste Deploy war grün. Die Live-Seite liefert HTTP 200, das Manifest nach W3 und den Build-SHA in `app.js`/`style.css`, `noindex` ist gesetzt, `claude.json` ist über raw.githubusercontent.com erreichbar.
- **Gegenprobe:** Wochenabruf von Hand, grün, 361 Tests auf Ubuntu, kein neuer Commit. Das Rechenwerk rechnet unter Windows und Linux byte-gleich, einschließlich der Simulation.
- **Fehler aus Baustein 3:** Direkt nach dem Periodenwechsel lässt ESPN die Liste der Transaktionen weg; das Archiv wertete das als Fehler (Lauf rot, Pages übersprungen). Behoben mit Freigabe Stephan (`c4f665d`), danach grün.
- **Härtung (Frage 5):** nur GitHub-eigene Actions, SHA-Pinning erzwungen; Pages und Wochenabruf laufen danach weiter grün.
- **Kernsätze W3:** von Stephan freigegeben (`3226396`), live in der App.
- **Ablösekriterien der Routine „Wochenimport (Di)“:** alle drei erfüllt; das Pausieren macht Stephan.

**Arbeitsweise:** Zwei Prüf-Agenten teilten sich eine Hilfsdatei im Scratchpad. Dadurch wurde `scripts/players.py` kurz überschrieben, vom zuständigen Prüfer aber byte-genau wiederhergestellt; die Tests laufen grün. Seitdem bekommt jeder Agent einen eigenen Scratchpad-Ordner.

## Nicht in dieser Session
- `mBoxscore` statt `mRoster` (−2,8 MB je Woche)
- kuratierte Rekorde, Trades vor 2026, Transaktions-Auswertungen (Record Book §8)
- Playoff-Bracket und Playoff-Rekorde aus W15–17 (Dezember)
- Live-Ansicht nach der Live-Regel
- ältere Spielerdaten über `leaguedefaults`
- Ex-ante-Aufstellungsqualität, Nutzungstrend, D/ST-Ersatzniveau je Woche, SRS-Bereinigung
- Notion-Rückbau-Texte (eigenes Freigabe-Paket)
- persönliche Sichten: nie in dieses Repo, später nur in einem eigenen privaten Repo mit Zugriffsschutz

## Danach
- Um den 06.10.:
  - Stat-Korrekturen prüfen: Hat sich W3 nach Dienstag geändert?
  - Transaktions-Archiv lesend mit Notion abgleichen, danach pausierst du „Transaktions-Sync“.
- Session 5: Teil B, falls er hier nicht fertig wird; sonst Record Book §8 (Transaktionen) und kuratierte Rekorde.
- Vor W15 (Dezember): Playoff-Bracket, dabei die Bye-Markierung der Playoff-Wochen an echten Daten prüfen.
