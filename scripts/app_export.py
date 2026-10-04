"""App-Export (Baustein 4): schreibt die App-Daten app/data/*.json nach docs/app_daten.md (Schema 1).

Nur Felder aus einer Positivliste, gerundet erst hier, deterministisch (keine Zeitstempel, feste Sortierung):
eine Datei ändert sich nur, wenn sich ihr Inhalt ändert – dann committen die Actions sie mit.
Format: eine Zeile je Datensatz, damit Diffs lesbar bleiben.
"""

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import espn_fetch as ef
import fantasypros
import matchup as matchup_module
import players as players_module
from records import ranked
from lineup import POSITION_NAMES, SLOT_NAMES
from zahlen import ZERO, dec, round_to, rounded

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
             "endplatz": 4, "pick1": 4, "pick_top3": 4,
             # Wetter (wetter.json): eine Stelle wie Open-Meteo, Regenwahrscheinlichkeit ganzzahlig
             "temp": 1, "wind": 1, "boeen": 1, "niederschlag": 1, "schnee": 1, "regen_wahrsch": 0,
             # Alter je Spieler und Altersprofil je Team (keeper.json): eine Stelle wie in der Anzeige
             "alter": 1, "altersprofil": 1,
             # Marktwert je Team (keeper.json): Werte ganzzahlig wie bei FantasyCalc, das gewichtete Alter mit einer Stelle
             "marktwert": 0}
LAZY = ("players.json", "dst.json", "matchup.json", "history.json", "transactions.json", "keeper.json", "waiver.json",
        "wetter.json", "claude.json", "claude_marktwert.json")


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
# nur Seeding „liga“ (Stufe 4): Endplatz-Verteilung und Draft-Position des Folgejahrs, solange das Bracket passt
SIM_ENDPLATZ = ("endplatz", "pick", "pick1", "pick_top3")
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
        liga = sim.get("liga", {}).get(tid) or {}
        if row["sim"] and "endplatz" in liga:
            row["sim"]["liga"].update({k: liga[k] for k in SIM_ENDPLATZ})
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


def market_values(result: dict) -> dict[int, dict]:
    """Alle Spieler mit Marktwert (keeper.value_rows: Werte, team, art, alter je ESPN-ID); leer ohne Auszug oder Draft."""
    return (result.get("keeper") or {}).get("werte") or {}


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


def daily_selection(result: dict) -> set[int]:
    """Spieler von waiver.json: die Auswahl von players.json, dazu alle, die laut Tagesstand in einem Kader stehen, und
    alle Spieler mit Marktwert (Horizont „Zukunft“: Der Auswahl fehlten am 01.10.2026 47 der 190 freien Spieler mit
    Wert, meist verletzt oder ohne Einsatz – sie kommen wie Kaderspieler ohne players.json-Zeile mit Name, Position und
    NFL-Team aus dem Wochenpool dazu). Leer ohne Spielerdaten oder Tagesstand."""
    selection, pool = player_selection(result), result.get("pool_latest")
    if not selection or not pool:
        return set()
    werte = market_values(result)
    return selection | {p["id"] for p in pool["players"] if p.get("onTeamId") or p["id"] in werte}


def add_fantasypros(rows: list[dict], result: dict) -> None:
    """FantasyPros-Adresse je Spieler (fp, ohne .php) aus dem Sitemap-Auszug; None, wenn sie nicht eindeutig ist – die App
    verlinkt dann die Suche. Bekämen zwei Spieler dieselbe Adresse, bekommen beide die Suche. Ohne Auszug fehlt das Feld,
    und die App bleibt bei ihrer Namensregel."""
    if not result.get("fantasypros"):
        return
    known = fantasypros.index(result["fantasypros"])
    slugs = {id(row): fantasypros.slug_for(row.get("name"), row.get("pos"), known, row.get("id")) for row in rows}
    taken = Counter(slugs.values())
    for row in rows:
        slug = slugs[id(row)]
        row["fp"] = slug if slug and taken[slug] == 1 else None


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
    add_fantasypros(rows, result)
    return {"weeks": data["weeks"], "ersatz": {POSITION_NAMES.get(k, str(k)): v for k, v in data["ersatz"].items()},
            "ros_nach_woche": data["ros_after_week"], "mu_woche": (m or {}).get("wochen", {}).get("n1"),
            "cv": {POSITION_NAMES.get(k, str(k)): v for k, v in data["cv"].items()}, "players": rows}


DST_FIELDS = ("id", "abbrev", "bye", "z25", "z26", "n", "r25", "r26", "f", "f_vorwoche", "delta", "rang",
              "rang_vorwoche", "z_last3", "naechste3", "rest", "sos_po", "besitzer", "status")


def build_dst(result: dict) -> dict | None:
    data = result.get("dst")
    if not data:
        return None
    abbrev = {t["id"]: t["abbrev"] for t in data["teams"]}
    teams = [{k: t[k] for k in DST_FIELDS} | {"naechste": [n | {"opp": abbrev.get(n["opp"])} if "opp" in n else n
                                                           for n in t["naechste"]]} for t in data["teams"]]
    return {"through_week": data["through_week"], "ligaschnitt": data["ligaschnitt"], "formel": data["formel"],
            "teams": teams}


