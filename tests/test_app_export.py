"""Tests App-Export (scripts/app_export.py) gegen den Datenvertrag docs/app_daten.md.

Aufruf: python -m pytest
"""

import gzip
import hashlib
import json
from decimal import Decimal

import pytest

import app_export
import check_public
import compute
import espn_fetch as ef
import rawdata
from zahlen import round_to

FIRST_LOAD = ("manifest.json", "teams.json", "schedule.json")


@pytest.fixture(scope="module")
def result():
    return compute.compute_season(2026, through=2)


@pytest.fixture(scope="module")
def content(result):
    return app_export.render(app_export.build(result), result)


@pytest.fixture(scope="module")
def data(content):
    return {name: json.loads(raw) for name, raw in content.items()}


def test_alle_dateien_und_gueltiges_json(data):
    immer = {"manifest.json", "teams.json", "schedule.json", "players.json", "dst.json", "matchup.json", "history.json",
             "transactions.json", "claude.json"}
    tageslauf = {"waiver.json", "wetter.json"}  # erst, wenn der Tageslauf Pool-Auszug und Wetter geliefert hat
    assert immer <= set(data) <= immer | tageslauf


def test_manifest(content, data):
    m = data["manifest.json"]
    assert (m["schema"], m["season"], m["through_week"]) == (app_export.SCHEMA, 2026, 2)
    assert set(m["files"]) == set(content) - {"manifest.json"}
    for name, info in m["files"].items():
        assert info["v"] == hashlib.sha256(content[name]).hexdigest()[:12]
        assert info["bytes"] == len(content[name])
        assert info["lazy"] == (name not in FIRST_LOAD)
    ds = m["datenstand"]
    assert {"woche_final", "ros_nach_woche", "pool_woche", "transaktionen_bis", "pool_stand", "wetter_stand"} <= set(ds)
    assert all(ds[k] is None or isinstance(ds[k], str) for k in ("pool_stand", "wetter_stand"))
    assert (ds["pool_stand"] is None) == ("waiver.json" not in data)
    assert (ds["wetter_stand"] is None) == ("wetter.json" not in data)


