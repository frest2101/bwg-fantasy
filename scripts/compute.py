"""Rechenwerk (Baustein 2): Team-Kennzahlen der BWG Fantasy Liga aus den ESPN-Rohdaten.

Liest data/raw/<saison>/wNN (Baustein 1), rechnet alle abgeschlossenen Wochen und schreibt
data/season_<saison>.json – die Datenquelle der App (Baustein 4).
Regeln: CLAUDE.md, Abschnitt „Rechenregeln“; Entscheidungen in docs/auftraege/session2.md.

Aufrufe:
    python scripts/compute.py                # alle abgeschlossenen Wochen
    python scripts/compute.py --through 2    # nur bis Woche 2
"""

import argparse
import json
import statistics
import sys
from decimal import Decimal

import espn_fetch as ef

SLOT_BENCH, SLOT_IR = 20, 21
QB, RB, WR, TE, K, DST = 1, 2, 3, 4, 5, 16  # defaultPositionId
SOURCE_ACTUAL, SOURCE_PROJECTION = 0, 1       # statSourceId: Ist / Projektion
SPLIT_WEEK = 1                                # statSplitTypeId: Wochenwert

# Score-Kennzahlen (alle: höher = besser) und Gewichtungsprofile laut CLAUDE.md
METRICS = ("pf", "allplay", "win", "coaching", "kader", "floor", "form")
PROFILES = {
    "Stärke":    {"pf": 30, "allplay": 25, "win": 15, "coaching": 10, "kader": 10, "floor": 10, "form": 0},
    "Verdienst": {"pf": 20, "allplay": 25, "win": 10, "coaching": 30, "kader": 0, "floor": 15, "form": 0},
    "Form":      {"pf": 20, "allplay": 25, "win": 0, "coaching": 10, "kader": 10, "floor": 0, "form": 35},
}
ACTIVE_PROFILE = "Stärke"
FORM_WEEKS = 3
ZERO, HUNDRED = Decimal(0), Decimal(100)


def dec(value) -> Decimal:
    """ESPN-Float als Decimal, über str() ohne Binär-Artefakte (ungerundet)."""
    return Decimal(str(value))


# ---------------------------------------------------------------- Aufstellung

def player_points(player: dict, season: int, week: int, source: int) -> Decimal:
    """Ist-Punkte (source 0) oder Projektion (source 1) eines Spielers in einer Woche; ohne Eintrag 0."""
    for stat in player.get("stats", []):
        if (stat.get("seasonId") == season and stat.get("scoringPeriodId") == week
                and stat.get("statSourceId") == source and stat.get("statSplitTypeId") == SPLIT_WEEK):
            return dec(stat.get("appliedTotal", 0))
    return ZERO


def optimal_points(players: list[tuple[int, Decimal]]) -> Decimal:
    """Beste Aufstellung nach CLAUDE.md aus (Position, Punkte) aller startfähigen Rosterspieler.

    Basis = QB1 + RB1–2 + WR1–3 + TE1 + D/ST1–2 + K1. Die übrigen RB/WR/TE („Reste“) füllen
    2 FLEX und OP: opt1 = drei beste Reste, opt2 = QB2 + zwei beste Reste; Optimal = Basis + max(opt1, opt2).
    """
    by_pos = {pos: sorted((p for q, p in players if q == pos), reverse=True) for pos in (QB, RB, WR, TE, K, DST)}
    base = sum((sum(by_pos[pos][:n], ZERO) for pos, n in {QB: 1, RB: 2, WR: 3, TE: 1, DST: 2, K: 1}.items()), ZERO)
    rest = sorted(by_pos[RB][2:] + by_pos[WR][3:] + by_pos[TE][1:], reverse=True)
    qb2 = by_pos[QB][1] if len(by_pos[QB]) > 1 else ZERO
    return base + max(sum(rest[:3], ZERO), qb2 + sum(rest[:2], ZERO))


def roster_week(entries: list[dict], season: int, week: int) -> dict:
    """Starter-Summe, Starter-Projektion, Bank-Punkte und Optimal eines Teams in einer Woche."""
    starters = projection = bench = ZERO
    candidates = []
    for entry in entries:
        slot = entry["lineupSlotId"]
        if slot == SLOT_IR:
            continue  # IR ist nicht startfähig und zählt nirgends
        player = entry["playerPoolEntry"]["player"]
        points = player_points(player, season, week, SOURCE_ACTUAL)
        candidates.append((player["defaultPositionId"], points))
        if slot == SLOT_BENCH:
            bench += points
        else:
            starters += points
            projection += player_points(player, season, week, SOURCE_PROJECTION)
    return {"starter_sum": starters, "starter_projection": projection, "bench": bench,
            "optimal": optimal_points(candidates)}


