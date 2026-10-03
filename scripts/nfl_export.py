"""Einmaliger Import der DSGVO-Auskunft von nfl.com (BWG-Liga 2015–2025) nach data/history: Wochen 2018–2022.

Quelle ist der CSV-Export der eigenen Auskunft vom 24.09.2026 (19 Dateien), lokal außerhalb des Repos. Das Repo ist öffentlich:
Das Skript öffnet nur drei Dateien und liest daraus nur die Spalten der Positivlisten in DATEIEN. Nutzer-, Konto-,
Paket- und Playoff-Challenge-Dateien, Kader, Waiver, Add/Drops, Aufstellungswechsel, Trades, Kommentare und Trophäen
liest es nicht. Rohdateien kommen nie ins Repo; geschrieben werden nur Saison, Woche, Slot und Ligaergebnisse.
Auch die nfl.com-Liga-ID steht nicht im Code: Geprüft wird nur, dass alle gelesenen Zeilen dieselbe Liga tragen.

- Wochen (league_team_week_stats): alle 10 Teams 2018–2022, game_id = 100000 + Saison. 2020–2022 gibt es je
  Team-Woche mehrere Versionen (Live-Stände, Stat-Korrekturen): Es gilt die letzte nach updated_ts, sie muss
  week_over = 1 tragen. Die Zeitstempel sind US-Pacific; in league_team stehen sie 2025 durchgehend in UTC (7 h
  Versatz, ab 02.11.2025 8 h). Liegt eine Version mit anderen Werten weniger als MIN_ABSTAND vor der letzten, bricht
  der Import ab (dann wäre unsicher, welche die jüngste ist); die Reihenfolge früherer Stände ist egal.
- Paarungen der Regular Season: Punkte gegen = Differenz von total_pts_against zur Vorwoche, Gegner = das Team mit
  genau diesen Punkten (± TOLERANZ); eindeutig, wechselseitig und passend zu matchup_result.
- Playoffs (der Export nennt keinen Gegner): Teilnehmer, Divisionssieger (Bye in Runde 1) und Endplätze aus
  team_seasons.csv. Runde 1 = Sieger (Endplatz 1–4) gegen Verlierer (5–6); Halbfinale = Bye-Teams gegen die Sieger
  der Runde 1; Finalwoche: Finale (1–2), Spiel um Platz 3 (3–4), Spiel um Platz 5 (5–6). Je Runde gelten alle
  Paarungen, in denen jedes Spiel einen Weiterkommenden hat und dieser mehr Punkte hat. Bleiben zwei, entscheidet ein
  Screenshot-Spiel aus matchups_hist.csv (dort zählt nur, wer gegen wen spielte) oder eine von Stephan bestätigte
  Paarung (BESTAETIGT), sonst die Seed-Regel (Entscheidung Stephan 03.10.2026, gilt auch 2022): Divisionssieger Seed 1–2, die übrigen 3–6 nach W, dann PF; Runde 1 3–6 und
  4–5; Halbfinale ohne Neusetzen 1 gegen den Sieger aus 4–5, 2 gegen den Sieger aus 3–6. Sie trifft jede Runde, die
  Punkte, Screenshots oder Bestätigungen festlegen, bis auf die Halbfinale 2020 und 2021 (HALBFINALE_VON_HAND) –
  jede andere Abweichung bricht ab. Jedes Screenshot-Spiel 2018–2022 muss danach mit demselben Sieger unter den Spielen stehen
  (check_screenshots). Das Spiel um Platz 5 in der Finalwoche ist 2018, 2019 und 2022 aus den
  Punkten belegt (in der Halbfinalwoche hatte der Sechste mehr), 2020 und 2021 passen beide Wochen – dort gilt das
  Format der übrigen Jahre. Trostrunde 7–10: Format unbekannt, nicht abgeleitet.
- Hugh Jass 2023–2025 (league_team): Der Export führt ligaweite Tabellen nur bis 2022 (vermutlich, weil die Auskunft an der
  Liga-Owner-Rolle des anfragenden Kontos hängt, bis 2022) und für 2023–2025 nur das eigene Team (team_id 1) als Snapshots der kumulierten Bilanz. Je
  Spielstand (W + L + T) gilt der letzte Snapshot; Wochenwerte = Differenzen. Ohne Gegner und Bank; All-Play steckt
  kumuliert in den Snapshots, wird aber nicht übernommen (nicht beauftragt). Gegenprobe (hj_gegenprobe): dieselbe
  Methode für Hugh Jass 2020–2022 gegen die echten Wochenwerte; 2022 verschob eine Neuberechnung von nfl.com am
  13.12.2022 Punkte aus W1/W2 nach W14 – die Grenze steht mit Zahlen im Kopf der Datei.

Aufruf: python scripts/nfl_export.py <export-ordner> [--check]
  --check schreibt nichts und prüft nur, ob die Dateien in data/history dem Export entsprechen (Exit-Code 1 sonst).
"""

