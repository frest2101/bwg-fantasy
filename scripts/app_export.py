"""App-Export (Baustein 4): schreibt die App-Daten app/data/*.json nach docs/app_daten.md (Schema 1).

Nur Felder aus einer Positivliste, gerundet erst hier, deterministisch (keine Zeitstempel, feste Sortierung):
eine Datei ändert sich nur, wenn sich ihr Inhalt ändert – dann committen die Actions sie mit.
Format: eine Zeile je Datensatz, damit Diffs lesbar bleiben.
"""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import espn_fetch as ef
import matchup as matchup_module
import players as players_module
from lineup import POSITION_NAMES, SLOT_NAMES
from zahlen import dec, round_to, rounded

SCHEMA = 1
APP_DATA = ef.REPO_DIR / "app" / "data"
# Eigene Kürzel je team_id (Auftrag Session 4, Frage 7) – die ESPN-Kürzel sind uneinheitlich
KUERZEL = {1: "ACB", 2: "HJS", 3: "4DS", 4: "CRN", 5: "TTY", 6: "SAM", 7: "RTZ", 8: "GLS", 9: "DYN", 10: "SGK"}
METRIC_LABELS = {"pf": "PF/Spiel", "allplay": "All-Play-Quote", "win": "Win %", "coaching": "Coaching-Effizienz",
                 "kader": {"potenzial": "Kader-Potenzial", "projektion": "Kader-Projektion ROS"},
                 "floor": "Floor", "form": "Form"}
# Stellen je Schlüssel (gilt für den Teilbaum), sonst zwei (Frage 11 a); Anteile in % mit einer Stelle wie in der Anzeige
PRECISION = {"z": 3, "e": 3, "f": 3, "f_vorwoche": 3, "delta": 3, "r25": 3, "r26": 3, "naechste3": 3, "rest": 3,
             "sos_po": 3, "playoff": 4, "division": 4, "bye": 4, "seeds": 4, "p_home": 4, "anteil": 1,
             # Wetter (wetter.json): eine Stelle wie Open-Meteo, Regenwahrscheinlichkeit ganzzahlig
             "temp": 1, "wind": 1, "boeen": 1, "niederschlag": 1, "schnee": 1, "regen_wahrsch": 0}
LAZY = ("players.json", "dst.json", "matchup.json", "history.json", "transactions.json", "waiver.json", "wetter.json",
        "claude.json")


# ---------------------------------------------------------------- Hilfen

def week_start(season: int, week: int) -> str:
    """Dienstag, an dem die NFL-Woche beginnt (ISO-Datum)."""
    return (ef.WEEK1_START[season] + timedelta(weeks=week - 1)).isoformat()


