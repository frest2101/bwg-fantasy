"""Record Book der Saison und Transaktionsliste (Baustein 4).

Reine Funktionen: Eingabe sind die Team-Wochen aus compute.compute_team_weeks, die Kaderzeilen (rawdata.RosterRow)
und das Transaktions-Archiv; Ausgabe sind ungerundete Decimal-Werte (gerundet wird erst beim Export).
Regeln: CLAUDE.md und docs/auftraege/session4_vorbereitung.md §2 (Record Book), Auftrag Session 4, Frage 10.

Bei Gleichstand nennt jeder Rekord alle Einträge. Wochen ohne Gegner (Bye, nur Playoffs) zählen nirgends.
Personenbezogene Felder des Archivs (memberId, isLeagueManager) gibt dieses Modul nie heraus.
"""

from decimal import Decimal

import rawdata
from lineup import (DST, K, POSITION_NAMES, QB, RB, SLOT_DST, SLOT_FLEX, SLOT_IR, SLOT_K, SLOT_NAMES, SLOT_OP, SLOT_QB,
                    SLOT_RB, SLOT_TE, SLOT_WR, TE, WR, is_starter)
from zahlen import HUNDRED, ZERO

# Reihenfolge der Rekorde in der Ausgabe (RS und Playoffs gleich)
RECORD_KEYS = ("hoechster_score", "niedrigster_score", "groesster_sieg", "knappstes_ergebnis",
               "hoechster_verlierer", "niedrigster_sieger", "laengste_siegesserie", "laengste_niederlagenserie",
               "hoechste_bank", "meiste_verschenkt", "bester_spieler")
# Positions-Breakdown: nach defaultPositionId und (Umschalter) nach Starter-Slot; FLEX und OP getrennt
POSITION_ORDER = (QB, RB, WR, TE, K, DST)
SLOT_ORDER = (SLOT_QB, SLOT_RB, SLOT_WR, SLOT_TE, SLOT_FLEX, SLOT_OP, SLOT_DST, SLOT_K)
TOP_SCORER = 10

# Transaktionen (Auftrag Session 4, Frage 10): nur ausgeführte Moves und angenommene Trades
EXECUTED, TRADE_ACCEPT = "EXECUTED", "TRADE_ACCEPT"
MOVE_TYPES = ("WAIVER", "FREEAGENT")
LINEUP_TYPES = ("ROSTER", "FUTURE_ROSTER")        # Aufstellungswechsel; reine Drops darin sind Moves (s. u.)
PLAYER_ITEMS = ("ADD", "DROP")                     # Item-Typen, die einen Spieler zwischen Team und Pool bewegen
LINEUP_ITEM = "LINEUP"
RECENT_DAYS, DAY_MS = 14, 86_400_000               # „letzte 14 Tage“ ab dem jüngsten Archivdatum


# ---------------------------------------------------------------- Hilfen

def games_only(team_weeks: list[dict]) -> list[dict]:
    """Team-Wochen mit Gegner; eine Woche ohne Gegner (Bye in den Playoffs) ist kein Spiel."""
    return [r for r in team_weeks if r.get("opponent_id") is not None]


def extremes(candidates: list, value, highest: bool = True) -> list:
    """Alle Kandidaten mit dem höchsten (bzw. niedrigsten) Wert – bei Gleichstand alle."""
    if not candidates:
        return []
    target = (max if highest else min)(value(c) for c in candidates)
    return [c for c in candidates if value(c) == target]


def team_week_entry(r: dict, value: Decimal) -> dict:
    """Team-Wochen-Eintrag eines Rekords: team_id, week, opponent_id, wert."""
    return {"team_id": r["team_id"], "week": r["week"], "opponent_id": r["opponent_id"], "wert": value}


def player_entry(p, week: int) -> dict:
    """Spieler-Eintrag aus einer RosterRow: Position und Slot als Namen (lineup.POSITION_NAMES, SLOT_NAMES)."""
    return {"player_id": p.player_id, "name": p.name, "pos": POSITION_NAMES.get(p.pos, str(p.pos)),
            "team_id": p.team_id, "week": week, "slot": SLOT_NAMES.get(p.slot, str(p.slot)), "wert": p.actual}