# Positions-Matchup: Kopf und je Defense und Position nur diese Felder (n25, zugelassen und f_verlauf bleiben im Rechenwerk)
MATCHUP_HEAD = ("through_week", "saison", "vorjahr", "vorjahr_quelle", "positionen", "ligaschnitt", "formel",
                "wochen")
MATCHUP_FIELDS = ("z25", "z26", "n", "r25", "r26", "f", "f_vorwoche", "delta", "rang", "rang_vorwoche")


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
    """Spieler, die der Spieler-Tab zeigen kann: die Auswahl von players.json plus die Spieler, die nur waiver.json
    führt (Kader laut Tagesstand, Spieler mit Marktwert; daily_selection); leer ohne Spielerdaten."""
    return daily_selection(result) or player_selection(result)


def build_transactions(result: dict) -> dict | None:
    """Moves; je Spieler in_app (bool), ob die App eine Spielerseite dazu hat – sonst zeigt sie den Namen ohne Link
    (gedroppte Spieler ohne Einsatz führt players.json nicht). Der Draft steht in keeper.json (picks)."""
    data = result.get("transactions")
    if not data:
        return None
    known = app_player_ids(result)
    items = [x | {"items": [i | {"in_app": i["player_id"] in known} for i in x["items"]]} for x in data["items"]]
    return {"spieler": data["spieler"], "items": items, "aufstellungswechsel": data["aufstellungswechsel"]}


KEEPER_HEAD = ("through_week", "stand", "draft_datum", "keeper_zahl", "kader_plaetze", "alter_stichtag", "alter_gewicht",
               "marktwert_stand", "keeper_linie")
KEEPER_TEAM = ("keeper", "keeper_da", "picks", "picks_da", "kader", "pf", "kern", "altersprofil", "marktwert")
# Marktwert je Spieler (FantasyCalc) in keeper.json und waiver.json; den Redraft-Wert führt nur claude_marktwert.json
WERT_KEYS = ("wert", "wert_rang", "wert_posrang", "wert_trend", "wert_ue")
KEEPER_ROSTER = ("id", "name", "pos", "nfl", "team", "art", "pick", "runde", "von", "seit", "g", "avg", "vj_g", "vj_pts",
                 "vj_avg", "vj_delta", "rookie", "alter", "nfl_jahr") + WERT_KEYS
KEEPER_PICK = ("pick", "runde", "runden_pick", "team_id", "player_id", "name", "pos", "keeper", "da", "team_jetzt", "g",
               "pts", "avg", "starts", "pf")


def build_keeper(result: dict) -> dict | None:
    """Keeper-Bilanz (keeper.compute_keeper) nach Positivliste: Kopf, liga, teams, kader (Herkunft je Kaderspieler
    heute) und picks (Draft inklusive Keeper mit Ertrag). Positionen als Kürzel, in_app wie in transactions.json;
    None vor dem Draft."""
    data = result.get("keeper")
    if not data:
        return None
    known = app_player_ids(result)
    pos = lambda p: POSITION_NAMES.get(p, str(p)) if p is not None else None  # noqa: E731
    liga = {k: data["liga"][k] for k in KEEPER_TEAM}
    if liga["altersprofil"]:   # Positionsschnitt der Liga mit Kürzeln als Schlüssel
        liga["altersprofil"] = liga["altersprofil"] | {
            "positionen": {pos(p): v for p, v in liga["altersprofil"]["positionen"].items()}}
    # Draft des Folgejahrs (Stufe 4): feste Reihenfolge erst, wenn alle Playoff-Spiele entschieden sind und ESPN nicht von
    # der Annahme abweicht; abweichung = Wochen mit Abweichung (dann auch keine Endplatz-Verteilung in teams.json)
    endplatz = (result.get("power_ranking") or {}).get("endplatz") or {}
    draft_next = {"saison": result["season"] + 1, "reihenfolge": endplatz.get("draft"), "endplatz": endplatz.get("fest"),
                  "abweichung": endplatz.get("abweichung") or [], "espn_bestaetigt": endplatz.get("espn_bestaetigt")}
    return {k: data[k] for k in KEEPER_HEAD} | {"draft_folgejahr": draft_next} | {
        "liga": liga,
        "teams": [{"team_id": t["team_id"]} | {k: t[k] for k in KEEPER_TEAM} for t in data["teams"]],
        "kader": [{k: r[k] for k in KEEPER_ROSTER} | {"pos": pos(r["pos"]), "in_app": r["id"] in known}
                  for r in data["kader"]],
        "picks": [{k: p[k] for k in KEEPER_PICK} | {"pos": pos(p["pos"]), "in_app": p["player_id"] in known}
                  for p in data["picks"]]}


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


def need_basis(result: dict) -> tuple[dict, dict, str] | None:
    """Grundlage von Bedarf und Profil (Beschluss 30.09.2026): bis W14 ROS/Spiel der Regular Season mit dem
    Ersatzniveau, danach bis W17 ROS Playoffs/Spiel (W15–17) mit dem Ersatzniveau der Playoffs.
    Rückgabe (Wert je Spieler, Ersatzniveau je Position, "regular" oder "playoffs"); None ohne ROS-Auszug und nach W17."""
    data = result["players"]
    after = data.get("ros_after_week")
    if after is None or after >= players_module.LAST_PLAYOFF_WEEK:
        return None
    if after < players_module.LAST_REGULAR_WEEK:
        return {pid: w["ros_pro_spiel"] for pid, w in data["players"].items()}, data["ersatz"], "regular"
    return ({pid: w["ros_po_pro_spiel"] for pid, w in data["players"].items()}, data.get("ersatz_po") or {},
            "playoffs")


