# App-Daten (`app/data/`, Schema 1)

`scripts/app_export.py` schreibt die Dateien bei jedem Lauf von `compute.py`. Die Actions committen sie, `pages.yml` veröffentlicht `app/`.

**Regeln für die Dateien:**
- **Positivliste:** Es kommen nur die unten genannten Felder hinein. Nie `members`, `owners`, `memberId`, `outlooks` oder Manager-Namen; `scripts/check_public.py` prüft das vor jedem Commit.
- **Zahlen:** mit Punkt als Dezimalzeichen, das Komma setzt die App.
  - Punkte 2 Stellen
  - z-Normwerte (`norm.z`) sowie F, r, E und μ-Hilfswerte 3 Stellen
  - Quoten in % mit 2 Stellen, Anteile der Positionen (`anteil`) mit 1 Stelle wie in der Anzeige
  - Anteile der Simulation (0–1) mit 4 Stellen
- **Deterministisch:** kein Zeitstempel der Erzeugung, feste Sortierung. Eine Datei ändert sich nur, wenn sich ihr Inhalt ändert.
- **Einheiten:** Anteile 0–1 in `sim.*`, `p_home` und `pr.e`; Prozent in `*_pct`, `efficiency`, `effizienz_liga`, `positionen.*.anteil` und `own` (auch je Woche in `wochen.allplay_pct` und `wochen.efficiency`). Slots als Text (`QB`, `RB`, `WR`, `TE`, `FLEX`, `OP`, `D/ST`, `K`, `Bank`, `IR`), Positionen als Kürzel.
- **Fehlende Werte:** `null`. Die App zeigt dafür „–“, sortiert solche Werte ans Ende und nennt im i-Text den Grund, z. B. „ab Wochenabruf W3“ oder „ab 4 Spielen“.
- **Schlüssel:** Team-Schlüssel ist `team_id` = Franchise-Slot 1–10, Spieler-Schlüssel die ESPN-ID, NFL-Teams per ESPN-`proTeamId` mit Kürzel.

## `manifest.json` (immer frisch geladen)
```json
{"schema": 1, "season": 2026, "through_week": 2,
 "datenstand": {"woche_final": 2, "ros_nach_woche": null, "pool_woche": 2, "transaktionen_bis": 1790000000000,
                "pool_stand": "2026-09-29T0645Z", "wetter_stand": "2026-09-29T0645Z"},
 "files": {"teams.json": {"v": "<sha256, 12 Zeichen>", "bytes": 13000, "lazy": false}, "…": {}}}
```
Die App lädt `data/manifest.json?t=<jetzt>` und danach jede Datei mit `?v=<v>`. Ist `schema` größer als die Schema-Version der App, zeigt sie „Neue Version – bitte neu laden“.
`pool_stand` und `wetter_stand` sind die Abrufzeit (UTC, `JJJJ-MM-TTThhmmZ`) des jüngsten Tageslaufs, der Pool-Auszug bzw. Wetter geändert hat; `null`, solange der Tageslauf nichts geliefert hat (dann fehlen auch `waiver.json` und `wetter.json`).

## `teams.json` (Erstaufruf)
- **`meta`:**
  - `weeks` (gerechnete Wochen), `sigma`, `ligafaktor`, `effizienz_liga` (Σ PF / Σ Optimal der Liga in %)
  - `kader_quelle` (`"potenzial"` oder `"projektion"`), `metrics` (Liste `{key, label}` in der Reihenfolge PF · All-Play · Win · Coaching · Kader · Floor · Form)
  - `profiles` (Name → Gewichte), `profil_standard`, `norm_standard`
  - `divisions` (id → Name), `kuerzel` (team_id → Kürzel)
