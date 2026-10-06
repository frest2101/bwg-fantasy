"""Rechenwerk (Baustein 2/4): Team-Kennzahlen der BWG Fantasy Liga aus den ESPN-Rohdaten.

Liest data/raw/<saison>/wNN (Baustein 1), rechnet alle abgeschlossenen Wochen und schreibt
data/season_<saison>.json – Grundlage der App (Baustein 4).
Regeln: CLAUDE.md, Abschnitt „Rechenregeln“; Entscheidungen in docs/auftraege/session2.md und session4.md.

Aufrufe:
    python scripts/compute.py                # alle abgeschlossenen Wochen
    python scripts/compute.py --through 2    # nur bis Woche 2
"""

import argparse
import json
import statistics
import sys
from decimal import Decimal

import app_export
import dst
import espn_fetch as ef
import history
import keeper
import matchup
import players
import powerranking
import rawdata
import records
import wetter
from lineup import SLOT_BENCH, SLOT_IR, optimal_points  # noqa: F401 (optimal_points: öffentliche Funktion des Rechenwerks)
from zahlen import HALF, HUNDRED, ONE, ZERO, dec, rounded  # noqa: F401 (dec: bisherige Schnittstelle)

# Score-Kennzahlen (alle: höher = besser) und Gewichtungsprofile laut CLAUDE.md und Auftrag Session 4 (Frage 1);
# das Standardprofil hieß bis 04.10.2026 „Stärke“ (umbenannt, weil Bereich und Spalte des Power Rankings so heißen)
METRICS = ("pf", "allplay", "win", "coaching", "kader", "floor", "form")
PROFILES = {
    "Standard":  {"pf": 30, "allplay": 25, "win": 0, "coaching": 10, "kader": 25, "floor": 10, "form": 0},
    "Verdienst": {"pf": 20, "allplay": 25, "win": 10, "coaching": 30, "kader": 0, "floor": 15, "form": 0},
    "Form":      {"pf": 20, "allplay": 25, "win": 0, "coaching": 10, "kader": 10, "floor": 0, "form": 35},
}
ACTIVE_PROFILE, ACTIVE_NORM = "Standard", "z"
NORMS = ("minmax", "rank", "z")
FORM_WEEKS = 3
# Gepoolte Wochenstreuung σ: Startwert 35 mit dem Gewicht von 20 Freiheitsgraden, läuft mit der Saison aus (Frage 8)
SIGMA_PRIOR, SIGMA_PRIOR_DF = Decimal(35), 20
JSON_PRECISION = {"z": 3}  # z-Normwerte mit drei Stellen (Frage 11 a), sonst zwei


# ---------------------------------------------------------------- Aufstellung

def lineup_values(rows) -> dict:
    """Starter-Summe, Starter-Projektion, Bank-Punkte und Optimal eines Teams aus seinen Kaderzeilen (RosterRow)."""
    starters = projection = bench = ZERO
    candidates = []
    for r in rows:
        if r.slot == SLOT_IR:
            continue  # IR ist nicht startfähig und zählt nirgends
        candidates.append((r.pos, r.actual))
        if r.slot == SLOT_BENCH:
            bench += r.actual
        else:
            starters += r.actual
            projection += r.projection
    return {"starter_sum": starters, "starter_projection": projection, "bench": bench,
            "optimal": optimal_points(candidates)}


def roster_week(entries: list[dict], season: int, week: int) -> dict:
    """Wie lineup_values, direkt aus den mRoster-Einträgen eines Teams (roster.entries)."""
    return lineup_values(rawdata.roster_rows({"teams": [{"id": 0, "roster": {"entries": entries}}]}, season, week))


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


def final_playoff_weeks(season: int, weeks: list[int], last_regular: int, through: int | None = None) -> list[int]:
    """Finale Playoff-Wochen (Stufe 4): W15 … W17 ohne Lücke nach einer ganz gerechneten Regular Season, höchstens bis
    through. Final wie espn_fetch.is_final (alle Spiele mit Gegner entschieden; Freilose zählen nicht). Tabelle,
    All-Play und Score bleiben bei der Regular Season; diese Wochen bestimmen nur den Playoff-Stand."""
    if not weeks or weeks[-1] != last_regular:
        return []
    out = []
    for week in range(last_regular + 1, ef.MAX_WEEK + 1):
        if (through and week > through) or not ef.is_final(season, week):
            break
        out.append(week)
    return out


