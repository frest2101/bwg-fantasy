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
ROS_KEYS = ("ros", "restspiele", "ros_pro_spiel", "ros_po", "restspiele_po", "ros_po_pro_spiel", "ros_rang",
            "ros_ueber_ersatz")


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
    ROS Playoffs = Σ W15–17 (noch offene Playoff-Wochen); Restspiele Playoffs und ROS Playoffs/Spiel genauso
    (Grundlage von Bedarf und Profil nach W14). Ohne Eintrag im Auszug (keine ESPN-Projektion) sind alle Werte None;
    eine einzelne fehlende Woche zählt 0.
    """
    if projections is None:
        return {"ros": None, "restspiele": None, "ros_pro_spiel": None, "ros_po": None, "restspiele_po": None,
                "ros_po_pro_spiel": None}
    regular, playoffs = ros_weeks(after_week, last_regular)
    rest = [w for w in regular if has_game(nfl, pro_team, w)]
    ros = sum((dec(projections.get(str(w), 0)) for w in rest), ZERO)
    po_weeks = [w for w in playoffs if has_game(nfl, pro_team, w)]
    po = sum((dec(projections.get(str(w), 0)) for w in po_weeks), ZERO)
    return {"ros": ros, "restspiele": len(rest), "ros_pro_spiel": ros / len(rest) if rest else None, "ros_po": po,
            "restspiele_po": len(po_weeks), "ros_po_pro_spiel": po / len(po_weeks) if po_weeks else None}


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
    return {pos: top_mean([per_game[r.player_id] for r in pool
                           if r.pos == pos and r.status in REPLACEMENT_STATUS and r.injury not in INJURED
                           and per_game.get(r.player_id) is not None])
            for pos in POSITION_CV}


def add_ros(players: dict[int, dict], ssn: rawdata.Season, ros: dict,
            last_regular: int = LAST_REGULAR_WEEK) -> tuple[dict[int, Decimal | None], dict[int, Decimal | None]]:
    """Trägt ROS, Restspiele, ROS/Spiel, ROS Playoffs, ROS-Rang und ROS über Ersatz in players ein.

    NFL-Team laut Pool N (N = ros["after_week"]). ROS über Ersatz = (ROS/Spiel − Ersatzniveau) × Restspiele.
    Rückgabe: Ersatzniveau je Position nach ROS/Spiel und nach ROS Playoffs/Spiel (gleiche Regel, W15–17).
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
    return levels, replacement_levels(pool, {pid: p["ros_po_pro_spiel"] for pid, p in players.items()})


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


# ---------------------------------------------------------------- Teil 3b: Wochensicht (Waiver-Tab, Beschluss 30.09.2026)

WEEK_OUT = INJURED + ("SUSPENSION",)    # zählen in der Woche N+1 als 0 (gesperrt spielt nicht)
DOUBTFUL = ("QUESTIONABLE", "DOUBTFUL", "DAY_TO_DAY")   # zählen mit ESPN-Projektion, die App markiert sie
HORIZON = 3                             # Summe der Wochen N+1 … N+3
CANDIDATES = 3                          # beste freie Spieler je Lücke der Wochensicht
SLOT_POSITIONS = {"QB": (QB,), "RB": (RB,), "WR": (WR,), "TE": (TE,), "D/ST": (DST,), "K": (K,),
                  "FLEX": (RB, WR, TE), "OP": (QB, RB, WR, TE)}


def week_value(projection, injury: str | None, game: bool) -> tuple[Decimal, str | None]:
    """Wert eines Spielers in der Woche N+1 und der Grund, wenn er sicher ausfällt.

    Ohne Spiel seines NFL-Teams 0 mit Grund "BYE"; OUT, INJURY_RESERVE und gesperrt 0 mit dem Status als Grund;
    sonst die ESPN-Wochenprojektion (ohne Projektion 0), auch bei fraglichen Spielern (QUESTIONABLE, DOUBTFUL).
    """
    if not game:
        return ZERO, "BYE"
    if injury in WEEK_OUT:
        return ZERO, injury
    return (dec(projection) if projection is not None else ZERO), None


def horizon_weeks(week: int, horizon: int = HORIZON) -> list[int]:
    """Wochen N+1 … N+horizon der Wochensicht, höchstens bis W17 (W18 zählt nicht)."""
    return list(range(week, min(week + horizon, LAST_PLAYOFF_WEEK + 1)))