- **`teams`:** Liste je Team, sortiert nach `rang`:
  - Tabelle:
    - Stammdaten: `team_id, name, kuerzel, division, games, w, l, t`
    - Punkte: `pf, pa, diff, pf_per_game, pa_per_game`
    - All-Play: `win_pct, allplay_w, allplay_l, allplay_t, allplay_pct, median_w, median_l, matchup_glueck` (Σ der Wochenwerte), `spielplan_pkt` (Σ Ligaschnitt − Gegnerpunkte)
    - Coaching: `optimal, verschenkt, verschenkt_avg, verschenkt_max, efficiency, kader_potenzial, kader_projektion, bench`
    - Form und Projektion: `floor, form, form_delta, form_band, streak, projection, projektions_delta`
    - Ränge und Liga: `waiver_prio, moves, rang, rang_division, rang_score`
  - Score: `norm` `{z, minmax, rank}` je Kennzahl; `score_ref` je Profil und Normierung (Python-Wert, damit der Test die Browserformel prüfen kann).
  - Power Ranking `pr`: `{mu, se, p, p_quelle, e, rang, rang_vorwoche, trend, kernsatz}`
  - Simulation `sim`: `{liga: {playoff, division, bye, restsiege, seeds: [6]}, espn: {…}}` – `liga` = Regel 2026 (Top 3 je Division), `espn` = Top 6 gesamt; dazu `espn_sim` (ESPN-Vergleich oder `null`)
  - `positionen`: `{summe, nach_position: {"QB": {pts, anteil, rang}, …}, nach_slot: {"QB", "RB", "WR", "TE", "FLEX", "OP", "D/ST", "K"}}` – `summe` = Σ Starter-Punkte aller Positionen (= PF, Grundlage von `anteil`)
  - `wochen`: Arrays in der Reihenfolge von `meta.weeks` (Einzelwoche, nicht kumuliert): `gegner, heim, pf, pa, ergebnis, wochenrang, allplay_w, allplay_l, allplay_t, allplay_pct` (All-Play-Anteil pₜ der Woche in %), `median_abstand` (PF − Wochenmedian), `gegner_abstand` (PA − Wochenmedian), `matchup_glueck` (Woche: Sieg unter dem Median +, Niederlage über dem Median −, Gewicht (|median_abstand| + |gegner_abstand|)/(2σ) gekappt bei 1, sonst 0), `matchup_kum` (laufende Summe, letzter Wert = `matchup_glueck` des Teams), `gegner_pkt` (Ligaschnitt − PA), `median_win, optimal, verschenkt, efficiency` (PF / Optimal der Woche in %), `bank, projektion, projektions_delta, mu, pr_rang`

## `schedule.json` (Erstaufruf)
- **`weeks`:** Liste je Woche 1–17 mit `week`, `start` (Dienstag, ISO-Datum), `status` (`final`, `laeuft`, `offen`) und `playoff` (bool). Für finale Wochen zusätzlich:
  - `ligaschnitt, median, effizienz_liga` (Σ PF / Σ Optimal der Woche in %)
  - `high {team_id, pf}`, `low {team_id, pf}`, `top_team_id`
  - `bank_suende {team_id, verschenkt}`
  - `top_scorer`: die 10 besten Kaderspieler der Woche über alle Teams, Bank eingeschlossen, ohne IR (bei Gleichstand auf Platz 10 mehr), absteigend nach Punkten, je `{rang, player_id, name, pos, pro_team, nfl, team_id, slot, pts, proj}` – `rang` = 1 + Zahl der Spieler mit mehr Punkten (Gleichstand teilt den Rang), `pro_team` = NFL-Team-ID zum Abruf der Woche, `nfl` das Kürzel dazu (`records.top_scorer`)
- **`games`:** Liste aller Paarungen mit `week, home, away, home_pf, away_pf, winner` (team_id, `"T"` bei Unentschieden, `null` wenn offen), `playoff` (bool: Paarung einer Matchup-Periode nach der Regular Season laut mSettings) und `p_home` (Siegchance nach μ, nur offene Spiele).
- **`h2h`:** Liste aller 45 Paare `{a, b, spiele, w_a, l_a, t, pf_diff}`, auch mit `spiele = 0`.
- **`records_rs`, `records_po`:** je Rekord eine Liste von Einträgen (bei Gleichstand mehrere):
  - Team-Woche `{team_id, week, opponent_id, wert}`: `hoechster_score`, `niedrigster_score`, `hoechster_verlierer`, `niedrigster_sieger`, `hoechste_bank`, `meiste_verschenkt`
  - Spiel `{week, team_ids: [Sieger, Verlierer], punkte, wert, unentschieden}`: `groesster_sieg`, `knappstes_ergebnis`
  - Serie `{team_id, weeks: [von, bis], wert, laufend}`: `laengste_siegesserie`, `laengste_niederlagenserie`
  - Spieler `{player_id, name, pos, team_id, week, slot, wert}`: `bester_spieler`