def season_started(season: int) -> bool:
    """Gibt es lokal schon eine abgeschlossene Woche 1 der Saison?"""
    if 1 not in ef.local_weeks(season):
        return False
    games = [m for m in ef.load_week_matchups(season, 1) if m["away_id"] is not None]
    return bool(games) and all(m["final"] for m in games)


def compute_team_weeks(ssn: rawdata.Season, weeks: list[int]) -> list[dict]:
    """Je Team und Woche: Ergebnis, Aufstellungswerte, Wochenrang, All-Play (Gleichstand = T) und Median-Sieg."""
    rows = []
    for week in weeks:
        by_team: dict[int, list] = {}
        for r in ssn.roster(week):
            by_team.setdefault(r.team_id, []).append(r)
        week_rows = []
        for m in ssn.matchups(week):
            if m["away_id"] is None:
                continue  # Bye (nur Playoffs): kein Spiel
            for side, other in (("home", "away"), ("away", "home")):
                team_id = m[f"{side}_id"]
                if team_id not in by_team:
                    raise ef.FetchError(f"W{week}: Team {team_id} fehlt in mRoster")
                pf, pa = m[f"{side}_points"], m[f"{other}_points"]
                row = {"team_id": team_id, "week": week, "opponent_id": m[f"{other}_id"], "home": side == "home",
                       "pf": pf, "pa": pa, "result": "W" if pf > pa else "L" if pf < pa else "T"}
                row.update(lineup_values(by_team[team_id]))
                row["verschenkt"] = row["optimal"] - pf
                row["efficiency"] = pf / row["optimal"] * HUNDRED if row["optimal"] else None  # Woche, in %
                row["projektions_delta"] = pf - row["starter_projection"]
                row["abweichung"] = row["starter_sum"] - pf  # Prüfpunkt 1: Soll 0
                week_rows.append(row)
        median = statistics.median(r["pf"] for r in week_rows)
        for r in week_rows:
            others = [o["pf"] for o in week_rows if o is not r]
            r["allplay_w"] = sum(1 for pf in others if pf < r["pf"])
            r["allplay_l"] = sum(1 for pf in others if pf > r["pf"])
            r["allplay_t"] = sum(1 for pf in others if pf == r["pf"])
            r["wochenrang"] = 1 + r["allplay_l"]  # Gleichstand teilt sich den besseren Rang
            r["median_win"] = r["pf"] > median
            r["median_abstand"] = r["pf"] - median  # Punkte über (+) oder unter (−) dem Wochenmedian
            r["gegner_abstand"] = r["pa"] - median  # dasselbe für den Gegner
            r["allplay_pct"] = (r["allplay_w"] + HALF * r["allplay_t"]) / len(others) * HUNDRED  # All-Play-Anteil pₜ
            r["gegner_pkt"] = statistics.mean(o["pf"] for o in week_rows) - r["pa"]  # Ligaschnitt − Gegnerpunkte
        rows.extend(sorted(week_rows, key=lambda r: r["team_id"]))
    return rows


def add_matchup(team_weeks: list[dict], sigma: Decimal) -> None:
    """Matchup-Glück je Team-Woche (Beschluss 29.09.2026) und laufende Summe, in place.

    Zählt nur, wenn das Ergebnis der Punkteseite widerspricht: Sieg unter dem Wochenmedian = Glück (+), Niederlage
    über dem Median = Pech (−). Gewicht = (eigener Abstand zum Median + Abstand des Gegners zum Median) / (2σ),
    gekappt bei 1 – der Gegner zählt also genau dort, wo er den Ausschlag gab. Sieg über oder Niederlage unter dem
    Median und Unentschieden = 0 (verdient). Ein Sieg als Wochen-4. ist damit kein Glück; der Wochen-2., der gegen
    den Wochenbesten verliert, hat fast ein volles Spiel Pech.
    """
    running: dict[int, Decimal] = {}
    for r in team_weeks:  # nach Woche sortiert
        weight = min(ONE, (abs(r["median_abstand"]) + abs(r["gegner_abstand"])) / (2 * sigma))
        if r["result"] == "W" and r["median_abstand"] < 0:
            r["matchup_glueck"] = weight
        elif r["result"] == "L" and r["median_abstand"] > 0:
            r["matchup_glueck"] = -weight
        else:
            r["matchup_glueck"] = ZERO
        running[r["team_id"]] = running.get(r["team_id"], ZERO) + r["matchup_glueck"]
        r["matchup_kum"] = running[r["team_id"]]


