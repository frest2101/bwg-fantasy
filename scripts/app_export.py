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
from lineup import POSITION_NAMES, SLOT_NAMES
from zahlen import round_to, rounded

SCHEMA = 1
APP_DATA = ef.REPO_DIR / "app" / "data"
# Eigene Kürzel je team_id (Auftrag Session 4, Frage 7) – die ESPN-Kürzel sind uneinheitlich
KUERZEL = {1: "ACB", 2: "HJS", 3: "4DS", 4: "CRN", 5: "TTY", 6: "SAM", 7: "RTZ", 8: "GLS", 9: "DYN", 10: "SGK"}
METRIC_LABELS = {"pf": "PF/Spiel", "allplay": "All-Play-Quote", "win": "Win %", "coaching": "Coaching-Effizienz",
                 "kader": {"potenzial": "Kader-Potenzial", "projektion": "Kader-Projektion ROS"},
                 "floor": "Floor", "form": "Form"}
# Stellen je Schlüssel (gilt für den Teilbaum), sonst zwei (Frage 11 a); Anteile in % mit einer Stelle wie in der Anzeige
PRECISION = {"z": 3, "e": 3, "f": 3, "f_vorwoche": 3, "delta": 3, "r25": 3, "r26": 3, "naechste3": 3, "rest": 3,
             "sos_po": 3, "playoff": 4, "division": 4, "bye": 4, "seeds": 4, "p_home": 4, "anteil": 1}
LAZY = ("players.json", "dst.json", "history.json", "transactions.json", "claude.json")


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
               "allplay_w", "allplay_l", "allplay_t", "allplay_pct", "median_w", "luck", "luck_band", "optimal", "verschenkt",
               "efficiency", "kader_potenzial", "kader_projektion", "bench", "floor", "form", "form_delta",
               "form_band", "streak", "projection", "projektions_delta", "waiver_prio", "moves", "rang",
               "rang_division", "rang_score", "norm", "score")
PR_FIELDS = ("mu", "se", "p", "p_quelle", "e", "rang", "rang_vorwoche", "trend", "kernsatz")
SIM_FIELDS = ("playoff", "division", "bye", "restsiege", "seeds")
# je Woche (Arrays in teams.json › wochen); Luck-Beitrag, laufende Summe und Effizienz kommen aus compute_team_weeks
WEEK_FIELDS = ("pf", "pa", "optimal", "verschenkt", "efficiency", "wochenrang", "allplay_w", "allplay_l", "allplay_t",
               "allplay_pct", "luck", "luck_kum", "median_win", "projektions_delta")


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