## `players.json` (lazy, Tab Spieler und Teamseite)
- **Kopf:** `ersatz` (Position → Ersatzniveau), `ros_nach_woche`, `cv`, `weeks`, `mu_woche` (Woche N+1 des Positions-Matchups, `null` nach der letzten Woche).
- **`players`:** Liste. Aufgenommen wird, wer mindestens ein Spiel hat oder im Kader steht, dazu die 20 besten Free Agents je Position nach ROS/Spiel. Felder:
  - Stammdaten: `id, name, pos` (Kürzel) `, nfl` (Kürzel) `, bye` (Bye-Woche des NFL-Teams, `null` ohne NFL-Team) `, team` (team_id oder 0) `, status, inj, own`
  - Saison: `g, pts, avg, floor, ceil, sd, form, form_d, trend, spark, starts, bench_pts, proj_d`
  - `wk`: Liste je Woche `[pts|null, proj|null, bye 0/1, team_id|0, slot|null]` in der Reihenfolge von `weeks`
  - ROS: `ros, ros_g, rest_g, ros_po, ros_rang, ros_ue`
  - `mu` (Positions-Matchup, Wochenstand wie ROS; die App verknüpft über `id`): `{n1: {week, opp, f, rang}, naechste3, rest, sos_po}` – `n1` = Gegner in Woche `mu_woche` (`opp` NFL-Kürzel der Defense, `f` ihr F für die Position des Spielers, `rang` 1 = günstigstes Matchup; bei Bye alle drei `null`; `n1` selbst `null` ohne Woche N+1), `naechste3` = Ø F der Gegner in N+1…N+3, `rest` = N+1…14, `sos_po` = W15–17 (eine Woche ohne Spiel fällt heraus, `null` ohne Spiel), F mit 3 Stellen. QB, RB, WR, TE und K aus `matchup.json`; D/ST aus `dst.json` (F und Rang der gegnerischen Offense, gleiche Richtung: > 1 günstig). `mu` ist `null` ohne NFL-Team.
  - `fp`: FantasyPros-Adresse ohne `.php` (Verweis `fantasypros.com/nfl/players/<fp>.php`), aus dem Abgleich des Namens mit der Positions-Sitemap (`scripts/fantasypros.py`, dazu die Handtabelle `HAND` für Spitznamen); `null` = keine eindeutige Zuordnung oder nicht in der Sitemap (die App verlinkt dann eine Seitensuche), bei D/ST immer `null` (Tabelle der App). Fehlt, solange der Wochenabruf keinen Sitemap-Auszug `data/raw/<saison>/fantasypros/sitemap.json` geholt hat.

## `dst.json` (lazy, Unter-Tab D/ST)
- **Kopf:** `ligaschnitt {"2025", "2026"}`, `formel`, `through_week`.
- **`teams`:** Liste je NFL-Team:
  - Offense-Werte: `id, abbrev, bye, z25, z26, n, r25, r26`
  - Faktor: `f, f_vorwoche, delta, rang` (1 = höchstes F), `rang_vorwoche`, `z_last3` (Ø Z der letzten 3 Spiele in Punkten; `null` ohne Spiel); keine Auslöser (seit 30.09.2026)
  - Sicht der D/ST: `naechste3, rest, sos_po, besitzer, status`
  - `naechste`: die Gegner der Wochen N+1…N+3 als `[{week, opp, f}]`, Bye ohne `opp`

## `matchup.json` (lazy, Positions-Matchup)
Position gegen Defense, kein Einzelduell: wie viele Punkte jede NFL-Defense den Spielern einer Position zulässt (`scripts/matchup.py`, Formel wie D/ST).
- **Kopf:**
  - `through_week`, `saison`, `vorjahr`, `positionen` (`["QB", "RB", "WR", "TE", "K"]`), `formel`
  - `vorjahr_quelle`: `"basis"` (Auszug `data/raw/<saison>/basis/positionen_<vorjahr>.json`) oder `"ligamittel"` (Auszug fehlt noch: r25 = 1,00 für alle, `z25` und Ligaschnitt des Vorjahrs `null`)
  - `ligaschnitt`: je Position `{"2025": LS25|null, "2026": LS26|null}` (Ø Z über die Defenses mit Spiel)
  - `wochen`: `{n1, naechste3, rest, sos_po}` – Woche N+1 (`null` nach der letzten Woche) und die Wochen der Spielplan-Faktoren