import argparse
import csv
import io
import itertools
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import espn_fetch as ef

GAME_ID_BASIS = 100000
SAISONS = range(2018, 2023)                  # Wochen aller Teams
HJ_SAISONS = range(2023, 2026)               # nur Hugh Jass, nur Regular Season
HJ_GEGENPROBE = range(2020, 2023)            # Snapshots und echte Wochen (2018/2019 nur ein Snapshot je Saison)
HJ_TEAM_ID, HJ_SLOT = 1, 2
# Halbfinale, die nach Runde 1 von Hand neu gepaart wurden: Nur 2020 und 2021 trägt das Commissioner-Protokoll des
# Exports „updated playoff teams“ zwischen Runde 1 und Halbfinale (sonst vor Runde 1), und nur dort weicht das Halbfinale
# von der Seed-Regel ab (2020 belegt per Screenshot, 2021 aus den Punkten; 2021 hängt die Abweichung zusätzlich am
# Tiebreak PF zwischen den beiden 10-4-Divisionssiegern). Gelesen von Hand, das Skript öffnet die Datei nicht.
HALBFINALE_VON_HAND = {2020, 2021}
# Paarungen, die Stephan aus eigenen Unterlagen bestätigt hat (03.10.2026); sie entscheiden wie ein Screenshot-Spiel.
# Halbfinale 2018 Hugh Jass gegen gloane saubande – die Paarung des festen Brackets (neu gesetzt wäre es SaschaM).
BESTAETIGT = {(2018, 15): {frozenset((2, 8))}}
# nfl.com team_id → Franchise-Slot (= ESPN-Team-ID 2026); belegt über PF, PA und Bilanz 2018–2022 (check_season_totals)
NFL_TEAM_SLOT = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 1, 10: 10}
TOLERANZ = Decimal("0.005")
MIN_ABSTAND = timedelta(hours=9)             # über dem größten Zeitzonen-Versatz (8 h im Winter)
CENT = Decimal("0.01")

# Datei-Präfix im Export → Positivliste der gelesenen Spalten
DATEIEN = {
    "wochen": ("nfl_fantasy_league_team_week_stats_", (
        "game_id", "league_id", "team_id", "week", "pts", "bench_pts", "matchup_result", "total_pts_against",
        "breakdown_wins", "breakdown_losses", "breakdown_ties", "week_over", "updated_ts")),
    "teams": ("nfl_fantasy_league_team_", (
        "game_id", "league_id", "team_id", "wins", "losses", "ties", "pts", "pts_against", "updated_ts")),
    "liga": ("nfl_fantasy_league_", (
        "game_id", "league_id", "max_teams", "regular_season_end_week", "playoff_start_week", "playoff_end_week",
        "num_playoff_teams", "updated_ts")),
}

RS, PO = "RS", "PO"
REGULAR, QUARTER, SEMI, FINAL = "Regular Season", "Quarterfinal", "Semifinal", "Final"
PLATZ3, PLATZ5 = "Spiel um Platz 3", "Spiel um Platz 5"
ERGEBNIS = {"win": "W", "loss": "L", "tie": "T"}