def test_waiver_vertrag(result):
    """waiver.json aus einem erfundenen Pool-Auszug: Auswahl = players.json-Spieler plus aktuelle Kaderspieler."""
    result = dict(result, fantasypros=None)  # ohne Sitemap-Auszug; fp prüft test_fantasypros_adressen
    keep = app_export.player_selection(result)
    inside = sorted(keep)[0]
    outside = max(result["players"]["players"]) + 1  # nicht in players.json, aber laut Tagesstand im Kader
    ignored = outside + 1                              # weder noch: bleibt draußen
    row = {"status": "WAIVERS", "injuryStatus": "QUESTIONABLE", "percentOwned": 64.66, "percentChange": -0.07,
           "percentStarted": 58.81, "waiverProcessDate": 1790751600000, "lastNewsDate": 1790569213000,
           "proj_naechste_woche": 8.7201752}
    pool = {"season": 2026, "woche": 3, "stand": "2026-09-29T0645Z",
            "players": [dict(row, id=inside, onTeamId=0), dict(row, id=outside, onTeamId=2, status="ONTEAM"),
                        dict(row, id=ignored, onTeamId=0)]}
    out = app_export.round_file("waiver.json", app_export.build_waiver(dict(result, pool_latest=pool)))
    assert (out["stand"], out["woche"]) == ("2026-09-29T0645Z", 3)
    assert set(out) == {"stand", "woche", "reihenfolge", "reihenfolge_quelle", "reihenfolge_stand", "bedarf", "spieler",
                        "horizont", "ersatz_woche", "ersatz_3", "anstoss", "bedarf_woche", "bedarf_basis", "profil"}
    assert out["horizont"] == [3, 4, 5] and len(out["anstoss"]) == 32   # W3: alle 32 Teams spielen
    # ohne Reihenfolge im Pool-Auszug: Wochenstand (waiver_prio aus mTeam des Wochenabrufs); ohne ROS kein Bedarf
    weekly = sorted(result["teams"], key=lambda t: t["waiver_prio"])
    assert out["reihenfolge"] == [t["team_id"] for t in weekly] and out["reihenfolge_quelle"] == "wochenabruf"
    assert len(out["reihenfolge"]) == 10 and out["bedarf"] is None and out["reihenfolge_stand"] is None
    assert out["profil"] is None and out["bedarf_basis"] is None   # ohne ROS-Auszug kein Profil
    daily = dict(pool, waiver_reihenfolge={str(i): r for i, r in zip(range(1, 11), [6, 10, 5, 7, 3, 1, 4, 8, 9, 2])},
                 waiver_reihenfolge_stand="2026-09-28T1540Z")
    out_daily = app_export.build_waiver(dict(result, pool_latest=daily))
    assert out_daily["reihenfolge"] == [6, 10, 5, 7, 3, 1, 4, 8, 9, 2] and out_daily["reihenfolge_quelle"] == "tageslauf"
    assert out_daily["reihenfolge_stand"] == "2026-09-28T1540Z"   # Stand der Reihenfolge, nicht des Pool-Auszugs
    assert app_export.build_waiver(dict(result, pool_latest=dict(daily, waiver_reihenfolge_stand=None)))["reihenfolge_stand"] == "2026-09-29T0645Z"
    assert [p["id"] for p in out["spieler"]] == [inside, outside]
    first = out["spieler"][0]
    assert set(first) == {"id", "team", "status", "inj", "own", "own_d", "started", "waiver_bis", "proj", "news",
                          "proj_ue", "proj3", "proj3_ue"}
    assert (first["team"], first["status"], first["inj"], first["own"], first["own_d"], first["started"],
            first["waiver_bis"], first["proj"], first["news"]) \
        == (0, "WAIVERS", "QUESTIONABLE", 64.66, -0.07, 58.81, 1790751600000, 8.72, 1790569213000)
    extra = out["spieler"][1]
    assert extra["team"] == 2 and set(extra) == set(first) | {"name", "pos", "nfl"}
    assert (extra["name"], extra["pos"], extra["nfl"]) == (None, None, None)  # nicht einmal im Wochenpool
    known = next(pid for pid in sorted(result["players"]["players"]) if pid not in keep)  # im Wochenpool, nicht in players.json
    out = app_export.build_waiver(dict(result, pool_latest=dict(pool, players=[dict(row, id=known, onTeamId=3)])))
    assert out["spieler"][0]["name"] == result["players"]["players"][known]["name"] and out["spieler"][0]["pos"]
    assert app_export.build_waiver(dict(result, pool_latest=None)) is None


def test_fantasypros_adressen(result):
    """Mit Sitemap-Auszug trägt jede Spielerzeile fp (Adresse oder None = Suche); ohne Auszug fehlt das Feld (App: alte
    Namensregel). Der Auszug ist ein erfundener Ausschnitt mit echten Adressen."""
    assert all("fp" not in p for p in app_export.build_players(dict(result, fantasypros=None))["players"])
    sitemap = {"positionen": {"QB": ["patrick-mahomes", "josh-allen-qb"], "RB": [], "WR": [], "TE": [], "K": [],
                              "DST": ["kansas-city-defense"]}}
    rows = {p["id"]: p for p in app_export.build_players(dict(result, fantasypros=sitemap))["players"]}
    assert all("fp" in p for p in rows.values())
    assert rows[3139477]["fp"] == "patrick-mahomes" and rows[3918298]["fp"] == "josh-allen-qb"   # Mahomes, Josh Allen
    assert all(p["fp"] is None for p in rows.values() if p["pos"] in ("D/ST", "RB"))           # D/ST: Tabelle der App
    twins = [{"name": "Josh Allen", "pos": "QB"}, {"name": "Josh Allen", "pos": "QB"}]           # erfundene Dopplung
    app_export.add_fantasypros(twins, dict(result, fantasypros=sitemap))
    assert [t["fp"] for t in twins] == [None, None]                                            # dieselbe Adresse: Suche
    # Kaderspieler, den nur der Tagesstand kennt: fp wie name, pos, nfl aus dem Wochenpool
    known = next(pid for pid in sorted(result["players"]["players"]) if pid not in app_export.player_selection(result))
    pool = {"season": 2026, "woche": 3, "stand": "2026-09-29T0645Z", "players": [{"id": known, "onTeamId": 3}]}
    extra = app_export.build_waiver(dict(result, pool_latest=pool, fantasypros=sitemap))["spieler"][0]
    assert "fp" in extra and "fp" not in app_export.build_waiver(dict(result, pool_latest=pool, fantasypros=None))["spieler"][0]