# ---------------------------------------------------------------- Team-Wochen

def last_regular_week(season: int) -> int:
    """Letzte NFL-Woche der Regular Season laut mSettings (matchupPeriodCount, hier W14)."""
    local = ef.local_weeks(season)
    if not local:
        raise ef.FetchError(f"keine lokalen Daten unter {ef.rel(ef.RAW_DIR / str(season))}")
    s = ef.load_json(ef.week_dir(season, local[0]) / "mSettings.json")["settings"]["scheduleSettings"]
    return max(w for mp, wks in s["matchupPeriods"].items() if int(mp) <= s["matchupPeriodCount"] for w in wks)


def completed_weeks(season: int, through: int | None = None) -> list[int]:
    """Abgeschlossene Wochen der Regular Season ab W1 ohne Lücke, höchstens bis through.

    Playoff-Wochen zählen nicht: dort gibt es Byes und Trostrunden, Tabelle und All-Play gelten nur für W1–14.
    """
    last_regular = last_regular_week(season)
    if through and through > last_regular:
        raise ef.FetchError(f"--through {through}: das Rechenwerk rechnet nur die Regular Season (bis W{last_regular})")
    weeks = []
    for week in ef.local_weeks(season):
        if week != len(weeks) + 1 or week > last_regular or (through and week > through):
            break
        matchups = ef.load_week_matchups(season, week)
        if not matchups or not all(m["final"] for m in matchups):
            break
        weeks.append(week)
    if not weeks:
        raise ef.FetchError(f"keine abgeschlossene Woche unter {ef.rel(ef.RAW_DIR / str(season))}")
    if through and weeks[-1] < through:
        raise ef.FetchError(f"Woche {through} ist lokal nicht abgeschlossen (zuletzt abgeschlossen: W{weeks[-1]})")
    return weeks


def compute_team_weeks(season: int, weeks: list[int]) -> list[dict]:
    """Je Team und Woche: Ergebnis, Aufstellungswerte, Wochenrang, All-Play und Median-Sieg."""
    rows = []
    for week in weeks:
        roster_file = ef.load_json(ef.week_dir(season, week) / "mRoster.json")
        rosters = {t["id"]: t["roster"]["entries"] for t in roster_file["teams"]}
        week_rows = []
        for m in ef.load_week_matchups(season, week):
            if m["away_id"] is None:
                continue  # Bye (nur Playoffs): kein Spiel
            for side, other in (("home", "away"), ("away", "home")):
                team_id = m[f"{side}_id"]
                if team_id not in rosters:
                    raise ef.FetchError(f"W{week}: Team {team_id} fehlt in mRoster")
                pf, pa = m[f"{side}_points"], m[f"{other}_points"]
                row = {"team_id": team_id, "week": week, "opponent_id": m[f"{other}_id"], "home": side == "home",
                       "pf": pf, "pa": pa, "result": "W" if pf > pa else "L" if pf < pa else "T"}
                row.update(roster_week(rosters[team_id], season, week))
                row["verschenkt"] = row["optimal"] - pf
                row["abweichung"] = row["starter_sum"] - pf  # Prüfpunkt 1: Soll 0
                week_rows.append(row)
        median = statistics.median(r["pf"] for r in week_rows)
        for r in week_rows:
            r["allplay_w"] = sum(1 for o in week_rows if o["pf"] < r["pf"])
            r["allplay_l"] = sum(1 for o in week_rows if o["pf"] > r["pf"])
            r["wochenrang"] = 1 + r["allplay_l"]
            r["median_win"] = r["pf"] > median
        rows.extend(week_rows)
    return rows


def compute_weeks(team_weeks: list[dict], weeks: list[int]) -> list[dict]:
    """Je Spielwoche: Top-Team, Ligaschnitt, Höchst-, Tiefst- und Medianwert."""
    result = []
    for week in weeks:
        rows = [r for r in team_weeks if r["week"] == week]
        pfs = [r["pf"] for r in rows]
        result.append({"week": week, "top_team_id": max(rows, key=lambda r: r["pf"])["team_id"],
                       "ligaschnitt": statistics.mean(pfs), "high": max(pfs), "low": min(pfs),
                       "median": statistics.median(pfs)})
    return result


# ---------------------------------------------------------------- Saisontabelle und Score

def streak(results: list[str]) -> str:
    """Jüngste Serie gleicher Ergebnisse, z. B. „W2“."""
    last, length = results[-1], 0
    for r in reversed(results):
        if r != last:
            break
        length += 1
    return f"{last}{length}"