def pool_rosters(pool: dict, weekly: dict) -> dict[int, list[tuple[int, int]]]:
    """Kader laut Tagesstand: team_id → [(Spieler-ID, Position)]; ohne Wochenpool-Eintrag ist die Position
    unbekannt, der Spieler ist dann nicht aufstellbar und fehlt."""
    rosters: dict[int, list] = {}
    for p in pool["players"]:
        w = weekly.get(p["id"])
        if p.get("onTeamId") and w:
            rosters.setdefault(p["onTeamId"], []).append((p["id"], w["pos"]))
    return rosters


def team_needs(pool: dict, result: dict) -> dict | None:
    """Bedarf je Team (players.team_needs) aus dem Kader laut Tagesstand und need_basis (ROS/Spiel bis W14, danach
    Playoffs); None ohne Grundlage. Positionen als Kürzel, Schlüssel team_id."""
    basis = need_basis(result)
    if basis is None:
        return None
    per_game, levels, _ = basis
    rosters = pool_rosters(pool, result["players"]["players"])
    name = lambda pos: POSITION_NAMES.get(pos, str(pos)) if pos is not None else None  # noqa: E731
    return {tid: {"luecken": [g | {"pos": name(g["pos"])} for g in n["luecken"]],
                  "ueber_ersatz": {name(pos): v for pos, v in n["ueber_ersatz"].items()}}
            for tid, n in players_module.team_needs(rosters, per_game, levels).items()}


WEEK_VIEW_HEAD = ("horizont", "ersatz_woche", "ersatz_3", "anstoss", "bedarf_woche")


def week_view(pool: dict, result: dict) -> dict | None:
    """Wochensicht des Waiver-Tabs (Beschluss 30.09.2026) für die Woche N+1 = pool["woche"] laut Tagesstand.

    Je Spieler (Schlüssel id): proj_ue = Wochenwert (players.week_value: Bye und OUT/IR/gesperrt 0) − Wochen-
    Ersatzniveau, proj3 = Σ N+1 … N+3 (N+1 Tagesstand, danach ROS-Auszug), proj3_ue = proj3 − Ersatzniveau der Summe.
    Kopf: horizont (Wochen), ersatz_woche, ersatz_3, anstoss (NFL-Kürzel → Epoch-ms des Spiels in N+1, ohne offene
    Anstöße), bedarf_woche (players.team_week_needs). None ohne NFL-Spielplan oder außerhalb W1–17.
    """
    week, nfl = pool.get("woche"), result.get("nfl")
    if not nfl or not week or not 1 <= week <= players_module.LAST_PLAYOFF_WEEK:
        return None
    weekly, ros = result["players"]["players"], result.get("ros_projektion")
    weeks = players_module.horizon_weeks(week)
    rows = {}
    for p in pool["players"]:
        w = weekly.get(p["id"])
        if not w:
            continue  # Position und NFL-Team unbekannt
        team = w["pro_team"]
        value, grund = players_module.week_value(p.get("proj_naechste_woche"), p.get("injuryStatus"),
                                                 players_module.has_game(nfl, team, week))
        total = players_module.horizon_sum(value, ros.get(str(p["id"])) if ros else None, team, nfl, weeks)
        rows[p["id"]] = {"p": p, "pos": w["pos"], "team": team, "value": value, "grund": grund, "sum": total}
    free = {pid: r for pid, r in rows.items() if r["p"].get("status") in players_module.REPLACEMENT_STATUS
            and r["grund"] not in players_module.WEEK_OUT}
    level = players_module.week_replacement_levels([(r["pos"], r["value"]) for r in free.values() if r["grund"] is None])
    level3 = players_module.week_replacement_levels([(r["pos"], r["sum"]) for r in free.values() if r["sum"] is not None])
    per_player = {pid: {"proj_ue": r["value"] - level[r["pos"]] if level.get(r["pos"]) is not None else None,
                        "proj3": r["sum"],
                        "proj3_ue": r["sum"] - level3[r["pos"]]
                        if r["sum"] is not None and level3.get(r["pos"]) is not None else None}
                  for pid, r in rows.items()}
    rosters: dict[int, list] = {}
    for pid, r in rows.items():
        if r["p"].get("onTeamId"):
            rosters.setdefault(r["p"]["onTeamId"], []).append((pid, r["pos"]))
    basis = need_basis(result)
    per_game = basis[0] if basis else None
    byes = {pid: [w for w in weeks[1:] if players_module.is_bye(nfl, r["team"], w)] for pid, r in rows.items()}
    candidates = sorted(((r["pos"], r["value"], pid) for pid, r in free.items() if r["grund"] is None),
                        key=lambda c: (-c[1], c[2]))
    needs = players_module.team_week_needs(rosters, {pid: (r["value"], r["grund"]) for pid, r in rows.items()},
                                           {pid: r["p"].get("injuryStatus") for pid, r in rows.items()}, level,
                                           candidates, per_game, byes)
    name = lambda pos: POSITION_NAMES.get(pos, str(pos)) if pos is not None else None  # noqa: E731
    abbrev = {tid: t.abbrev for tid, t in nfl.items()}
    anstoss = {}
    for g in result.get("nfl_spiele") or []:
        if g["woche"] == week and not g["tbd"]:
            ms = int(g["kickoff"].timestamp() * 1000)
            anstoss.update({abbrev[t]: ms for t in (g["heim"], g["gast"]) if t in abbrev})
    return {"horizont": weeks,
            "ersatz_woche": {name(pos): v for pos, v in level.items()},
            "ersatz_3": {name(pos): v for pos, v in level3.items()},
            "anstoss": dict(sorted(anstoss.items())),
            "bedarf_woche": {tid: {"luecken": [g | {"pos": name(g["pos"])} for g in n["luecken"]],
                                   "ausfaelle": [a | {"pos": name(a["pos"])} for a in n["ausfaelle"]],
                                   "byes": [b | {"pos": name(b["pos"])} for b in n["byes"]]}
                             for tid, n in needs.items()},
            "spieler": per_player,
            "_rows": rows, "_weeks": weeks}   # für team_view, nicht exportiert