def test_bedarf_vertrag():
    """bedarf aus erfundenen Wochen- und Tagesdaten: Kader laut Tagesstand, ROS/Spiel und Ersatz laut Wochenstand.
    Team 1 hat nur QB 20, RB 9 (unter Ersatz 10), WR 12 und einen D/ST; Team 2 nur einen QB unter Ersatz."""
    from lineup import DST, QB, RB, WR
    weekly = {10: {"pos": QB, "ros_pro_spiel": Decimal(20)}, 15: {"pos": RB, "ros_pro_spiel": Decimal(9)},
              30: {"pos": WR, "ros_pro_spiel": Decimal(12)}, -1: {"pos": DST, "ros_pro_spiel": Decimal(8)},
              70: {"pos": QB, "ros_pro_spiel": Decimal("15.5")}, 99: {"pos": RB, "ros_pro_spiel": None}}
    for pid, w in weekly.items():   # Playoffs W15–17: hier nur QB 70 mit 25 über dem Playoff-Ersatz 20
        w["ros_po_pro_spiel"] = Decimal(25) if pid == 70 else None
    result = {"players": {"players": weekly, "ros_after_week": 3,
                          "ersatz": {QB: Decimal(18), RB: Decimal(10), WR: Decimal(7), DST: None},
                          "ersatz_po": {QB: Decimal(20), RB: None, WR: None, DST: None}}}
    pool = {"players": [{"id": 10, "onTeamId": 1}, {"id": 15, "onTeamId": 1}, {"id": 30, "onTeamId": 1},
                        {"id": -1, "onTeamId": 1}, {"id": 70, "onTeamId": 2}, {"id": 99, "onTeamId": 0},
                        {"id": 12345, "onTeamId": 2}]}   # 12345 fehlt im Wochenpool: Position unbekannt, entfällt
    out = app_export.round_file("waiver.json", {"bedarf": app_export.team_needs(pool, result)})["bedarf"]
    assert list(out) == [1, 2]
    assert out[1]["ueber_ersatz"] == {"QB": 1, "RB": 0, "WR": 1, "TE": None, "K": None, "D/ST": None}
    assert [(g["slot"], g["id"], g["pos"], g["ros_g"]) for g in out[1]["luecken"]] == [
        ("RB", 15, "RB", 9.0), ("RB", None, None, None), ("WR", None, None, None), ("WR", None, None, None),
        ("TE", None, None, None), ("D/ST", None, None, None), ("K", None, None, None),
        ("FLEX", None, None, None), ("FLEX", None, None, None), ("OP", None, None, None)]
    assert [(g["slot"], g["id"], g["ros_g"]) for g in out[2]["luecken"]][:2] == [("QB", 70, 15.5), ("RB", None, None)]
    assert app_export.team_needs(pool, {"players": dict(result["players"], ros_after_week=None)}) is None
    # nach W14 zählen die Playoffs (Beschluss 30.09.2026): Team 2 hat mit QB 70 (25 > 20) keine QB-Lücke mehr
    po = app_export.team_needs(pool, {"players": dict(result["players"], ros_after_week=14)})
    assert po[2]["luecken"][0]["slot"] == "RB" and po[2]["ueber_ersatz"]["QB"] == 1
    assert app_export.need_basis({"players": dict(result["players"], ros_after_week=14)})[2] == "playoffs"
    assert app_export.team_needs(pool, {"players": dict(result["players"], ros_after_week=17)}) is None


