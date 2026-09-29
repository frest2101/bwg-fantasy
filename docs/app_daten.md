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
 "datenstand": {"woche_final": 2, "ros_nach_woche": null, "pool_woche": 2, "transaktionen_bis": 1790000000000},
 "files": {"teams.json": {"v": "<sha256, 12 Zeichen>", "bytes": 13000, "lazy": false}, "…": {}}}
```
Die App lädt `data/manifest.json?t=<jetzt>` und danach jede Datei mit `?v=<v>`. Ist `schema` größer als die Schema-Version der App, zeigt sie „Neue Version – bitte neu laden“.

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
    - All-Play: `win_pct, allplay_w, allplay_l, allplay_t, allplay_pct, median_w, luck, luck_band` (Zufallsband von Luck)
    - Coaching: `optimal, verschenkt, verschenkt_avg, verschenkt_max, efficiency, kader_potenzial, kader_projektion, bench`
    - Form und Projektion: `floor, form, form_delta, form_band, streak, projection, projektions_delta`
    - Ränge und Liga: `waiver_prio, moves, rang, rang_division, rang_score`
  - Score: `norm` `{z, minmax, rank}` je Kennzahl; `score_ref` je Profil und Normierung (Python-Wert, damit der Test die Browserformel prüfen kann).
  - Power Ranking `pr`: `{mu, se, p, p_quelle, e, rang, rang_vorwoche, trend, kernsatz}`
  - Simulation `sim`: `{liga: {playoff, division, bye, restsiege, seeds: [6]}, espn: {…}}` – `liga` = Regel 2026 (Top 3 je Division), `espn` = Top 6 gesamt; dazu `espn_sim` (ESPN-Vergleich oder `null`)
  - `positionen`: `{nach_position: {"QB": {pts, anteil, rang}, …}, nach_slot: {"QB", "RB", "WR", "TE", "FLEX", "OP", "D/ST", "K"}}`
  - `wochen`: Arrays in der Reihenfolge von `meta.weeks` (Einzelwoche, nicht kumuliert): `gegner, heim, pf, pa, ergebnis, wochenrang, allplay_w, allplay_l, allplay_t, allplay_pct` (All-Play-Anteil pₜ der Woche in %), `luck` (Beitrag der Woche = Ergebnis W 1 · T 0,5 · L 0 − pₜ; Σ = `luck` des Teams, je Woche Nullsumme über alle Teams), `luck_kum` (laufende Summe, letzter Wert = `luck`), `median_win, optimal, verschenkt, efficiency` (PF / Optimal der Woche in %), `bank, projektion, projektions_delta, mu, pr_rang`

## `schedule.json` (Erstaufruf)
- **`weeks`:** Liste je Woche 1–17 mit `week`, `start` (Dienstag, ISO-Datum), `status` (`final`, `laeuft`, `offen`) und `playoff` (bool). Für finale Wochen zusätzlich:
  - `ligaschnitt, median, effizienz_liga` (Σ PF / Σ Optimal der Woche in %)
  - `high {team_id, pf}`, `low {team_id, pf}`, `top_team_id`
  - `bank_suende {team_id, verschenkt}`
  - `top_scorer` (10 × `{player_id, name, pos, nfl, team_id, slot, pts, proj}`)
- **`games`:** Liste aller Paarungen mit `week, home, away, home_pf, away_pf, winner` (team_id, `"T"` bei Unentschieden, `null` wenn offen) und `p_home` (Siegchance nach μ, nur offene Spiele).
- **`h2h`:** Liste aller 45 Paare `{a, b, spiele, w_a, l_a, t, pf_diff}`, auch mit `spiele = 0`.
- **`records_rs`, `records_po`:** je Rekord eine Liste von Einträgen (bei Gleichstand mehrere):
  - Team-Woche `{team_id, week, opponent_id, wert}`: `hoechster_score`, `niedrigster_score`, `hoechster_verlierer`, `niedrigster_sieger`, `hoechste_bank`, `meiste_verschenkt`
  - Spiel `{week, team_ids: [Sieger, Verlierer], punkte, wert, unentschieden}`: `groesster_sieg`, `knappstes_ergebnis`
  - Serie `{team_id, weeks: [von, bis], wert, laufend}`: `laengste_siegesserie`, `laengste_niederlagenserie`
  - Spieler `{player_id, name, pos, team_id, week, slot, wert}`: `bester_spieler`

## `players.json` (lazy, Tab Spieler und Teamseite)
- **Kopf:** `ersatz` (Position → Ersatzniveau), `ros_nach_woche`, `cv`, `weeks`.
- **`players`:** Liste. Aufgenommen wird, wer mindestens ein Spiel hat oder im Kader steht, dazu die 20 besten Free Agents je Position nach ROS/Spiel. Felder:
  - Stammdaten: `id, name, pos` (Kürzel) `, nfl` (Kürzel) `, team` (team_id oder 0) `, status, inj, own`
  - Saison: `g, pts, avg, floor, ceil, sd, form, form_d, trend, spark, starts, bench_pts, proj_d`
  - `wk`: Liste je Woche `[pts|null, proj|null, bye 0/1, team_id|0, slot|null]` in der Reihenfolge von `weeks`
  - ROS: `ros, ros_g, rest_g, ros_po, ros_rang, ros_ue`

## `dst.json` (lazy, Unter-Tab D/ST)
- **Kopf:** `ligaschnitt {"2025", "2026"}`, `formel`, `through_week`, `ausloeser_legende` (Schlüssel → Text).
- **`teams`:** Liste je NFL-Team:
  - Offense-Werte: `id, abbrev, bye, z25, z26, n, r25, r26`
  - Faktor und Auslöser: `f, f_vorwoche, delta, rang` (1 = höchstes F), `rang_vorwoche`, `z_last3` (Ø Z der letzten 3 Spiele in Punkten), `ausloeser` (Liste aus `delta`, `z`, `rang`), `beobachten`
  - Sicht der D/ST: `naechste3, rest, sos_po, besitzer, status`
  - `naechste`: die Gegner der Wochen N+1…N+3 als `[{week, opp, f}]`, Bye ohne `opp`

## `history.json` (lazy, Rekorde › Historie)
- `alltime`, `seasons`, `team_seasons`, `champions`, `rekorde` wie `scripts/history.py`.

## `transactions.json` (lazy)
- `spieler` (id → Name), `aufstellungswechsel` (team_id → Zahl).
- `items`: `{id, type, team_id, datum (Epoch-ms), periode, items: [{type ADD/DROP, player_id, name, from_team_id, to_team_id}]}`. `type` ist WAIVER, FREEAGENT, ROSTER (reine Drops) oder TRADE_ACCEPT (ohne Spieler).
- `draft`: `{pick, runde, runden_pick, team_id, player_id, name, keeper}`.

## `claude.json` (kompakt, < 50 KB, für Claude-Sessions unterwegs)
- **Stand:** `legende`, `stand`.
- **Liga:**
  - `tabelle`: 10 Teams mit Rang, W-L-T, PF, All-Play-Quote, Luck, Effizienz, Form, Score, Power Ranking (μ, E, Rang, Trend) und Playoff-%
  - `spiele`: alle Paarungen mit Ergebnis
- **Spieler:**
  - `kader`: alle Kaderspieler mit Name, Position, NFL-Team, Team, Verletzung, Ø, Form, ROS/Spiel und ROS-Rang
  - `free_agents`: die Top 10 je Position nach ROS/Spiel
- **D/ST und Bewegungen:**
  - `dst`: 32 D/ST mit F, nächste 3, Rest, SoS und Besitzer
  - `transaktionen` (mit `transaktionen_spalten`): die Moves der 14 Tage bis zur letzten Transaktion
- **Form:** Tabellen als Spaltenkopf (`*_spalten`) plus Zeilen, Teams als Kürzel (`teams` = Kürzel → Name).

Abruf: `https://raw.githubusercontent.com/frest2101/bwg-fantasy/main/app/data/claude.json`.
