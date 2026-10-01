# Auftrag Session 9 – Keeper-Tab Stufe 3 (Marktwert) und Stufe 4 (Offseason, Draft-Position 2027)

Start in einer neuen lokalen Session (braucht `gh`, Netz und den Browser). Stufe 1 (Keeper-Bilanz) und Stufe 2
(Altersprofil) sind seit 01.10.2026 auf `main` und live (`scripts/keeper.py`, `scripts/nflverse.py`, `keeper.json`,
`app/js/v_keeper.js`). Grundlage: CLAUDE.md (Rechenregeln „Keeper-Bilanz“ und „Altersprofil“, Gelernt „Keeper-Tab“ und
„Marktwert“), `docs/app_daten.md` (`keeper.json`), die Beschlüsse unten. Beide Stufen sind freigegeben; gebaut wird
Stufe 3 zuerst und für sich gemerged, dann Stufe 4.

## Beschlüsse Stephan (01.10.2026)
**Stufe 3 – Marktwert (FantasyCalc):**
1. Keine Mail an FantasyCalc. Die API-Doku bittet darum, die Nutzungsbedingungen verlangen sie nicht; das Restrisiko
   (Zugang kann jederzeit ohne Ankündigung entzogen werden) trägt Stephan bewusst.
2. Gespeichert werden die Werte aller Spieler des ESPN-Pools, aber nur die Felder, die App und Claude-Projekt brauchen –
   nie die Rohantwort, keine Draft-Pick-Werte.
3. Ein Abruf je Tag (so wünscht es FantasyCalc), nicht bei jedem der 13 Tagesläufe.
4. Gesamtrangliste und Hilfe für Trades werden **Daten für das Claude-Projekt** (claude.ai, Projekt mit Notion), keine
   eigene Seite der App und kein eigener Trade-Rechner. Die App zeigt die Werte im Liga-Zusammenhang.
5. Pick-Werte von FantasyCalc werden nicht gezeigt (der BWG-Draft enthält neben Rookies alle nicht gehaltenen Veteranen).
6. Schon am Vormittag beschlossen: Marktwert je Spieler und die Team-Summe der zwölf wertvollsten als Zahl ohne Namen
   sind erlaubt; eine fertige Liste „die zwölf wertvollsten je Team“ kommt nicht in die App.

**Stufe 4 – Offseason und Draft-Position:**
1. Draft-Reihenfolge des Folgejahrs = umgekehrte Endplatzierung, fest, ohne Lotterie (Letzter hat Pick 1 in jeder der
   zwölf Runden, der Draft ist linear).
2. Endplatz: Plätze 1 und 2 aus dem Finale, je ein Spiel um Platz 3 und um Platz 5; für die Plätze 7–10 gilt das
   Ergebnis der ESPN-Trostrunde. (Stephans Satz lautete „je ein Spiel um Platz und Platz 5“ – als Platz 3 gelesen;
   steht seine Bestätigung beim Start der Session noch aus, zuerst nachfragen.)
3. Getauschte Picks stehen vorerst nicht in der App. Bisher gab es 2026 keinen Pick-Trade; kommt einer, zuerst prüfen,
   was ESPN dazu liefert.

## Geprüfte Fakten (Recherche 30.09., Gegenprüfung des Auftrags 01.10.2026; vor dem Bau kurz gegenlesen)
- **API:** `https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=2&numTeams=10&ppr=1`, ohne Schlüssel, JSON-Liste
  mit 420 Einträgen (396 Spieler QB/RB/WR/TE, 24 Picks), rund 330 KB. Dokumentierte Felder: `value`, `overallRank`,
  `positionRank`, `trend30Day`, `redraftValue`, `starter`, dazu `player` mit `id`, `name`, `position`, `espnId`
  (Text oder null: am 01.10. bei 3 Spielern und allen Picks leer – solche Einträge überspringen), `maybeTeam`,
  `maybeAge` … Nur dokumentierte Felder verwenden (`maybeTier`, `maybeTradeFrequency` u. a. sind undokumentiert).
  Dokumentiert unter `https://fantasycalc.com/api-docs`; andere Endpunkte sind verboten.