def league_efficiency(rows: list[dict]) -> Decimal | None:
    """Coaching-Effizienz der Liga über die Zeilen: Σ PF / Σ Optimal in % (None ohne Optimal)."""
    optimal = sum((r["optimal"] for r in rows), ZERO)
    return sum((r["pf"] for r in rows), ZERO) / optimal * HUNDRED if optimal else None


def compute_weeks(team_weeks: list[dict], weeks: list[int]) -> list[dict]:
    """Je Spielwoche: Top-Team, Ligaschnitt, Höchst-, Tiefst-, Medianwert und Liga-Effizienz der Woche."""
    result = []
    for week in weeks:
        rows = [r for r in team_weeks if r["week"] == week]
        pfs = [r["pf"] for r in rows]
        result.append({"week": week, "top_team_id": max(rows, key=lambda r: r["pf"])["team_id"],
                       "ligaschnitt": statistics.mean(pfs), "high": max(pfs), "low": min(pfs),
                       "median": statistics.median(pfs), "effizienz_liga": league_efficiency(rows)})
    return result


# ---------------------------------------------------------------- Saisontabelle und Score

def streak(results: list[str]) -> str:
    """Jüngste Serie gleicher Ergebnisse, z. B. „W2“ (ein Unentschieden ist eine eigene Serie „T1“)."""
    last, length = results[-1], 0
    for r in reversed(results):
        if r != last:
            break
        length += 1
    return f"{last}{length}"


def pooled_sigma(team_weeks: list[dict]) -> Decimal:
    """Gepoolte Wochenstreuung der Team-PF mit Startwert (Frage 8).

    σ² = (Σ Quadratsummen innerhalb der Teams + 20·35²) / (Σ(nᵢ − 1) + 20); nach W2 ≈ 35,5.
    """
    by_team: dict[int, list] = {}
    for r in team_weeks:
        by_team.setdefault(r["team_id"], []).append(r["pf"])
    ss = sum((sum(((pf - statistics.mean(pfs)) ** 2 for pf in pfs), ZERO) for pfs in by_team.values()), ZERO)
    df = sum(len(pfs) - 1 for pfs in by_team.values())
    return ((ss + SIGMA_PRIOR_DF * SIGMA_PRIOR ** 2) / (df + SIGMA_PRIOR_DF)).sqrt()


def form_band(sigma: Decimal, games: int) -> Decimal | None:
    """±-Band der Form Δ aus reinem Zufall: σ·√(1/3 − 1/n); erst ab 4 Spielen definiert (vorher None)."""
    if games <= FORM_WEEKS:
        return None
    return sigma * (Decimal(1) / FORM_WEEKS - Decimal(1) / games).sqrt()


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


def weighted_score(norm: dict[str, Decimal], weights: dict[str, int]) -> Decimal | None:
    """Σ Gewicht × Normwert / Σ Gewichte; None, wenn alle Gewichte 0 sind."""
    total = sum(weights.values())
    return sum((w * norm[m] for m, w in weights.items()), ZERO) / total if total else None


def rank_by(teams: list[dict], key) -> dict[int, int]:
    """Rang 1…n nach absteigendem Schlüssel."""
    return {t["team_id"]: i for i, t in enumerate(sorted(teams, key=key, reverse=True), start=1)}


def wins(t: dict) -> Decimal:
    """Siege mit Unentschieden als halbem Sieg (W + 0,5·T)."""
    return t["w"] + HALF * t["t"]