def game_rows(team_weeks: list[dict]) -> list[dict]:
    """Je Spiel eine Zeile aus Sicht des Siegers (bei Unentschieden die kleinere team_id)."""
    return [r for r in games_only(team_weeks)
            if r["result"] == "W" or (r["result"] == "T" and r["team_id"] < r["opponent_id"])]


def game_entry(r: dict) -> dict:
    """Spiel-Eintrag: team_ids = [Sieger, Verlierer], punkte in derselben Reihenfolge, wert = Differenz."""
    return {"week": r["week"], "team_ids": [r["team_id"], r["opponent_id"]], "punkte": [r["pf"], r["pa"]],
            "wert": r["pf"] - r["pa"], "unentschieden": r["result"] == "T"}


# ---------------------------------------------------------------- H2H

def h2h(team_weeks: list[dict], team_ids: list[int] | None = None) -> list[dict]:
    """Direkte Duelle je Paar a < b: Spiele, Siege/Niederlagen von a, Unentschieden, pf_diff = Σ PF a − Σ PF b.

    Mit team_ids erscheinen alle Paare (auch ohne Spiel, dann mit Nullen); sonst nur die aus team_weeks.
    """
    ids = sorted(set(team_ids) if team_ids is not None
                 else {r["team_id"] for r in games_only(team_weeks)} | {r["opponent_id"] for r in games_only(team_weeks)})
    pairs = {(a, b): {"a": a, "b": b, "spiele": 0, "w_a": 0, "l_a": 0, "t": 0, "pf_diff": ZERO}
             for i, a in enumerate(ids) for b in ids[i + 1:]}
    for r in games_only(team_weeks):
        a, b = r["team_id"], r["opponent_id"]
        if a > b or (a, b) not in pairs:
            continue  # jedes Spiel steht zweimal in team_weeks; gezählt wird die Zeile von a
        p = pairs[(a, b)]
        p["spiele"] += 1
        p["w_a"] += r["result"] == "W"
        p["l_a"] += r["result"] == "L"
        p["t"] += r["result"] == "T"
        p["pf_diff"] += r["pf"] - r["pa"]
    return list(pairs.values())


# ---------------------------------------------------------------- Serien

def result_runs(rows: list[dict]) -> list[tuple[str, int, int, int]]:
    """Serien gleicher Ergebnisse eines Teams, chronologisch: (Ergebnis, erste Woche, letzte Woche, Länge).

    Ein Unentschieden ist eine eigene Serie (wie compute.streak) und unterbricht Sieg- und Niederlagenserien.
    """
    runs: list[tuple[str, int, int, int]] = []
    for r in sorted(games_only(rows), key=lambda r: r["week"]):
        if runs and runs[-1][0] == r["result"]:
            result, first, _, length = runs[-1]
            runs[-1] = (result, first, r["week"], length + 1)
        else:
            runs.append((r["result"], r["week"], r["week"], 1))
    return runs


def longest_streaks(team_weeks: list[dict], result: str) -> list[dict]:
    """Längste Serie aus result („W“ oder „L“) über alle Teams; bei Gleichstand alle Serien (auch zwei eines Teams).

    Eintrag: team_id, weeks = [erste, letzte Woche], wert = Länge, laufend = Serie reicht bis zum letzten Spiel.
    """
    candidates = []
    for team_id in sorted({r["team_id"] for r in team_weeks}):
        runs = result_runs([r for r in team_weeks if r["team_id"] == team_id])
        candidates += [{"team_id": team_id, "weeks": [first, last], "wert": length, "laufend": i == len(runs) - 1}
                       for i, (res, first, last, length) in enumerate(runs) if res == result]
    return sorted(extremes(candidates, lambda c: c["wert"]), key=lambda c: (c["weeks"][0], c["team_id"]))


# ---------------------------------------------------------------- Rekorde

