"""D/ST-Faktoren (Baustein 4): wie viele D/ST-Punkte jede NFL-Offense zulässt und was das für den Spielplan einer D/ST heißt.

Löst das D/ST-Board in Notion ab. Regeln: Beschluss Stephan 28.09.2026 (docs/auftraege/session4_vorbereitung.md §2)
und Auftrag Session 4, Frage 9.
- Off. zugelassen Z (je Offense und Saison) = Ø der D/ST-Punkte (Liga-Scoring, appliedTotal), die die gegnerische
  D/ST gegen sie erzielt hat; nur Spiele mit stats["210"] == 1 der D/ST, Gegner aus dem NFL-Spielplan der Saison.
- Ligaschnitt LS = Ø der Z über alle Offenses mit mindestens einem Spiel; r = Z/LS.
- Faktor F = (n·r26 + 5·r25 + 5·1,00)/(n + 10), n = Spiele der Offense in der laufenden Saison.
  Die alte Notion-Formel (n·r26 + 5·r25)/(n + 5) dient nur als Test der Datenkette (docs/referenz_dst.md).
- Für eine D/ST: nächste 3 = Ø F der Gegner in den Kalenderwochen N+1…N+3, Rest = N+1…14, SoS = W15–17;
  eine Woche ohne Gegner im NFL-Spielplan (Bye) fällt heraus.
F > 1 heißt: Gegen diese Offense holen D/ST mehr Punkte als im Schnitt (gutes Matchup für die D/ST).
Die Faktorreihe je Woche wird bei jedem Lauf neu aus den Rohdaten gerechnet; es gibt keinen gespeicherten Zwischenstand.
"""

import statistics
from decimal import Decimal

import espn_fetch as ef
import rawdata
from lineup import DST
from zahlen import ONE, ZERO, dec

PRIOR_GAMES = 5            # Gewicht des Vorjahrs, in Spielen
MEAN_GAMES = 5             # Gewicht des Ligamittels 1,00, in Spielen (nur neue Formel)
NEXT_WEEKS = 3             # „nächste 3“ nach Kalenderwochen
LAST_GAMES = 3             # Auslöser 2: Ø der letzten 3 Spiele der Offense
DST_CV = Decimal("0.55")   # Streuung eines D/ST-Spiels relativ zum Ligaschnitt (Positions-CV D/ST, Frage 11 b)
DELTA_TRIGGER = Decimal("0.10")
Z_TRIGGER = 2
RANK_TRIGGER = 5
WATCH_COUNT = 3            # „beobachten“: die drei größten |z|

FORMEL = "F = (n·r26 + 5·r25 + 5·1,00)/(n + 10); r = Z/Ligaschnitt; Z = Ø D/ST-Punkte der Gegner je Spiel"
FORMEL_ALT = "F_alt = (n·r26 + 5·r25)/(n + 5) (Notion bis W2, nur zum Vergleich)"
AUSLOESER = {
    "delta": "|F − F Vorwoche| ≥ 0,10",
    "z": "|z| ≥ 2: die letzten 3 Spiele weichen stärker vom Saisonschnitt ab, als Zufall erklärt (ab 4 Spielen)",
    "rang": "Rang nach F um mindestens 5 Plätze verschoben",
}
# Stellen im JSON (Frage 11 a): F, r und die daraus gemittelten Spielplan-Faktoren 3, z 3, Punkte und Z 2
PRECISION = {k: 3 for k in ("f", "f_alt", "f_vorwoche", "delta", "r25", "r26", "naechste3", "rest", "sos_po",
                            "naechste3_alt", "rest_alt", "f_verlauf", "z")}


# ---------------------------------------------------------------- Punkte und Off. zugelassen

def prior_points(data: dict, season: int) -> dict[int, dict[int, Decimal]]:
    """D/ST-Punkte je NFL-Team und Woche aus der Rohantwort basis/kona_dst_<Jahr>.json; nur Ist-Wochen der Saison mit 210 == 1."""
    points: dict[int, dict[int, Decimal]] = {}
    for entry in data["players"]:
        player = entry["player"]
        if player["defaultPositionId"] != DST:
            continue
        for s in player.get("stats", []):
            if ((s.get("seasonId"), s.get("statSourceId"), s.get("statSplitTypeId"))
                    == (season, rawdata.STAT_ACTUAL, rawdata.SPLIT_WEEK) and rawdata.played(s)):
                points.setdefault(player["proTeamId"], {})[s["scoringPeriodId"]] = dec(s["appliedTotal"])
    return {t: dict(sorted(w.items())) for t, w in sorted(points.items())}


