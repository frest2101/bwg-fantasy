"""Spieler-Kennzahlen (Baustein 4): Wochenreihen, Form und Trend, Rest of Season, Ersatzniveau, Kader-Projektion.

Regeln: CLAUDE.md „Rechenregeln“ (Spieler, Rest of Season) mit den Beschlüssen in docs/auftraege/session4_vorbereitung.md §2
und den Antworten in session4.md (Frage 8: Ligafaktor und Verletzte, Frage 11 b: Positions-CV).
- Ist und Projektion der Woche kommen aus dem ganzen Spielerpool (kona_player_info), Team und Slot aus mRoster.
- „Gespielt“ heißt stats["210"] == 1 (rawdata.PoolRow.played); ESPN legt Ist-Einträge auch für Inaktive an.
- ROS kommt aus dem Auszug wNN/ros.json (Projektion je Restwoche). Byes bestimmt immer der NFL-Spielplan,
  weil ESPN D/ST auch in ihrer Bye-Woche Punkte projiziert. Alle Projektionen sind ESPN-Input, keine Wahrheit.
Gerechnet wird ungerundet mit Decimal; gerundet wird erst beim Export (zahlen.rounded).
"""

import statistics
from decimal import ROUND_HALF_UP, Decimal

import espn_fetch as ef
import rawdata
from lineup import DST, K, QB, RB, SLOT_BENCH, TE, WR, is_starter, optimal_lineup, optimal_points
from zahlen import ONE, ZERO, dec

# Positions-CV für die Trendschwelle bei weniger als 6 Spielen (Frage 11 b); am Saisonende neu messen
POSITION_CV = {QB: Decimal("0.45"), RB: Decimal("0.60"), WR: Decimal("0.75"), TE: Decimal("0.75"),
               K: Decimal("0.55"), DST: Decimal("0.55")}
FORM_WEEKS = 3                          # Form = Ø der letzten drei gespielten Wochen
SD_FROM_GAMES = 6                       # ab so vielen Spielen die eigene Std-Abw. statt Positions-CV × Ø
TREND_MIN_POINTS, TREND_MIN_SHARE = Decimal(1), Decimal("0.15")
TREND_UP, TREND_DOWN, TREND_FLAT = "↑", "↓", "→"
SPARK_BARS, SPARK_BYE, SPARK_OUT = "▁▂▃▄▅▆▇█", "·", "–"
LAST_REGULAR_WEEK, LAST_PLAYOFF_WEEK = 14, ef.MAX_WEEK   # W1–14 Regular Season, W15–17 Playoffs; W18 zählt nicht
REPLACEMENT_STATUS = ("WAIVERS", "FREEAGENT")
INJURED = ("OUT", "INJURY_RESERVE")     # zählen im Ersatzniveau nicht und in der Kader-Projektion in Woche N+1 als 0
REPLACEMENT_COUNT = 3                   # Ersatzniveau = Ø der drei besten verfügbaren Spieler je Position
ROS_KEYS = ("ros", "restspiele", "ros_pro_spiel", "ros_po", "ros_rang", "ros_ueber_ersatz")


# ---------------------------------------------------------------- Hilfen

def has_game(nfl: dict[int, rawdata.NflTeam], pro_team: int, week: int) -> bool:
    """Hat das NFL-Team in der Woche ein Spiel? Unbekanntes Team (0 = ohne NFL-Team) hat keins."""
    team = nfl.get(pro_team)
    return team is not None and week in team.opponents


def is_bye(nfl: dict[int, rawdata.NflTeam], pro_team: int, week: int) -> bool:
    """Bye = bekanntes NFL-Team ohne Spiel in der Woche (Spieler ohne NFL-Team haben keinen Bye)."""
    return pro_team in nfl and week not in nfl[pro_team].opponents


def ligafaktor(team_weeks: list[dict]) -> Decimal:
    """Ligafaktor = Σ PF / Σ Starter-Projektion über alle Team-Wochen (Frage 8; nach W2 ≈ 0,977)."""
    projection = sum((r["starter_projection"] for r in team_weeks), ZERO)
    return sum((r["pf"] for r in team_weeks), ZERO) / projection


def pool_now(ssn: rawdata.Season, week: int) -> list[rawdata.PoolRow]:
    """Spielerpool der Woche als aktueller Stand (Kader, Status, Verletzung); ohne Pool ist ROS nicht rechenbar."""
    pool = ssn.pool(week)
    if pool is None:
        raise ef.FetchError(f"ROS-Auszug nach W{week}, aber kein Spielerpool W{week} ({ef.KONA_FILE})")
    return pool