TEAM_WEEKS = ("season", "week", "phase", "slot", "pts", "bench_pts", "allplay_w", "allplay_l", "allplay_t", "result")
GAMES = ("season", "week", "round", "slot_a", "slot_b", "pts_a", "pts_b", "winner_slot", "herleitung")
HUGH_JASS = ("season", "week", "slot", "pts", "pts_against", "result")
HUGH_JASS_KOPF = (
    "# Umfang: nur Hugh Jass (Slot 2), nur Regular Season 2023–2025 (je 14 Wochen); ohne Gegner, Bank und All-Play.",
    "# Quelle: DSGVO-Auskunft nfl.com (Export 24.09.2026), Snapshots der kumulierten Bilanz: je Spielstand der letzte",
    "# Snapshot, Wochenwerte als Differenzen (eine Stat-Korrektur zählt in der Woche, in der sie erschien).",
    "# Gegenprobe 2020–2022 mit derselben Methode: {exakt} von {wochen} Wochen exakt, {abw} um höchstens {max} Punkte",
    "# verschoben ({wo}); Saisonsummen und Ergebnisse exakt, einzelne Wochenwerte nicht garantiert.",
)


class ImportFehler(Exception):
    """Der Export passt nicht zu den Annahmen; nichts wird geschrieben."""


# ---------------------------------------------------------------- Lesen

def export_file(folder: Path, prefix: str) -> Path:
    """Die eine Datei <prefix><Datum>.csv im Export (ein längeres Präfix einer anderen Datei zählt nicht)."""
    hits = [p for p in folder.glob(f"{prefix}*.csv") if p.name[len(prefix):-4].isdigit()]
    if len(hits) != 1:
        raise ImportFehler(f"{prefix}<Datum>.csv: {len(hits)} Treffer in {folder}")
    return hits[0]