- **Tücken:** `overallRank` der Spieler zählt die Picks nicht mit (1 … 396, lückenlos und eindeutig; ein Pick trägt nur
  den Rang des nächsten Spielers) – als `rang` unverändert übernehmen, nicht neu zählen (67 Spieler teilen ihren Wert
  mit einem anderen, und vier Spieler der Liste fehlen im ESPN-Pool). `starter` ist immer false. `redraftValue` ist bei
  rund der Hälfte 0 oder leer. 32 Namen weichen von ESPN ab (18 bei Kaderspielern; meist ohne „Jr.“/„Sr.“/„III“, dazu
  „Marquise Brown“ statt „Hollywood Brown“) – in der App die ESPN-Namen zeigen, zugeordnet wird nur über `espnId`.
  K und D/ST haben keinen Wert.
- **Abdeckung:** alle Offense-Kaderspieler über `espnId` (201/201 am 30.09.), dazu rund 190 freie Spieler; der beste
  freie stand auf Gesamtrang 124. Im ESPN-Pool lagen am 01.10. 392 der 396 Spieler (3 ohne `espnId`, 1 nicht im Pool).
  Die Teamzahl im Aufruf ändert die Werte nur pauschal je Position (wenige Prozent).
- **Nutzungsbedingungen** (`https://fantasycalc.com/terms-of-usage`, Stand 24.02.2024, ganz gelesen): Nutzung auf anderen
  Webseiten erlaubt; nicht kommerziell; Nennung „FantasyCalc“ oder „FantasyCalc.com“ gut sichtbar auf jeder Seite mit den
  Daten, nahe bei den Daten; sichtbarer Link auf FantasyCalc.com; Zwischenspeichern erwünscht, am besten ein Abruf je
  Tag (API-Doku: höchstens einer je Stunde); verboten ist, wesentliche Teile ihres Angebots wiederzugeben oder zu
  ersetzen. Non-Endorsement: kein Eindruck von Partnerschaft, Billigung oder Empfehlung durch FantasyCalc –
  Quellenzeile, Glossar und README neutral halten („Werte: FantasyCalc“, kein „mit Erlaubnis von“ oder „in
  Zusammenarbeit mit“). FantasyCalc kann die Bedingungen jederzeit ohne Ankündigung ändern. Die Nennung gilt laut
  API-Doku auch für abgeleitete Werte.
- **Einordnung:** Die Werte sind Tauschpreise aus Dynasty-Ligen mit rund 300 dauerhaft gehaltenen Spielern; die BWG hält
  120. Oberhalb der Keeper-Linie passen sie (95 von 113 Offense-Keepern 2026 lagen in den Top 120), darunter
  überzeichnen sie. Keine Punktprognose.
- **Änderungstakt:** Zwischen 30.09. 22:09 UTC und 01.10. 07:56 UTC hatten sich 409 von 420 Werten geändert – der
  Auszug ändert sich also praktisch jeden Tag (ein Commit je Tag).
- **Ungeprüft:** ob `api.fantasycalc.com` von GitHub-Actions-Runnern erreichbar ist (lokal ja) – vor dem Bau mit dem
  Probe-Workflow klären.

## Starttext
Wir starten Session 9 nach `docs/auftraege/session9.md`. Lies zuerst CLAUDE.md, `docs/app_daten.md` (Abschnitt
`keeper.json`), `scripts/keeper.py`, `scripts/nflverse.py` (Muster für eine Fremdquelle mit Auszug) und
`app/js/v_keeper.js`; dann `git pull` und im eigenen Worktree arbeiten (Branch `claude/keeper-marktwert`, später
`claude/keeper-offseason`). Reihenfolge:

### Stufe 3
1. **Probe:** `scripts/probe.py` um einen Aufruf der FantasyCalc-API ergänzen (nur Statuscode, Zahl der Einträge, Größe)
   und den Probe-Workflow von Hand laufen lassen. Antwortet die API dem Runner nicht, Stephan fragen, bevor weitergebaut
   wird.