def team_view(pool: dict, result: dict, view: dict | None, keep: set[int]) -> tuple[dict | None, dict[int, dict]]:
    """Profil je Team und Zugewinn je freiem Spieler (Beschluss 30.09.2026), Kader laut Tagesstand.

    Profil (players.team_profiles) nach need_basis, dazu je Gruppe ist_rang (Ist-Punkte der Starter-Slots W1–N aus
    records.positions, QB-Gruppe = QB + OP), absicherung je Position (players.cover_loss mit dem besten
    verfügbaren Spieler ohne OUT/IR) samt Rang (1 = geringster Verlust), byes = Kosten der Byes N+1 … W14 bzw.
    W17 in den Playoffs (players.bye_costs), kader = {spieler, ir, voll, limit} (players.must_drop mit dem IR-Slot laut
    Tagesstand ir_slot; ohne ihn steht niemand auf IR).
    Zugewinn (players.team_gains) je Spieler der Auswahl keep mit Status WAIVERS/FREEAGENT und Horizont:
    woche = Wochenwert N+1, drei = Wochenwerte N+1 … N+3 (je Woche eigene Aufstellung), ros = need_basis.
    Rückgabe (profil oder None ohne Grundlage, {Spieler-ID: {Horizont: {team_id: {"b", "n"}}}}).
    """
    weekly = result["players"]["players"]
    rosters = pool_rosters(pool, weekly)
    on_ir = {pid for ids in (pool.get("ir_slot") or {}).values() for pid in ids}   # tatsächlicher IR-Slot (mRoster)
    rules = result.get("kader_regeln")
    drop_rule = {tid: players_module.must_drop(r, on_ir, rules) for tid, r in rosters.items()} if rules else {}
    free = [p for p in pool["players"] if p["id"] in keep and p["id"] in weekly
            and p.get("status") in players_module.REPLACEMENT_STATUS]
    gains: dict[int, dict] = {}

    def add(horizon: str, weeks_values: list[dict], cand: list[tuple]) -> None:
        for pid, by_team in players_module.team_gains(rosters, weeks_values, cand, drop_rule).items():
            gains.setdefault(pid, {})[horizon] = by_team

    if view:
        rows, weeks, nfl, ros = view["_rows"], view["_weeks"], result["nfl"], result.get("ros_projektion") or {}
        values = {pid: players_module.horizon_values(r["value"], ros.get(str(pid)), r["team"], nfl, weeks)
                  for pid, r in rows.items()}
        add("woche", [{pid: v[0] for pid, v in values.items()}],
            [(p["id"], weekly[p["id"]]["pos"], values[p["id"]][:1]) for p in free if p["id"] in values])
        add("drei", [{pid: v[i] for pid, v in values.items()} for i in range(len(weeks))],
            [(p["id"], weekly[p["id"]]["pos"], values[p["id"]]) for p in free if p["id"] in values])
    basis = need_basis(result)
    if basis is None:
        return None, gains
    per_game, _, kind = basis
    add("ros", [per_game], [(p["id"], weekly[p["id"]]["pos"], [per_game.get(p["id"]) or ZERO]) for p in free])
    profiles = players_module.team_profiles(rosters, per_game)
    # Absicherung: bester verfügbarer Spieler je Position (ohne OUT/IR, wie das Ersatzniveau)
    free_best: dict[int, Decimal] = {}
    for p in free:
        v = per_game.get(p["id"])
        if v is not None and p.get("injuryStatus") not in players_module.INJURED:
            pos = weekly[p["id"]]["pos"]
            free_best[pos] = max(free_best.get(pos, v), v)
    cover = {tid: players_module.cover_loss(r, per_game, free_best) for tid, r in rosters.items()}
    cover_rank = {pos: ranked({tid: c[pos]["wert"] for tid, c in cover.items() if c[pos] is not None})
                  for pos in players_module.POSITION_CV}
    after, nfl = result["players"]["ros_after_week"], result.get("nfl") or {}
    last = players_module.LAST_REGULAR_WEEK if kind == "regular" else players_module.LAST_PLAYOFF_WEEK
    bye_weeks = list(range(after + 1, last + 1))
    byes = {pid: {w for w in bye_weeks if players_module.is_bye(nfl, weekly[pid]["pro_team"], w)}
            for r in rosters.values() for pid, _ in r}
    ist = (result.get("records") or {}).get("positions") or {}
    ist_group = {g: {tid: sum((ist[tid]["nach_slot"][s]["pts"] for s in slots), ZERO) for tid in ist}
                 for g, slots, _ in players_module.PROFILE_GROUPS}
    ist_rank = {g: ranked(vals) for g, vals in ist_group.items()}
    name = lambda pos: POSITION_NAMES.get(pos, str(pos))  # noqa: E731
    out = {}
    for tid, prof in profiles.items():
        full, at_limit = drop_rule.get(tid, (None, set()))
        out[tid] = prof | {
            "gruppen": {g: grp | {"ist_rang": ist_rank[g].get(tid)} for g, grp in prof["gruppen"].items()},
            "absicherung": {name(pos): (v and v | {"rang": cover_rank[pos].get(tid)}) for pos, v in cover[tid].items()},
            "byes": players_module.bye_costs(rosters[tid], per_game, byes, bye_weeks),
            "kader": {"spieler": len(rosters[tid]), "ir": sum(1 for pid, _ in rosters[tid] if pid in on_ir),
                      "voll": full, "limit": sorted(name(p) for p in at_limit)}}
    return out, gains