def test_wetter_vertrag():
    """wetter.json: Verdichtung je Spiel mit einer Stelle, Regenwahrscheinlichkeit ganzzahlig."""
    import wetter
    site = {"stadion": "S", "ort": "O", "lat": 1, "lon": 2, "dach": "offen", "zeitzone": "UTC", "neutral": False}
    stunden = {"zeit": ["a"] * 4, "temp": [10.04, 10.06, 10.0, 10.0], "wind": [1, 2, 3, 4], "boeen": [5, 6, 7, 8],
               "regen_wahrsch": [10, 55, 30, 0], "niederschlag": [0.1, 0.25, 0, 0], "schnee": [0, 0, 0, 0]}
    prognose = {"woche": 4, "stand": "2026-09-29T0645Z",
                "spiele": [dict(site, id=1, woche=4, kickoff="2026-10-02T00:15Z", heim=12, gast=7, stunden=stunden)]}
    out = app_export.round_file("wetter.json", wetter.compute_wetter(prognose, None, {12: "KC", 7: "DEN"}))
    game = out["prognose"][0]
    assert (game["heim"], game["gast"], game["temp"], game["wind"], game["boeen"], game["regen_wahrsch"],
            game["niederschlag"], game["schnee"]) == ("KC", "DEN", 10.0, 2.5, 8.0, 55, 0.4, 0.0)
    assert isinstance(game["regen_wahrsch"], int) and out["ist"] == [] and out["stand"] == "2026-09-29T0645Z"
    assert set(game) == {"id", "woche", "kickoff", "tbd", "heim", "gast", "stadion", "ort", "dach", "neutral",
                         "temp", "wind", "boeen", "regen_wahrsch", "niederschlag", "schnee", "markierung"}
    assert game["markierung"] == []
    assert set(out) == {"stand", "woche", "einheiten", "schwellen", "prognose", "ist"}
    assert out["schwellen"] == {"wind": 25, "boeen": 40, "regen_wahrsch": 60, "schnee": 0}
    assert all(isinstance(v, int) for v in out["schwellen"].values())
    stunden = dict(stunden, wind=[30, 30, 30, 30], schnee=[0, 0.2, 0, 0])
    prognose["spiele"][0]["stunden"] = stunden
    out = app_export.round_file("wetter.json", wetter.compute_wetter(prognose, None, {12: "KC", 7: "DEN"}))
    assert out["prognose"][0]["markierung"] == ["wind", "schnee"]


def test_deterministisch(result, content):
    """Zweimal gerechnet und geschrieben: byte-gleich (sonst gäbe es Commits ohne Inhalt)."""
    again = app_export.render(app_export.build(compute.compute_season(2026, through=2)), result)
    assert again == content


def test_groessen(content):
    first = sum(len(gzip.compress(content[n])) for n in FIRST_LOAD)
    assert first < 20_000, f"Erstaufruf {first} B gzip"
    assert len(content["claude.json"]) < 50_000
    assert len(gzip.compress(content["players.json"])) < 60_000


def test_teams_vertrag(data):
    teams = data["teams.json"]
    meta = teams["meta"]
    assert [m["key"] for m in meta["metrics"]] == list(compute.METRICS)
    assert meta["profil_standard"] == "Stärke" and meta["norm_standard"] == "z"
    assert meta["profiles"]["Stärke"]["kader"] == 25 and meta["kader_quelle"] == "potenzial"
    assert set(meta["kuerzel"].values()) == {"ACB", "HJS", "4DS", "CRN", "TTY", "SAM", "RTZ", "GLS", "DYN", "SGK"}
    assert [t["rang"] for t in teams["teams"]] == list(range(1, 11))
    for t in teams["teams"]:
        for key in ("kuerzel", "diff", "pa_per_game", "verschenkt_avg", "verschenkt_max", "norm", "score_ref", "pr",
                    "sim", "positionen", "wochen"):
            assert key in t, key
        assert all(isinstance(v, int) for v in t["norm"]["rank"].values())
        assert set(t["sim"]) == {"liga", "espn"} and len(t["sim"]["liga"]["seeds"]) == 6
        assert set(t["wochen"]) == {"gegner", "heim", "pf", "pa", "ergebnis", "wochenrang", "allplay_w", "allplay_l",
                                    "allplay_t", "allplay_pct", "median_win", "median_abstand", "gegner_abstand", "matchup_glueck",
                                    "matchup_kum", "gegner_pkt", "optimal", "verschenkt", "efficiency", "bank",
                                    "projektion", "projektions_delta", "mu", "pr_rang"}
        assert all(len(v) == len(meta["weeks"]) for v in t["wochen"].values())
        assert t["wochen"]["matchup_kum"][-1] == t["matchup_glueck"]  # dieselbe Decimal-Summe, gleich gerundet
        assert t["median_w"] + t["median_l"] == t["games"] and "luck" not in t
    assert 0 < meta["effizienz_liga"] <= 100