def read_export(folder: Path, key: str) -> list[dict]:
    """Zeilen einer Exportdatei, nur mit den Spalten der Positivliste."""
    prefix, columns = DATEIEN[key]
    with open(export_file(folder, prefix), encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise ImportFehler(f"{prefix}: Spalten fehlen: {', '.join(missing)}")
        return [{c: r[c] for c in columns} for r in reader]


def one_league(*tables: list[dict]) -> None:
    """Alle gelesenen Zeilen gehören zu einer Liga (die ID selbst kommt nicht ins Repo)."""
    if len({r["league_id"] for rows in tables for r in rows}) != 1:
        raise ImportFehler("Zeilen aus mehr als einer Liga im Export")


def season_of(row: dict) -> int:
    return int(row["game_id"]) - GAME_ID_BASIS


def stamp(row: dict) -> datetime:
    return datetime.fromisoformat(row["updated_ts"])


def points(text: str) -> Decimal:
    """Punkte als Decimal; mehr als zwei Stellen gibt es im Export nicht (sonst Abbruch statt stiller Rundung)."""
    value = Decimal(text)
    if value != value.quantize(CENT):
        raise ImportFehler(f"Punktwert mit mehr als zwei Stellen: {text}")
    return value


def latest(versions: list[dict], values) -> dict:
    """Letzte Version nach updated_ts. Liegt eine Version mit anderen values weniger als MIN_ABSTAND vor ihr, könnte
    wegen der gemischten Zeitzonen jene die jüngste sein → Abbruch. Die Reihenfolge früherer Stände ist egal."""
    last = max(versions, key=stamp)
    for v in versions:
        if values(v) != values(last) and stamp(last) - stamp(v) < MIN_ABSTAND:
            raise ImportFehler(f"Versionen {v['updated_ts']} und {last['updated_ts']} zu dicht für eine sichere Reihenfolge")
    return last


def formats(liga_rows: list[dict]) -> dict[int, dict]:
    """Format je Saison 2018–2022 aus dem jüngsten Liga-Eintrag: Ende der Regular Season, Playoff-Wochen."""
    by_season = defaultdict(list)
    for r in liga_rows:
        by_season[season_of(r)].append(r)
    result = {}
    for season in SAISONS:
        if season not in by_season:
            raise ImportFehler(f"Liga-Einstellungen {season} fehlen")
        r = max(by_season[season], key=stamp)
        fmt = {"teams": int(r["max_teams"]), "rs_end": int(r["regular_season_end_week"]),
               "po_start": int(r["playoff_start_week"]), "po_end": int(r["playoff_end_week"]),
               "po_teams": int(r["num_playoff_teams"])}
        if (fmt["teams"], fmt["po_teams"]) != (10, 6) or fmt["po_start"] != fmt["rs_end"] + 1 \
                or fmt["po_end"] != fmt["po_start"] + 2:
            raise ImportFehler(f"unerwartetes Format {season}: {fmt}")
        result[season] = fmt
    return result


# ---------------------------------------------------------------- Wochen

def latest_weeks(rows: list[dict]) -> dict[tuple[int, int, int], dict]:
    """Je (Saison, Slot, Woche) die letzte Version; sie muss week_over = 1 tragen."""
    versions = defaultdict(list)
    for r in rows:
        if season_of(r) in SAISONS:
            if int(r["team_id"]) not in NFL_TEAM_SLOT:
                raise ImportFehler(f"unbekannte team_id {r['team_id']} ({season_of(r)})")
            versions[(season_of(r), NFL_TEAM_SLOT[int(r["team_id"])], int(r["week"]))].append(r)
    result = {}
    for key, vs in versions.items():
        last = latest(vs, lambda r: (r["pts"], r["bench_pts"], r["total_pts_against"], r["breakdown_wins"]))
        if last["week_over"] != "1":
            raise ImportFehler(f"Woche {key} ohne finale Version")
        result[key] = last
    return result


def team_weeks(latest_rows: dict, fmts: dict[int, dict]) -> list[dict]:
    """Je Saison, Woche und Slot: Phase, Punkte, Bankpunkte, All-Play der Woche (nur RS) und Ergebnis (nur RS)."""
    result = []
    for season, fmt in fmts.items():
        for week in range(1, fmt["po_end"] + 1):
            for slot in range(1, fmt["teams"] + 1):
                r = latest_rows.get((season, slot, week))
                if r is None:
                    raise ImportFehler(f"Woche fehlt: {season} W{week} Slot {slot}")
                phase = RS if week <= fmt["rs_end"] else PO
                row = {"season": season, "week": week, "phase": phase, "slot": slot,
                       "pts": points(r["pts"]), "bench_pts": points(r["bench_pts"])}
                if phase == RS:
                    if r["matchup_result"] not in ERGEBNIS:
                        raise ImportFehler(f"Ergebnis fehlt: {season} W{week} Slot {slot}")
                    row.update(allplay_w=int(r["breakdown_wins"]), allplay_l=int(r["breakdown_losses"]),
                               allplay_t=int(r["breakdown_ties"] or 0), result=ERGEBNIS[r["matchup_result"]])
                else:
                    if r["matchup_result"] or any(r[k] not in ("", "0") for k in
                                                  ("breakdown_wins", "breakdown_losses", "breakdown_ties")):
                        raise ImportFehler(f"Playoff-Woche mit Ergebnis oder All-Play: {season} W{week} Slot {slot}")
                    row.update(allplay_w=None, allplay_l=None, allplay_t=None, result=None)
                result.append(row)
    return result


def rs_games(latest_rows: dict, weeks: list[dict]) -> list[dict]:
    """Paarungen der Regular Season aus den Punkten gegen; je Spiel eine Zeile aus Sicht des Siegers."""
    pts = {(w["season"], w["week"], w["slot"]): w for w in weeks}
    games = []
    for (season, week), slots in sorted(_by_week(weeks, RS).items()):
        opponent = {}
        for slot in slots:
            before = Decimal(latest_rows[(season, slot, week - 1)]["total_pts_against"]) if week > 1 else Decimal(0)
            against = Decimal(latest_rows[(season, slot, week)]["total_pts_against"]) - before
            hits = [o for o in slots if o != slot and abs(pts[(season, week, o)]["pts"] - against) <= TOLERANZ]
            if len(hits) != 1:
                raise ImportFehler(f"Gegner nicht eindeutig: {season} W{week} Slot {slot} ({len(hits)} Treffer)")
            opponent[slot] = hits[0]
        for slot, opp in opponent.items():
            if opponent[opp] != slot:
                raise ImportFehler(f"Paarung nicht wechselseitig: {season} W{week} Slot {slot}")
            mine, theirs = pts[(season, week, slot)], pts[(season, week, opp)]
            expected = "W" if mine["pts"] > theirs["pts"] else "L" if mine["pts"] < theirs["pts"] else "T"
            if mine["result"] != expected:
                raise ImportFehler(f"Ergebnis passt nicht zu den Punkten: {season} W{week} Slot {slot}")
            if expected == "W" or (expected == "T" and slot < opp):
                games.append(game(season, week, REGULAR, mine, theirs, "Punkte gegen"))
    return games


def _by_week(weeks: list[dict], phase: str) -> dict[tuple[int, int], list[int]]:
    result = defaultdict(list)
    for w in weeks:
        if w["phase"] == phase:
            result[(w["season"], w["week"])].append(w["slot"])
    return result


def game(season: int, week: int, round_: str, a: dict, b: dict, herleitung: str) -> dict:
    """Spielzeile; a ist der Sieger (bei Gleichstand der kleinere Slot)."""
    winner = a["slot"] if a["pts"] > b["pts"] else b["slot"] if b["pts"] > a["pts"] else None
    return {"season": season, "week": week, "round": round_, "slot_a": a["slot"], "slot_b": b["slot"],
            "pts_a": a["pts"], "pts_b": b["pts"], "winner_slot": winner, "herleitung": herleitung}


# ---------------------------------------------------------------- Playoffs

def seeds(field: list[int], teams: dict[int, dict]) -> list[int]:
    """Seed-Regel: die beiden Divisionssieger auf Seed 1–2, die übrigen vier auf 3–6, je nach W, dann PF
    (Tiebreaker „Points For“ seit 2018). Ein Gleichstand in W und PF bricht ab."""
    def key(s):
        return -int(teams[s]["w"]), -Decimal(teams[s]["pf"])
    groups = [sorted((s for s in field if (teams[s]["div_rank"] == "1") == bye), key=key) for bye in (True, False)]
    for group in groups:
        if any(key(a) == key(b) for a, b in zip(group, group[1:])):
            raise ImportFehler("Seed-Regel: Gleichstand in W und PF")
    return groups[0] + groups[1]


def rule_pairs(seed: list[int], place: dict[int, int]) -> dict[str, set[frozenset]]:
    """Paarungen laut Seed-Regel: Runde 1 Seed 3–6 und 4–5; Halbfinale ohne Neusetzen, 1 gegen den Sieger aus 4–5 und
    2 gegen den Sieger aus 3–6 (wie die Annahme zu ESPN 2026). Sieger der Runde 1 = Endplatz 1–4."""
    s1, s2, s3, s4, s5, s6 = seed
    def winner(a, b):
        return a if place[a] <= 4 else b
    return {QUARTER: {frozenset((s3, s6)), frozenset((s4, s5))},
            SEMI: {frozenset((s1, winner(s4, s5))), frozenset((s2, winner(s3, s6)))}}


def playoff_games(season: int, fmt: dict, weeks: list[dict], seasons_rows: list[dict],
                  screenshots: list[dict]) -> list[dict]:
    """Bracket einer Saison aus Endplätzen, Punkten, Screenshot-Spielen und Seed-Regel. Siehe Moduldoku."""
    teams = {int(r["slot"]): r for r in seasons_rows if int(r["season"]) == season}
    place = {slot: int(r["final_rank"]) for slot, r in teams.items()}
    field = sorted(slot for slot, r in teams.items() if r["playoffs"] == "1")
    byes = sorted(slot for slot in field if teams[slot]["div_rank"] == "1")
    if len(field) != fmt["po_teams"] or len(byes) != 2 or sorted(place[s] for s in field) != list(range(1, 7)):
        raise ImportFehler(f"Playoff-Feld {season} passt nicht zu team_seasons.csv")
    pts = {(w["week"], w["slot"]): w for w in weeks if w["season"] == season}
    r1 = [s for s in field if s not in byes]
    r1_sieger = sorted(s for s in r1 if place[s] <= 4)
    week1, week2, week3 = fmt["po_start"], fmt["po_start"] + 1, fmt["po_end"]
    shots = defaultdict(set)
    for m in screenshots:
        if int(m["season"]) == season:
            shots[int(m["week"])].add(frozenset((int(m["slot_a"]), int(m["slot_b"]))))
    rule = rule_pairs(seeds(field, teams), place)

    def as_set(option):
        return {frozenset(p) for p in option}

    games = []
    for week, round_, teams_a, teams_b, weiter in (
            (week1, QUARTER, r1_sieger, sorted(s for s in r1 if place[s] > 4), lambda s: place[s] <= 4),
            (week2, SEMI, byes, r1_sieger, lambda s: place[s] <= 2)):
        options = []
        for perm in itertools.permutations(teams_b):
            pairs = list(zip(teams_a, perm))
            if all(weiter(a) != weiter(b) for a, b in pairs):
                for a, b in pairs:
                    if pts[(week, a)]["pts"] == pts[(week, b)]["pts"]:
                        raise ImportFehler(f"Gleichstand im Playoff-Spiel {season} W{week}: von Hand prüfen")
                if all((pts[(week, a)]["pts"] > pts[(week, b)]["pts"]) == weiter(a) for a, b in pairs):
                    options.append(pairs)
        teilnehmer = set(teams_a) | set(teams_b)
        shown = {p for p in shots[week] if p <= teilnehmer}
        confirmed = BESTAETIGT.get((season, week), set())
        if not all(p <= teilnehmer for p in confirmed):
            raise ImportFehler(f"bestätigte Paarung passt nicht zur Runde: {season} W{week} {round_}")
        matching = [o for o in options if shown | confirmed <= as_set(o)]
        by_shots = [o for o in options if shown <= as_set(o)]
        by_rule = [o for o in matching if as_set(o) == rule[round_]]
        if len(matching) == 1:
            chosen = matching[0]
            herleitung = "Bracket" if len(options) == 1 else "Screenshot" if len(by_shots) == 1 else "Bestätigt"
        elif by_rule:
            chosen, herleitung = by_rule[0], "Seed-Regel"
        else:
            raise ImportFehler(f"keine Paarung passt zu Punkten, Screenshots und Seed-Regel: {season} W{week} {round_}")
        von_hand = round_ == SEMI and season in HALBFINALE_VON_HAND
        if (as_set(chosen) == rule[round_]) == von_hand:
            raise ImportFehler(f"Seed-Regel {'trifft' if von_hand else 'widerspricht'} {season} {round_} "
                               "(HALBFINALE_VON_HAND prüfen)")
        for a, b in chosen:
            winner, loser = (a, b) if weiter(a) else (b, a)
            games.append(game(season, week, round_, pts[(week, winner)], pts[(week, loser)], herleitung))

    by_place = {place[s]: s for s in field}
    for round_, (better, worse) in ((FINAL, (1, 2)), (PLATZ3, (3, 4)), (PLATZ5, (5, 6))):
        a, b = pts[(week3, by_place[better])], pts[(week3, by_place[worse])]
        if a["pts"] <= b["pts"]:
            raise ImportFehler(f"{round_} {season} W{week3}: Endplatz {better} hat nicht mehr Punkte")
        games.append(game(season, week3, round_, a, b, "Endplatz"))
    return games


# ---------------------------------------------------------------- Hugh Jass 2023–2025

def hugh_jass(team_rows: list[dict], seasons_rows: list[dict], rs_games_by_season: dict[int, int],
              seasons=HJ_SAISONS) -> list[dict]:
    """Wochen der Regular Season von Hugh Jass aus den Snapshots der kumulierten Bilanz (Standard 2023–2025)."""
    result = []
    for season in seasons:
        snaps = [r for r in team_rows if season_of(r) == season and int(r["team_id"]) == HJ_TEAM_ID and r["wins"]]
        by_count = defaultdict(list)
        for r in snaps:
            by_count[int(r["wins"]) + int(r["losses"]) + int(r["ties"] or 0)].append(r)
        n_games = rs_games_by_season[season]
        if sorted(by_count) != list(range(1, n_games + 1)):
            raise ImportFehler(f"Hugh Jass {season}: Spielstände {sorted(by_count)} statt 1–{n_games}")
        prev = {"wins": 0, "losses": 0, "ties": 0, "pts": Decimal(0), "pa": Decimal(0)}
        for n in range(1, n_games + 1):
            r = latest(by_count[n], lambda r: (r["wins"], r["losses"], r["ties"], r["pts"], r["pts_against"]))
            now = {"wins": int(r["wins"]), "losses": int(r["losses"]), "ties": int(r["ties"] or 0),
                   "pts": points(r["pts"]), "pa": points(r["pts_against"])}
            step = {k: now[k] - prev[k] for k in ("wins", "losses", "ties")}
            if sorted(step.values()) != [0, 0, 1]:
                raise ImportFehler(f"Hugh Jass {season}: Spielstand {n} ist kein einzelnes Spiel")
            res = "W" if step["wins"] else "L" if step["losses"] else "T"
            pf, pa = now["pts"] - prev["pts"], now["pa"] - prev["pa"]
            if res != ("W" if pf > pa else "L" if pf < pa else "T"):
                raise ImportFehler(f"Hugh Jass {season} W{n}: Ergebnis passt nicht zu den Punkten")
            result.append({"season": season, "week": n, "slot": HJ_SLOT, "pts": pf, "pts_against": pa, "result": res})
            prev = now
        ts = next(r for r in seasons_rows if int(r["season"]) == season and int(r["slot"]) == HJ_SLOT)
        if (prev["wins"], prev["losses"], prev["pts"], prev["pa"]) != \
                (int(ts["w"]), int(ts["l"]), Decimal(ts["pf"]), Decimal(ts["pa"])):
            raise ImportFehler(f"Hugh Jass {season}: Endstand weicht von team_seasons.csv ab")
    return result


# ---------------------------------------------------------------- Prüfung gegen data/history

def check_season_totals(weeks: list[dict], games: list[dict], seasons_rows: list[dict]) -> None:
    """50 Team-Saisons 2018–2022: PF, PA und W-L der Regular Season exakt wie in team_seasons.csv (belegt das Mapping)."""
    for r in seasons_rows:
        season, slot = int(r["season"]), int(r["slot"])
        if season not in SAISONS:
            continue
        mine = [w for w in weeks if (w["season"], w["slot"], w["phase"]) == (season, slot, RS)]
        pa = sum((g["pts_b"] if g["slot_a"] == slot else g["pts_a"] for g in games
                  if g["season"] == season and g["round"] == REGULAR and slot in (g["slot_a"], g["slot_b"])),
                 Decimal(0))
        got = (sum((w["pts"] for w in mine), Decimal(0)), pa,
               sum(w["result"] == "W" for w in mine), sum(w["result"] == "L" for w in mine))
        if got != (Decimal(r["pf"]), Decimal(r["pa"]), int(r["w"]), int(r["l"])):
            raise ImportFehler(f"Saison {season} Slot {slot}: PF/PA/Bilanz weichen von team_seasons.csv ab")


def hj_gegenprobe(team_rows: list[dict], seasons_rows: list[dict], rs_games_by_season: dict[int, int],
                  weeks: list[dict], games: list[dict]) -> dict:
    """Snapshot-Methode für Hugh Jass 2020–2022 gegen die echten Wochenwerte (PF aus den Wochen, PA aus den Spielen):
    Zahl der Wochen, der abweichenden Wochen, größte Abweichung und die abweichenden Wochen."""
    pf = {(w["season"], w["week"]): w["pts"] for w in weeks if w["slot"] == HJ_SLOT and w["phase"] == RS}
    pa = {(g["season"], g["week"]): g["pts_b"] if g["slot_a"] == HJ_SLOT else g["pts_a"]
          for g in games if g["round"] == REGULAR and HJ_SLOT in (g["slot_a"], g["slot_b"])}
    off = {}
    for r in hugh_jass(team_rows, seasons_rows, rs_games_by_season, HJ_GEGENPROBE):
        key = (r["season"], r["week"])
        d = max(abs(r["pts"] - pf[key]), abs(r["pts_against"] - pa[key]))
        if d:
            off[key] = d
    n = sum(rs_games_by_season[s] for s in HJ_GEGENPROBE)
    return {"wochen": n, "exakt": n - len(off), "abw": len(off), "max": max(off.values(), default=Decimal(0)),
            "wo": ", ".join(f"{s} W{w}" for s, w in sorted(off)) or "keine"}


def check_confirmed(fmts: dict[int, dict]) -> None:
    """Jede bestätigte Paarung trifft Runde 1 oder Halbfinale einer Saison des Exports – sonst würde sie nie gelesen."""
    for season, week in BESTAETIGT:
        if season not in fmts or week not in (fmts[season]["po_start"], fmts[season]["po_start"] + 1):
            raise ImportFehler(f"bestätigte Paarung {season} W{week} liegt nicht in Runde 1 oder Halbfinale")


def check_screenshots(games: list[dict], screenshots: list[dict]) -> None:
    """Jedes Screenshot-Spiel 2018–2022 (auch live/partial: der Sieger ist belegt) steht mit demselben Sieger unter den
    abgeleiteten Spielen – sonst widerspricht die Herleitung einer Primärquelle."""
    for m in screenshots:
        season, week = int(m["season"]), int(m["week"])
        if season not in SAISONS:
            continue
        pair = {int(m["slot_a"]), int(m["slot_b"])}
        hits = [g for g in games if (g["season"], g["week"]) == (season, week) and {g["slot_a"], g["slot_b"]} == pair]
        if len(hits) != 1 or hits[0]["winner_slot"] != int(m["winner_slot"]):
            raise ImportFehler(f"Screenshot-Spiel {season} W{week} fehlt oder hat einen anderen Sieger")


# ---------------------------------------------------------------- Schreiben

def cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def to_csv(columns: tuple, rows: list[dict], head: tuple = ()) -> str:
    out = io.StringIO()
    for line in head:
        out.write(line + "\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for r in rows:
        writer.writerow([cell(r[c]) for c in columns])
    return out.getvalue()


def build(folder: Path) -> dict[str, str]:
    """Alle Ausgabedateien als Text (Dateiname → Inhalt); prüft vorher alles, was der Auftrag verlangt."""
    history = ef.REPO_DIR / "data" / "history"
    seasons_rows = read_csv(history / "team_seasons.csv")
    rs_games_by_season = {int(r["season"]): int(r["rs_games"]) for r in read_csv(history / "seasons.csv")}
    screenshots = read_csv(history / "matchups_hist.csv")

    liga, wochen, teams = (read_export(folder, key) for key in ("liga", "wochen", "teams"))
    one_league(liga, wochen, teams)
    fmts = formats(liga)
    check_confirmed(fmts)
    for season, fmt in fmts.items():
        if fmt["rs_end"] != rs_games_by_season[season]:
            raise ImportFehler(f"Regular Season {season}: Export {fmt['rs_end']} Wochen, seasons.csv anders")
    latest_rows = latest_weeks(wochen)
    weeks = team_weeks(latest_rows, fmts)
    games = rs_games(latest_rows, weeks)
    for season, fmt in fmts.items():
        games += playoff_games(season, fmt, weeks, seasons_rows, screenshots)
    check_season_totals(weeks, games, seasons_rows)
    check_screenshots(games, screenshots)
    hj = hugh_jass(teams, seasons_rows, rs_games_by_season)
    probe = hj_gegenprobe(teams, seasons_rows, rs_games_by_season, weeks, games)
    kopf = tuple(line.format(**dict(probe, max=f"{probe['max']:.2f}".replace(".", ","))) for line in HUGH_JASS_KOPF)

    games.sort(key=lambda g: (g["season"], g["week"], g["slot_a"]))
    return {
        "team_weeks.csv": to_csv(TEAM_WEEKS, weeks),
        "games.csv": to_csv(GAMES, games),
        "hugh_jass_2023_2025.csv": to_csv(HUGH_JASS, hj, kopf),
    }


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="DSGVO-Auskunft nfl.com → data/history (Wochen 2018–2022)")
    parser.add_argument("ordner", type=Path, help="Ordner mit den CSV-Dateien des Exports (außerhalb des Repos)")
    parser.add_argument("--check", action="store_true", help="nichts schreiben, nur mit data/history vergleichen")
    args = parser.parse_args(argv)
    try:
        files = build(args.ordner)
    except ImportFehler as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 1
    history = ef.REPO_DIR / "data" / "history"
    if args.check:
        stale = [name for name, text in files.items()
                 if not (history / name).exists() or (history / name).read_text(encoding="utf-8") != text]
        print("aktuell" if not stale else f"weicht ab: {', '.join(stale)}")
        return 1 if stale else 0
    for name, text in files.items():
        (history / name).write_text(text, encoding="utf-8", newline="\n")
        rows = sum(1 for line in text.splitlines() if not line.startswith("#")) - 1
        print(f"geschrieben: data/history/{name} ({rows} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