2. **Abruf `scripts/fantasycalc.py`** (Muster `nflverse.py`): `update(session, season, now)` im **Tageslauf**, aber nur,
   wenn der gespeicherte Auszug nicht vom selben UTC-Tag stammt (ein Abruf je Tag); fängt jeden Fehler selbst
   (Warnung, alter Auszug bleibt). Im Tageslauf läuft nur, was geschaltet ist: eigener Schalter `--marktwert` in
   `parse_args` und `cmd_daily` (Ausfall = Warnung, macht den Lauf nicht rot) und in `.github/workflows/tageslauf.yml`
   (`--transactions --pool --wetter --marktwert`); Kopfkommentare von `espn_fetch.py` und `tageslauf.yml` sowie
   CLAUDE.md (Baustein 3) nachziehen. Auszug `data/raw/<saison>/fantasycalc/latest.json`: Kopf `quelle`, `stand`
   (Abrufzeit), `parameter`; je ESPN-ID der Pool-Spieler nur `wert`, `rang` (= `overallRank`, unverändert),
   `pos_rang`, `trend30`, `redraft` – eine Zeile je Spieler, sortiert, ohne Namen, ohne Picks. `stand` wird bei jedem
   gelungenen Abruf neu geschrieben, auch ohne geänderten Wert – er ist die Tagessperre (anders als der Pool-Auszug,
   dessen `stand` die letzte Änderung ist). Der Abruf prüft, dass die Ränge der Spieler 1 … n ohne Lücke und Doppel
   sind; unbrauchbar (Ränge kaputt, zu wenige Treffer, fehlende Felder) = Fehler, nichts schreiben. Tests mit
   Fake-Sitzung wie `tests/test_nflverse.py`, dazu ein Tageslauf-Test mit Fake-Sitzung (zweiter Lauf am selben UTC-Tag
   ruft nicht ab; ein Fehlschlag lässt den alten Auszug stehen und der nächste Lauf versucht es wieder); die
   Anfrage-Folgen des Wochenabrufs in `tests/test_fetch.py` bleiben unverändert.
3. **Rechenwerk** (in `keeper.py` oder eigenes Modul, reine Funktionen): je Kaderspieler und je freiem Spieler mit
   Marktwert `wert`, `rang`, `pos_rang`, `trend30`, `redraft`. Die App-Auswahl (`player_selection`: mit Spiel, im Kader
   oder unter den 20 besten Free Agents je Position nach ROS/Spiel) reicht dafür nicht: Am 01.10. fehlten ihr 47 der
   190 freien Spieler mit Wert, darunter 5 der 30 wertvollsten (meist verletzt oder ohne Einsatz, z. B. der
   drittwertvollste freie). Für den Horizont „Zukunft“ nimmt die Auswahl deshalb zusätzlich alle freien Spieler mit
   Wert auf (Stammdaten aus dem Wochenpool wie bei Kaderspielern, die `players.json` nicht führt); Größe von
   `players.json`/`waiver.json` danach prüfen, Aufnahme-Regel in `docs/app_daten.md` anpassen, Tests mit und ohne
   Auszug. **Keeper-Linie** = Wert des 120.-wertvollsten Kaderspielers der Liga (`keeper_zahl` × Teams); **Wert über
   der Linie** = Wert − Keeper-Linie. Je Team: **Kern-Wert** = Σ der `keeper_zahl` wertvollsten Kaderspieler (nur die
   Zahl), Σ Wert über der Linie (nur positive Beträge), wertgewichtetes Alter (Alter aus Stufe 2, Gewicht = Wert).
   Kein Wert fließt in Score, Power Ranking oder Simulation. Regel und Schwächen (unterhalb der Linie überzeichnet,
   ohne K und D/ST) in CLAUDE.md festhalten.