def horizon_sum(first: Decimal, projections: dict | None, pro_team: int, nfl: dict[int, rawdata.NflTeam],
                weeks: list[int]) -> Decimal | None:
    """Σ der Wochenwerte über weeks: erste Woche = week_value (Tagesstand), die folgenden aus dem ROS-Auszug
    ({"5": x, …}), Wochen ohne Spiel 0. None ohne Eintrag im ROS-Auszug (keine ESPN-Projektion)."""
    if projections is None:
        return None
    return first + sum((dec(projections.get(str(w), 0)) for w in weeks[1:] if has_game(nfl, pro_team, w)), ZERO)


def horizon_values(first: Decimal, projections: dict | None, pro_team: int, nfl: dict[int, rawdata.NflTeam],
                   weeks: list[int]) -> list[Decimal]:
    """Wochenwerte über weeks wie horizon_sum, aber je Woche (Zugewinn mit eigener Aufstellung je Woche); ohne
    Eintrag im ROS-Auszug zählen die Folgewochen 0."""
    return [first] + [dec((projections or {}).get(str(w), 0)) if has_game(nfl, pro_team, w) else ZERO
                      for w in weeks[1:]]


def top_mean(values: list[Decimal], n: int = REPLACEMENT_COUNT) -> Decimal | None:
    """Ø der n größten Werte (weniger → Ø der vorhandenen, keiner → None)."""
    best = sorted(values, reverse=True)[:n]
    return statistics.mean(best) if best else None


def week_replacement_levels(free: list[tuple[int, Decimal]]) -> dict[int, Decimal | None]:
    """Wochen-Ersatzniveau je Position: Ø der drei besten Werte unter den verfügbaren Spielern.

    free: (Position, Wert) der Spieler mit Status WAIVERS oder FREEAGENT, die nicht sicher ausfallen (WEEK_OUT);
    dieselbe Regel wie beim ROS-Ersatzniveau, nur mit dem Wert der Woche N+1 bzw. der Summe N+1 … N+3.
    """
    return {pos: top_mean([v for p, v in free if p == pos]) for pos in POSITION_CV}


def team_week_needs(rosters: dict[int, list[tuple[int, int]]], value: dict[int, tuple[Decimal, str | None]],
                    injury: dict[int, str | None], levels: dict[int, Decimal | None],
                    free: list[tuple[int, Decimal, int]], per_game: dict[int, Decimal | None] | None,
                    byes_ahead: dict[int, list[int]]) -> dict[int, dict]:
    """Wochenbedarf je Team für die Woche N+1 (Tagesstand).

    Aufstellung = lineup.optimal_lineup des Kaders mit dem Wochenwert (week_value). Lücken = unbesetzte Slots,
    Starter, die sicher ausfallen (Grund BYE, OUT, INJURY_RESERVE, SUSPENSION), und Starter unter dem
    Wochen-Ersatzniveau ihrer Position; je Lücke die drei besten freien Spieler (free, absteigend sortiert), die
    in den Slot passen und mehr bringen als die Besetzung.
    Ausfälle und Byes beziehen sich auf die ROS-optimale Aufstellung (per_game wie team_needs): Starter, die in N+1
    ausfallen oder fraglich sind (Grund = Status bzw. BYE), und Starter mit Bye in N+2 … N+3 (byes_ahead: Spieler →
    Wochen). Ohne per_game (keine ROS-Grundlage, app_export.need_basis) bleiben beide leer.
    Rückgabe team_id → {"luecken": [{"slot", "id", "pos", "proj", "grund", "kandidaten"}],
    "ausfaelle": [{"slot", "id", "pos", "grund"}], "byes": [{"woche", "slot", "id", "pos"}]}.
    """
    def candidates(slot: str, floor: Decimal) -> list[int]:
        fits = SLOT_POSITIONS[slot]
        return [pid for pos, v, pid in free if pos in fits and v > floor][:CANDIDATES]

    needs = {}
    for tid, roster in sorted(rosters.items()):
        gaps = []
        for slot, entry in optimal_lineup([(pos, value[pid][0], pid) for pid, pos in roster]):
            if entry is None:
                gaps.append({"slot": slot, "id": None, "pos": None, "proj": None, "grund": None,
                             "kandidaten": candidates(slot, ZERO)})
                continue
            pos, v, pid = entry
            grund, level = value[pid][1], levels.get(pos)
            if grund is None and (level is None or v >= level):
                continue
            gaps.append({"slot": slot, "id": pid, "pos": pos, "proj": v, "grund": grund,
                         "kandidaten": candidates(slot, v)})
        out, byes = [], []
        if per_game is not None:
            for slot, entry in optimal_lineup([(pos, per_game.get(pid) or ZERO, pid) for pid, pos in roster]):
                if entry is None:
                    continue
                pos, _, pid = entry
                grund = value[pid][1] or (injury.get(pid) if injury.get(pid) in DOUBTFUL else None)
                if grund:
                    out.append({"slot": slot, "id": pid, "pos": pos, "grund": grund})
                byes += [{"woche": w, "slot": slot, "id": pid, "pos": pos} for w in byes_ahead.get(pid, [])]
        byes.sort(key=lambda b: b["woche"])   # stabil: innerhalb der Woche in Slot-Reihenfolge
        needs[tid] = {"luecken": gaps, "ausfaelle": out, "byes": byes}
    return needs