def test_browserformel_gleich_python(data):
    """Die App rechnet den Score aus den gerundeten Normwerten; das Ergebnis muss dem Python-Score entsprechen."""
    teams = data["teams.json"]
    for profile, weights in teams["meta"]["profiles"].items():
        for kind in ("z", "minmax", "rank"):
            browser = {t["team_id"]: sum(w * t["norm"][kind][m] for m, w in weights.items()) / sum(weights.values())
                       for t in teams["teams"]}
            for t in teams["teams"]:
                scale = 10 if kind == "z" else 1  # Anzeige 50 + 10·z
                assert abs(browser[t["team_id"]] - t["score_ref"][profile][kind]) * scale < 0.05, (profile, kind)


def test_schedule_vertrag(data):
    s = data["schedule.json"]
    assert [w["week"] for w in s["weeks"]] == list(range(1, ef.MAX_WEEK + 1))
    assert [w["status"] for w in s["weeks"][:2]] == ["final", "final"]
    assert all(0 < w["effizienz_liga"] <= 100 for w in s["weeks"][:2]) and "effizienz_liga" not in s["weeks"][2]
    assert s["weeks"][0]["start"] == "2026-09-08" and s["weeks"][14]["playoff"]
    assert len(s["games"]) == 70 and len(s["h2h"]) == 45
    finals = [g for g in s["games"] if g["winner"] is not None]
    assert len(finals) == 10 and all(g["p_home"] is None for g in finals)
    assert all(0 < g["p_home"] < 1 for g in s["games"] if g["winner"] is None)
    assert len(s["weeks"][0]["top_scorer"]) >= 10


def test_players_auswahl(result, data):
    """Alle Kaderspieler und alle mit mindestens einem Spiel sind drin; Wochenzeilen passen zu weeks."""
    rows = {p["id"]: p for p in data["players.json"]["players"]}
    pool = result["players"]["players"]
    must = {pid for pid, p in pool.items() if p["team_id"] or p["games"]}
    for pos in {p["pos"] for p in pool.values()}:
        free = sorted((p for p in pool.values() if not p["team_id"] and p["pos"] == pos
                       and p["ros_pro_spiel"] is not None), key=lambda p: (-p["ros_pro_spiel"], p["player_id"]))
        must |= {p["player_id"] for p in free[:app_export.FREE_AGENTS_PER_POS]}
    assert set(rows) == must  # genau Kader ∪ mit Spiel ∪ die 20 besten Free Agents je Position
    assert all(len(p["wk"]) == len(data["players.json"]["weeks"]) for p in rows.values())
    assert rows[3139477]["bye"] == 5 and isinstance(rows[3139477]["bye"], int) and rows[3139477]["nfl"] == "KC"  # Mahomes: KC, Bye W5
    assert all(p["bye"] is None or 1 <= p["bye"] <= 18 for p in rows.values())
    assert all(p["bye"] is None for p in rows.values() if p["nfl"] is None)  # ohne NFL-Team kein Bye
    assert {p["pos"] for p in rows.values()} <= {"QB", "RB", "WR", "TE", "K", "D/ST"}


def test_dst_und_transaktionen(data):
    d = data["dst.json"]
    assert len(d["teams"]) == ef.NFL_TEAMS
    lv = next(t for t in d["teams"] if t["abbrev"] == "LV")
    assert abs(Decimal(str(lv["f"])) - Decimal("1.200")) <= Decimal("0.001")
    assert all(isinstance(n.get("opp", ""), str) for t in d["teams"] for n in t["naechste"])
    assert set(data["transactions.json"]) == {"spieler", "items", "aufstellungswechsel", "draft"}