def compute_teams(ssn: rawdata.Season, weeks: list[int], team_weeks: list[dict], sigma: Decimal,
                  kader_projection: dict[int, Decimal] | None = None) -> list[dict]:
    """Saisontabelle mit allen Team-Kennzahlen und dem Score je Profil und Normierung.

    kader_projection: Kader-Projektion ROS je Team (ab W3, aus players.py). Fehlt sie, nimmt die Score-Kennzahl
    „Kader“ das Kader-Potenzial (Rückblick) – das Feld kader_quelle sagt, welche.
    """
    snapshot = ssn.teams()  # Namen, Divisionen, Waiver-Prio und Moves aus dem jüngsten Abruf („heute“)
    teams = []
    for info in snapshot:
        rows = sorted((r for r in team_weeks if r["team_id"] == info["id"]), key=lambda r: r["week"])
        if not rows:
            raise ef.FetchError(f"Team {info['id']} hat keine gespielte Woche")
        games = len(rows)
        results = [r["result"] for r in rows]
        pf = sum((r["pf"] for r in rows), ZERO)
        optimal = sum((r["optimal"] for r in rows), ZERO)
        projection = sum((r["starter_projection"] for r in rows), ZERO)
        form = statistics.mean(r["pf"] for r in rows[-FORM_WEEKS:])
        allplay_w, allplay_t = sum(r["allplay_w"] for r in rows), sum(r["allplay_t"] for r in rows)
        w, l, t = results.count("W"), results.count("L"), results.count("T")
        kader_potenzial = optimal / games
        team = {
            "team_id": info["id"], "name": info["name"], "division": info["divisionId"],
            "games": games, "w": w, "l": l, "t": t,
            "pf": pf, "pa": sum((r["pa"] for r in rows), ZERO),
            "pf_per_game": pf / games,
            "win_pct": (w + HALF * t) / games * HUNDRED,
            "allplay_w": allplay_w, "allplay_l": sum(r["allplay_l"] for r in rows), "allplay_t": allplay_t,
            "allplay_pct": (allplay_w + HALF * allplay_t) / ((len(snapshot) - 1) * games) * HUNDRED,
            "median_w": sum(1 for r in rows if r["median_win"]),
            "median_l": sum(1 for r in rows if not r["median_win"]),
            # Matchup-Glück = Σ Wochenwerte (add_matchup); Spielplan = Σ (Ligaschnitt − Gegnerpunkte), + = leichte Gegner
            "matchup_glueck": sum((r["matchup_glueck"] for r in rows), ZERO),
            "spielplan_pkt": sum((r["gegner_pkt"] for r in rows), ZERO),
            "optimal": optimal, "verschenkt": optimal - pf,
            "efficiency": pf / optimal * HUNDRED, "kader_potenzial": kader_potenzial,
            "kader_projektion": kader_projection.get(info["id"]) if kader_projection else None,
            "bench": sum((r["bench"] for r in rows), ZERO),
            "floor": min(r["pf"] for r in rows), "form": form, "form_delta": form - pf / games,
            "form_band": form_band(sigma, games),
            "streak": streak(results),
            "projection": projection, "projektions_delta": pf - projection,
            "waiver_prio": info["waiverRank"], "moves": (info["transactionCounter"] or {}).get("acquisitions"),
        }
        team["kader_quelle"] = "projektion" if team["kader_projektion"] is not None else "potenzial"
        teams.append(team)
    by_id = {t["team_id"]: t for t in teams}

    # Ränge: Siege (Unentschieden halb), dann PF – gesamt und je Division
    for tid, rang in rank_by(teams, lambda t: (wins(t), t["pf"])).items():
        by_id[tid]["rang"] = rang
    for division in {t["division"] for t in teams}:
        members = [t for t in teams if t["division"] == division]
        for tid, rang in rank_by(members, lambda t: (wins(t), t["pf"])).items():
            by_id[tid]["rang_division"] = rang

    # Score: jede Kennzahl dreifach normiert, je Profil gewichtet
    raw = {"pf": lambda t: t["pf_per_game"], "allplay": lambda t: t["allplay_pct"], "win": lambda t: t["win_pct"],
           "coaching": lambda t: t["efficiency"], "floor": lambda t: t["floor"], "form": lambda t: t["form"],
           "kader": lambda t: t["kader_projektion"] if t["kader_quelle"] == "projektion" else t["kader_potenzial"]}
    norms = {metric: normalize({t["team_id"]: raw[metric](t) for t in teams}) for metric in METRICS}
    for t in teams:
        t["norm"] = {kind: {metric: norms[metric][kind][t["team_id"]] for metric in METRICS} for kind in NORMS}
        t["score"] = {profile: {kind: weighted_score(t["norm"][kind], weights) for kind in NORMS}
                      for profile, weights in PROFILES.items()}
    for tid, rang in rank_by(teams, lambda t: (t["score"][ACTIVE_PROFILE][ACTIVE_NORM], t["pf_per_game"])).items():
        by_id[tid]["rang_score"] = rang
    return sorted(teams, key=lambda t: t["rang"])