# ---------------------------------------------------------------- Teil 1: Wochenreihen und Kennzahlen

def player_weeks(ssn: rawdata.Season, weeks: list[int]) -> tuple[dict[int, dict], list[int]]:
    """Je Spieler Stammdaten und Wochenreihe; dazu die Wochen ohne Spielerpool.

    Ist, Projektion und „gespielt“ aus dem Pool der Woche (ganzer Pool), Team und Slot aus mRoster der Woche.
    Fehlt ein Kaderspieler im Pool (oder der ganze Pool), gelten seine Werte aus mRoster (Status und Besitz dann
    None). Die Stammdaten (NFL-Team, Fantasy-Team, Status, Verletzung, Besitz) sind der Stand der jüngsten Woche.
    Wochenzeile: {week, actual (nur wenn gespielt, sonst None), projection, bye, team_id, slot}.
    """
    nfl = ssn.nfl()
    info: dict[int, dict] = {}
    rows: dict[int, dict[int, dict]] = {}
    missing = []
    for week in sorted(weeks):
        pool = ssn.pool(week)
        if pool is None:
            missing.append(week)
        roster = {r.player_id: r for r in ssn.roster(week)}
        for r in pool or []:
            info[r.player_id] = {"player_id": r.player_id, "name": r.name, "pos": r.pos, "pro_team": r.pro_team,
                                 "team_id": r.on_team or None, "status": r.status, "injury": r.injury,
                                 "owned": dec(r.owned) if r.owned is not None else None}
            rows.setdefault(r.player_id, {})[week] = {
                "actual": (r.actual if r.actual is not None else ZERO) if r.played else None,
                "projection": r.projection, "pro_team": r.pro_team}
        for r in roster.values():
            if week not in rows.get(r.player_id, {}):  # Kaderspieler ohne Pool-Zeile: Werte aus mRoster
                info[r.player_id] = {"player_id": r.player_id, "name": r.name, "pos": r.pos, "pro_team": r.pro_team,
                                     "team_id": r.team_id, "status": None, "injury": r.injury, "owned": None}
                rows.setdefault(r.player_id, {})[week] = {"actual": r.actual if r.played else None,
                                                          "projection": r.projection, "pro_team": r.pro_team}
        for pid, row in rows.items():
            if week in row:
                r = roster.get(pid)
                row[week].update(team_id=r.team_id if r else None, slot=r.slot if r else None)

    players = {}
    for pid in sorted(info):
        series = []
        for week in sorted(weeks):
            row = rows[pid].get(week) or {"actual": None, "projection": None, "team_id": None, "slot": None}
            series.append({"week": week, "actual": row["actual"], "projection": row["projection"],
                           "bye": is_bye(nfl, row.get("pro_team", info[pid]["pro_team"]), week),
                           "team_id": row["team_id"], "slot": row["slot"]})
        team = nfl.get(info[pid]["pro_team"])
        players[pid] = {**info[pid], "nfl": team.abbrev if team else None, "bye_week": team.bye if team else None,
                        "weeks": series}
    return players, missing


def trend(values: list[Decimal], pos: int) -> tuple[str | None, Decimal | None]:
    """Trendpfeil der Form gegen den Ø; Rückgabe (Pfeil, Schwelle).

    ↑/↓ nur, wenn |Form − Ø| > max(1; 0,15·|Ø|; s·√(1/3 − 1/n)), sonst →. s = Std-Abw. der Spiele ab 6 Spielen,
    vorher Positions-CV × |Ø|. Bis 3 Spiele ist Form = Ø und die Formel nicht definiert: (None, None).
    """
    n = len(values)
    if n <= FORM_WEEKS:
        return None, None
    avg, form = statistics.mean(values), statistics.mean(values[-FORM_WEEKS:])
    s = statistics.stdev(values) if n >= SD_FROM_GAMES else POSITION_CV.get(pos, ZERO) * abs(avg)
    threshold = max(TREND_MIN_POINTS, TREND_MIN_SHARE * abs(avg), s * (ONE / FORM_WEEKS - ONE / n).sqrt())
    delta = form - avg
    if abs(delta) > threshold:
        return (TREND_UP if delta > 0 else TREND_DOWN), threshold
    return TREND_FLAT, threshold