# ---------------------------------------------------------------- Einstiege für compute.py

def compute_players(ssn: rawdata.Season, weeks: list[int]) -> dict:
    """Alle Spieler des Pools und der Kader: Wochenreihe, Kennzahlen und – sobald ros.json vorliegt – ROS.

    Rückgabe: {"weeks", "players": {pid: {...}}, "ersatz": {pos: Decimal|None} (leer ohne ros), "ersatz_po" (dasselbe
    nach ROS Playoffs/Spiel),
    "ros_after_week" (None ohne ros), "cv": POSITION_CV, "wochen_ohne_pool": [Wochen ohne kona]}.
    """
    players, missing = player_weeks(ssn, weeks)
    for p in players.values():
        p.update(player_stats(p["weeks"], p["pos"]))
        p.update(dict.fromkeys(ROS_KEYS))
    ros, levels, levels_po = ssn.ros(), {}, {}
    if ros is not None:
        if weeks and ros["after_week"] != max(weeks):
            raise ef.FetchError(f"ROS-Auszug nach W{ros['after_week']} passt nicht zu Woche {max(weeks)}")
        levels, levels_po = add_ros(players, ssn, ros)
    return {"weeks": sorted(weeks), "players": players, "ersatz": levels, "ersatz_po": levels_po,
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


# ---------------------------------------------------------------- Teil 3c: Profil je Team (Beschluss 30.09.2026)

# Slot-Gruppen der Aufstellung: QB und OP zählen zusammen (Superflex, sonst zählt dieselbe Schwäche doppelt)
PROFILE_GROUPS = (("QB", ("QB", "OP"), 2), ("RB", ("RB",), 2), ("WR", ("WR",), 3), ("TE", ("TE",), 1),
                  ("FLEX", ("FLEX",), 2), ("D/ST", ("D/ST",), 2), ("K", ("K",), 1))
PROFILE_RANKS = 3                 # schwach nur auf den letzten drei Rängen, stark auf den ersten drei
PROFILE_POINTS = Decimal(1)       # … und mindestens 1 Pkt/Spiel je Slot der Gruppe vom Ligaschnitt entfernt
PLACEHOLDER = 0                   # Spieler-ID des freien Ersatzes in der Absicherung (keine echte ID ist 0)


def team_profiles(rosters: dict[int, list[tuple[int, int]]], value: dict[int, Decimal | None]) -> dict[int, dict]:
    """Stärken und Schwächen je Team nach Slot-Gruppen der wertoptimalen Aufstellung (lineup.optimal_lineup).

    value = ROS/Spiel (Regular Season, nach W14 Playoffs) je Spieler, ohne Wert 0. Je Gruppe: wert = Σ der Starter,
    abstand = wert − Ligaschnitt (Ø der Teams), rang (1 = höchster Wert, Gleichstand teilt den besseren Rang),
    wertung "schwach" auf den letzten PROFILE_RANKS Rängen mit abstand ≤ −PROFILE_POINTS × Slots, "stark" auf den
    ersten mit abstand ≥ +PROFILE_POINTS × Slots, sonst None; ids = Starter der Gruppe in Slot-Reihenfolge.
    gesamt = Summe der Gruppen (= optimal_points) mit abstand und rang. Rückgabe team_id → {"gruppen", "gesamt",
    "schwach", "stark"} (Gruppennamen in PROFILE_GROUPS-Reihenfolge).
    """
    slot_group = {slot: g for g, slots, _ in PROFILE_GROUPS for slot in slots}
    raw = {}
    for tid, roster in sorted(rosters.items()):
        groups = {g: {"wert": ZERO, "ids": []} for g, _, _ in PROFILE_GROUPS}
        for slot, entry in optimal_lineup([(pos, value.get(pid) or ZERO, pid) for pid, pos in roster]):
            if entry is not None:
                groups[slot_group[slot]]["wert"] += entry[1]
                groups[slot_group[slot]]["ids"].append(entry[2])
        raw[tid] = groups
    if not raw:
        return {}
    n = len(raw)

    def rate(values: dict[int, Decimal]) -> dict[int, tuple[Decimal, int]]:
        mean = sum(values.values(), ZERO) / n
        return {t: (v - mean, 1 + sum(1 for o in values.values() if o > v)) for t, v in values.items()}

    out = {tid: {"gruppen": {}, "schwach": [], "stark": []} for tid in raw}
    for g, _, slots in PROFILE_GROUPS:
        for tid, (gap, rank) in rate({tid: raw[tid][g]["wert"] for tid in raw}).items():
            limit = PROFILE_POINTS * slots
            rating = ("schwach" if rank > n - PROFILE_RANKS and gap <= -limit
                      else "stark" if rank <= PROFILE_RANKS and gap >= limit else None)
            out[tid]["gruppen"][g] = {"wert": raw[tid][g]["wert"], "abstand": gap, "rang": rank, "wertung": rating,
                                      "ids": raw[tid][g]["ids"]}
            if rating:
                out[tid][rating].append(g)
    totals = {tid: sum((grp["wert"] for grp in raw[tid].values()), ZERO) for tid in raw}
    for tid, (gap, rank) in rate(totals).items():
        out[tid]["gesamt"] = {"wert": totals[tid], "abstand": gap, "rang": rank}
    return out


def cover_loss(roster: list[tuple[int, int]], value: dict[int, Decimal | None],
               free_best: dict[int, Decimal | None]) -> dict[int, dict | None]:
    """Absicherung je Position: Was die beste Aufstellung verliert, wenn der beste Spieler der Position ausfällt und
    der beste verfügbare Spieler der Position (free_best, ohne: niemand) nachrückt.

    Rückgabe je Position {"wert": Verlust ≤ 0, "frei_gleichwertig": bool} oder None ohne Spieler der Position.
    frei_gleichwertig = ein freier Spieler ist mindestens so gut wie der eigene Beste; dann ist wert 0 (ein Ausfall
    kostet nichts, die Chance zeigt der Zugewinn). Bester Spieler = höchster Wert, bei Gleichstand die kleinere ID."""
    entries = [(pos, value.get(pid) or ZERO, pid) for pid, pos in roster]
    base = optimal_points(entries)
    out = {}
    for pos in POSITION_CV:
        mine = sorted((e for e in entries if e[0] == pos), key=lambda e: (-e[1], e[2]))
        if not mine:
            out[pos] = None
            continue
        rest = [e for e in entries if e[2] != mine[0][2]]
        free = free_best.get(pos)
        if free is not None:
            rest.append((pos, free, PLACEHOLDER))
        equal = free is not None and free >= mine[0][1]
        out[pos] = {"wert": ZERO if equal else min(ZERO, optimal_points(rest) - base), "frei_gleichwertig": equal}
    return out


def bye_costs(roster: list[tuple[int, int]], value: dict[int, Decimal | None], byes: dict[int, set[int]],
              weeks: list[int]) -> list[dict]:
    """Kosten der Byes je Restwoche: beste Aufstellung mit den spielfreien Spielern der Woche auf 0 minus die
    beste Aufstellung ohne Bye (beides nach value, also ROS/Spiel); nur Wochen mit Verlust. ids = Starter der
    wertoptimalen Aufstellung, die in der Woche spielfrei sind. Rückgabe [{"woche", "kosten", "ids"}]."""
    entries = [(pos, value.get(pid) or ZERO, pid) for pid, pos in roster]
    base = optimal_points(entries)
    starters = [e[2] for _, e in optimal_lineup(entries) if e is not None]
    out = []
    for w in weeks:
        off = {pid for pid, _ in roster if w in byes.get(pid, ())}
        if not off:
            continue
        cost = optimal_points([(p, ZERO if pid in off else v, pid) for p, v, pid in entries]) - base
        if cost < 0:
            out.append({"woche": w, "kosten": cost, "ids": [pid for pid in starters if pid in off]})
    return out


def roster_rules(settings: dict) -> dict:
    """Kaderregeln aus mSettings (rosterSettings): plaetze = Σ lineupSlotCounts (Starter, Bank, IR), ir = IR-Slots,
    limits = Höchstzahl je Position (positionLimits; 0 oder −1 = ohne Grenze)."""
    r = settings.get("rosterSettings") or {}
    counts = {int(k): v for k, v in (r.get("lineupSlotCounts") or {}).items()}
    limits = {int(k): v for k, v in (r.get("positionLimits") or {}).items()}
    return {"plaetze": sum(counts.values()), "ir": counts.get(21, 0),
            "limits": {pos: limits[pos] for pos in POSITION_CV if limits.get(pos, 0) > 0}}


def must_drop(roster: list[tuple[int, int]], on_ir: set[int], rules: dict) -> tuple[bool, set[int]]:
    """Braucht ein Zugang einen Drop? (voll, Positionen am Limit).

    Voll = die Spieler außerhalb des IR-Slots füllen alle übrigen Plätze: len(Kader) − Spieler im IR-Slot
    ≥ Plätze − IR-Slots. on_ir = Spieler-IDs, die laut ESPN (mRoster, Tagesstand ir_slot) im IR-Slot stehen; ohne
    diese Angabe (leere Menge) steht niemand auf IR – es wird nicht nach Status geraten (Korrektur Stephan
    30.09.2026). Am Limit = so viele Spieler der Position wie laut positionLimits erlaubt.
    """
    parked = min(rules["ir"], sum(1 for pid, _ in roster if pid in on_ir))
    full = len(roster) - parked >= rules["plaetze"] - rules["ir"]
    counts = {pos: sum(1 for _, p in roster if p == pos) for pos in rules["limits"]}
    return full, {pos for pos, limit in rules["limits"].items() if counts[pos] >= limit}


def team_gains(rosters: dict[int, list[tuple[int, int]]], weeks_values: list[dict[int, Decimal]],
               candidates: list[tuple[int, int, list[Decimal]]],
               drop_rule: dict[int, tuple[bool, set[int]]]) -> dict[int, dict[int, dict]]:
    """Zugewinn freier Spieler je Team: um wie viel die beste Aufstellung (optimal_points) mit ihm besser wird,
    summiert über die Wochen des Horizonts (je Woche eigene Aufstellung).

    weeks_values: je Woche Wert der Kaderspieler (fehlt → 0); candidates: (id, Position, Werte je Woche).
    brutto = Σ_w optimal(Kader + Spieler) − optimal(Kader). netto = mit dem günstigsten nötigen Drop: Ist der Kader
    voll oder die Position am Limit (drop_rule, must_drop), das Maximum über alle erlaubten Drops (am Limit nur
    dieselbe Position) von Σ_w optimal(Kader − Drop + Spieler) − optimal(Kader); sonst netto = brutto.
    Nur Paare mit brutto > 0. Rückgabe Spieler-ID → team_id → {"b": brutto, "n": netto}.
    """
    out: dict[int, dict[int, dict]] = {}
    for tid, roster in sorted(rosters.items()):
        entries = [[(pos, vals.get(pid) or ZERO, pid) for pid, pos in roster] for vals in weeks_values]
        base = [optimal_points(e) for e in entries]
        full, at_limit = drop_rule.get(tid, (False, set()))
        for pid, pos, cvals in candidates:
            if all(v <= 0 for v in cvals):
                continue

            def gain(drop=None):
                return sum((optimal_points([x for x in e if x[2] != drop] + [(pos, v, pid)]) - b
                            for e, b, v in zip(entries, base, cvals)), ZERO)
            brutto = gain()
            if brutto <= 0:
                continue
            netto = brutto
            if full or pos in at_limit:
                drops = [q for q, p in roster if pos not in at_limit or p == pos]
                netto = max((gain(q) for q in drops), default=ZERO)
            out.setdefault(pid, {})[tid] = {"b": brutto, "n": netto}
    return out