- **`defenses`:** Liste je NFL-Team (nach NFL-ID) mit `id, abbrev, bye` und `pos`: je Position (Schlüssel wie `positionen`):
  - `z25, z26` (Z = Ø Punkte je Spiel, die Spieler der Position mit Einsatz gegen die Defense erzielt haben; `null` ohne Spiel), `n` (Spiele 2026 mit mindestens einem Spieler der Position)
  - `r25, r26` (Z/Ligaschnitt; r25 = 1 ohne Vorjahresspiel), `f` (F = (n·r26 + 5·r25 + 5·1,00)/(n + 10)), `f_vorwoche`, `delta`
  - `rang` (1 = höchstes F = günstigstes Matchup für Spieler der Position; Gleichstand teilt sich den besseren Rang), `rang_vorwoche`; keine Auslöser (seit 30.09.2026)
- Zahlen: F, r und `delta` 3 Stellen, Z und Ligaschnitt 2. Die Werte je Spieler stehen in `players.json` (`mu`).

## `history.json` (lazy, Rekorde › Historie)
- `alltime`, `seasons`, `team_seasons`, `champions`, `rekorde` wie `scripts/history.py`.

## `transactions.json` (lazy)
- `spieler` (id → Name), `aufstellungswechsel` (team_id → Zahl).
- `items`: `{id, type, team_id, datum (Epoch-ms), periode, items: [{type ADD/DROP, player_id, name, from_team_id, to_team_id, in_app}]}`. `type` ist WAIVER, FREEAGENT, ROSTER (reine Drops) oder TRADE_ACCEPT (ohne Spieler).
- `in_app` (bool): Die App hat eine Spielerseite zu diesem Spieler (players.json oder Kader laut Tagesstand); sonst zeigt sie den Namen ohne Link.
- Der Draft steht seit dem Keeper-Tab in `keeper.json` (`picks`).

## `keeper.json` (lazy, Keeper-Tab `#keeper`, dazu Herkunft auf Team- und Spielerseite)
Keeper-Bilanz (`scripts/keeper.py`): woher die Punkte eines Teams kommen. Herkunft = Nachspielen von Draft (`mDraftDetail`) und Transaktions-Archiv; fehlt vor dem Draft.
- **Kopf:** `through_week` (Punkte bis zu dieser Woche), `stand` (Abrufzeit des Tagesstands, nach dem sich der Kader heute richtet; `null` = Wochenstand), `draft_datum` (Draft-Ende, Epoch-ms), `keeper_zahl` (mSettings `keeperCount`), `kader_plaetze` (Kaderplätze ohne IR-Slot).
- **`teams`** (nach `team_id`) und **`liga`** (dieselben Felder über alle Teams):
  - `keeper`, `keeper_da` (Keeper-Picks und wie viele davon heute noch als Keeper im Kader des Teams stehen), `picks`, `picks_da` (Draft-Picks der Saison genauso)
  - `kader`: Zahl der Kaderspieler heute je Art `{keeper, draft, waiver, free_agent, trade}`
  - `pf` und `kern`: `{summe, pts: {keeper, draft, zugang, trade}, anteil: {…}}` – Starter-Punkte W1 … `through_week` nach Herkunft; `zugang` = Waiver-Claims und Free Agents zusammen; `anteil` in % der Summe (eine Stelle, `null` ohne Punkte). `pf.summe` = PF des Teams; `kern` = dieselbe Aufteilung nur für QB, RB, WR, TE.
- **`kader`:** Kaderspieler heute, sortiert nach (`team`, `id`):
  - `id, name, pos, nfl, team, in_app` (`name`, `pos`, `nfl` aus dem Wochenpool, `null` für Spieler, die er nicht kennt)
  - `art` (`keeper`, `draft`, `waiver`, `free_agent`, `trade`), `pick`, `runde`, `von` (Pick, Runde und Team des Picks: bei Keepern und Draft-Picks, und bei getauschten Spielern, die seit dem Draft ununterbrochen in einem Kader stehen; sonst `null`), `seit` (Epoch-ms: Draft-Ende, Zugang oder Trade; `null` bei Keepern und bei Trades ohne Datum)
  - `g`, `avg` (Spiele und Punkte je Spiel der laufenden Saison), `vj_g`, `vj_pts`, `vj_avg` (Vorjahr im heutigen Liga-Scoring aus `mRoster`), `vj_delta` (`avg` − `vj_avg`), `rookie` (bool: kein Vorjahres-Eintrag bei ESPN; `null`, wenn der Spieler in keiner gewerteten Woche im Kader stand – dann sind auch die `vj_*` `null`)