def dumps(obj) -> str:
    """JSON mit einer Zeile je Datensatz: Schlüssel der obersten Ebene und Listen-/Dict-Einträge je eine Zeile."""
    def compact(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def nested(value):
        return isinstance(value, (dict, list))

    lines = []
    for key, value in obj.items():
        if isinstance(value, list) and value and all(nested(v) for v in value):
            lines.append(f"{compact(key)}:[\n" + ",\n".join(compact(v) for v in value) + "\n]")
        elif isinstance(value, dict) and len(value) > 1 and all(nested(v) for v in value.values()):
            lines.append(f"{compact(key)}:{{\n" + ",\n".join(f"{compact(str(k))}:{compact(v)}"
                                                         for k, v in value.items()) + "\n}")
        else:
            lines.append(f"{compact(key)}:{compact(value)}")
    return "{\n" + ",\n".join(lines) + "\n}\n"


def pick(source: dict | None, keys) -> dict | None:
    return {k: source.get(k) for k in keys} if source else None


# ---------------------------------------------------------------- teams.json

TEAM_FIELDS = ("team_id", "name", "division", "games", "w", "l", "t", "pf", "pa", "pf_per_game", "win_pct",
               "allplay_w", "allplay_l", "allplay_t", "allplay_pct", "median_w", "median_l", "matchup_glueck",
               "spielplan_pkt", "optimal", "verschenkt",
               "efficiency", "kader_potenzial", "kader_projektion", "bench", "floor", "form", "form_delta",
               "form_band", "streak", "projection", "projektions_delta", "waiver_prio", "moves", "rang",
               "rang_division", "rang_score", "norm", "score")
PR_FIELDS = ("mu", "se", "p", "p_quelle", "e", "rang", "rang_vorwoche", "trend", "kernsatz")
SIM_FIELDS = ("playoff", "division", "bye", "restsiege", "seeds")
# je Woche (Arrays in teams.json › wochen); Matchup-Glück, laufende Summe und Effizienz kommen aus compute.py
WEEK_FIELDS = ("pf", "pa", "optimal", "verschenkt", "efficiency", "wochenrang", "allplay_w", "allplay_l", "allplay_t",
               "allplay_pct", "median_win", "median_abstand", "gegner_abstand", "matchup_glueck", "matchup_kum", "gegner_pkt",
               "projektions_delta")


def build_teams(result: dict) -> dict:
    import compute  # erst hier: compute importiert dieses Modul
    weeks = [w["week"] for w in result["weeks"]]
    pr = (result.get("power_ranking") or {}).get("teams", {})
    sim = (result.get("power_ranking") or {}).get("sim") or {}
    positions = (result.get("records") or {}).get("positions", {})
    kader_quelle = result["teams"][0]["kader_quelle"]
    teams = []
    for t in result["teams"]:
        tid = t["team_id"]
        rows = {r["week"]: r for r in result["team_weeks"] if r["team_id"] == tid}
        row = {k: t[k] for k in TEAM_FIELDS}
        row["score_ref"] = row.pop("score")
        row.update(kuerzel=KUERZEL.get(tid), diff=t["pf"] - t["pa"], pa_per_game=t["pa"] / t["games"],
                   verschenkt_avg=t["verschenkt"] / t["games"],
                   verschenkt_max=max((r["verschenkt"] for r in rows.values()), default=None))
        row["pr"] = pick(pr.get(tid), PR_FIELDS)
        if row["pr"] and row["pr"]["trend"] is None:
            row["pr"]["rang_vorwoche"] = None  # kein gültiger Vergleich (Quellwechsel Vorjahr → Projektion, W1)
        row["sim"] = {seeding: pick(sim.get(seeding, {}).get(tid), SIM_FIELDS) for seeding in ("liga", "espn")} \
            if sim else None
        row["espn_sim"] = ((result.get("power_ranking") or {}).get("espn_sim") or {}).get(tid)
        row["positionen"] = positions.get(tid)
        verlauf = {v["week"]: v for v in (pr.get(tid) or {}).get("verlauf", [])}
        wochen = {k: [rows[w][k] if w in rows else None for w in weeks] for k in WEEK_FIELDS}
        wochen.update(gegner=[rows[w]["opponent_id"] for w in weeks], heim=[rows[w]["home"] for w in weeks],
                      ergebnis=[rows[w]["result"] for w in weeks], bank=[rows[w]["bench"] for w in weeks],
                      projektion=[rows[w]["starter_projection"] for w in weeks],
                      mu=[verlauf.get(w, {}).get("mu") for w in weeks],
                      pr_rang=[verlauf.get(w, {}).get("rang") for w in weeks])
        row["wochen"] = wochen
        teams.append(row)
    metrics = [{"key": m, "label": METRIC_LABELS[m][kader_quelle] if m == "kader" else METRIC_LABELS[m]}
               for m in compute.METRICS]
    meta = {"weeks": weeks, "sigma": result["sigma"], "ligafaktor": result.get("ligafaktor"),
            "effizienz_liga": compute.league_efficiency(result["team_weeks"]),
            "kader_quelle": kader_quelle, "metrics": metrics, "profiles": compute.PROFILES,
            "profil_standard": compute.ACTIVE_PROFILE, "norm_standard": compute.ACTIVE_NORM,
            "divisions": result.get("divisions", {}), "kuerzel": KUERZEL}
    return {"meta": meta, "teams": teams}


# ---------------------------------------------------------------- schedule.json

def build_schedule(result: dict) -> dict:
    season = result["season"]
    records = result.get("records") or {}
    top = records.get("top_scorer", {})
    p_home = {g["id"]: g.get("p_home") for g in (result.get("power_ranking") or {}).get("spiele", [])}
    by_week = {w["week"]: w for w in result["weeks"]}
    weeks = []
    for week in range(1, ef.MAX_WEEK + 1):
        entry = {"week": week, "start": week_start(season, week), "playoff": week > result["last_regular_week"],
                 "status": "final" if week in by_week else result["week_status"].get(week, "offen")}
        if week in by_week:
            w = by_week[week]
            rows = [r for r in result["team_weeks"] if r["week"] == week]
            high, low = max(rows, key=lambda r: r["pf"]), min(rows, key=lambda r: r["pf"])
            worst = max(rows, key=lambda r: r["verschenkt"])
            entry.update(ligaschnitt=w["ligaschnitt"], median=w["median"], effizienz_liga=w["effizienz_liga"],
                         top_team_id=w["top_team_id"],
                         high={"team_id": high["team_id"], "pf": high["pf"]},
                         low={"team_id": low["team_id"], "pf": low["pf"]},
                         bank_suende={"team_id": worst["team_id"], "verschenkt": worst["verschenkt"]},
                         top_scorer=top.get(week, []))
        weeks.append(entry)
    games = [{k: g[k] for k in ("week", "home", "away", "home_pf", "away_pf", "winner", "playoff")}
             | {"p_home": p_home.get(g["id"]) if g["winner"] is None else None} for g in result["games"]]
    return {"weeks": weeks, "games": games, "h2h": records.get("h2h", []),
            "records_rs": records.get("records_rs", {}), "records_po": records.get("records_po", {})}


# ---------------------------------------------------------------- lazy-Dateien und claude.json

FREE_AGENTS_PER_POS = 20


def player_selection(result: dict) -> set[int]:
    """Spieler der App: mindestens ein Spiel oder im Kader (Wochenstand), dazu die 20 besten Free Agents je Position
    nach ROS/Spiel. Leer ohne Spielerdaten."""
    data = result.get("players")
    if not data:
        return set()
    pool = data["players"]
    keep = {pid for pid, p in pool.items() if p["team_id"] or p["games"]}
    for pos in POSITION_NAMES:
        free = sorted((p for p in pool.values() if not p["team_id"] and p["pos"] == pos
                       and p["ros_pro_spiel"] is not None), key=lambda p: (-p["ros_pro_spiel"], p["player_id"]))
        keep |= {p["player_id"] for p in free[:FREE_AGENTS_PER_POS]}
    return keep


def build_players(result: dict) -> dict | None:
    """Spieler mit mindestens einem Spiel oder im Kader, dazu die 20 besten Free Agents je Position nach ROS/Spiel.

    mu = Positions-Matchup des Spielers (matchup.player_mu: Gegner und F in Woche mu_woche = N+1, nächste 3, Rest,
    SoS; D/ST aus den D/ST-Faktoren), Wochenstand wie ROS.
    """
    data = result.get("players")
    if not data:
        return None
    pool = data["players"]
    keep = player_selection(result)
    m, dst = result.get("matchup"), result.get("dst")
    rows = []
    for pid in sorted(keep):
        p = pool[pid]
        rows.append({"id": pid, "name": p["name"], "pos": POSITION_NAMES.get(p["pos"], str(p["pos"])),
                     "nfl": p["nfl"], "bye": p["bye_week"] or None, "team": p["team_id"] or 0, "status": p["status"],
                     "inj": p["injury"],
                     "own": p["owned"], "g": p["games"], "pts": p["pts"], "avg": p["avg"], "floor": p["floor"],
                     "ceil": p["ceiling"], "sd": p["sd"], "form": p["form"], "form_d": p["form_delta"],
                     "trend": p["trend"], "spark": p["sparkline"], "starts": p["starts"],
                     "bench_pts": p["bench_pts"], "proj_d": p["proj_delta"],
                     "wk": [[w["actual"], w["projection"], 1 if w["bye"] else 0, w["team_id"] or 0,
                             SLOT_NAMES.get(w["slot"]) if w["slot"] is not None else None] for w in p["weeks"]],
                     "ros": p["ros"], "ros_g": p["ros_pro_spiel"], "rest_g": p["restspiele"], "ros_po": p["ros_po"],
                     "ros_rang": p["ros_rang"], "ros_ue": p["ros_ueber_ersatz"],
                     "mu": matchup_module.player_mu(m, dst, p["pos"], p["pro_team"])})
    return {"weeks": data["weeks"], "ersatz": {POSITION_NAMES.get(k, str(k)): v for k, v in data["ersatz"].items()},
            "ros_nach_woche": data["ros_after_week"], "mu_woche": (m or {}).get("wochen", {}).get("n1"),
            "cv": {POSITION_NAMES.get(k, str(k)): v for k, v in data["cv"].items()}, "players": rows}


DST_FIELDS = ("id", "abbrev", "bye", "z25", "z26", "n", "r25", "r26", "f", "f_vorwoche", "delta", "rang",
              "rang_vorwoche", "z_last3", "ausloeser", "beobachten", "naechste3", "rest", "sos_po", "besitzer", "status")


def build_dst(result: dict) -> dict | None:
    data = result.get("dst")
    if not data:
        return None
    abbrev = {t["id"]: t["abbrev"] for t in data["teams"]}
    teams = [{k: t[k] for k in DST_FIELDS} | {"naechste": [n | {"opp": abbrev.get(n["opp"])} if "opp" in n else n
                                                           for n in t["naechste"]]} for t in data["teams"]]
    return {"through_week": data["through_week"], "ligaschnitt": data["ligaschnitt"], "formel": data["formel"],
            "ausloeser_legende": data["ausloeser_legende"], "teams": teams}


# Positions-Matchup: Kopf und je Defense und Position nur diese Felder (n25, zugelassen und f_verlauf bleiben im Rechenwerk)
MATCHUP_HEAD = ("through_week", "saison", "vorjahr", "vorjahr_quelle", "positionen", "ligaschnitt", "formel",
                "ausloeser_legende", "wochen")
MATCHUP_FIELDS = ("z25", "z26", "n", "r25", "r26", "f", "f_vorwoche", "delta", "rang", "rang_vorwoche", "ausloeser")


def build_matchup(result: dict) -> dict | None:
    """Positions-Matchup je NFL-Defense und Position (Positivliste MATCHUP_HEAD, MATCHUP_FIELDS); None ohne Daten."""
    data = result.get("matchup")
    if not data:
        return None
    defenses = [{"id": d["id"], "abbrev": d["abbrev"], "bye": d["bye"],
                 "pos": {name: {k: p[k] for k in MATCHUP_FIELDS} for name, p in d["pos"].items()}}
                for d in data["defenses"]]
    return {k: data[k] for k in MATCHUP_HEAD} | {"defenses": defenses}


def app_player_ids(result: dict) -> set[int]:
    """Spieler, die der Spieler-Tab zeigen kann: die Auswahl von players.json plus die Kaderspieler laut Tagesstand
    (waiver.json); leer ohne Spielerdaten."""
    selection = player_selection(result)
    pool = result.get("pool_latest")
    if selection and pool:
        selection |= {p["id"] for p in pool["players"] if p.get("onTeamId")}
    return selection


def build_transactions(result: dict) -> dict | None:
    """Moves und Draft; je Spieler in_app (bool), ob die App eine Spielerseite dazu hat – sonst zeigt sie den Namen
    ohne Link (gedroppte Spieler ohne Einsatz führt players.json nicht)."""
    data = result.get("transactions")
    if not data:
        return None
    known = app_player_ids(result)
    items = [x | {"items": [i | {"in_app": i["player_id"] in known} for i in x["items"]]} for x in data["items"]]
    draft = [d | {"in_app": d["player_id"] in known} for d in data["draft"]]
    return {"spieler": data["spieler"], "items": items, "aufstellungswechsel": data["aufstellungswechsel"], "draft": draft}


def waiver_order(pool: dict, result: dict) -> tuple[list[int] | None, str | None, str | None]:
    """Waiver-Reihenfolge als Liste der team_ids (1 = zuerst), ihre Quelle und ihr Stand: "tageslauf" aus dem
    Pool-Auszug (mTeam.waiverRank; Stand = Abrufzeit der letzten Änderung, auch wenn ein späterer Lauf sie nur
    nachgezogen hat), sonst "wochenabruf" aus dem Wochenstand (teams.waiver_prio, Stand None); (None, None, None) ohne beides."""
    daily = pool.get("waiver_reihenfolge")
    if daily:
        order = [int(tid) for tid, _ in sorted(daily.items(), key=lambda kv: (kv[1], int(kv[0])))]
        return order, "tageslauf", pool.get("waiver_reihenfolge_stand") or pool["stand"]
    weekly = sorted((t["waiver_prio"], t["team_id"]) for t in result["teams"] if t.get("waiver_prio") is not None)
    return ([tid for _, tid in weekly], "wochenabruf", None) if weekly else (None, None, None)


def team_needs(pool: dict, result: dict) -> dict | None:
    """Bedarf je Team (players.team_needs) aus dem Kader laut Tagesstand und ROS/Spiel laut Wochenstand; None ohne
    Regular-Season-ROS (vor dem ersten ROS-Auszug und nach W14). Positionen als Kürzel, Schlüssel team_id."""
    data = result["players"]
    after = data.get("ros_after_week")
    if after is None or after >= players_module.LAST_REGULAR_WEEK:
        return None
    weekly = data["players"]
    rosters: dict[int, list] = {}
    for p in pool["players"]:
        w = weekly.get(p["id"])
        if p.get("onTeamId") and w:  # ohne Wochenpool-Eintrag ist die Position unbekannt: nicht aufstellbar
            rosters.setdefault(p["onTeamId"], []).append((p["id"], w["pos"]))
    per_game = {pid: w["ros_pro_spiel"] for pid, w in weekly.items()}
    name = lambda pos: POSITION_NAMES.get(pos, str(pos)) if pos is not None else None  # noqa: E731
    return {tid: {"luecken": [g | {"pos": name(g["pos"])} for g in n["luecken"]],
                  "ueber_ersatz": {name(pos): v for pos, v in n["ueber_ersatz"].items()}}
            for tid, n in players_module.team_needs(rosters, per_game, data["ersatz"]).items()}


def build_waiver(result: dict) -> dict | None:
    """Tagesstand je Spieler aus dem Pool-Auszug des Tageslaufs (Session 6): Status, Fantasy-Team, Verletzung,
    Besitz ESPN-weit mit Trend, Waiver-Frist, Projektion der nächsten Woche, letzte ESPN-News. Dazu (Session 7) die
    Waiver-Reihenfolge der Teams und der Bedarf je Team.

    Spieler: die Auswahl von players.json (Kader, mit Spiel, 20 beste Free Agents je Position) plus alle, die laut
    Tagesstand in einem Kader stehen. Grundlage des Waiver-Tabs; None ohne Pool-Auszug oder Spielerdaten.
    """
    pool = result.get("pool_latest")
    selection = player_selection(result)
    if not pool or not selection:
        return None
    keep = selection | {p["id"] for p in pool["players"] if p.get("onTeamId")}
    weekly = result["players"]["players"]  # ganzer Wochenpool mit Stammdaten (Name, Position, NFL-Team)
    number = lambda v: dec(v) if v is not None else None  # noqa: E731 – ESPN-Floats erst beim Schreiben runden
    rows = []
    for p in pool["players"]:
        if p["id"] not in keep:
            continue
        row = {"id": p["id"], "team": p.get("onTeamId") or 0, "status": p.get("status"), "inj": p.get("injuryStatus"),
               "own": number(p.get("percentOwned")), "own_d": number(p.get("percentChange")),
               "started": number(p.get("percentStarted")), "waiver_bis": p.get("waiverProcessDate"),
               "proj": number(p.get("proj_naechste_woche")), "news": p.get("lastNewsDate")}
        if p["id"] not in selection:
            # Kaderspieler, den players.json nicht führt (unter der Woche geholt, ohne Spiel, nicht Top 20 seiner
            # Position): Stammdaten aus dem Wochenpool, damit die App ihn benennen kann; None, wenn auch dort unbekannt
            w = weekly.get(p["id"])
            row.update(name=w["name"] if w else None, pos=POSITION_NAMES.get(w["pos"], str(w["pos"])) if w else None,
                       nfl=w["nfl"] if w else None)
        rows.append(row)
    reihenfolge, quelle, stand = waiver_order(pool, result)
    return {"stand": pool["stand"], "woche": pool["woche"], "reihenfolge": reihenfolge, "reihenfolge_quelle": quelle,
            "reihenfolge_stand": stand, "bedarf": team_needs(pool, result), "spieler": rows}


CLAUDE_PLAYER_COLS = ("name", "pos", "nfl", "inj", "avg", "form", "trend", "ros_g", "ros_rang", "gegner_n1", "mu_n1")


def fixed(value, places: int):
    """Zahl mit fester Stellenzahl für Zeilen ohne Schlüssel (claude.json); None bleibt None."""
    return None if value is None else float(round_to(value, places))


def claude_player(p: dict) -> list:
    """Spielerzeile nach CLAUDE_PLAYER_COLS; gegner_n1 und mu_n1 aus mu.n1 (Kürzel und F mit 3 Stellen, None bei Bye
    oder ohne Wert)."""
    n1 = (p.get("mu") or {}).get("n1") or {}
    mu = {"gegner_n1": n1.get("opp"), "mu_n1": fixed(n1.get("f"), 3)}
    return [mu[c] if c in mu else p.get(c) for c in CLAUDE_PLAYER_COLS]


def build_claude(result: dict, teams: dict, schedule: dict, players: dict | None, dst: dict | None,
                 transactions: dict | None) -> dict:
    """Kompakte Datei für Claude-Sessions unterwegs (< 50 KB): Tabellen als Spaltenkopf plus Zeilen, Teams als Kürzel."""
    k = KUERZEL.get
    tabelle = []
    for t in teams["teams"]:
        pr, sim = t.get("pr") or {}, (t.get("sim") or {}).get("liga") or {}
        tabelle.append([t["rang"], k(t["team_id"]), t["name"], f"{t['w']}-{t['l']}-{t['t']}", t["pf"],
                        t["allplay_pct"], t["matchup_glueck"], t["efficiency"], t["form"],
                        50 + 10 * t["score_ref"]["Stärke"]["z"], t["kader_projektion"] or t["kader_potenzial"],
                        pr.get("rang"), pr.get("mu"), fixed(pr.get("e"), 3), pr.get("trend"),
                        fixed(sim.get("playoff"), 4)])
    out = {"legende": "BWG Fantasy Liga (ESPN 1166555857), inoffizielle Auswertung. Punkte = ESPN appliedTotal; "
                      "Projektionen sind ESPN-Input. Zeilen gehören zu den *_spalten; mu_n1 = Positions-Matchup F des "
                      "Gegners in matchup_woche, > 1 günstig. Definitionen: docs/app_daten.md "
                      "und CLAUDE.md (Rechenregeln) im Repo frest2101/bwg-fantasy.",
           "stand": {"saison": result["season"], "nach_woche": result["through_week"],
                     "kader_quelle": teams["meta"]["kader_quelle"], "ros_nach_woche": result.get("ros_after_week"),
                     "matchup_woche": (result.get("matchup") or {}).get("wochen", {}).get("n1")},
           "teams": {k(t["team_id"]): t["name"] for t in teams["teams"]},
           "tabelle_spalten": ["rang", "team", "name", "w_l_t", "pf", "allplay_pct", "matchup_glueck", "effizienz_pct", "form",
                               "score_50_10z", "kader", "pr_rang", "mu", "e", "trend", "playoff_anteil"],
           "tabelle": tabelle,
           "spiele_spalten": ["woche", "heim", "gast", "pf_heim", "pf_gast", "p_heim"],
           "spiele": [[g["week"], k(g["home"]), k(g["away"]), g["home_pf"], g["away_pf"], fixed(g.get("p_home"), 4)]
                      for g in schedule["games"]]}
    if players:
        rows = players["players"]
        out["spieler_spalten"] = list(CLAUDE_PLAYER_COLS)
        out["kader"] = {k(tid): [claude_player(p) for p in rows if p["team"] == tid] for tid in sorted(KUERZEL)}
        free = [p for p in rows if not p["team"] and p.get("ros_g") is not None]
        out["free_agents"] = {pos: [claude_player(p) + [p.get("status")]
                                    for p in sorted((p for p in free if p["pos"] == pos), key=lambda p: -p["ros_g"])[:10]]
                              for pos in POSITION_NAMES.values()}
    if dst:
        out["dst_spalten"] = ["nfl", "f", "naechste3", "rest", "sos_w15_17", "besitzer"]
        out["dst"] = [[d["abbrev"], fixed(d["f"], 3), fixed(d["naechste3"], 3), fixed(d["rest"], 3), fixed(d["sos_po"], 3),
                       k(d["besitzer"]) if d["besitzer"] else d["status"]] for d in dst["teams"]]
    if transactions:
        out["transaktionen_spalten"] = ["datum_ms", "team", "typ", "zugang", "abgang"]
        out["transaktionen"] = [[t["datum"], k(t["team_id"]), t["type"],
                                 [i["name"] for i in t["items"] if i["type"] == "ADD"],
                                 [i["name"] for i in t["items"] if i["type"] == "DROP"]]
                                for t in transactions.get("letzte", [])]
    return out


def build(result: dict) -> dict[str, dict]:
    """Alle App-Dateien (ohne manifest) als Python-Objekte, noch ungerundet."""
    teams, schedule = build_teams(result), build_schedule(result)
    files = {"teams.json": teams, "schedule.json": schedule}
    players, dst = build_players(result), build_dst(result)
    optional = {"players.json": players, "dst.json": dst, "matchup.json": build_matchup(result),
                "history.json": result.get("history"),
                "transactions.json": build_transactions(result),
                "waiver.json": build_waiver(result), "wetter.json": result.get("wetter")}
    files.update({name: obj for name, obj in optional.items() if obj})
    files["claude.json"] = build_claude(result, teams, schedule, players, dst, result.get("transactions"))
    return files


# ---------------------------------------------------------------- Schreiben

def round_file(name: str, obj: dict):
    """Rundung je Datei: D/ST und Positions-Matchup mit den Stellen ihres Moduls (PRECISION dort), sonst PRECISION;
    Rangpunkte als ganze Zahlen."""
    import dst as dst_module
    own = {"dst.json": dst_module.PRECISION, "matchup.json": matchup_module.PRECISION}
    data = rounded(obj, precision=own.get(name, PRECISION))
    if name == "teams.json":
        for t in data["teams"]:
            t["norm"]["rank"] = {m: int(v) for m, v in t["norm"]["rank"].items()}
    return data


def render(files: dict[str, dict], result: dict) -> dict[str, bytes]:
    """Gerundete, serialisierte Dateien plus manifest.json (Hash je Datei)."""
    content = {name: dumps(round_file(name, obj)).encode("utf-8") for name, obj in sorted(files.items())}
    manifest = {"schema": SCHEMA, "season": result["season"], "through_week": result["through_week"],
                "datenstand": {"woche_final": result["through_week"], "ros_nach_woche": result.get("ros_after_week"),
                               "pool_woche": result.get("pool_week"),
                               "transaktionen_bis": result.get("transactions_until"),
                               # Tageslauf: Abrufzeit (UTC, ISO) des jüngsten Pool-Auszugs bzw. Wetterabrufs
                               "pool_stand": (result.get("pool_latest") or {}).get("stand"),
                               "wetter_stand": (result.get("wetter") or {}).get("stand")},
                "files": {name: {"v": hashlib.sha256(data).hexdigest()[:12], "bytes": len(data),
                                 "lazy": name in LAZY} for name, data in content.items()}}
    content["manifest.json"] = dumps(manifest).encode("utf-8")
    return content


def write(content: dict[str, bytes], folder: Path = APP_DATA) -> list[str]:
    """Schreibt geänderte Dateien, entfernt veraltete *.json im Ordner; gibt die geänderten Namen zurück."""
    folder.mkdir(parents=True, exist_ok=True)
    changed = []
    for name, data in content.items():
        path = folder / name
        if not path.exists() or path.read_bytes() != data:
            ef.save_atomic(path, data)
            changed.append(name)
    for stale in sorted(folder.glob("*.json")):
        if stale.name not in content:
            stale.unlink()
            changed.append(f"{stale.name} (entfernt)")
    return changed