def season_records(team_weeks: list[dict], rosters: dict[int, list]) -> dict[str, list[dict]]:
    """Rekorde einer Saisonphase (RS oder Playoffs) aus Team-Wochen und Kaderzeilen je Woche.

    Team-Woche (team_id, week, opponent_id, wert): höchster/niedrigster Score, höchster Verlierer-Score,
    niedrigster Sieger-Score, höchste Bank-Punkte, meiste Verschenkt (Optimal − PF).
    Spiel (week, team_ids [Sieger, Verlierer], punkte, wert = Differenz, unentschieden): größter Sieg (ohne
    Unentschieden), knappstes Ergebnis (Unentschieden = 0 zählt mit). Serien siehe longest_streaks.
    Bester Einzelspieler über alle Kaderspieler außer IR (auch Bank), Slot als Angabe.
    """
    games = games_only(team_weeks)

    def team_week_top(rows: list[dict], key: str, highest: bool = True) -> list[dict]:
        return sorted((team_week_entry(r, r[key]) for r in extremes(rows, lambda r: r[key], highest)),
                      key=lambda e: (e["week"], e["team_id"]))

    def game_top(rows: list[dict], highest: bool) -> list[dict]:
        return sorted((game_entry(r) for r in extremes(rows, lambda r: r["pf"] - r["pa"], highest)),
                      key=lambda e: (e["week"], e["team_ids"]))

    played = {(r["team_id"], r["week"]) for r in games}
    players = [(week, p) for week, rows in sorted(rosters.items()) for p in rows
               if p.slot != SLOT_IR and (p.team_id, week) in played]
    return {
        "hoechster_score": team_week_top(games, "pf"),
        "niedrigster_score": team_week_top(games, "pf", highest=False),
        "groesster_sieg": game_top([r for r in game_rows(games) if r["result"] == "W"], highest=True),
        "knappstes_ergebnis": game_top(game_rows(games), highest=False),
        "hoechster_verlierer": team_week_top([r for r in games if r["result"] == "L"], "pf"),
        "niedrigster_sieger": team_week_top([r for r in games if r["result"] == "W"], "pf", highest=False),
        "laengste_siegesserie": longest_streaks(games, "W"),
        "laengste_niederlagenserie": longest_streaks(games, "L"),
        "hoechste_bank": team_week_top(games, "bench"),
        "meiste_verschenkt": team_week_top(games, "verschenkt"),
        "bester_spieler": sorted((player_entry(p, week) for week, p in extremes(players, lambda wp: wp[1].actual)),
                                 key=lambda e: (e["week"], e["team_id"], e["player_id"])),
    }


# ---------------------------------------------------------------- Positionen

def ranked(values: dict[int, Decimal]) -> dict[int, int]:
    """Ligarang 1…n nach absteigendem Wert; Gleichstand teilt sich den besseren Rang (1 + Anzahl besserer)."""
    return {t: 1 + sum(1 for o in values.values() if o > v) for t, v in values.items()}


def positions(team_weeks: list[dict], rosters: dict[int, list]) -> dict[int, dict]:
    """Kumulierte Starter-Punkte je Team nach Position (defaultPositionId) und nach Starter-Slot.

    Je Schlüssel: pts, anteil = pts / summe × 100, rang = Ligarang der Punkte. summe = Σ Starter = PF.
    Gezählt werden die Team-Wochen aus team_weeks (Bye-Wochen nicht).
    """
    played = {(r["team_id"], r["week"]) for r in games_only(team_weeks)}
    team_ids = sorted({t for t, _ in played})
    by_pos = {t: dict.fromkeys(POSITION_ORDER, ZERO) for t in team_ids}
    by_slot = {t: dict.fromkeys(SLOT_ORDER, ZERO) for t in team_ids}
    for week, rows in sorted(rosters.items()):
        for p in rows:
            if (p.team_id, week) not in played or not is_starter(p.slot):
                continue
            if p.pos not in by_pos[p.team_id] or p.slot not in by_slot[p.team_id]:
                raise ValueError(f"W{week}: Starter {p.player_id} mit unbekannter Position {p.pos} oder Slot {p.slot}")
            by_pos[p.team_id][p.pos] += p.actual
            by_slot[p.team_id][p.slot] += p.actual

    def breakdown(sums: dict[int, dict[int, Decimal]], order: tuple, names: dict) -> dict[int, dict]:
        ranks = {key: ranked({t: sums[t][key] for t in team_ids}) for key in order}
        out = {}
        for t in team_ids:
            total = sum(sums[t].values(), ZERO)
            out[t] = {names[key]: {"pts": sums[t][key],
                                   "anteil": sums[t][key] / total * HUNDRED if total else ZERO,
                                   "rang": ranks[key][t]} for key in order}
        return out

    nach_position = breakdown(by_pos, POSITION_ORDER, POSITION_NAMES)
    nach_slot = breakdown(by_slot, SLOT_ORDER, SLOT_NAMES)
    return {t: {"summe": sum(by_pos[t].values(), ZERO), "nach_position": nach_position[t],
                "nach_slot": nach_slot[t]} for t in team_ids}