4. **Datei für das Claude-Projekt:** kompakte, spaltenweise Datei wie `claude.json` (eigene Datei, damit `claude.json`
   unter 50 KB bleibt), abrufbar über `raw.githubusercontent.com`: alle Spieler mit Wert (ESPN-Name, Position,
   NFL-Team, BWG-Team als Kürzel oder Status, Wert, Rang, Positionsrang, Trend, Redraft-Wert, Wert über der Linie,
   Alter, Herkunft), Kopf mit Stand, Keeper-Linie, Quelle und einer Legende (jede Zeichenkette unter 400 Zeichen:
   `check_public.py`). Keine Liste „beste zwölf je Team“ – das Projekt rechnet selbst. Dazu ein **Absatz für die
   Projektanweisung in claude.ai** (Adresse der Datei, Lesart, Vorgehen bei Trade-Fragen: Werte beider Seiten,
   Wert über der Linie, Alter, ROS aus `claude.json`; Hinweis, dass Trade-Überlegungen im Chat oder im persönlichen
   Notion-Bereich bleiben). Den Absatz legt Claude Stephan mit Wortlaut vor; einfügen kann nur Stephan.
5. **App:** Keeper › Kader mit Spalten Wert, Rang und Trend; neue Ansicht `#keeper/wert` (Kern-Wert, Wert über der
   Linie und wertgewichtetes Alter je Team, kein Spieler-Ranking); Spielerseite mit Wert, Rang und Trend; Waiver-Tab
   mit Horizont „Zukunft“ (freie Spieler nach Marktwert, `#waiver?h=zukunft`). Auf jeder dieser Ansichten nahe bei den
   Zahlen „Werte: FantasyCalc“ mit Link auf `https://fantasycalc.com` (neutral, siehe Non-Endorsement), dazu ein
   Verweis auf deren Trade-Rechner statt eines eigenen. Glossar-Block „Marktwert“ mit der ehrlichen Einordnung;
   Glossar „Quelle“ und README „Quellen“ ergänzen.
6. **Doku und Tests:** `docs/app_daten.md`, CLAUDE.md (Bausteine, Repo-Struktur, Rechenregel „Marktwert“,
   Saisonwechsel: Parameter und Keeper-Zahl prüfen, Nutzungsbedingungen und API-Doku von FantasyCalc neu lesen),
   README. Tests so, dass sie mit und ohne Auszug grün sind und grün bleiben, wenn der erste echte Auszug ins Repo
   kommt (Lehre aus Stufe 2: Generalprobe mit dem echten Auszug, nur lokal, nicht committen).

### Stufe 4
**Voraussetzung – Stand in den Playoffs:** Das Rechenwerk endet heute bei W14 (`compute.completed_weeks` bricht nach der
letzten Regular-Season-Woche ab; `Season.through` ≤ 14, Einstellungen, Spielplan und ROS kommen dauerhaft aus w14, der
Seed der Simulation bleibt Saison·100 + 14). Die Rohdaten W15–17 liegen vor (Wochenabruf bis W17), werden aber nicht
gelesen. Zuerst festlegen (Plan in wenigen Sätzen an Stephan) und bauen, wie das Rechenwerk finale Playoff-Wochen
kennt: Tabelle, All-Play und Score bleiben beim Stand W14; dazu ein eigener Playoff-Stand = letzte finale Woche 15–17,
gelesen aus `wNN/mMatchupScore.json` dieser Woche. Die Endplatz-Simulation nimmt gespielte Playoff-Spiele als Tatsache
und simuliert nur die offenen; Seed = Saison·100 + letzte finale Woche (auch 15–17). `ros_after_week`, `alter_gewicht`
und die Bedarfs-Basis ziehen mit, damit „nach W17“ in der echten Pipeline erreicht wird.