def league_games(ssn: rawdata.Season, weeks: list[int]) -> list[dict]:
    """Alle Paarungen des Liga-Spielplans: Woche, Heim, Gast (None bei Bye), Punkte und Sieger, sobald final.

    Für die gerechneten Wochen kommen Punkte und Sieger aus der Datei der jeweiligen Woche samt Stat-Korrektur
    (espn_fetch.load_week_matchups, wie Tabelle und Rekorde). Weicht der Spielplan der Stand-Woche davon ab, hat ESPN
    nach dem Dienstag korrigiert und der Wochenabruf das noch nicht übernommen – oder nicht übernehmen können, weil die
    Korrektur in sich nicht stimmt (dann meldet er „nicht übernommen“) –, dann eine Warnung am Lauf; nach der
    Übernahme (wNN/statkorrektur.json) ist sie still.
    """
    settings = ssn.settings()["scheduleSettings"]
    week_of = {int(mp): min(wks) for mp, wks in settings["matchupPeriods"].items()}
    own = {m["id"]: m for week in weeks for m in ssn.matchups(week)}
    games = []
    for m in sorted(ssn.schedule(), key=lambda m: (m["matchupPeriodId"], m["id"])):
        home, away = m.get("home"), m.get("away")
        final = m.get("winner") not in (None, "UNDECIDED")
        winner = {"HOME": home and home["teamId"], "AWAY": away and away["teamId"], "TIE": "T"}.get(m.get("winner"))
        game = {"week": week_of.get(m["matchupPeriodId"]), "id": m["id"],
                "playoff": m["matchupPeriodId"] > settings["matchupPeriodCount"],
                "home": home["teamId"] if home else None, "away": away["teamId"] if away else None,
                "home_pf": ef.to_points(home["totalPoints"]) if final and home else None,
                "away_pf": ef.to_points(away["totalPoints"]) if final and away else None,
                "winner": winner if final else None}
        if m["id"] in own and own[m["id"]]["final"]:
            o = own[m["id"]]
            if (game["home_pf"], game["away_pf"]) != (o["home_points"], o["away_points"]):
                ef.warn(f"W{game['week']} Spiel {m['id']}: Spielplan der Stand-Woche {game['home_pf']}:{game['away_pf']}, "
                        f"Wochendatei {o['home_points']}:{o['away_points']} – Stat-Korrektur noch nicht übernommen "
                        f"(der Wochenabruf übernimmt sie nach wNN/{ef.STATKORREKTUR_FILE}, sobald sie in sich stimmt; "
                        f"sonst meldet er dort „nicht übernommen“)")
            pf, pa = o["home_points"], o["away_points"]
            game.update(home_pf=pf, away_pf=pa if o["away_id"] is not None else None,
                        winner=(o["home_id"] if pf > pa else o["away_id"] if pf < pa else "T")
                        if o["away_id"] is not None else None)
        games.append(game)
    return games


def week_status(season: int, through: int) -> dict[int, str]:
    """Wochen nach through, die lokal schon angelegt, aber noch nicht abgeschlossen sind: „laeuft“.

    Bye-Einträge der Playoffs zählen nicht (wie espn_fetch.is_final), sonst bliebe eine Playoff-Woche ewig „laeuft“.
    """
    status = {}
    for week in ef.local_weeks(season):
        if week > through:
            games = [m for m in ef.load_week_matchups(season, week) if m["away_id"] is not None]
            if games and not all(m["final"] for m in games):
                status[week] = "laeuft"
    return status


def projection_by_week(season: int, weeks: list[int], team_weeks: list[dict], current: dict | None) -> dict | None:
    """Kader-Projektion P je Woche für die μ-Reihe des Power Rankings: aus der ros.json der jeweiligen Woche.

    Wochen ohne ros.json fehlen (dort gilt der Vorjahres-Prior); die jüngste Woche kommt schon gerechnet (current).
    """
    by_week = {}
    for week in weeks[:-1]:
        if (ef.week_dir(season, week) / ef.ROS_FILE).exists():
            faktor = players.ligafaktor([r for r in team_weeks if r["week"] <= week])
            kader = players.kader_projection(rawdata.Season(season, week), faktor)
            if kader:
                by_week[week] = kader["teams"]
    if current:
        by_week[weeks[-1]] = current["teams"]
    return by_week or None