def sparkline(series: list[dict]) -> str:
    """Formkurve je Woche aus ▁…█: Bye „·“, nicht gespielt „–“, negative Punkte als 0.

    Skala 0 … eigenes Maximum: Stufe = round_half_up(Punkte / Maximum × 7); Maximum ≤ 0 → alle ▁.
    """
    top = max((max(w["actual"], ZERO) for w in series if w["actual"] is not None), default=ZERO)
    chars = []
    for w in series:
        if w["actual"] is None:
            chars.append(SPARK_BYE if w["bye"] else SPARK_OUT)
        elif top <= 0:
            chars.append(SPARK_BARS[0])
        else:
            level = (max(w["actual"], ZERO) / top * (len(SPARK_BARS) - 1)).quantize(ONE, rounding=ROUND_HALF_UP)
            chars.append(SPARK_BARS[int(level)])
    return "".join(chars)


def player_stats(series: list[dict], pos: int) -> dict:
    """Kennzahlen eines Spielers aus seiner Wochenreihe (nur gespielte Wochen zählen).

    Spiele n = Wochen mit Stat 210; Pkt = Σ Ist; Ø = Pkt/n; Floor/Ceiling = min/max; Konstanz sd = Stichproben-
    Std-Abw. (ab 2 Spielen); Form = Ø der letzten 3; Form Δ = Form − Ø; Starts = Wochen im Starter-Slot;
    Bank-Punkte = Ist auf der Bank (ohne IR); Proj.-Δ = Σ Ist − Σ Wochenprojektion der gespielten Wochen.
    """
    played = [w for w in series if w["actual"] is not None]
    values = [w["actual"] for w in played]
    n = len(values)
    pts = sum(values, ZERO)
    avg = pts / n if n else None
    form = statistics.mean(values[-FORM_WEEKS:]) if n else None
    arrow, threshold = trend(values, pos)
    return {
        "games": n, "pts": pts, "avg": avg,
        "floor": min(values) if n else None, "ceiling": max(values) if n else None,
        "sd": statistics.stdev(values) if n >= 2 else None,
        "form": form, "form_delta": form - avg if n else None,
        "trend": arrow, "trend_schwelle": threshold,
        "sparkline": sparkline(series),
        "starts": sum(1 for w in series if w["slot"] is not None and is_starter(w["slot"])),
        "bench_pts": sum((w["actual"] for w in series if w["slot"] == SLOT_BENCH and w["actual"] is not None), ZERO),
        "proj_delta": pts - sum((w["projection"] or ZERO for w in played), ZERO),
    }


# ---------------------------------------------------------------- Teil 2: Rest of Season

def ros_weeks(after_week: int, last_regular: int = LAST_REGULAR_WEEK) -> tuple[list[int], list[int]]:
    """Restwochen der Regular Season (N+1 … 14) und die noch offenen Playoff-Wochen (15 … 17)."""
    return (list(range(after_week + 1, last_regular + 1)),
            list(range(max(after_week, last_regular) + 1, LAST_PLAYOFF_WEEK + 1)))


def ros_player(projections: dict | None, pro_team: int, nfl: dict[int, rawdata.NflTeam], after_week: int,
               last_regular: int = LAST_REGULAR_WEEK) -> dict:
    """ROS eines Spielers aus seinen Wochenprojektionen ({"4": x, …}); Wochen ohne Spiel des NFL-Teams zählen 0.

    ROS = Σ Projektion N+1…14; Restspiele = Wochen mit Spiel; ROS/Spiel = ROS/Restspiele (None bei 0);
    ROS Playoffs = Σ W15–17. Ohne Eintrag im Auszug (keine ESPN-Projektion) sind alle Werte None;
    eine einzelne fehlende Woche zählt 0.
    """
    if projections is None:
        return {"ros": None, "restspiele": None, "ros_pro_spiel": None, "ros_po": None}
    regular, playoffs = ros_weeks(after_week, last_regular)
    rest = [w for w in regular if has_game(nfl, pro_team, w)]
    ros = sum((dec(projections.get(str(w), 0)) for w in rest), ZERO)
    po = sum((dec(projections.get(str(w), 0)) for w in playoffs if has_game(nfl, pro_team, w)), ZERO)
    return {"ros": ros, "restspiele": len(rest), "ros_pro_spiel": ros / len(rest) if rest else None, "ros_po": po}