- **`picks`:** alle Picks des Drafts inklusive Keeper, sortiert nach `pick`:
  - `pick, runde, runden_pick, team_id, player_id, name, pos, keeper, in_app`
  - `da` (bool: der Spieler steht seit dem Draft ununterbrochen beim Team des Picks), `team_jetzt` (team_id heute, 0 = frei)
  - `g, pts, avg` (Saison des Spielers insgesamt, `null` ohne Eintrag im Wochenpool), `starts`, `pf` (Wochen im Starter-Slot und Punkte für das Team des Picks, solange der Abschnitt des Picks lief; Σ `pf` der Keeper-Picks = `liga.pf.pts.keeper`, der übrigen = `liga.pf.pts.draft`)
- Trades: Das Archiv nennt bei einem Trade keine Spieler. `art` ist `trade`, wenn kein Zugang im Archiv den Spieler zum Team geführt hat oder der Tagesstand ihn als Trade nennt (`pool/latest.json`, Kopf `trades` = Spieler-ID → `[team_id, acquisitionDate]` aus `mRoster` `acquisitionType` TRADE; von dort kommt `seit`).

## `waiver.json` (lazy, Tagesstand je Spieler – Grundlage des Waiver-Tabs)
- **Kopf:** `stand` (Abrufzeit des Pool-Auszugs, UTC), `woche` (die Woche der Projektion `proj`: die Kalenderwoche, deren Spiele als Nächstes anstehen).
- **`reihenfolge`:** Waiver-Reihenfolge als Liste der `team_id` (1 = zuerst); `reihenfolge_quelle` `"tageslauf"` (`waiverRank` aus `mTeam` je Tageslauf, Kopf `waiver_reihenfolge` in `pool/latest.json`) oder `"wochenabruf"` (`waiver_prio` aus `teams.json`, solange der Tageslauf noch keine Reihenfolge geliefert hat); `reihenfolge_stand` = Abrufzeit (UTC) des Laufs, der die Reihenfolge zuletzt geändert hat (Kopf `waiver_reihenfolge_stand`; kann älter sein als `stand`, wenn `mTeam` in einem späteren Lauf nicht antwortete), `null` beim Wochenstand; alle drei `null`, wenn nichts vorliegt.
- **`bedarf`:** je `team_id` (Schlüssel als Text) `{luecken: [{slot, id, pos, ros_g}], ueber_ersatz: {Position: Zahl}}` – Python rechnet (`players.team_needs`): ROS-optimale Aufstellung des Kaders laut Tagesstand nach ROS/Spiel (Regular Season, Wochenstand); `luecken` = Starter mit ROS/Spiel unter dem Ersatzniveau ihrer Position (`slot` als Text, `pos` Kürzel, `ros_g` ROS/Spiel oder `null`) und unbesetzte Slots (`id`, `pos`, `ros_g` `null`), in Slot-Reihenfolge QB · RB · RB · WR · WR · WR · TE · D/ST · D/ST · K · FLEX · FLEX · OP; `ueber_ersatz` = Kaderspieler je Position mit ROS/Spiel über dem Ersatzniveau (`null` ohne Ersatzniveau). Verletzte zählen mit ihrem ROS/Spiel (ESPN projiziert ab der Rückkehr), auch mit Status INJURY_RESERVE – der Fantasy-IR-Slot ist im Tagesstand nicht bekannt, die Regel entspricht der Kader-Projektion ROS. `bedarf` ist `null` ohne Regular-Season-ROS (vor dem ersten ROS-Auszug, nach W14).
- **Wochensicht** (Beschluss 30.09.2026, `app_export.week_view`, `players.week_value` ff.): `horizont` = Wochen N+1 … N+3 (N+1 = `woche`, höchstens bis W17); `ersatz_woche` / `ersatz_3` je Positionskürzel = Ø der drei besten Wochenwerte bzw. Summen unter den verfügbaren Spielern (WAIVERS, FREEAGENT) ohne OUT, IR und Sperre, `null` ohne Kandidaten; `anstoss` = NFL-Kürzel → Anstoß (Epoch-ms) des Spiels in N+1 (ohne offene Anstöße und ohne Bye), damit die App „gespielt“ erkennt. Wochenwert = ESPN-Projektion N+1 laut Tagesstand, 0 bei Bye (NFL-Spielplan) und bei OUT, INJURY_RESERVE oder SUSPENSION; fragliche Spieler (QUESTIONABLE, DOUBTFUL, DAY_TO_DAY) zählen mit Projektion. Alle fünf Felder `null` ohne NFL-Spielplan oder außerhalb W1–17.
- **`bedarf_woche`:** je `team_id` `{luecken: [{slot, id, pos, proj, grund, kandidaten}], ausfaelle: [{slot, id, pos, grund}], byes: [{woche, slot, id, pos}]}` – beste Aufstellung des Kaders (Tagesstand) nach Wochenwert; `luecken` = unbesetzte Slots (`id`, `pos`, `proj`, `grund` `null`), Starter mit `grund` (`BYE`, `OUT`, `INJURY_RESERVE`, `SUSPENSION`) und Starter unter `ersatz_woche` ihrer Position; `kandidaten` = bis zu drei `id` freier Spieler (ohne sicheren Ausfall), die in den Slot passen (FLEX RB/WR/TE, OP QB/RB/WR/TE) und mehr Wochenwert haben als die Besetzung, absteigend. `ausfaelle` = Starter der ROS-optimalen Aufstellung (Regel wie `bedarf`), die in N+1 sicher ausfallen oder fraglich sind (`grund` = Status bzw. `BYE`); `byes` = Starter dieser Aufstellung mit Bye in N+2 … N+3. Ohne Regular-Season-ROS sind `ausfaelle` und `byes` leer. Slot-Reihenfolge wie bei `bedarf`.
- **Bedarf-Grundlage** (Beschluss 30.09.2026, `app_export.need_basis`): `bedarf_basis` = `"regular"` (bis W14: ROS/Spiel der Regular Season) oder `"playoffs"` (nach W14 bis W17: ROS Playoffs/Spiel über die offenen Wochen W15–17, Ersatzniveau nach derselben Regel); `bedarf_ersatz` = Ersatzniveau dieser Grundlage je Positionskürzel. Beide `null` ohne ROS-Auszug und nach W17 (dann auch `bedarf` und `profil`). Gilt für `bedarf`, `profil`, die Ausfälle in `bedarf_woche` und den Zugewinn `ros`.
- **`profil`:** je `team_id` (Schlüssel als Text) Stärken und Schwächen (`players.team_profiles`, Kader laut Tagesstand, Werte nach `bedarf_basis`): `gruppen` in der Reihenfolge QB (Slots QB + OP), RB, WR, TE, FLEX, D/ST, K mit `{wert, abstand, rang, wertung, ids, ist_rang}` – `wert` = Σ der Starter der Gruppe in der wertoptimalen Aufstellung, `abstand` zum Ligaschnitt, `rang` 1 = höchster Wert (Gleichstand teilt den besseren Rang), `wertung` `"schwach"` (Rang 8–10 und `abstand` ≤ −1 Pkt × Slots der Gruppe), `"stark"` (Rang 1–3 und ≥ +1 × Slots) oder `null`, `ids` = Starter in Slot-Reihenfolge, `ist_rang` = Ligarang der Ist-Punkte der Starter-Slots W1–N (`positionen.nach_slot`, QB-Gruppe = QB + OP); `gesamt` `{wert, abstand, rang}`; `schwach`, `stark` = Gruppennamen; `absicherung` je Positionskürzel `{wert, frei_gleichwertig, rang}` = Verlust der besten Aufstellung, wenn der beste Spieler der Position ausfällt und der beste verfügbare (ohne OUT/IR) nachrückt, höchstens 0; `frei_gleichwertig` = ein freier Spieler ist mindestens so gut wie der eigene Beste (dann `wert` 0), `null` ohne Spieler der Position, Rang 1 = geringster Verlust; `byes` = `[{woche, kosten, ids}]` Verlust der besten Aufstellung durch Byes je Restwoche bis W14 (Playoffs: bis W17), nur Wochen mit Verlust; `kader` `{spieler, ir, voll, limit}` (`players.must_drop`: `ir` = Spieler im IR-Slot laut `ir_slot`, voll = die Spieler außerhalb des IR-Slots füllen alle übrigen Plätze laut mSettings, ohne `ir_slot` steht niemand auf IR; `limit` = Positionskürzel am Positionslimit).
- **`spieler`:** Liste der Spieler aus `players.json` plus alle, die laut Tagesstand in einem Kader stehen; Namen, Position und ROS kommen aus `players.json` (Schlüssel `id`). Felder je Spieler:
  - `id, team` (team_id oder 0), `status` (`ONTEAM`, `WAIVERS`, `FREEAGENT`), `inj` (ESPN-Verletzungsstatus, Stand des Abrufs)
  - Besitz ESPN-weit in %: `own` (Anteil der Ligen), `own_d` (Änderung gegenüber dem Vortag), `started` (Anteil gestartet)
  - `waiver_bis` (Epoch-ms, Ende der Waiver-Frist; `null` bei Free Agents und Kaderspielern), `proj` (ESPN-Projektion der Woche `woche`, 2 Stellen), `news` (Epoch-ms der letzten ESPN-Meldung, `null` ohne)
  - `zug` (nur freie Spieler mit Zugewinn, sonst fehlt das Feld): je Horizont `woche`, `drei`, `ros` und `team_id` `{b, n}` – `b` = brutto, um wie viel die beste Aufstellung des Teams mit dem Spieler besser wird (`players.team_gains`; `woche` = Wochenwert N+1, `drei` = Σ der Wochen N+1 … N+3 mit eigener Aufstellung je Woche, `ros` = Grundlage `bedarf_basis`), `n` = netto mit dem günstigsten nötigen Drop (voller Kader oder Position am Limit; am Limit nur dieselbe Position), sonst = `b`; nur Teams mit `b` > 0.
  - Wochensicht: `proj_ue` (Wochenwert − `ersatz_woche` der Position), `proj3` (Σ Wochenwerte über `horizont`: N+1 aus dem Tagesstand, danach aus `wNN/ros.json`, Bye 0; `null` ohne Eintrag im ROS-Auszug), `proj3_ue` (`proj3` − `ersatz_3`); `null` ohne Ersatzniveau der Position oder ohne Wochenpool-Eintrag
  - Kaderspieler, die `players.json` nicht führt (unter der Woche geholt, ohne Spiel, nicht unter den 20 besten Free Agents), tragen zusätzlich `name, pos, nfl` aus dem Wochenpool (`null`, wenn auch dort unbekannt) und – mit Sitemap-Auszug – `fp` wie in `players.json`.