def normalize(values: dict[int, Decimal]) -> dict[str, dict[int, Decimal]]:
    """Min–Max 0–100 (50 bei max = min), Rangpunkte (n − Anzahl besserer Teams), z-Score (Std-Abw. ÷ n)."""
    lo, hi = min(values.values()), max(values.values())
    mean, sd = statistics.mean(values.values()), statistics.pstdev(values.values())
    n = len(values)
    return {
        "minmax": {t: (v - lo) / (hi - lo) * HUNDRED if hi != lo else Decimal(50) for t, v in values.items()},
        "rank": {t: Decimal(n - sum(1 for o in values.values() if o > v)) for t, v in values.items()},
        "z": {t: (v - mean) / sd if sd else ZERO for t, v in values.items()},
    }


def rank_by(teams: list[dict], key) -> dict[int, int]:
    """Rang 1…n nach absteigendem Schlüssel."""
    return {t["team_id"]: i for i, t in enumerate(sorted(teams, key=key, reverse=True), start=1)}


def compute_teams(season: int, weeks: list[int], team_weeks: list[dict]) -> list[dict]:
    last = weeks[-1]
    folder = ef.week_dir(season, last)
    settings = ef.load_json(folder / "mSettings.json")["settings"]["scheduleSettings"]
    schedule = ef.load_json(folder / "mMatchupScore.json")["schedule"]
    # Namen, Divisionen, Waiver-Prio und Moves aus dem jüngsten Abruf (mTeam ist immer ein Snapshot „heute“)
    snapshot = ef.load_json(ef.week_dir(season, ef.local_weeks(season)[-1]) / "mTeam.json")["teams"]

    teams = []
    for info in sorted(snapshot, key=lambda t: t["id"]):
        rows = sorted((r for r in team_weeks if r["team_id"] == info["id"]), key=lambda r: r["week"])
        if not rows:
            raise ef.FetchError(f"Team {info['id']} hat keine gespielte Woche")
        games = len(rows)
        results = [r["result"] for r in rows]
        pf = sum((r["pf"] for r in rows), ZERO)
        optimal = sum((r["optimal"] for r in rows), ZERO)
        projection = sum((r["starter_projection"] for r in rows), ZERO)
        form = statistics.mean(r["pf"] for r in rows[-FORM_WEEKS:])
        allplay_w = sum(r["allplay_w"] for r in rows)
        teams.append({
            "team_id": info["id"], "name": info["name"], "division": info["divisionId"],
            "games": games, "w": results.count("W"), "l": results.count("L"), "t": results.count("T"),
            "pf": pf, "pa": sum((r["pa"] for r in rows), ZERO),
            "pf_per_game": pf / games,
            "win_pct": Decimal(results.count("W")) / games * HUNDRED,
            "allplay_w": allplay_w, "allplay_l": sum(r["allplay_l"] for r in rows),
            "allplay_pct": Decimal(allplay_w) / ((len(snapshot) - 1) * games) * HUNDRED,
            "median_w": sum(1 for r in rows if r["median_win"]),
            "optimal": optimal, "verschenkt": optimal - pf,
            "efficiency": pf / optimal * HUNDRED, "kader_potenzial": optimal / games,
            "bench": sum((r["bench"] for r in rows), ZERO),
            "floor": min(r["pf"] for r in rows), "form": form, "form_delta": form - pf / games,
            "streak": streak(results),
            "projection": projection, "projektions_delta": pf - projection,
            "waiver_prio": info["waiverRank"], "moves": info["transactionCounter"]["acquisitions"],
        })
    by_id = {t["team_id"]: t for t in teams}
    for t in teams:
        t["luck"] = t["w"] - t["allplay_pct"] / HUNDRED * t["games"]

    # Restspielplan: Ø All-Play % der Gegner je offenem Spiel der Regular Season
    last_period = next(int(mp) for mp, wks in settings["matchupPeriods"].items() if last in wks)
    open_games = [m for m in schedule
                  if last_period < m["matchupPeriodId"] <= settings["matchupPeriodCount"] and m.get("away")]
    for t in teams:
        opponents = [m["away"]["teamId"] if m["home"]["teamId"] == t["team_id"] else m["home"]["teamId"]
                     for m in open_games if t["team_id"] in (m["home"]["teamId"], m["away"]["teamId"])]
        t["restspielplan"] = statistics.mean(by_id[o]["allplay_pct"] for o in opponents) if opponents else None

    # Ränge: Siege, dann PF – gesamt und je Division
    for tid, rang in rank_by(teams, lambda t: (t["w"], t["pf"])).items():
        by_id[tid]["rang"] = rang
    for division in {t["division"] for t in teams}:
        members = [t for t in teams if t["division"] == division]
        for tid, rang in rank_by(members, lambda t: (t["w"], t["pf"])).items():
            by_id[tid]["rang_division"] = rang

    # Score: jede Kennzahl dreifach normiert, je Profil gewichtet
    raw = {"pf": "pf_per_game", "allplay": "allplay_pct", "win": "win_pct", "coaching": "efficiency",
           "kader": "kader_potenzial", "floor": "floor", "form": "form"}
    norms = {metric: normalize({t["team_id"]: t[field] for t in teams}) for metric, field in raw.items()}
    for t in teams:
        t["norm"] = {kind: {metric: norms[metric][kind][t["team_id"]] for metric in METRICS}
                     for kind in ("minmax", "rank", "z")}
        t["score"] = {profile: {kind: sum((w * t["norm"][kind][m] for m, w in weights.items()), ZERO)
                                / sum(weights.values()) for kind in ("minmax", "rank", "z")}
                      for profile, weights in PROFILES.items()}
    for tid, rang in rank_by(teams, lambda t: t["score"][ACTIVE_PROFILE]["minmax"]).items():
        by_id[tid]["rang_score"] = rang
    return sorted(teams, key=lambda t: t["rang"])