def build_waiver(result: dict) -> dict | None:
    """Tagesstand je Spieler aus dem Pool-Auszug des Tageslaufs (Session 6): Status, Fantasy-Team, Verletzung,
    Besitz ESPN-weit mit Trend, Waiver-Frist, Projektion der nächsten Woche, letzte ESPN-News. Dazu (Session 7) die
    Waiver-Reihenfolge der Teams und der Bedarf je Team.

    Spieler: daily_selection (die Auswahl von players.json plus alle, die laut Tagesstand in einem Kader stehen, und
    alle mit Marktwert); Spieler mit Marktwert tragen WERT_KEYS (Stufe 3) und – mit Stammdaten – alter, der Kopf
    wert_stand und keeper_linie.
    Grundlage des Waiver-Tabs; None ohne Pool-Auszug oder Spielerdaten.
    """
    pool = result.get("pool_latest")
    selection = player_selection(result)
    if not pool or not selection:
        return None
    keep = daily_selection(result)
    weekly = result["players"]["players"]  # ganzer Wochenpool mit Stammdaten (Name, Position, NFL-Team)
    number = lambda v: dec(v) if v is not None else None  # noqa: E731 – ESPN-Floats erst beim Schreiben runden
    rows, extra = [], []
    for p in pool["players"]:
        if p["id"] not in keep:
            continue
        row = {"id": p["id"], "team": p.get("onTeamId") or 0, "status": p.get("status"), "inj": p.get("injuryStatus"),
               "own": number(p.get("percentOwned")), "own_d": number(p.get("percentChange")),
               "started": number(p.get("percentStarted")), "waiver_bis": p.get("waiverProcessDate"),
               "proj": number(p.get("proj_naechste_woche")), "news": p.get("lastNewsDate")}
        if p["id"] not in selection:
            # Spieler, den players.json nicht führt (Kaderspieler unter der Woche geholt, ohne Spiel, nicht Top 20 seiner
            # Position; oder freier Spieler mit Marktwert): Stammdaten aus dem Wochenpool, damit die App ihn benennen
            # kann; None, wenn auch dort unbekannt
            w = weekly.get(p["id"])
            row.update(name=w["name"] if w else None, pos=POSITION_NAMES.get(w["pos"], str(w["pos"])) if w else None,
                       nfl=w["nfl"] if w else None)
            extra.append(row)
        rows.append(row)
    add_fantasypros(extra, result)
    werte = market_values(result)   # Marktwert (FantasyCalc) nur bei Spielern mit Wert, sonst fehlen die Felder
    for row in rows:
        w = werte.get(row["id"])
        if w:
            row.update({k: w[k] for k in WERT_KEYS} | ({"alter": w["alter"]} if w["alter"] is not None else {}))
    reihenfolge, quelle, stand = waiver_order(pool, result)
    view = week_view(pool, result)
    if view:
        for row in rows:
            row.update(view["spieler"].get(row["id"], dict.fromkeys(("proj_ue", "proj3", "proj3_ue"))))
    profil, gains = team_view(pool, result, view, keep)
    for row in rows:
        if row["id"] in gains:
            row["zug"] = gains[row["id"]]
    head = {k: v for k, v in (view or dict.fromkeys(WEEK_VIEW_HEAD)).items() if k in WEEK_VIEW_HEAD}
    basis = need_basis(result)
    keeper = result.get("keeper") or {}
    return {"stand": pool["stand"], "woche": pool["woche"], "reihenfolge": reihenfolge, "reihenfolge_quelle": quelle,
            "reihenfolge_stand": stand, "bedarf": team_needs(pool, result),
            "bedarf_basis": basis[2] if basis else None,
            "bedarf_ersatz": {POSITION_NAMES.get(k, str(k)): v for k, v in basis[1].items()} if basis else None,
            "profil": profil,
            # Horizont „Zukunft“: Stand des Marktwert-Auszugs und Keeper-Linie (beide None ohne Auszug)
            "wert_stand": keeper.get("marktwert_stand"), "keeper_linie": keeper.get("keeper_linie")} | head | {"spieler": rows}