def build_players(result: dict) -> dict | None:
    """Spieler mit mindestens einem Spiel oder im Kader, dazu die 20 besten Free Agents je Position nach ROS/Spiel."""
    data = result.get("players")
    if not data:
        return None
    pool = data["players"]
    keep = {pid for pid, p in pool.items() if p["team_id"] or p["games"]}
    for pos in POSITION_NAMES:
        free = sorted((p for p in pool.values() if not p["team_id"] and p["pos"] == pos
                       and p["ros_pro_spiel"] is not None), key=lambda p: (-p["ros_pro_spiel"], p["player_id"]))
        keep |= {p["player_id"] for p in free[:FREE_AGENTS_PER_POS]}
    rows = []
    for pid in sorted(keep):
        p = pool[pid]
        rows.append({"id": pid, "name": p["name"], "pos": POSITION_NAMES.get(p["pos"], str(p["pos"])),
                     "nfl": p["nfl"], "team": p["team_id"] or 0, "status": p["status"], "inj": p["injury"],
                     "own": p["owned"], "g": p["games"], "pts": p["pts"], "avg": p["avg"], "floor": p["floor"],
                     "ceil": p["ceiling"], "sd": p["sd"], "form": p["form"], "form_d": p["form_delta"],
                     "trend": p["trend"], "spark": p["sparkline"], "starts": p["starts"],
                     "bench_pts": p["bench_pts"], "proj_d": p["proj_delta"],
                     "wk": [[w["actual"], w["projection"], 1 if w["bye"] else 0, w["team_id"] or 0,
                             SLOT_NAMES.get(w["slot"]) if w["slot"] is not None else None] for w in p["weeks"]],
                     "ros": p["ros"], "ros_g": p["ros_pro_spiel"], "rest_g": p["restspiele"], "ros_po": p["ros_po"],
                     "ros_rang": p["ros_rang"], "ros_ue": p["ros_ueber_ersatz"]})
    return {"weeks": data["weeks"], "ersatz": {POSITION_NAMES.get(k, str(k)): v for k, v in data["ersatz"].items()},
            "ros_nach_woche": data["ros_after_week"],
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


def build_transactions(result: dict) -> dict | None:
    data = result.get("transactions")
    return {k: data[k] for k in ("spieler", "items", "aufstellungswechsel", "draft")} if data else None


CLAUDE_PLAYER_COLS = ("name", "pos", "nfl", "inj", "avg", "form", "trend", "ros_g", "ros_rang")


def fixed(value, places: int):
    """Zahl mit fester Stellenzahl für Zeilen ohne Schlüssel (claude.json); None bleibt None."""
    return None if value is None else float(round_to(value, places))


def build_claude(result: dict, teams: dict, schedule: dict, players: dict | None, dst: dict | None,
                 transactions: dict | None) -> dict:
    """Kompakte Datei für Claude-Sessions unterwegs (< 50 KB): Tabellen als Spaltenkopf plus Zeilen, Teams als Kürzel."""
    k = KUERZEL.get
    tabelle = []
    for t in teams["teams"]:
        pr, sim = t.get("pr") or {}, (t.get("sim") or {}).get("liga") or {}
        tabelle.append([t["rang"], k(t["team_id"]), t["name"], f"{t['w']}-{t['l']}-{t['t']}", t["pf"],
                        t["allplay_pct"], t["luck"], t["efficiency"], t["form"],
                        50 + 10 * t["score_ref"]["Stärke"]["z"], t["kader_projektion"] or t["kader_potenzial"],
                        pr.get("rang"), pr.get("mu"), fixed(pr.get("e"), 3), pr.get("trend"),
                        fixed(sim.get("playoff"), 4)])
    out = {"legende": "BWG Fantasy Liga (ESPN 1166555857), inoffizielle Auswertung. Punkte = ESPN appliedTotal; "
                      "Projektionen sind ESPN-Input. Zeilen gehören zu den *_spalten. Definitionen: docs/app_daten.md "
                      "und CLAUDE.md (Rechenregeln) im Repo frest2101/bwg-fantasy.",
           "stand": {"saison": result["season"], "nach_woche": result["through_week"],
                     "kader_quelle": teams["meta"]["kader_quelle"], "ros_nach_woche": result.get("ros_after_week")},
           "teams": {k(t["team_id"]): t["name"] for t in teams["teams"]},
           "tabelle_spalten": ["rang", "team", "name", "w_l_t", "pf", "allplay_pct", "luck", "effizienz_pct", "form",
                               "score_50_10z", "kader", "pr_rang", "mu", "e", "trend", "playoff_anteil"],
           "tabelle": tabelle,
           "spiele_spalten": ["woche", "heim", "gast", "pf_heim", "pf_gast", "p_heim"],
           "spiele": [[g["week"], k(g["home"]), k(g["away"]), g["home_pf"], g["away_pf"], fixed(g.get("p_home"), 4)]
                      for g in schedule["games"]]}
    if players:
        rows = players["players"]
        out["spieler_spalten"] = list(CLAUDE_PLAYER_COLS)
        out["kader"] = {k(tid): [[p.get(c) for c in CLAUDE_PLAYER_COLS] for p in rows if p["team"] == tid]
                        for tid in sorted(KUERZEL)}
        free = [p for p in rows if not p["team"] and p.get("ros_g") is not None]
        out["free_agents"] = {pos: [[p.get(c) for c in CLAUDE_PLAYER_COLS] + [p.get("status")]
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
    optional = {"players.json": players, "dst.json": dst, "history.json": result.get("history"),
                "transactions.json": build_transactions(result)}
    files.update({name: obj for name, obj in optional.items() if obj})
    files["claude.json"] = build_claude(result, teams, schedule, players, dst, result.get("transactions"))
    return files


# ---------------------------------------------------------------- Schreiben

def round_file(name: str, obj: dict):
    """Rundung je Datei: D/ST mit den Stellen aus dst.PRECISION, sonst PRECISION; Rangpunkte als ganze Zahlen."""
    import dst as dst_module
    data = rounded(obj, precision=dst_module.PRECISION if name == "dst.json" else PRECISION)
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
                               "transaktionen_bis": result.get("transactions_until")},
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