def compute_season(season: int = ef.DEFAULT_SEASON, through: int | None = None) -> dict:
    """Komplettes Rechenwerk mit allen Modulen; Zahlen als ungerundete Decimal (gerundet wird erst beim Schreiben).

    Playoff-Stand (Stufe 4): Tabelle, All-Play, Score und Power Ranking rechnen mit der Regular Season (bis W14).
    Stand-Woche = letzte finale Playoff-Woche (W15–17), sonst die letzte gerechnete Woche: aus ihr kommen ROS, Bedarf
    und Altersgewicht (players.compute_players), die gespielten Playoff-Spiele der Endplatz-Simulation und deren Seed.
    """
    last_regular = last_regular_week(season)
    weeks = completed_weeks(season, min(through, last_regular) if through else None)
    playoffs = final_playoff_weeks(season, weeks, last_regular, through)
    ssn = rawdata.Season(season, weeks[-1])
    stand = ssn.at(playoffs[-1]) if playoffs else ssn
    team_weeks = compute_team_weeks(ssn, weeks)
    sigma = pooled_sigma(team_weeks)
    add_matchup(team_weeks, sigma)
    faktor = players.ligafaktor(team_weeks)
    kader = players.kader_projection(ssn, faktor)
    teams = compute_teams(ssn, weeks, team_weeks, sigma, kader_projection=kader["teams"] if kader else None)
    pr = powerranking.compute_power_ranking(ssn, weeks, team_weeks, teams, sigma,
                                            p_by_week=projection_by_week(season, weeks, team_weeks, kader),
                                            p_dev=kader["dev"] if kader else None, stand=stand)
    transactions = records.compute_transactions(ssn)
    spieler = players.compute_players(stand, weeks)
    settings = ssn.settings()["scheduleSettings"]
    return {"season": season, "through_week": weeks[-1], "last_regular_week": last_regular,
            "playoff_woche": playoffs[-1] if playoffs else None,
            "active_profile": ACTIVE_PROFILE, "active_norm": ACTIVE_NORM, "sigma": sigma, "ligafaktor": faktor,
            "divisions": {d["id"]: d["name"] for d in settings.get("divisions", [])},
            "teams": teams, "team_weeks": team_weeks, "weeks": compute_weeks(team_weeks, weeks),
            "week_status": week_status(season, weeks[-1]), "games": league_games(ssn, weeks),
            "power_ranking": pr, "kader": kader,
            "records": records.compute_records(ssn, weeks, team_weeks),
            "transactions": transactions, "transactions_until": transactions.get("bis"),
            # Vorausschau (N+1, nächste 3, Rest, SoS) ab der Stand-Woche; Z, F und Rang bleiben beim Stand W14
            "dst": dst.compute_dst(ssn, weeks, stand.through),
            "matchup": matchup.compute_matchup(ssn, weeks, stand.through),
            "history": history.compute_history(ssn),
            "players": spieler, "ros_after_week": spieler["ros_after_week"],
            "keeper": keeper.compute_keeper(ssn, weeks, spieler, records.player_names(ssn), stand_week=stand.through),
            "pool_week": weeks[-1] if ssn.pool(weeks[-1]) is not None else None,
            # Tageslauf (Session 6): Pool-Auszug und Wetter, Stand des jüngsten Laufs – None, solange er nicht lief
            "pool_latest": ssn.pool_latest(),
            # Wochensicht im Waiver-Tab: NFL-Spielplan (Byes, Anstoß) und Wochenprojektionen des ROS-Auszugs
            "nfl": ssn.nfl(), "nfl_spiele": wetter.season_games(ef.load_json(ef.season_files(season)["schedule"])),
            "ros_projektion": (stand.ros() or {}).get("players"),
            "kader_regeln": players.roster_rules(ssn.settings()),
            "wetter": wetter.compute_wetter(ssn.wetter_prognose(), ssn.wetter_ist(),
                                            {tid: t.abbrev for tid, t in ssn.nfl().items()}),
            # Wochenabruf: FantasyPros-Adressen je Position (Verweis im Spielerprofil) – None, solange er sie nicht holte
            "fantasypros": ssn.fantasypros()}


# ---------------------------------------------------------------- Ausgabe

SEASON_JSON_KEYS = ("season", "through_week", "active_profile", "active_norm", "sigma", "ligafaktor",
                    "teams", "team_weeks", "weeks")