# ---------------------------------------------------------------- Top-Scorer

def top_scorer(rosters: dict[int, list], n: int = TOP_SCORER, abbrev: dict[int, str] | None = None) -> dict[int, list]:
    """Je Woche die n besten Kaderspieler aller Teams inklusive Bank (ohne IR); Gleichstand auf Platz n kommt mit.

    {week: [Spieler]}, Spieler: rang (1 + Anzahl besserer), player_id, name, pos, pro_team (NFL-Team-ID zum
    Abrufzeitpunkt der Woche), nfl (Kürzel dazu aus abbrev, sonst None), team_id, slot, pts, proj.
    """
    abbrev = abbrev or {}
    result = {}
    for week, rows in sorted(rosters.items()):
        ordered = sorted((p for p in rows if p.slot != SLOT_IR), key=lambda p: (-p.actual, p.team_id, p.player_id))
        cut = ordered[n - 1].actual if len(ordered) >= n else None
        chosen = [p for p in ordered if cut is None or p.actual >= cut]
        result[week] = [{"rang": 1 + sum(1 for o in chosen if o.actual > p.actual), "player_id": p.player_id,
                         "name": p.name, "pos": POSITION_NAMES.get(p.pos, str(p.pos)), "pro_team": p.pro_team,
                         "nfl": abbrev.get(p.pro_team), "team_id": p.team_id,
                         "slot": SLOT_NAMES.get(p.slot, str(p.slot)), "pts": p.actual, "proj": p.projection}
                        for p in chosen]
    return result


# ---------------------------------------------------------------- Einstieg Record Book

def compute_records(ssn: rawdata.Season, weeks: list[int], team_weeks: list[dict],
                    playoff_team_weeks: list[dict] | None = None) -> dict:
    """Record Book der Saison: H2H (nur RS), Rekorde RS und Playoffs getrennt, Positionen, Top-Scorer je Woche.

    team_weeks: Regular Season aus compute.compute_team_weeks (nur die Wochen in weeks zählen).
    playoff_team_weeks: dieselbe Form für W15–17, sobald es sie gibt; ohne sie ist records_po leer.
    """
    rs = [r for r in team_weeks if r["week"] in weeks]
    rosters = {week: ssn.roster(week) for week in sorted(weeks)}
    po = playoff_team_weeks or []
    po_rosters = {week: ssn.roster(week) for week in sorted({r["week"] for r in games_only(po)})}
    return {
        "h2h": h2h(rs, [t["id"] for t in ssn.teams()]),
        "records_rs": season_records(rs, rosters),
        "records_po": season_records(po, po_rosters),
        "positions": positions(rs, rosters),
        "top_scorer": top_scorer(rosters, abbrev={t.id: t.abbrev for t in ssn.nfl().values()}),
    }


# ---------------------------------------------------------------- Transaktionen

def player_names(ssn: rawdata.Season) -> dict[int, str]:
    """Spielernamen je ID aus Kader und Pool der Wochen 1…through; eine jüngere Woche überschreibt eine ältere."""
    names: dict[int, str] = {}
    for week in range(1, ssn.through + 1):
        for row in list(ssn.roster(week)) + list(ssn.pool(week) or []):
            if row.name:
                names[row.player_id] = row.name
    return names


def tx_date(t: dict) -> int | None:
    """Datum eines Archiv-Eintrags als Epoch-ms: processDate, sonst proposedDate (FREEAGENT, ROSTER, TRADE_ACCEPT)."""
    return t.get("processDate") or t.get("proposedDate")


def player_items(t: dict, names: dict[int, str]) -> list[dict]:
    """ADD/DROP-Items eines Archiv-Eintrags mit Spielername (None, wenn unbekannt); von/nach 0 = Pool."""
    return [{"type": i["type"], "player_id": i["playerId"], "name": names.get(i["playerId"]),
             "from_team_id": i["fromTeamId"], "to_team_id": i["toTeamId"]}
            for i in t.get("items") or [] if i.get("type") in PLAYER_ITEMS]