# id = ESPN-Spieler-ID (Schlüssel von waiver.json, das die meisten Spieler nur per id führt); proj und proj3 sind die
# Wochenwerte des Tagesstands (waiver.json), ohne Eintrag dort None
CLAUDE_PLAYER_COLS = ("id", "name", "pos", "nfl", "inj", "avg", "form", "trend", "ros_g", "ros_rang", "gegner_n1",
                      "mu_n1", "proj", "proj3")
# Free Agents zusätzlich mit Status
CLAUDE_FREE_COLS = CLAUDE_PLAYER_COLS + ("status",)
# je Spieler aus dem Tagesstand (waiver.json) überlagert; die Wochenwerte gibt es nur dort
CLAUDE_DAILY = ("team", "status", "inj", "proj", "proj3")
CLAUDE_DAILY_ONLY = ("proj", "proj3")


def fixed(value, places: int):
    """Zahl mit fester Stellenzahl für Zeilen ohne Schlüssel (claude.json); None bleibt None."""
    return None if value is None else float(round_to(value, places))


def claude_player(p: dict, cols: tuple = CLAUDE_PLAYER_COLS) -> list:
    """Spielerzeile nach cols; gegner_n1 und mu_n1 aus mu.n1 (Kürzel und F mit 3 Stellen, None bei Bye
    oder ohne Wert)."""
    n1 = (p.get("mu") or {}).get("n1") or {}
    mu = {"gegner_n1": n1.get("opp"), "mu_n1": fixed(n1.get("f"), 3)}
    return [mu[c] if c in mu else p.get(c) for c in cols]


def claude_rows(players: dict, waiver: dict | None) -> list[dict]:
    """Spieler für claude.json, nach ID: players.json (Wochenstand), je Spieler team, status, inj, proj und proj3 aus
    dem Tagesstand überlagert (team, status, inj wie merge() in app/js/v_spieler.js). Kaderspieler, die nur der
    Tagesstand kennt, kommen mit name, pos, nfl aus waiver.json dazu (unbekannter Name: „Spieler <id>“ wie in der App),
    ihre Werte des Wochenstands (avg bis mu_n1) fehlen. Spieler ohne Eintrag im Tagesstand und alle ohne waiver
    bleiben beim Wochenstand, proj und proj3 (nur Tagesstand) sind dann None."""
    daily = {s["id"]: s for s in (waiver or {}).get("spieler", [])}
    rows = [p | dict.fromkeys(CLAUDE_DAILY_ONLY) | {c: daily[p["id"]].get(c) for c in CLAUDE_DAILY if p["id"] in daily}
            for p in players["players"]]
    known = {p["id"] for p in players["players"]}
    rows += [{"id": d["id"], "name": d.get("name") or f"Spieler {d['id']}", "pos": d.get("pos"), "nfl": d.get("nfl")}
             | {c: d.get(c) for c in CLAUDE_DAILY} for d in daily.values() if d["id"] not in known and d["team"]]
    return sorted(rows, key=lambda p: p["id"])


CLAUDE_FREE_PER_POS = 10