MATCHUP_POS = {"z25", "z26", "n", "r25", "r26", "f", "f_vorwoche", "delta", "rang", "rang_vorwoche"}


def test_matchup_vertrag(data, result):
    """matchup.json: Kopf und je Defense und Position genau die Felder der Positivliste (ohne n25, zugelassen,
    f_verlauf); lazy im Manifest; F, r und Δ mit drei Stellen."""
    m = data["matchup.json"]
    assert set(m) == {"through_week", "saison", "vorjahr", "vorjahr_quelle", "positionen", "ligaschnitt", "formel",
                      "wochen", "defenses"}
    assert (m["through_week"], m["saison"], m["vorjahr"]) == (2, 2026, 2025) and m["positionen"] == ["QB", "RB", "WR", "TE", "K"]
    assert m["vorjahr_quelle"] in ("basis", "ligamittel")
    assert set(m["ligaschnitt"]) == set(m["positionen"]) and all(set(v) == {"2025", "2026"} for v in m["ligaschnitt"].values())
    assert m["wochen"] == {"n1": 3, "naechste3": [3, 4, 5], "rest": list(range(3, 15)), "sos_po": [15, 16, 17]}
    assert data["manifest.json"]["files"]["matchup.json"]["lazy"]
    assert [d["id"] for d in m["defenses"]] == sorted(d["id"] for d in m["defenses"]) and len(m["defenses"]) == ef.NFL_TEAMS
    for d in m["defenses"]:
        assert set(d) == {"id", "abbrev", "bye", "pos"} and list(d["pos"]) == m["positionen"]
        for p in d["pos"].values():
            assert set(p) == MATCHUP_POS and isinstance(p["rang"], int) and isinstance(p["n"], int)
            assert all(len(str(p[k]).split(".")[-1]) <= 3 for k in ("f", "r25", "r26", "delta") if p[k] is not None)
    qb = {d["abbrev"]: d["pos"]["QB"] for d in m["defenses"]}
    raw = {d["abbrev"]: d["pos"]["QB"] for d in result["matchup"]["defenses"]}
    assert qb["KC"]["f"] == float(round_to(raw["KC"]["f"], 3)) and qb["KC"]["z26"] == float(round_to(raw["KC"]["z26"], 2))


def test_players_mu(data, result):
    """players.json: mu je Spieler (Wochenstand, Woche mu_woche = N+1) für QB bis K aus dem Positions-Matchup, für
    D/ST aus den D/ST-Faktoren; ohne NFL-Team None."""
    pj = data["players.json"]
    assert pj["mu_woche"] == 3
    rows = {p["id"]: p for p in pj["players"]}
    assert all("mu" in p for p in rows.values())
    with_mu = [p for p in rows.values() if p["mu"]]
    assert all(p["nfl"] is not None for p in with_mu) and all(p["mu"] is None for p in rows.values() if p["nfl"] is None)
    for p in with_mu:
        assert set(p["mu"]) == {"n1", "naechste3", "rest", "sos_po"} and p["mu"]["n1"]["week"] == 3
        n1 = p["mu"]["n1"]
        assert set(n1) == {"week", "opp", "f", "rang"} and (n1["opp"] is None) == (n1["f"] is None) == (n1["rang"] is None)
        assert n1["rang"] is None or isinstance(n1["rang"], int)
    mahomes = rows[3139477]["mu"]  # KC-QB: Gegner W3 laut Spielplan, F und Rang der Defense für QB
    nfl = rawdata.Season(2026, 2).nfl()
    opp = nfl[12].opponents[3]
    assert mahomes["n1"]["opp"] == nfl[opp].abbrev
    assert mahomes["n1"]["f"] == float(round_to(result["matchup"]["f"]["QB"][opp], 3))
    assert mahomes["n1"]["rang"] == result["matchup"]["rang"]["QB"][opp]
    dst_rows = [p for p in with_mu if p["pos"] == "D/ST"]
    by_team = {t["abbrev"]: t for t in data["dst.json"]["teams"]}
    assert dst_rows and all(p["mu"]["naechste3"] == by_team[p["nfl"]]["naechste3"] for p in dst_rows)