7. **Endplatz in der Simulation:** `powerranking.py` simuliert heute bis zum Seeding. Neu: W15–17 ausspielen –
   Playoffs der sechs (Seed 1–2 mit Freilos in W15, `playoffReseed` ist false), Spiel um Platz 3 und um Platz 5, und
   die Trostrunde der vier übrigen Teams für die Plätze 7–10. Ausgespielt wird das Feld nach dem Seeding „liga“
   (Standard laut CLAUDE.md: Top 3 je Division, Divisionssieger Seed 1–2); „espn“ bleibt Vergleich bis zum Seeding und
   bekommt keine Endplatz-Verteilung. Trostrunde in der Simulation = die vier nach der Liga-Regel nicht qualifizierten
   Teams, gesetzt 7–10 nach Stand (W + 0,5·T, dann PF). Offen: ob bei der Handkorrektur des Commissioners nach W14
   auch die ESPN-Trostrunde das Feld der Liga-Regel bekommt (nach W3 weichen beide Regeln ab: ESPN-Seeds 1–6 mit vier
   Teams aus Division 2) – nach W14 an `status.isPlayoffMatchupEdited` und den echten Paarungen prüfen, sonst Stephan
   fragen. Sobald echte Paarungen vorliegen, gelten sie, nicht die Regel.
   Die Mechanik von ESPN **zuerst klären und belegen**: wer in welcher Woche gegen wen spielt, wann das Spiel um
   Platz 5 liegt, wie die Trostrunde die Plätze vergibt (ESPN-Hilfe lesen:
   `espn.com/fantasy/football/ffl/story?page=fflrulesplayoffs`; `mSettings.scheduleSettings` trägt
   `consolationLadderDisabled: false`. Achtung: `mMatchupScore` enthält bis W14 nur die Perioden 1–14 mit
   `playoffTierType` „NONE“ – die Playoff-Paarungen legt ESPN erst nach W14 an (frühestens Di 15.12.2026), spätere
   Runden vermutlich erst nach der Vorrunde; 2026 ist die erste ESPN-Saison der Liga. Belegt aus der ESPN-Hilfe: Die
   Trostrunde ist eine Leiter, erste Runde 7–8 und 9–10, der Sieger rückt auf, der Verlierer ab; Verlierer des
   Winner's Bracket spielen bis zum Saisonende gegen andere Verlierer; bei Punktgleichheit gewinnt der höhere Seed.
   Fest (Beschluss 2): je ein Spiel um Platz 3 und um Platz 5, für die Plätze 7–10 gilt der Stand der Trostrunde nach
   W17. Vor dem 15.12. nicht belegbar: in welcher Woche ESPN das Spiel um Platz 5 ansetzt (die W15-Verlierer können in
   W16 und W17 aufeinandertreffen), wie die Leiter in W16 und W17 paart und welche Werte `playoffTierType` annimmt. Die
   Simulation baut darauf als gekennzeichnete Annahme (Glossar, CLAUDE.md); nach W15, W16 und W17 die Annahme gegen die
   echten Paarungen, `playoffTierType` und `rankCalculatedFinal` aus mTeam prüfen, bei Abweichung Stephan fragen.)
   Ergebnis je Team: Verteilung des Endplatzes, erwartete Draft-Position 2027, Anteil für Pick 1 und für die
   ersten drei Picks; Seed wie in der Voraussetzung (Saison·100 + letzte finale Woche).
8. **Nach W17:** Stehen die Endplätze fest, zeigt die App die Draft-Reihenfolge 2027 als Tatsache (aus den Ergebnissen,
   nicht aus ESPN `pickOrder` – die trägt der Commissioner erst später von Hand ein). Sieger eines Playoff-Spiels =
   ESPN-Feld `winner` (HOME/AWAY) aus `mMatchupScore`, nicht der Punktevergleich wie in `compute.league_games`. Bei
   Punktgleichheit entscheidet laut ESPN-Hilfe der höhere Seed (`playoffMatchupTieRule` steht auf „NONE“); liefert
   ESPN trotzdem „TIE“, Warnung ausgeben und Stephan fragen statt einen Endplatz zu raten.