def ros_ranks(per_game: dict[int, tuple[int, Decimal | None]]) -> dict[int, int]:
    """ROS-Rang je Position nach ROS/Spiel (1 + Zahl der besseren Spieler); nur Spieler mit ROS/Spiel."""
    by_pos: dict[int, list[Decimal]] = {}
    for pos, value in per_game.values():
        if value is not None:
            by_pos.setdefault(pos, []).append(value)
    return {pid: 1 + sum(1 for other in by_pos[pos] if other > value)
            for pid, (pos, value) in sorted(per_game.items()) if value is not None}


def replacement_levels(pool: list[rawdata.PoolRow], per_game: dict[int, Decimal | None]) -> dict[int, Decimal | None]:
    """Ersatzniveau je Position: Ø ROS/Spiel der drei besten verfügbaren Spieler.

    Verfügbar = Status WAIVERS oder FREEAGENT und Verletzung weder OUT noch INJURY_RESERVE (Stand des Pools N).
    Weniger als drei Kandidaten → Ø der vorhandenen; keiner → None.
    """
    levels = {}
    for pos in POSITION_CV:
        best = sorted((per_game[r.player_id] for r in pool
                       if r.pos == pos and r.status in REPLACEMENT_STATUS and r.injury not in INJURED
                       and per_game.get(r.player_id) is not None), reverse=True)[:REPLACEMENT_COUNT]
        levels[pos] = statistics.mean(best) if best else None
    return levels


def add_ros(players: dict[int, dict], ssn: rawdata.Season, ros: dict,
            last_regular: int = LAST_REGULAR_WEEK) -> dict[int, Decimal | None]:
    """Trägt ROS, Restspiele, ROS/Spiel, ROS Playoffs, ROS-Rang und ROS über Ersatz in players ein.

    NFL-Team laut Pool N (N = ros["after_week"]). ROS über Ersatz = (ROS/Spiel − Ersatzniveau) × Restspiele.
    Rückgabe: Ersatzniveau je Position.
    """
    after = ros["after_week"]
    pool = pool_now(ssn, after)
    nfl, projections = ssn.nfl(), ros.get("players") or {}
    current = {r.player_id: r.pro_team for r in pool}
    for pid, p in players.items():
        p.update(ros_player(projections.get(str(pid)), current.get(pid, p["pro_team"]), nfl, after, last_regular))
    per_game = {pid: p["ros_pro_spiel"] for pid, p in players.items()}
    ranks = ros_ranks({pid: (p["pos"], p["ros_pro_spiel"]) for pid, p in players.items()})
    levels = replacement_levels(pool, per_game)
    for pid, p in players.items():
        level = levels.get(p["pos"])
        p["ros_rang"] = ranks.get(pid)
        p["ros_ueber_ersatz"] = ((p["ros_pro_spiel"] - level) * p["restspiele"]
                                 if p["ros_pro_spiel"] is not None and level is not None else None)
    return levels


# ---------------------------------------------------------------- Teil 3: Bedarf je Team (Waiver-Tab, Session 7)

def team_needs(rosters: dict[int, list[tuple[int, int]]], per_game: dict[int, Decimal | None],
               levels: dict[int, Decimal | None]) -> dict[int, dict]:
    """Bedarf je Team aus dem aktuellen Kader (Tagesstand) und ROS/Spiel der Regular Season (Wochenstand).

    Je Team die ROS-optimale Aufstellung nach lineup.optimal_lineup mit ROS/Spiel als Wert (ohne Projektion 0).
    Lücken = Starter, deren ROS/Spiel unter dem Ersatzniveau ihrer Position liegt, dazu unbesetzte Slots; ohne
    Ersatzniveau der Position (kein verfügbarer Spieler) zählt nur ein leerer Slot. Über Ersatz = je Position die
    Zahl der Kaderspieler mit ROS/Spiel über dem Ersatzniveau (None ohne Ersatzniveau).
    rosters: team_id → [(player_id, Position)]; per_game: player_id → ROS/Spiel; levels: Position → Ersatzniveau.
    Rückgabe team_id → {"luecken": [{"slot", "id", "pos", "ros_g"}], "ueber_ersatz": {Position: Zahl}}.
    """
    needs = {}
    for tid, roster in sorted(rosters.items()):
        entries = [(pos, per_game.get(pid) or ZERO, pid) for pid, pos in roster]
        gaps = []
        for slot, entry in optimal_lineup(entries):
            if entry is None:
                gaps.append({"slot": slot, "id": None, "pos": None, "ros_g": None})
                continue
            pos, _, pid = entry
            value, level = per_game.get(pid), levels.get(pos)
            if level is not None and (value is None or value < level):
                gaps.append({"slot": slot, "id": pid, "pos": pos, "ros_g": value})
        above = {pos: (sum(1 for pid, p in roster if p == pos and per_game.get(pid) is not None
                           and per_game[pid] > levels[pos]) if levels.get(pos) is not None else None)
                 for pos in POSITION_CV}
        needs[tid] = {"luecken": gaps, "ueber_ersatz": above}
    return needs