- Quelle: `data/raw/2026/pool/latest.json` (Tageslauf, stündlich vormittags und abends; Kopf `waiver_reihenfolge` = `waiverRank` je Team aus `mTeam`, `waiver_reihenfolge_stand` = Abrufzeit ihrer letzten Änderung; Kopf `ir_slot` = Spieler-IDs im IR-Slot je Team aus `mRoster`, `ir_slot_stand` genauso; Kopf `trades` = per Trade gekommene Kaderspieler aus demselben Aufruf, Grundlage von `keeper.json`); Besitz, Verletzung und Status sind der Stand des Abrufs, ESPN führt keine Historie.

## `wetter.json` (lazy, Wetter je Spiel – Ansicht `#wetter`, Spielerseite, Fähnchen im Waiver-Tab)
- **Kopf:** `stand` (jüngster Wetterabruf, UTC), `woche` (Woche der Prognose oder `null`), `einheiten` (`temp` °C, `wind` und `boeen` km/h, `regen_wahrsch` %, `niederschlag` mm, `schnee` cm), `schwellen` (Faustregel der Markierung: `{"wind": 25, "boeen": 40, "regen_wahrsch": 60, "schnee": 0}`).
- **`prognose`:** die Spiele der laufenden NFL-Woche (W1–17: die erste Woche mit einem noch nicht beendeten Spiel; nach dem letzten Spiel der W17 leer). **`ist`:** alle gespielten Spiele der Saison (ohne `regen_wahrsch`). Felder je Spiel:
  - `id` (ESPN-Spiel-ID), `woche`, `kickoff` (UTC, `JJJJ-MM-TTThh:mmZ`; `null`, wenn ESPN den Anstoß noch offen führt), `tbd` (Anstoß offen, Flex-Spiele der späten Wochen), `heim`, `gast` (NFL-Kürzel), `stadion`, `ort`, `dach` (`offen`, `fest`, `beweglich`), `neutral` (Auslandsspiel)
  - Werte über die Kickoff-Stunde und drei Stunden danach: `temp` (Ø), `wind` (Ø), `boeen` (max), `regen_wahrsch` (max, ganzzahlig), `niederschlag` (Σ), `schnee` (Σ); eine Stelle. Alle `null`, wenn `tbd`.
  - `markierung`: Liste der Schlüssel ab der Schwelle in der Reihenfolge `wind, boeen, regen_wahrsch, schnee` – Python rechnet (`wetter.markierung`) mit dem Wert, wie die App ihn zeigt: Wind, Böen und Regenwahrscheinlichkeit ganzzahlig (aus dem Wert mit einer Stelle, round half up) ≥ Schwelle, Schnee mit einer Stelle > 0; fehlende Werte zählen nicht. Leer bei `tbd` und bei Dachspielen.
  - Dachspiele (`fest`, `beweglich`) tragen dieselben Werte; die App zeigt sie dort nicht als Wetter an.