9. **Offseason-Stand des Keeper-Tabs:** Heute bleibt das Rechenwerk nach W14 stehen: `alter_gewicht` bliebe den ganzen
   Winter „ros_po“ mit den Projektionen aus `w14/ros.json`. Erst mit der Voraussetzung vor Schritt 7 gibt es nach W17
   keine ROS-Projektion mehr (`alter_gewicht` wird leer). Prüfen und mit konstruierten Tests absichern, dass Bilanz,
   Kader, Alter und Wert dann vollständig bleiben; das Alter „nach ROS“ weicht dann dem wertgewichteten Alter aus
   Stufe 3. Der Tageslauf läuft in der Offseason technisch weiter (bis zum 1. August), liest aber nur das Liga-Objekt
   der Saison 2026. Ungeprüft: ob ESPN dort nach W17 noch Moves zulässt (Trade-Deadline laut mSettings 30.12.2026) –
   möglich ist, dass der Kader von Januar bis zum Saisonwechsel stillsteht. Die Keeper-Phase 2027 läuft im Liga-Objekt
   2027 (2026 lagen die Vorsaison-Moves in Periode 0 nach der Aktivierung am 07.08.); die sieht der Tab erst mit einem
   Vorsaison-Pfad (Schritt 11). Im Januar an den echten Daten prüfen, ob sich der Kader 2026 noch bewegt, und das
   Ergebnis in CLAUDE.md festhalten; bis dahin in App und Glossar nichts versprechen.
10. **App:** neue Ansicht `#keeper/draft2027` (oder Abschnitt in `#keeper/draft`): je Team erwartete Draft-Position,
    Anteil Pick 1 und Top 3, nach W17 die feste Reihenfolge; Glossar mit der Regel (umgekehrte Endplatzierung, linear,
    keine Lotterie), der gekennzeichneten Annahme zur ESPN-Mechanik und dem Hinweis, dass getauschte Picks nicht
    berücksichtigt sind. Rechenregel „Playoff-Simulation“ in CLAUDE.md, `docs/app_daten.md` (`sim`, `keeper.json`) und
    Tests für Bracket, Leiter und Endplatz mit konstruierten Ergebnissen ergänzen (echte W15–17-Daten gibt es erst ab
    Mitte Dezember).
11. **Offen lassen und notieren:** Zwischen dem Saisonwechsel (spätestens 1. August) und der ersten finalen Woche
    rechnet `compute.py` nichts – die App steht in der Keeper-Phase 2027 auf dem Stand des Wechsels. Ob es dafür einen
    eigenen Vorsaison-Pfad geben soll, entscheidet Stephan vor dem Saisonwechsel; in die Checkliste aufnehmen.

Je Stufe vor dem Merge: `main` nachziehen, `python scripts/compute.py`, `pytest`, `python scripts/check_public.py app .`,
Gegenprüfung, Ansichten im Browser bei 320/360/390 px und am Desktop, dann Pull Request anlegen und mergen
(Beschluss 29.09.). Rohdaten holt nur die Action.

## Nicht in dieser Session
- Kein eigener Trade-Rechner und keine Ranglisten-Seite in der App; keine Pick-Werte; keine getauschten Picks.
- Keine Trade-Überlegungen, Keeper-Pläne oder Ziele einzelner Teams im Repo – die entstehen im Claude-Projekt.
- Nichts automatisch nach Notion.

## Ergebnis Stufe 3 (01.10.2026, Branch `claude/keeper-marktwert`)
- Beschluss 2 von Stufe 4 („je ein Spiel um Platz 3 und um Platz 5“) hat Stephan zu Beginn der Session bestätigt.
- Probe: Der Runner erreicht FantasyCalc (Probe-Lauf 36836250337: HTTP 200, 420 Einträge, 396 Spieler, 393 mit `espnId`, 24 Picks).
- Gebaut wie beschrieben: `scripts/fantasycalc.py` (`--marktwert` im Tageslauf, Tagessperre über `stand`, jeder Fehler eine
  Warnung), Rechenwerk in `keeper.py`, App (Keeper › Wert, Wertspalten in Keeper › Kader, Abschnitt Marktwert auf der
  Spielerseite, Horizont „Zukunft“ im Waiver-Tab), `claude_marktwert.json`, Glossar, Datenvertrag, CLAUDE.md, README.
- Abweichung vom Auftragstext: Die freien Spieler mit Wert, die `players.json` nicht führt (01.10.: 47), kommen nur in
  `waiver.json` (wie unter der Woche geholte Kaderspieler, mit Name aus dem Wochenpool), nicht in `players.json` – sonst
  wäre `players.json` schon nach W3 über der Testgrenze von 60 KB gzip gewesen (60,2 KB). Die App gibt ihnen trotzdem eine
  Spielerseite (ohne Wochenwerte).