def to_json(season_data: dict) -> dict:
    """Ausgabeform für data/season_<saison>.json (Tabellenkern; alles Weitere steht in app/data):
    zwei Stellen, z-Normwerte drei, Rangpunkte als ganze Zahlen."""
    data = rounded({k: season_data[k] for k in SEASON_JSON_KEYS}, precision=JSON_PRECISION)
    for t in data["teams"]:
        t["norm"]["rank"] = {metric: int(value) for metric, value in t["norm"]["rank"].items()}
    return data


def display_score(value: Decimal) -> Decimal:
    """Score in der Anzeige: 50 + 10·z (z-Normierung)."""
    return 50 + 10 * value


def print_table(season_data: dict) -> None:
    print(f"Stand nach Woche {season_data['through_week']} · Score = 50 + 10·z, Profil {ACTIVE_PROFILE}\n")
    print(f"{'Rang':>4}  {'Team':<18} {'W-L':>5} {'PF':>8} {'All-Play':>9} {'Eff. %':>7} {'Score':>6} {'R Score':>7}")
    for t in season_data["teams"]:
        wl = f"{t['w']}-{t['l']}" + (f"-{t['t']}" if t["t"] else "")
        score = display_score(t["score"][ACTIVE_PROFILE][ACTIVE_NORM])
        print(f"{t['rang']:>4}  {t['name']:<18} {wl:>5} {ef.to_points(t['pf']):>8} "
              f"{t['allplay_w']:>5}-{t['allplay_l']:<3} {ef.to_points(t['efficiency']):>7} "
              f"{score.quantize(Decimal('0.1')):>6} {t['rang_score']:>7}")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
    parser = argparse.ArgumentParser(description="Team-Kennzahlen der BWG Fantasy Liga aus den lokalen Rohdaten.")
    parser.add_argument("--season", type=int, default=ef.DEFAULT_SEASON, help=f"Saison (Standard: {ef.DEFAULT_SEASON})")
    parser.add_argument("--through", type=int, metavar="N",
                        help="nur bis Woche N rechnen (N über W14: Regular Season ganz, Playoff-Stand bis N)")
    args = parser.parse_args(argv)
    if args.through is not None and args.through < 1:
        parser.error("--through muss mindestens 1 sein")
    if args.through is None and not season_started(args.season):
        # Vorsaison (nach dem Saisonwechsel bis W1 final): nichts zu rechnen, kein Fehler – sonst wären die Actions
        # wochenlang rot, gerade in der Keeper- und Draft-Phase, in der das Transaktions-Archiv wichtig ist.
        print(f"Saison {args.season}: noch keine abgeschlossene Woche – nichts zu rechnen.")
        return 0
    try:
        season_data = compute_season(args.season, args.through)
    except (ef.FetchError, KeyError, ValueError) as exc:
        reason = f"fehlender Schlüssel {exc}" if isinstance(exc, KeyError) else exc
        print(f"FEHLER – {reason}", file=sys.stderr)
        return 1
    for r in season_data["team_weeks"]:
        if ef.to_points(r["abweichung"]) != 0:   # Prüfpunkt 1; nach einer übernommenen Stat-Korrektur weiter 0
            ef.warn(f"W{r['week']} Team {r['team_id']}: Starter-Summe weicht von PF ab ({ef.to_points(r['abweichung'])})")
    for warning in season_data["matchup"]["warnungen"]:
        print(f"Warnung: Positions-Matchup {warning}", file=sys.stderr)
    for warning in (season_data["keeper"] or {}).get("warnungen", []):
        print(f"Warnung: Keeper-Bilanz {warning}", file=sys.stderr)
    for warning in (season_data["power_ranking"].get("endplatz") or {}).get("warnungen", []):
        ef.warn(warning)   # in der Action als Hinweis am Lauf sichtbar: Playoff-Annahme prüfen, Stephan fragen
    path = ef.REPO_DIR / "data" / f"season_{args.season}.json"
    path.write_text(json.dumps(to_json(season_data), ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")
    changed = app_export.write(app_export.render(app_export.build(season_data), season_data))
    print_table(season_data)
    print(f"\n-> {ef.rel(path)}")
    print(f"-> {ef.rel(app_export.APP_DATA)}: {', '.join(changed) if changed else 'unverändert'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