- Quelle: Open-Meteo (Modellwerte, kein Stationsmesswert), Spielorte aus `data/raw/2026/nfl/stadien.json` (von Hand, gegen die ESPN-Scoreboard-API geprüft). Rohdaten: `data/raw/2026/wetter/prognose/wNN_<UTC>.json` (nur laufende Woche) und `wetter/ist_2026.json` (dauerhaft).

## `claude.json` (kompakt, < 50 KB, für Claude-Sessions unterwegs)
- **Stand:**
  - `legende` (Lesehilfe), `legende_stand` (welche Spalten Tages- und welche Wochenstand sind); jeder Text unter 400 Zeichen (Grenze von `check_public.py`)
  - `stand`: `saison, nach_woche, kader_quelle, ros_nach_woche, matchup_woche` (Woche N+1 des Positions-Matchups), `pool_stand` (Abrufzeit des Tagesstands, UTC, wie `datenstand.pool_stand` im Manifest) und `pool_woche` (`woche` aus `waiver.json`: die Woche von `proj`, deren Spiele als Nächstes anstehen; nicht `datenstand.pool_woche` des Manifests, das den Wochen-Pool meint); beide `null` ohne Tagesstand
- **Liga:**
  - `tabelle`: 10 Teams mit Rang, W-L-T, PF, All-Play-Quote, Matchup-Glück, Effizienz, Form, Score, Power Ranking (μ, E, Rang, Trend) und Playoff-%
  - `spiele`: alle Paarungen mit Ergebnis