def pool_points(pools: dict[int, list]) -> dict[int, dict[int, Decimal]]:
    """D/ST-Punkte je NFL-Team und Woche aus den Spielerpools {Woche: [PoolRow]}; nur gespielt (210 == 1)."""
    points: dict[int, dict[int, Decimal]] = {}
    for week, rows in sorted(pools.items()):
        for r in rows:
            if r.pos == DST and r.played:
                points.setdefault(r.pro_team, {})[week] = r.actual
    return {t: dict(sorted(w.items())) for t, w in sorted(points.items())}


def allowed(points: dict[int, dict[int, Decimal]], nfl: dict) -> dict[int, dict[int, Decimal]]:
    """Offense → {Woche: Punkte der gegnerischen D/ST}; Gegner laut NFL-Spielplan (rawdata.NflTeam.opponents)."""
    result: dict[int, dict[int, Decimal]] = {}
    for dst_team, weeks in points.items():
        for week, pts in weeks.items():
            offense = nfl[dst_team].opponents.get(week)
            if offense is None:
                raise ValueError(f"D/ST {nfl[dst_team].abbrev} hat in W{week} gespielt, laut NFL-Spielplan aber Bye")
            if week in result.get(offense, {}):
                raise ValueError(f"W{week}: Offense {nfl[offense].abbrev} hat laut NFL-Spielplan zwei Gegner")
            result.setdefault(offense, {})[week] = pts
    return {o: dict(sorted(w.items())) for o, w in sorted(result.items())}


def means(games: dict[int, dict[int, Decimal]]) -> dict[int, Decimal]:
    """Z je Offense = Ø ihrer Spiele; Offenses ohne Spiel fehlen."""
    return {o: statistics.mean(w.values()) for o, w in games.items() if w}


def league_average(z: dict[int, Decimal]) -> Decimal | None:
    """Ligaschnitt LS = Ø der Z über die Offenses mit mindestens einem Spiel; None ohne Spiel."""
    return statistics.mean(z.values()) if z else None


# ---------------------------------------------------------------- Faktor und Stand je Woche

def factor(n: int, r26: Decimal | None, r25: Decimal, new: bool = True) -> Decimal:
    """F = (n·r26 + 5·r25 + 5·1,00)/(n + 10); alt: (n·r26 + 5·r25)/(n + 5). Bei n = 0 zählt r26 nicht."""
    own = n * r26 if n else ZERO
    if new:
        return (own + PRIOR_GAMES * r25 + MEAN_GAMES * ONE) / (n + PRIOR_GAMES + MEAN_GAMES)
    return (own + PRIOR_GAMES * r25) / (n + PRIOR_GAMES)


def ranks(values: dict[int, Decimal]) -> dict[int, int]:
    """Rang 1 = höchster F (günstigstes Matchup für D/ST); Gleichstand teilt sich den besseren Rang."""
    return {t: 1 + sum(1 for o in values.values() if o > v) for t, v in values.items()}


def season_state(allowed26: dict[int, dict[int, Decimal]], upto: int, r25: dict[int, Decimal]) -> dict:
    """Stand nach Woche upto (0 = vor der Saison): Spiele, Z26, n, LS26, r26, F neu und alt, Rang je Offense.

    Alle Offenses aus r25 bekommen einen Faktor; ohne Spiel gilt n = 0, also F = (5·r25 + 5)/10.
    """
    games = {o: {w: p for w, p in weeks.items() if w <= upto} for o, weeks in allowed26.items()}
    games = {o: g for o, g in games.items() if g}
    z26 = means(games)
    ls26 = league_average(z26)
    r26 = {o: z / ls26 for o, z in z26.items()}
    n = {o: len(games.get(o, {})) for o in r25}
    f = {o: factor(n[o], r26.get(o), r25[o]) for o in r25}
    f_alt = {o: factor(n[o], r26.get(o), r25[o], new=False) for o in r25}
    return {"games": games, "z26": z26, "n": n, "ls26": ls26, "r26": r26, "f": f, "f_alt": f_alt, "rang": ranks(f)}