def test_claude_matchup_spalten(data):
    c = data["claude.json"]
    assert c["spieler_spalten"][-2:] == ["gegner_n1", "mu_n1"] and c["stand"]["matchup_woche"] == 3
    cols = {name: i for i, name in enumerate(c["spieler_spalten"])}
    rows = [r for team in c["kader"].values() for r in team] + [r for pos in c["free_agents"].values() for r in pos]
    assert rows and all(len(r) in (len(cols), len(cols) + 1) for r in rows)  # Free Agents zusätzlich mit Status
    assert all((r[cols["gegner_n1"]] is None) == (r[cols["mu_n1"]] is None) for r in rows)
    assert any(isinstance(r[cols["mu_n1"]], float) for r in rows) and "mu_n1" in c["legende"]


def test_transaktionen_markieren_spieler_ohne_seite(data):
    """in_app stimmt mit den Spielern überein, die der Spieler-Tab kennt (players.json plus Kader laut Tagesstand)."""
    t = data["transactions.json"]
    known = {p["id"] for p in data["players.json"]["players"]}
    known |= {s["id"] for s in data.get("waiver.json", {}).get("spieler", []) if s["team"] > 0}
    moves = [i for x in t["items"] for i in x["items"]]
    assert moves and all(i["in_app"] == (i["player_id"] in known) for i in moves)
    assert all(d["in_app"] == (d["player_id"] in known) for d in t["draft"])


def test_oeffentlich(tmp_path, content):
    for name, raw in content.items():
        (tmp_path / name).write_bytes(raw)
    assert check_public.check(tmp_path, ef.REPO_DIR) == []


def test_committete_app_daten_sind_aktuell():
    """Die App-Daten im Repo entsprechen dem Code: nach Änderungen am Rechenwerk compute.py laufen lassen."""
    if not (app_export.APP_DATA / "manifest.json").exists():
        pytest.skip("app/data noch nicht erzeugt")
    latest = compute.compute_season(2026)
    fresh = app_export.render(app_export.build(latest), latest)
    stale = [n for n, raw in fresh.items() if (app_export.APP_DATA / n).read_bytes() != raw]
    assert not stale, f"app/data veraltet ({', '.join(stale)}) – python scripts/compute.py ausführen"