def compute_season(season: int = ef.DEFAULT_SEASON, through: int | None = None) -> dict:
    """Komplettes Rechenwerk; Zahlen als ungerundete Decimal (gerundet wird erst in to_json)."""
    weeks = completed_weeks(season, through)
    team_weeks = compute_team_weeks(season, weeks)
    return {"season": season, "through_week": weeks[-1], "active_profile": ACTIVE_PROFILE,
            "teams": compute_teams(season, weeks, team_weeks),
            "team_weeks": team_weeks, "weeks": compute_weeks(team_weeks, weeks)}


# ---------------------------------------------------------------- Ausgabe

def rounded(value):
    """Decimal → Zahl mit zwei Stellen (round half up), rekursiv für dict/list."""
    if isinstance(value, Decimal):
        return float(ef.to_points(value))
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


def to_json(season_data: dict) -> dict:
    """Ausgabeform für data/season_<saison>.json: zwei Stellen, Rangpunkte als ganze Zahlen."""
    data = rounded(season_data)
    for t in data["teams"]:
        t["norm"]["rank"] = {metric: int(value) for metric, value in t["norm"]["rank"].items()}
    return data


def print_table(season_data: dict) -> None:
    print(f"Stand nach Woche {season_data['through_week']} · Score = Min–Max, Profil {ACTIVE_PROFILE}\n")
    print(f"{'Rang':>4}  {'Team':<18} {'W-L':>5} {'PF':>8} {'All-Play':>9} {'Eff. %':>7} {'Score':>6} {'R Score':>7}")
    for t in season_data["teams"]:
        print(f"{t['rang']:>4}  {t['name']:<18} {t['w']:>3}-{t['l']:<1} {ef.to_points(t['pf']):>8} "
              f"{t['allplay_w']:>5}-{t['allplay_l']:<3} {ef.to_points(t['efficiency']):>7} "
              f"{ef.to_points(t['score'][ACTIVE_PROFILE]['minmax']):>6} {t['rang_score']:>7}")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
    parser = argparse.ArgumentParser(description="Team-Kennzahlen der BWG Fantasy Liga aus den lokalen Rohdaten.")
    parser.add_argument("--season", type=int, default=ef.DEFAULT_SEASON, help=f"Saison (Standard: {ef.DEFAULT_SEASON})")
    parser.add_argument("--through", type=int, metavar="N", help="nur bis Woche N rechnen")
    args = parser.parse_args(argv)
    if args.through is not None and args.through < 1:
        parser.error("--through muss mindestens 1 sein")
    try:
        season_data = compute_season(args.season, args.through)
    except (ef.FetchError, KeyError, ValueError) as exc:
        reason = f"fehlender Schlüssel {exc}" if isinstance(exc, KeyError) else exc
        print(f"FEHLER – {reason}", file=sys.stderr)
        return 1
    for r in season_data["team_weeks"]:
        if ef.to_points(r["abweichung"]) != 0:
            print(f"Warnung: W{r['week']} Team {r['team_id']}: Starter-Summe weicht von PF ab "
                  f"({ef.to_points(r['abweichung'])})", file=sys.stderr)
    path = ef.REPO_DIR / "data" / f"season_{args.season}.json"
    path.write_text(json.dumps(to_json(season_data), ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")
    print_table(season_data)
    print(f"\n-> {ef.rel(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