def schedule_factor(f: dict[int, Decimal], opponents: dict[int, int], weeks) -> Decimal | None:
    """Ø F der Gegner in den Wochen weeks; eine Woche ohne Gegner (Bye) fällt heraus; None ohne Spiel."""
    values = [f[opponents[w]] for w in weeks if w in opponents]
    return statistics.mean(values) if values else None


# ---------------------------------------------------------------- Auslöser

def last_games_mean(games: dict[int, Decimal]) -> Decimal | None:
    """Ø der letzten (höchstens) 3 Spiele nach Woche; None ohne Spiel."""
    last = [games[w] for w in sorted(games)][-LAST_GAMES:]
    return statistics.mean(last) if last else None


def z_score(games: dict[int, Decimal], z26: Decimal | None, ls26: Decimal | None) -> Decimal | None:
    """Auslöser 2: z = (Ø letzte 3 − Z26)/(0,55·LS26·√(1/3 − 1/n)); erst ab n ≥ 4 definiert (vorher None)."""
    n = len(games)
    if n <= LAST_GAMES:
        return None
    spread = DST_CV * ls26 * (ONE / LAST_GAMES - ONE / n).sqrt()
    return (last_games_mean(games) - z26) / spread


def triggers(delta: Decimal | None, z: Decimal | None, rank_shift: int | None) -> list[str]:
    """Kürzel der Auslöser (AUSLOESER): |ΔF| ≥ 0,10 · |z| ≥ 2 · Rangsprung ≥ 5."""
    codes = []
    if delta is not None and abs(delta) >= DELTA_TRIGGER:
        codes.append("delta")
    if z is not None and abs(z) >= Z_TRIGGER:
        codes.append("z")
    if rank_shift is not None and abs(rank_shift) >= RANK_TRIGGER:
        codes.append("rang")
    return codes


def watch_list(z: dict[int, Decimal | None]) -> set[int]:
    """„beobachten“: die drei größten |z| (nur Offenses mit z, also n ≥ 4); Gleichstand nach NFL-ID."""
    candidates = sorted((t for t, v in z.items() if v is not None), key=lambda t: (-abs(z[t]), t))
    return set(candidates[:WATCH_COUNT])


# ---------------------------------------------------------------- Einstieg

def season_weeks(settings: dict) -> tuple[list[int], list[int]]:
    """NFL-Wochen der Regular Season und der Playoffs laut mSettings (matchupPeriods, matchupPeriodCount)."""
    s = settings["scheduleSettings"]
    periods = {int(mp): wks for mp, wks in s["matchupPeriods"].items()}
    regular = sorted(w for mp, wks in periods.items() if mp <= s["matchupPeriodCount"] for w in wks)
    playoffs = sorted(w for mp, wks in periods.items() if mp > s["matchupPeriodCount"] for w in wks)
    return regular, playoffs