def transaction_list(entries: list[dict], names: dict[int, str]) -> list[dict]:
    """Ausgeführte Moves und angenommene Trades, sortiert nach (datum, id).

    - WAIVER/FREEAGENT mit status EXECUTED: je Item ADD/DROP mit Spieler, von/nach Team (0 = Pool).
    - ROSTER/FUTURE_ROSTER mit status EXECUTED und ADD/DROP-Items (reine Drops, z. B. Keeper-Kürzung vor dem
      Draft): ebenfalls Moves, mit ihrem ESPN-Typ; ihre LINEUP-Items zählen nur in lineup_changes.
    - TRADE_ACCEPT (im Archiv ohne status, items und processDate): Team und Datum, ohne Spieler.
    Gescheiterte und zurückgezogene Claims, Vorschläge und der Draft fallen weg; memberId & Co. nie.
    """
    out = []
    for t in entries:
        kind = t.get("type")
        if kind == TRADE_ACCEPT and t.get("status") in (None, EXECUTED):
            items = []
        elif kind in MOVE_TYPES + LINEUP_TYPES and t.get("status") == EXECUTED:
            items = player_items(t, names)
            if not items:
                continue  # reiner Aufstellungswechsel
        else:
            continue
        out.append({"id": t["id"], "type": kind, "team_id": t.get("teamId"), "datum": tx_date(t),
                    "periode": t.get("scoringPeriodId"), "items": items})
    return sorted(out, key=lambda m: (m["datum"] or 0, m["id"]))


def lineup_changes(entries: list[dict], team_ids: list[int]) -> dict[int, int]:
    """Zahl der ausgeführten Aufstellungswechsel (ROSTER/FUTURE_ROSTER mit LINEUP-Item) je team_id."""
    counts = dict.fromkeys(sorted(team_ids), 0)
    for t in entries:
        if t.get("type") in LINEUP_TYPES and t.get("status") == EXECUTED \
                and any(i.get("type") == LINEUP_ITEM for i in t.get("items") or []):
            counts[t["teamId"]] = counts.get(t["teamId"], 0) + 1
    return dict(sorted(counts.items()))


def draft_list(picks: list[dict], names: dict[int, str]) -> list[dict]:
    """Draft inklusive Keeper, sortiert nach Pick: pick, runde, runden_pick, team_id, player_id, name, keeper."""
    return [{"pick": p["overallPickNumber"], "runde": p["roundId"], "runden_pick": p["roundPickNumber"],
             "team_id": p["teamId"], "player_id": p["playerId"], "name": names.get(p["playerId"]),
             "keeper": bool(p["keeper"])}
            for p in sorted(picks, key=lambda p: p["overallPickNumber"])]


def recent(items: list[dict], until: int | None, days: int = RECENT_DAYS) -> list[dict]:
    """Moves der letzten days Tage, gezählt ab dem jüngsten Datum der Liste (until), nicht ab heute."""
    if until is None:
        return []
    return [m for m in items if m["datum"] and m["datum"] > until - days * DAY_MS]


def compute_transactions(ssn: rawdata.Season) -> dict:
    """Transaktionsliste für die App.

    items (Moves und Trades, transaction_list), aufstellungswechsel je Team, draft, spieler (id → Name aller
    genannten Spieler), bis = jüngstes Datum der Liste (Epoch-ms, None ohne Eintrag), letzte = items der
    14 Tage bis bis. Namen aus Kader und Pool bis Woche through.
    """
    entries = ssn.transactions()
    names = player_names(ssn)
    items = transaction_list(entries, names)
    draft = draft_list(ssn.draft(), names)
    until = max((m["datum"] for m in items if m["datum"]), default=None)
    ids = sorted({i["player_id"] for m in items for i in m["items"]} | {d["player_id"] for d in draft})
    return {
        "items": items,
        "aufstellungswechsel": lineup_changes(entries, [t["id"] for t in ssn.teams()]),
        "draft": draft,
        "spieler": {pid: names.get(pid) for pid in ids},
        "bis": until,
        "letzte": recent(items, until),
    }