def claude_free_agents(rows: list[dict], waiver: dict | None) -> dict[str, list[dict]]:
    """Free Agents für claude.json je Position (frei = WAIVERS oder FREEAGENT laut rows): zuerst die 10 besten nach
    ROS/Spiel, danach die übrigen der 10 besten nach Wochenprojektion (proj_ue aus waiver.json wie im Waiver-Tab,
    Horizont Woche), ohne Spieler, deren Spiel in pool_woche zum Stand des Tagesstands schon angepfiffen war (anstoss,
    wie played() in app/js/v_waiver.js mit dem Stand statt der Uhrzeit). Ohne Tagesstand nur nach ROS/Spiel."""
    ue = {s["id"]: s.get("proj_ue") for s in (waiver or {}).get("spieler", [])}
    kick = (waiver or {}).get("anstoss") or {}
    stand = (int(datetime.strptime(waiver["stand"], "%Y-%m-%dT%H%MZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
             if waiver else None)
    free = [p for p in rows if p.get("status") in players_module.REPLACEMENT_STATUS]
    out = {}
    for pos in POSITION_NAMES.values():
        mine = [p for p in free if p["pos"] == pos]
        by_ros = sorted((p for p in mine if p.get("ros_g") is not None),
                        key=lambda p: (-p["ros_g"], p["id"]))[:CLAUDE_FREE_PER_POS]
        by_week = sorted((p for p in mine if ue.get(p["id"]) is not None
                          and not (p.get("nfl") in kick and kick[p["nfl"]] <= stand)),
                         key=lambda p: (-ue[p["id"]], p["id"]))[:CLAUDE_FREE_PER_POS]
        seen = {p["id"] for p in by_ros}
        out[pos] = by_ros + [p for p in by_week if p["id"] not in seen]
    return out


def build_claude(result: dict, teams: dict, schedule: dict, players: dict | None, dst: dict | None,
                 transactions: dict | None, waiver: dict | None = None) -> dict:
    """Kompakte Datei für Claude-Sessions unterwegs (< 50 KB): Tabellen als Spaltenkopf plus Zeilen, Teams als Kürzel.

    waiver = build_waiver (Tagesstand, noch ungerundet): Kader, freie Spieler und D/ST-Besitzer folgen ihm, sobald es
    ihn gibt (Freigabe Stephan 30.09.2026); ohne ihn (vor dem ersten Tageslauf) gilt der Wochenstand, pool_stand None.
    """
    k = KUERZEL.get
    tabelle = []
    for t in teams["teams"]:
        pr, sim = t.get("pr") or {}, (t.get("sim") or {}).get("liga") or {}
        tabelle.append([t["rang"], k(t["team_id"]), t["name"], f"{t['w']}-{t['l']}-{t['t']}", t["pf"],
                        t["allplay_pct"], t["matchup_glueck"], t["efficiency"], t["form"],
                        50 + 10 * t["score_ref"]["Standard"]["z"], t["kader_projektion"] or t["kader_potenzial"],
                        pr.get("rang"), pr.get("mu"), fixed(pr.get("e"), 3), pr.get("trend"),
                        fixed(sim.get("playoff"), 4)])
    out = {"legende": "BWG Fantasy Liga (ESPN 1166555857), inoffizielle Auswertung. Punkte = ESPN appliedTotal; "
                      "Projektionen sind ESPN-Input. Zeilen gehören zu den *_spalten; id = ESPN-Spieler-ID wie in "
                      "waiver.json; mu_n1 = Positions-Matchup F des Gegners in matchup_woche, > 1 günstig. "
                      "Definitionen: docs/app_daten.md "
                      "und CLAUDE.md (Rechenregeln) im Repo frest2101/bwg-fantasy.",
           "legende_stand": "Tagesstand (pool_stand): Zuordnung zu kader/free_agents, inj, status, proj (ESPN-Projektion "
                            "pool_woche, roh: bei Bye/OUT/IR nicht 0), proj3 (Σ pool_woche…+2; erste Woche Bye/OUT/IR "
                            "0, dann ROS-Auszug), D/ST-besitzer, transaktionen. Wochenstand (nach_woche): alles Übrige; "
                            "Spieler nur aus dem Tagesstand: avg…mu_n1 null. pool_stand null: alles Wochenstand, "
                            "proj/proj3 null.",
           "stand": {"saison": result["season"], "nach_woche": result["through_week"],
                     "kader_quelle": teams["meta"]["kader_quelle"], "ros_nach_woche": result.get("ros_after_week"),
                     "matchup_woche": (result.get("matchup") or {}).get("wochen", {}).get("n1"),
                     # Tagesstand: Abrufzeit (UTC) wie manifest datenstand.pool_stand, Woche der Projektion proj
                     "pool_stand": waiver["stand"] if waiver else None, "pool_woche": waiver["woche"] if waiver else None},
           "teams": {k(t["team_id"]): t["name"] for t in teams["teams"]},
           "tabelle_spalten": ["rang", "team", "name", "w_l_t", "pf", "allplay_pct", "matchup_glueck", "effizienz_pct", "form",
                               "score_50_10z", "kader", "pr_rang", "mu", "e", "trend", "playoff_anteil"],
           "tabelle": tabelle,
           "spiele_spalten": ["woche", "heim", "gast", "pf_heim", "pf_gast", "p_heim"],
           "spiele": [[g["week"], k(g["home"]), k(g["away"]), g["home_pf"], g["away_pf"], fixed(g.get("p_home"), 4)]
                      for g in schedule["games"]]}
    owner = {}  # D/ST laut Tagesstand: NFL-Kürzel → (team_id, Status)
    if players:
        rows = claude_rows(players, waiver)
        out["spieler_spalten"] = list(CLAUDE_PLAYER_COLS)
        out["free_agents_spalten"] = list(CLAUDE_FREE_COLS)
        out["kader"] = {k(tid): [claude_player(p) for p in rows if p["team"] == tid] for tid in sorted(KUERZEL)}
        out["free_agents"] = {pos: [claude_player(p, CLAUDE_FREE_COLS) for p in free]
                              for pos, free in claude_free_agents(rows, waiver).items()}
        daily = {s["id"] for s in (waiver or {}).get("spieler", [])}
        owner = {p["nfl"]: (p["team"], p["status"]) for p in rows if p["pos"] == "D/ST" and p["id"] in daily}
    if dst:
        out["dst_spalten"] = ["nfl", "f", "naechste3", "rest", "sos_w15_17", "besitzer"]
        out["dst"] = []
        for d in dst["teams"]:
            team, status = owner.get(d["abbrev"], (d["besitzer"], d["status"]))
            out["dst"].append([d["abbrev"], fixed(d["f"], 3), fixed(d["naechste3"], 3), fixed(d["rest"], 3),
                               fixed(d["sos_po"], 3), k(team) if team else status])
    if transactions:
        out["transaktionen_spalten"] = ["datum_ms", "team", "typ", "zugang", "abgang"]
        out["transaktionen"] = [[t["datum"], k(t["team_id"]), t["type"],
                                 [i["name"] for i in t["items"] if i["type"] == "ADD"],
                                 [i["name"] for i in t["items"] if i["type"] == "DROP"]]
                                for t in transactions.get("letzte", [])]
    return out


MARKTWERT_COLS = ("name", "pos", "nfl", "team", "wert", "rang", "pos_rang", "trend30", "redraft", "ue_linie", "alter",
                  "herkunft")


def build_claude_marktwert(result: dict) -> dict | None:
    """Datei für das Claude-Projekt (claude.ai, Beschluss Stephan 01.10.2026): alle Spieler mit Marktwert als Gesamt-
    rangliste, spaltenweise wie claude.json, aber eigene Datei (claude.json bleibt unter 50 KB). Keine Liste „beste
    zwölf je Team“ – das Projekt rechnet selbst. Namen, Position und NFL-Team aus dem Wochenpool (ESPN-Namen, nicht
    FantasyCalcs), team = Kürzel laut Tagesstand oder Status (WAIVERS, FREEAGENT), herkunft = Art bei Kaderspielern.
    None ohne Marktwert-Auszug."""
    werte, keeper = market_values(result), result.get("keeper") or {}
    if not werte:
        return None
    weekly = result["players"]["players"]
    daily = {p["id"]: p.get("status") for p in (result.get("pool_latest") or {}).get("players", [])}
    roster = {k["id"]: k for k in keeper.get("kader", [])}
    rows = []
    for pid, w in sorted(werte.items(), key=lambda kv: kv[1]["wert_rang"]):
        # Stammdaten aus dem Wochenpool; ein unter der Woche geholter Kaderspieler, den er nicht kennt, aus der Kaderzeile
        p = weekly.get(pid) or roster.get(pid) or {}
        pos = p.get("pos")
        rows.append([p.get("name") or f"Spieler {pid}", POSITION_NAMES.get(pos, str(pos)) if pos is not None else None,
                     p.get("nfl"), KUERZEL.get(w["team"]) if w["team"] else daily.get(pid) or p.get("status"),
                     w["wert"], w["wert_rang"], w["wert_posrang"], w["wert_trend"], w["wert_redraft"], w["wert_ue"],
                     fixed(w["alter"], 1), w["art"]])
    return {"legende": "BWG Fantasy Liga (ESPN 1166555857): Marktwerte aller Spieler mit Wert als Gesamtrangliste. "
                       "Werte: FantasyCalc (https://fantasycalc.com), Dynasty, Superflex, 10 Teams, PPR – Tauschpreise "
                       "aus Ligen mit rund 300 gehaltenen Spielern; die BWG hält 120 (12 je Team). Oberhalb der "
                       "keeper_linie passen sie, darunter überzeichnen sie. Keine Punktprognose; K und D/ST ohne Wert.",
            "legende_spalten": "team = Kürzel (teams) oder Status; rang/pos_rang = FantasyCalc gesamt/Position; "
                               "trend30 = Wertänderung 30 Tage; redraft = Wert nur für diese Saison (null = keiner); "
                               "ue_linie = wert − keeper_linie; alter am stand.alter_stichtag; herkunft = keeper, "
                               "draft, waiver, free_agent, trade (null = frei). ROS und Form: claude.json.",
            "quelle": "Werte: FantasyCalc (https://fantasycalc.com); Namen, Teams und Herkunft: ESPN; Alter: nflverse "
                      "(CC BY 4.0). Inoffizielle Auswertung.",
            "stand": {"saison": result["season"], "nach_woche": result["through_week"],
                      "marktwert": keeper.get("marktwert_stand"),
                      "pool_stand": (result.get("pool_latest") or {}).get("stand"),
                      "alter_stichtag": keeper.get("alter_stichtag")},
            "keeper_linie": keeper.get("keeper_linie"), "keeper_zahl": keeper.get("keeper_zahl"),
            "teams": {KUERZEL[t["team_id"]]: t["name"] for t in result["teams"]},
            "spalten": list(MARKTWERT_COLS), "spieler": rows}


def build(result: dict) -> dict[str, dict]:
    """Alle App-Dateien (ohne manifest) als Python-Objekte, noch ungerundet."""
    teams, schedule = build_teams(result), build_schedule(result)
    files = {"teams.json": teams, "schedule.json": schedule}
    players, dst, waiver = build_players(result), build_dst(result), build_waiver(result)
    optional = {"players.json": players, "dst.json": dst, "matchup.json": build_matchup(result),
                "history.json": result.get("history"),
                "transactions.json": build_transactions(result), "keeper.json": build_keeper(result),
                "waiver.json": waiver, "wetter.json": result.get("wetter"),
                "claude_marktwert.json": build_claude_marktwert(result)}
    files.update({name: obj for name, obj in optional.items() if obj})
    files["claude.json"] = build_claude(result, teams, schedule, players, dst, result.get("transactions"), waiver)
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
                               # Stufe 4: letzte finale Playoff-Woche (W15–17), null bis dahin
                               "playoff_woche": result.get("playoff_woche"),
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