def test_wochensicht_vertrag():
    """week_view aus erfundenen Wochen- und Tagesdaten (Woche 4, Horizont 4–6): Team AAA hat in W5 Bye, BBB spielt immer.
    Freie QBs 24,5 / 20 / OUT; Wochen-Ersatz QB = Ø(24,5; 20) (der OUT-Spieler zählt nicht); Kader Team 1: QB 30 fällt
    aus (OUT), QB 31 mit 10 unter Ersatz."""
    from datetime import datetime, timezone
    from lineup import QB
    nfl = {1: rawdata.NflTeam(1, "AAA", 5, {4: 2, 6: 2}), 2: rawdata.NflTeam(2, "BBB", 13, {4: 1, 5: 1, 6: 1})}
    kick = datetime(2026, 10, 2, 0, 15, tzinfo=timezone.utc)
    games = [{"id": 1, "woche": 4, "heim": 1, "gast": 2, "kickoff": kick, "tbd": False},
             {"id": 2, "woche": 6, "heim": 2, "gast": 1, "kickoff": kick, "tbd": False}]
    weekly = {pid: {"pos": QB, "pro_team": team, "ros_pro_spiel": Decimal(ros)}
              for pid, team, ros in ((10, 1, 5), (11, 2, 4), (12, 2, 9), (30, 1, 22), (31, 2, 10))}
    ros = {"10": {"4": 24.5, "5": 3, "6": 1}, "11": {"4": 20, "5": 18, "6": 17}, "30": {"4": 21, "5": 22, "6": 22}}
    row = lambda pid, status, team, proj, inj="ACTIVE": {"id": pid, "status": status, "onTeamId": team,  # noqa: E731
                                                         "injuryStatus": inj, "proj_naechste_woche": proj}
    pool = {"woche": 4, "players": [row(10, "FREEAGENT", 0, 24.5), row(11, "WAIVERS", 0, 20),
                                    row(12, "FREEAGENT", 0, 30, "OUT"), row(30, "ONTEAM", 1, 21, "OUT"),
                                    row(31, "ONTEAM", 1, 10), row(99, "FREEAGENT", 0, 50)]}   # 99 ohne Wochenpool: entfällt
    result = {"nfl": nfl, "nfl_spiele": games, "ros_projektion": ros,
              "players": {"players": weekly, "ros_after_week": 3, "ersatz": {}}}
    view = app_export.round_file("waiver.json", app_export.week_view(pool, result))
    assert view["horizont"] == [4, 5, 6] and view["anstoss"] == dict.fromkeys(("AAA", "BBB"), int(kick.timestamp() * 1000))
    assert view["ersatz_woche"]["QB"] == 22.25 and view["ersatz_woche"]["RB"] is None
    assert view["ersatz_3"]["QB"] == 40.25                      # Σ: 10 = 24,5 + Bye + 1 = 25,5; 11 = 20 + 18 + 17 = 55
    assert view["spieler"][10] == {"proj_ue": 2.25, "proj3": 25.5, "proj3_ue": -14.75}
    assert view["spieler"][12] == {"proj_ue": -22.25, "proj3": None, "proj3_ue": None}   # OUT: 0, ohne ROS-Eintrag
    assert 99 not in view["spieler"]
    need = view["bedarf_woche"][1]
    assert [(g["slot"], g["id"], g["pos"], g["proj"], g["grund"], g["kandidaten"]) for g in need["luecken"]][:2] == [
        ("QB", 31, "QB", 10.0, None, [10, 11]), ("RB", None, None, None, None, [])]
    assert need["ausfaelle"][0] == {"slot": "QB", "id": 30, "pos": "QB", "grund": "OUT"}
    assert need["byes"] == [{"woche": 5, "slot": "QB", "id": 30, "pos": "QB"}]
    # ohne Regular-Season-ROS keine Ausfälle und Byes, ohne Spielplan oder nach W17 keine Wochensicht
    late = app_export.week_view(pool, dict(result, players={"players": weekly, "ros_after_week": 17, "ersatz": {}}))
    assert late["bedarf_woche"][1]["ausfaelle"] == [] and late["bedarf_woche"][1]["byes"] == []
    assert app_export.week_view(pool, dict(result, nfl=None)) is None
    assert app_export.week_view(dict(pool, woche=18), result) is None


def test_profil_und_zugewinn_echte_daten():
    """Profil und Zugewinn auf dem echten Stand. Der Tagesstand wechselt stündlich, deshalb nur Invarianten:
    sieben Gruppen je Team, Σ Gruppen = Gesamt, schwach und stark getrennt, Absicherung und Bye-Kosten ≤ 0,
    Zugewinn nur für freie Spieler mit brutto > 0 und netto ≤ brutto."""
    res = compute.compute_season(2026)
    if not res.get("pool_latest") or res["players"]["ros_after_week"] is None:
        pytest.skip("noch kein Tagesstand oder ROS-Auszug")
    out = app_export.build_waiver(res)
    assert out["bedarf_basis"] in ("regular", "playoffs") and set(out["profil"]) == set(range(1, 11))
    for p in out["profil"].values():
        assert list(p["gruppen"]) == ["QB", "RB", "WR", "TE", "FLEX", "D/ST", "K"]
        assert sum((g["wert"] for g in p["gruppen"].values()), Decimal(0)) == p["gesamt"]["wert"]
        assert set(p["schwach"]).isdisjoint(p["stark"]) and set(p["schwach"]) | set(p["stark"]) <= set(p["gruppen"])
        assert all(a["wert"] is None or a["wert"] <= 0 for a in p["absicherung"].values())
        assert all(b["kosten"] < 0 and b["ids"] for b in p["byes"])
        assert p["kader"]["spieler"] >= 13 and isinstance(p["kader"]["voll"], bool)
    zug = [s for s in out["spieler"] if "zug" in s]
    assert zug and all(s["status"] in ("WAIVERS", "FREEAGENT") for s in zug)
    assert all(set(s["zug"]) <= {"woche", "drei", "ros"} and v["b"] > 0 and v["n"] <= v["b"]
               for s in zug for h in s["zug"].values() for v in h.values())