- **Spieler** (Tagesstand seit 30.09.2026, Freigabe Stephan): Grundlage sind die Spieler aus `players.json` (Wochenstand nach `nach_woche`); je Spieler kommen `team`, `status` und `inj` aus `waiver.json` wie in der App (`merge()` in `app/js/v_spieler.js`). Spieler ohne Eintrag im Tagesstand behalten den Wochenstand; ohne `waiver.json` (vor dem ersten Tageslauf) gilt überall der Wochenstand.
  - `kader` (Spalten `spieler_spalten`): je Team-Kürzel alle Spieler mit diesem Team laut Tagesstand, nach ESPN-ID, mit Name, Position, NFL-Team, Verletzung (Tagesstand), Ø, Form, Trend, ROS/Spiel, ROS-Rang, `gegner_n1` (Gegner in `matchup_woche`, NFL-Kürzel) und `mu_n1` (Positions-Matchup F dieses Gegners, 3 Stellen, > 1 günstig; beide `null` bei Bye oder ohne Wert); Ø bis `mu_n1` sind Wochenstand. Kaderspieler, die `players.json` nicht führt (unter der Woche geholt), stehen mit `name, pos, nfl` aus `waiver.json` darin (`name` = „Spieler <id>“, wenn auch der Wochenpool ihn nicht kennt), die übrigen Spalten `null`.
  - `free_agents` (Spalten `free_agents_spalten` = `spieler_spalten` + `status, proj, proj3`): je Position die 10 besten Spieler mit Status `WAIVERS` oder `FREEAGENT` laut Tagesstand nach ROS/Spiel (ohne ROS/Spiel nicht dabei); `proj` = ESPN-Projektion der Woche `pool_woche` (wie `waiver.json › proj`), `proj3` = Σ der Wochenwerte `pool_woche` … +2 (wie `waiver.json › proj3`: erste Woche mit Bye, OUT, IR und Sperre 0, danach ROS-Auszug; `null` ohne Eintrag im ROS-Auszug); beide `null` ohne Tagesstand.
- **D/ST und Bewegungen:**
  - `dst`: 32 D/ST mit F, nächste 3, Rest, SoS (Wochenstand) und Besitzer (Team-Kürzel oder Status; laut Tagesstand, damit `dst` und `kader` übereinstimmen, sonst Wochenstand)
  - `transaktionen` (mit `transaktionen_spalten`): die Moves der 14 Tage bis zur letzten Transaktion (Archiv, das der Tageslauf laufend ergänzt)
- **Form:** Tabellen als Spaltenkopf (`*_spalten`) plus Zeilen, Teams als Kürzel (`teams` = Kürzel → Name).

Abruf: `https://raw.githubusercontent.com/frest2101/bwg-fantasy/main/app/data/claude.json`.