# ---------------------------------------------------------------- Einstiege für compute.py

def compute_players(ssn: rawdata.Season, weeks: list[int]) -> dict:
    """Alle Spieler des Pools und der Kader: Wochenreihe, Kennzahlen und – sobald ros.json vorliegt – ROS.

    Rückgabe: {"weeks", "players": {pid: {...}}, "ersatz": {pos: Decimal|None} (leer ohne ros),
    "ros_after_week" (None ohne ros), "cv": POSITION_CV, "wochen_ohne_pool": [Wochen ohne kona]}.
    """
    players, missing = player_weeks(ssn, weeks)
    for p in players.values():
        p.update(player_stats(p["weeks"], p["pos"]))
        p.update(dict.fromkeys(ROS_KEYS))
    ros, levels = ssn.ros(), {}
    if ros is not None:
        if weeks and ros["after_week"] != max(weeks):
            raise ef.FetchError(f"ROS-Auszug nach W{ros['after_week']} passt nicht zu Woche {max(weeks)}")
        levels = add_ros(players, ssn, ros)
    return {"weeks": sorted(weeks), "players": players, "ersatz": levels,
            "ros_after_week": ros["after_week"] if ros is not None else None,
            "cv": dict(POSITION_CV), "wochen_ohne_pool": missing}


def team_week_projection(rows: list[rawdata.PoolRow], week: int, first_week: int, projections: dict,
                         nfl: dict[int, rawdata.NflTeam]) -> Decimal:
    """Projektionsoptimale Aufstellung eines Kaders in einer Restwoche (ohne Ligafaktor).

    Wert je Spieler = ESPN-Wochenprojektion; 0 ohne Spiel des NFL-Teams (Bye) und in der ersten Restwoche N+1
    bei OUT oder INJURY_RESERVE; ohne Projektion 0. Aufstellung nach lineup.optimal_points.
    """
    def value(r: rawdata.PoolRow) -> Decimal:
        if not has_game(nfl, r.pro_team, week) or (week == first_week and r.injury in INJURED):
            return ZERO
        return dec((projections.get(str(r.player_id)) or {}).get(str(week), 0))
    return optimal_points([(r.pos, value(r)) for r in rows])


def kader_projection(ssn: rawdata.Season, ligafaktor, last_regular: int = LAST_REGULAR_WEEK) -> dict | None:
    """Kader-Projektion ROS je Team (Beschluss §2, Frage 8); None ohne ros.json oder ohne Restwoche.

    Kader = onTeamId im Pool N. P_i,w = projektionsoptimale Aufstellung × Ligafaktor für w = N+1 … 14;
    kader_projektion_i = Ø_w P_i,w; dev_i,w = P_i,w − Ø (Wochenabweichung für die Playoff-Simulation).
    Nach der letzten Woche der Regular Season zählen die Playoff-Wochen 15 … 17; nach W17 gibt es keine Projektion.
    Rückgabe: {"teams": {team_id: Ø}, "wochen": {team_id: {week: P}}, "dev": {team_id: {week: P − Ø}}}.
    """
    ros = ssn.ros()
    if ros is None:
        return None
    after = ros["after_week"]
    regular, playoffs = ros_weeks(after, last_regular)
    regular = regular or playoffs  # nach W14 (Schlusstabelle) über die Playoff-Wochen, damit P nicht aufs Vorjahr fällt
    if not regular:
        return None
    nfl, projections, factor = ssn.nfl(), ros.get("players") or {}, dec(ligafaktor)
    rosters: dict[int, list] = {}
    for r in pool_now(ssn, after):
        if r.on_team:
            rosters.setdefault(r.on_team, []).append(r)
    wochen = {tid: {w: team_week_projection(rows, w, after + 1, projections, nfl) * factor for w in regular}
              for tid, rows in sorted(rosters.items())}
    teams = {tid: statistics.mean(values.values()) for tid, values in wochen.items()}
    dev = {tid: {w: p - teams[tid] for w, p in values.items()} for tid, values in wochen.items()}
    return {"teams": teams, "wochen": wochen, "dev": dev}