def compute_dst(ssn: rawdata.Season, weeks: list[int]) -> dict:
    """D/ST-Faktoren nach Woche N = weeks[-1]: je NFL-Team die Offense-Werte (Z, r, F, Rang, Auslöser) und die Sicht
    seiner D/ST (Spielplan-Faktoren, Besitzer). weeks = abgeschlossene Wochen 1…N (compute.completed_weeks).

    Vorwoche von W1 ist der Stand vor der Saison (n = 0 für alle). Zahlen als ungerundete Decimal; beim Export mit
    zahlen.rounded(…, precision=PRECISION) runden.
    """
    through = weeks[-1]
    if list(weeks) != list(range(1, through + 1)):
        raise ValueError(f"D/ST-Faktoren brauchen die Wochen 1…{through} ohne Lücke, nicht {weeks}")
    nfl, prior_nfl, prior_raw = ssn.nfl(), ssn.prior_nfl(), ssn.prior_dst()
    if prior_nfl is None or prior_raw is None:
        raise ef.FetchError(f"D/ST-Grundlage {ssn.season - 1} fehlt (basis/) – holt der Wochenabruf")
    pools = {}
    for week in weeks:
        pools[week] = ssn.pool(week)
        if pools[week] is None:
            raise ef.FetchError(f"W{week}: {ef.KONA_FILE} fehlt – die D/ST-Faktoren brauchen den Spielerpool jeder Woche")

    # Vorjahr: Z25, LS25, r25 (fest für die ganze Saison)
    allowed25 = allowed(prior_points(prior_raw, ssn.season - 1), prior_nfl)
    z25 = means(allowed25)
    missing = sorted(nfl[t].abbrev for t in nfl if t not in z25)
    if missing:
        raise ValueError(f"D/ST-Grundlage {ssn.season - 1}: keine Spiele gegen {', '.join(missing)}")
    ls25 = league_average(z25)
    r25 = {t: z25[t] / ls25 for t in sorted(nfl)}

    # Saison: Stand nach jeder Woche 0…N, jeweils nur mit den Daten bis dahin
    points26 = pool_points(pools)
    allowed26 = allowed(points26, nfl)
    states = {w: season_state(allowed26, w, r25) for w in range(0, through + 1)}
    now, before = states[through], states[through - 1]
    z_now = {t: z_score(now["games"].get(t, {}), now["z26"].get(t), now["ls26"]) for t in sorted(nfl)}
    watch = watch_list(z_now)

    regular, playoffs = season_weeks(ssn.settings())
    all_weeks = range(1, max(regular + playoffs) + 1)
    next_weeks = [w for w in range(through + 1, through + NEXT_WEEKS + 1) if w in all_weeks]
    rest_weeks = [w for w in regular if w > through]
    owners = {r.pro_team: r for r in pools[through] if r.pos == DST}

    teams = []
    for t in sorted(nfl):
        team, own = nfl[t], owners.get(t)
        opp = team.opponents
        delta = now["f"][t] - before["f"][t]
        rank_shift = before["rang"][t] - now["rang"][t]  # > 0: nach oben
        games = now["games"].get(t, {})
        teams.append({
            "id": t, "abbrev": team.abbrev,
            "bye": next((w for w in all_weeks if w not in opp), None),
            "player_id": own.player_id if own else None, "name": own.name if own else None,
            "z25": z25[t], "n25": len(allowed25[t]), "z26": now["z26"].get(t), "n": now["n"][t],
            "r25": r25[t], "r26": now["r26"].get(t),
            "f": now["f"][t], "f_alt": now["f_alt"][t], "f_vorwoche": before["f"][t], "delta": delta,
            "rang": now["rang"][t], "rang_vorwoche": before["rang"][t],
            "z_last3": last_games_mean(games), "z": z_now[t],
            "ausloeser": triggers(delta, z_now[t], rank_shift), "beobachten": t in watch,
            "naechste3": schedule_factor(now["f"], opp, next_weeks),
            "rest": schedule_factor(now["f"], opp, rest_weeks),
            "sos_po": schedule_factor(now["f"], opp, playoffs),
            "naechste3_alt": schedule_factor(now["f_alt"], opp, next_weeks),
            "rest_alt": schedule_factor(now["f_alt"], opp, rest_weeks),
            "naechste": [{"week": w, "opp": opp[w], "f": now["f"][opp[w]]} if w in opp else {"week": w}
                         for w in next_weeks],
            "besitzer": (own.on_team or None) if own else None, "status": own.status if own else None,
            "gegner": [opp.get(w) for w in all_weeks],
            "punkte_dst": [points26.get(t, {}).get(w) for w in weeks],
            "zugelassen": [allowed26.get(t, {}).get(w) for w in weeks],
            "f_verlauf": [states[w]["f"][t] for w in weeks],
        })
    return {
        "saison": ssn.season, "vorjahr": ssn.season - 1, "through_week": through,
        "ligaschnitt": {str(ssn.season - 1): ls25, str(ssn.season): now["ls26"]},
        "ligaschnitt_verlauf": [states[w]["ls26"] for w in weeks],
        "formel": FORMEL, "formel_alt": FORMEL_ALT, "ausloeser_legende": AUSLOESER,
        "wochen": {"naechste3": next_weeks, "rest": rest_weeks, "sos_po": playoffs},
        "teams": teams,
    }