- Generalprobe mit dem echten Auszug (nur lokal): Keeper-Linie 1.661, alle 202 Offense-Kaderspieler mit Wert, bester
  freier Spieler auf Gesamtrang 126, 121 Kaderspieler auf oder über der Linie (Gleichstand an der Linie). Zwei
  Testdefinitionen („hat eine Spielerseite“) mussten der neuen Regel folgen; danach 566 Tests grün mit und ohne Auszug.
  Größen mit Auszug: `waiver.json` 30,8 KB gzip, `keeper.json` 23,8 KB, `claude_marktwert.json` 31 KB (11,9 KB gzip).
- Gegenprüfung (vier Blickwinkel, je Befund ein Skeptiker): 8 Befunde, 2 bestätigt und umgesetzt (Kaderspieler, die der
  Wochenpool nicht kennt, fehlten in `waiver.json` und `claude_marktwert.json`; Vertrag zu `in_app`), 6 widerlegt (u. a.
  der erneute Abruf nach einem Fehlschlag – so bestellt).
- Offen für Stephan: den Absatz für die Projektanweisung des Claude-Projekts einfügen (Wortlaut im Chat vorgelegt).
- Gemergt als PR #45. Der erste Tageslauf danach (36846153258) holte den Auszug, war aber rot: Ein Test erwartete den
  lokalen Warn-Präfix „Warnung: “, in der Action schreibt `espn_fetch.warn` „::warning::“. Behoben in PR #46 (Test prüft
  nur den Text; App-Daten mit dem ersten echten Auszug). Lehre: Tests, die Ausgaben prüfen, auch mit
  `GITHUB_ACTIONS=true` laufen lassen.

## Ergebnis Stufe 4 (01.10.2026, Branch `claude/keeper-offseason`)
- Playoff-Stand: `compute.final_playoff_weeks`, `rawdata.Season.at` (Stand-Woche teilt die geladenen Wochendateien);
  Tabelle, All-Play, Score, Power Ranking und Kader-Projektion bleiben bei W14. Aus der Stand-Woche: ROS (nach W17 ohne
  Werte), Bedarf/Profil, Altersgewicht und Stichtag, Vorausschau von Positions-Matchup und D/ST, gespielte Playoff-Spiele,
  Seed. `schedule.json` zeigt Playoff-Wochen weiter nicht als final (Playoff-Session).
- Endplatz-Simulation (`powerranking.play_bracket`, eigener Zufallsstrom – die bisherigen Werte bleiben gleich) mit
  Draft-Position des Folgejahrs; nach W17 feste Reihenfolge (`final_places`), nur ohne Abweichung von ESPN (Paarungen,
  TIE, ESPN-Endplatz `rankFinal`/`rankCalculatedFinal`); bei Abweichung keine Verteilung und keine Reihenfolge, Hinweis
  am Lauf. Stand W3: SaureGurken Ø Pick 2,6, Asse's Cowboys 8,7.
- App: Ansicht `#keeper/draft-folgejahr` (statt `#keeper/draft2027`, damit die Route jede Saison stimmt), Alter „nach
  Wert“ in der Offseason, Datenstand-Chip in den Playoffs; Glossar mit gekennzeichneter Annahme.
- Gegenprüfung: 13 Befunde, 11 bestätigt und umgesetzt (u. a. Echtdaten-Test hätte nach W17 jede Action rot gemacht;
  feste Reihenfolge trotz Abweichung; FantasyCalc-Nennung in der Alter-Ansicht; Datenstand-Chip ab 23.12.).
- Offen (in CLAUDE.md): Annahme zur ESPN-Mechanik nach W15, W16 und W17 an den echten Paarungen prüfen (ab 15.12.);
  im Januar prüfen, ob sich der Kader nach W17 bewegt und ob ESPN `rankCalculatedFinal` füllt; Entscheidung Stephan vor
  dem Saisonwechsel: eigener Vorsaison-Pfad.
