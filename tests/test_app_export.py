"""Tests App-Export (scripts/app_export.py) gegen den Datenvertrag docs/app_daten.md.

Aufruf: python -m pytest
"""

import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import app_export
import check_public
import compute
import espn_fetch as ef
import rawdata
from lineup import QB, RB, WR
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
             "transactions.json", "keeper.json", "claude.json"}
    # erst, wenn der Tageslauf Pool-Auszug, Wetter und Marktwerte geliefert hat
    tageslauf = {"waiver.json", "wetter.json", "claude_marktwert.json"}
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
    assert {"woche_final", "ros_nach_woche", "pool_woche", "transaktionen_bis", "pool_stand", "wetter_stand",
            "experten_woche", "experten_quellen"} <= set(ds)
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
                        "horizont", "ersatz_woche", "ersatz_3", "anstoss", "bedarf_woche", "bedarf_basis", "bedarf_ersatz", "profil",
                        "wert_stand", "keeper_linie", "experten_quellen", "experten_tiefe"}
    assert (out["experten_quellen"], out["experten_tiefe"]) == (None, None)   # Pool-Auszug ohne Expertenränge
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
                          "proj_ue", "proj3", "proj3_ue", "rang_woche", "rang_woche_ges", "rang_3", "rang_3_ges",
                          "exp", "exp_n"}
    assert (first["exp"], first["exp_n"]) == (None, None)
    assert (first["rang_woche"], first["rang_woche_ges"]) == (1, 1)   # einziger Spieler des Pools mit Wochenwert
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


def test_expertenrang_waiver(result):
    """Expertenrang in waiver.json (Beschluss 09.10.2026) aus einem Pool-Auszug mit erfundenen Rängen und echten Spielern:
    Median über alle acht Experten, wer fehlt, zählt als außerhalb seiner Top N (ab 5 von 8 ein Wert), Listentiefe je
    Position aus den Rängen; ist das Spiel zum Stand schon angepfiffen, bleibt der Spieler leer."""
    result = dict(result, fantasypros=None)
    weekly = result["players"]["players"]
    games = sorted((g for g in result["nfl_spiele"] if g["woche"] == 3 and not g["tbd"]), key=lambda g: g["kickoff"])
    first = (games[0]["heim"], games[0]["gast"])           # Teams des ersten Spiels der Woche (Donnerstag)
    rbs = [pid for pid in sorted(app_export.player_selection(result)) if weekly[pid]["pos"] == RB]
    early = next(pid for pid in rbs if weekly[pid]["pro_team"] in first)
    late = [pid for pid in rbs if weekly[pid]["pro_team"] not in first][:3]
    pool = {"season": 2026, "woche": 3, "stand": (games[0]["kickoff"] - timedelta(hours=2)).strftime("%Y-%m-%dT%H%MZ"),
            "experten_quellen": 8, "players": [
                {"id": late[0], "onTeamId": 1, "experten": [3, 4, 4, 5, 6, 6, 7, 9]},      # alle acht: (5 + 6) / 2
                {"id": late[1], "onTeamId": 0, "status": "FREEAGENT", "experten": [40, 44, 47, 50, 50]},  # 5 von 8
                {"id": late[2], "onTeamId": 0, "status": "FREEAGENT", "experten": [12, 30, 48, 49]},      # 4 von 8
                {"id": early, "onTeamId": 2, "experten": [1, 1, 1, 1, 1, 1, 1, 2]},
                # im Kader, aber nicht im Wochenpool (unter der Woche aktiviert): ohne NFL-Team keine Sperre nach dem
                # Anstoß möglich, also kein Wert
                {"id": max(weekly) + 1, "onTeamId": 3, "experten": [3, 3, 4, 4, 5, 5, 6, 6]}]}

    def build(p):
        out = app_export.round_file("waiver.json", app_export.build_waiver(dict(result, pool_latest=p)))
        return out, {s["id"]: (s["exp"], s["exp_n"]) for s in out["spieler"]}

    out, exp = build(pool)
    assert exp == {late[0]: (5.5, 8), late[1]: (50.0, 5), late[2]: (None, 4), early: (1.0, 8), max(weekly) + 1: (None, None)}
    assert (out["experten_quellen"], out["experten_tiefe"]) == (8, {"RB": 50})
    # bis in Manifest (Datenstand-Fenster) und claude.json (Chat): Woche und Zahl der Experten, Tiefe, Spalten
    res = dict(result, pool_latest=pool)
    content = app_export.render(app_export.build(res), res)
    ds = json.loads(content["manifest.json"])["datenstand"]
    claude = json.loads(content["claude.json"])
    assert (ds["experten_woche"], ds["experten_quellen"]) == (3, 8)
    assert (claude["stand"]["experten_quellen"], claude["stand"]["experten_tiefe"]) == (8, {"RB": 50})
    cols = claude["spieler_spalten"]
    row = next(r for rows in claude["kader"].values() for r in rows if r[0] == late[0])
    assert (row[cols.index("exp")], row[cols.index("exp_n")]) == (5.5, 8)
    # Stand nach dem ersten Anstoß: dessen Spieler leer, die übrigen unverändert
    _, exp = build(dict(pool, stand=(games[0]["kickoff"] + timedelta(hours=8)).strftime("%Y-%m-%dT%H%MZ")))
    assert exp[early] == (None, None) and exp[late[0]] == (5.5, 8)
    # ESPN hat die Woche noch nicht veröffentlicht: keine Werte, n = 0
    out, exp = build(dict(pool, experten_quellen=0, players=[dict(p, experten=None) for p in pool["players"]]))
    assert {v for pid, v in exp.items() if pid in weekly} == {(None, 0)} and exp[max(weekly) + 1] == (None, None)
    assert (out["experten_quellen"], out["experten_tiefe"]) == (0, {})


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
    assert meta["profil_standard"] == "Standard" and meta["norm_standard"] == "z"
    assert meta["profiles"]["Standard"]["kader"] == 25 and meta["kader_quelle"] == "potenzial"
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
        must |= {p["player_id"] for p in free[:app_export.free_agents_per_pos(pos)]}
    assert set(rows) == must  # genau Kader ∪ mit Spiel ∪ die 30 (RB, WR: 40) besten Free Agents je Position
    assert (app_export.free_agents_per_pos(RB), app_export.free_agents_per_pos(WR), app_export.free_agents_per_pos(QB)) == (40, 40, 30)
    assert all(len(p["wk"]) == len(data["players.json"]["weeks"]) for p in rows.values())
    assert rows[3139477]["bye"] == 5 and isinstance(rows[3139477]["bye"], int) and rows[3139477]["nfl"] == "KC"  # Mahomes: KC, Bye W5
    assert all(p["bye"] is None or 1 <= p["bye"] <= 18 for p in rows.values())
    assert all(p["bye"] is None for p in rows.values() if p["nfl"] is None)  # ohne NFL-Team kein Bye
    assert {p["pos"] for p in rows.values()} <= {"QB", "RB", "WR", "TE", "K", "D/ST"}
    # Ränge (06.10.2026): Saison nach Punkten nur mit Spiel, je Position und gesamt; Rest je Spiel genauso; ESPNs
    # Saison-Ränge aus kona (Position und gesamt) – alle Spieler mit Spiel tragen sie
    with_game = [p for p in rows.values() if p["g"]]
    assert all(p["saison_rang"] is None and p["saison_rang_ges"] is None for p in rows.values() if not p["g"])
    assert all(1 <= p["saison_rang"] <= p["saison_rang_ges"] for p in with_game)
    assert all(p["espn_rang"] and p["espn_rang_ges"] for p in with_game)
    for pos in ("QB", "RB", "WR", "TE", "K", "D/ST"):
        best = [p for p in with_game if p["pos"] == pos and p["saison_rang"] == 1]
        assert best and all(p["pts"] == max(x["pts"] for x in with_game if x["pos"] == pos) for p in best)
    assert all((p["ros_rang"] is None) == (p["ros_rang_ges"] is None) for p in rows.values())
    assert all(p["ros_rang"] <= p["ros_rang_ges"] for p in rows.values() if p["ros_rang"] is not None)


def test_dst_und_transaktionen(data):
    d = data["dst.json"]
    assert len(d["teams"]) == ef.NFL_TEAMS
    lv = next(t for t in d["teams"] if t["abbrev"] == "LV")
    assert abs(Decimal(str(lv["f"])) - Decimal("1.200")) <= Decimal("0.001")
    assert all(isinstance(n.get("opp", ""), str) for t in d["teams"] for n in t["naechste"])
    assert set(data["transactions.json"]) == {"spieler", "items", "aufstellungswechsel"}   # Draft: keeper.json


KEEPER_TEAM = {"keeper", "keeper_da", "picks", "picks_da", "kader", "pf", "kern", "altersprofil", "marktwert"}
KEEPER_ALTER = {"n", "kader", "ros", "bereinigt", "bereinigt_ros", "jung", "alt", "rookies", "zweites_jahr"}
KEEPER_WERT = {"n", "kern", "ueber_linie", "n_linie", "alter"}
WERT_KEYS = {"wert", "wert_rang", "wert_posrang", "wert_trend", "wert_ue"}
KEEPER_GRUPPEN = {"keeper", "draft", "zugang", "trade"}


def test_keeper_vertrag(data):
    """keeper.json: Kopf, liga, teams, kader und picks genau nach Positivliste; lazy; Anteile mit einer Stelle,
    Punkte mit zwei; Positionen als Kürzel; in_app wie in transactions.json."""
    k = data["keeper.json"]
    assert set(k) == {"through_week", "stand", "draft_datum", "keeper_zahl", "kader_plaetze", "alter_stichtag", "alter_gewicht",
                      "marktwert_stand", "keeper_linie", "draft_folgejahr", "liga", "teams", "kader", "picks"}
    # Draft des Folgejahrs: vor dem Ende der Playoffs ohne feste Reihenfolge (Stufe 4)
    assert k["draft_folgejahr"] == {"saison": 2027, "reihenfolge": None, "endplatz": None, "abweichung": [],
                                    "espn_bestaetigt": None}
    assert (k["through_week"], k["keeper_zahl"], k["kader_plaetze"]) == (2, 12, 24)
    assert data["manifest.json"]["files"]["keeper.json"]["lazy"]
    assert k["stand"] == data["manifest.json"]["datenstand"]["pool_stand"]
    assert set(k["liga"]) == KEEPER_TEAM and [t["team_id"] for t in k["teams"]] == list(range(1, 11))
    places = lambda v: len(str(v).split(".")[-1])  # noqa: E731
    for t in k["teams"] + [k["liga"]]:
        assert set(t) - {"team_id"} == KEEPER_TEAM
        assert set(t["kader"]) == {"keeper", "draft", "waiver", "free_agent", "trade"}
        for part in (t["pf"], t["kern"]):
            assert set(part) == {"summe", "pts", "anteil"} and set(part["pts"]) == set(part["anteil"]) == KEEPER_GRUPPEN
            assert all(places(v) <= 1 for v in part["anteil"].values()) and all(places(v) <= 2 for v in part["pts"].values())
    pf = {t["team_id"]: t["pf"] for t in data["teams.json"]["teams"]}
    assert all(t["pf"]["summe"] == pf[t["team_id"]] for t in k["teams"])
    assert all(set(r) == {"id", "name", "pos", "nfl", "team", "art", "pick", "runde", "von", "seit", "g", "avg", "vj_g",
                          "vj_pts", "vj_avg", "vj_delta", "rookie", "alter", "nfl_jahr", "in_app"} | WERT_KEYS for r in k["kader"])
    assert all(set(p) == {"pick", "runde", "runden_pick", "team_id", "player_id", "name", "pos", "keeper", "da",
                          "team_jetzt", "g", "pts", "avg", "starts", "pf", "in_app"} for p in k["picks"])
    assert len(k["picks"]) == 240 and sum(p["keeper"] for p in k["picks"]) == 119
    assert {p["pos"] for p in k["picks"]} <= {"QB", "RB", "WR", "TE", "K", "D/ST"}
    assert {r["pos"] for r in k["kader"]} <= {"QB", "RB", "WR", "TE", "K", "D/ST", None}
    assert all(p["in_app"] == (p["player_id"] in app_known(data)) for p in k["picks"])
    assert all(r["in_app"] for r in k["kader"]) if "waiver.json" in data else True
    # Altersprofil: ohne nflverse-Stammdaten überall null, mit ihnen je Team die Felder der Positivliste
    if k["alter_stichtag"] is None:
        assert k["alter_gewicht"] is None and all(t["altersprofil"] is None for t in k["teams"] + [k["liga"]])
        assert all(r["alter"] is None and r["nfl_jahr"] is None for r in k["kader"])
    else:
        assert all(set(t["altersprofil"]) == KEEPER_ALTER for t in k["teams"])
        assert set(k["liga"]["altersprofil"]) == KEEPER_ALTER | {"positionen"}
        assert set(k["liga"]["altersprofil"]["positionen"]) <= {"QB", "RB", "WR", "TE", "K"}
        assert all(places(r["alter"]) <= 1 for r in k["kader"] if r["alter"] is not None)
    # Marktwert (Stufe 3): ohne Auszug überall null, mit ihm Werte als ganze Zahlen und je Team die Positivliste
    if k["marktwert_stand"] is None:
        assert k["keeper_linie"] is None and all(t["marktwert"] is None for t in k["teams"] + [k["liga"]])
        assert all(r[key] is None for r in k["kader"] for key in WERT_KEYS)
    else:
        assert isinstance(k["keeper_linie"], int)
        assert all(set(t["marktwert"]) == KEEPER_WERT for t in k["teams"] + [k["liga"]] if t["marktwert"])
        assert all(isinstance(r[key], int) for r in k["kader"] if r["wert"] is not None for key in WERT_KEYS)
        assert all(r["wert"] is None for r in k["kader"] if r["pos"] in ("K", "D/ST"))


def test_keeper_alter_export(result):
    """Export mit erfundenen Stammdaten: Positionen der Liga als Kürzel, Alter je Spieler und das
    Altersprofil der Teams mit einer Stelle."""
    import keeper
    import rawdata
    import players
    import records
    from datetime import date
    ssn = rawdata.Season(2026, 2)
    base = keeper.compute_keeper(ssn, [1, 2], result["players"], records.player_names(ssn))
    ssn._memo["nflverse"] = {"spieler": {str(r["id"]): {"geb": date(1992 + r["id"] % 12, 3, 1 + r["id"] % 28).isoformat(),
                                                        "rookie": 2015 + r["id"] % 12, "draft": None}
                                         for r in base["kader"] if r["id"] > 0}}
    fake = dict(result, keeper=keeper.compute_keeper(ssn, [1, 2], result["players"], records.player_names(ssn)))
    k = app_export.round_file("keeper.json", app_export.build_keeper(fake))
    # ohne ROS-Auszug gewichtet das Altersprofil mit dem Marktwert, sobald es einen Auszug gibt (Stufe 4)
    assert k["alter_stichtag"] == "2026-09-22" and k["alter_gewicht"] in ("ros", "wert", None)
    liga = k["liga"]["altersprofil"]
    assert set(liga) == KEEPER_ALTER | {"positionen"} and set(liga["positionen"]) == {"QB", "RB", "WR", "TE", "K"}
    places = lambda v: len(str(v).split(".")[-1])  # noqa: E731
    assert all(places(p["alter"]) <= 1 for p in liga["positionen"].values())
    assert all(places(r["alter"]) <= 1 and isinstance(r["nfl_jahr"], int) for r in k["kader"] if r["alter"] is not None)
    assert all(set(t["altersprofil"]) == KEEPER_ALTER and places(t["altersprofil"]["bereinigt"]) <= 1 for t in k["teams"])
    findings = []
    check_public.check_json(k, "", findings, "keeper.json")
    assert findings == []


def test_marktwert_export(result):
    """Marktwert (Stufe 3) mit erfundenen Werten für die echten Kader und drei freie Spieler, die players.json nicht
    führt: Keeper-Linie = 120. Wert der Kaderspieler, Kern-Wert = Σ der zwölf wertvollsten je Team; keeper.json,
    waiver.json (Felder nur bei Spielern mit Wert, freie Spieler mit Wert samt Name aus dem Wochenpool) und
    claude_marktwert.json (Gesamtrangliste) – alles erfunden bis auf Kader, Namen und Tagesstand."""
    import keeper
    import records
    if not result.get("pool_latest"):
        pytest.skip("noch kein Tagesstand")
    ssn = rawdata.Season(2026, 2)
    names = records.player_names(ssn)
    # erfundener Kaderspieler (Team 2), den der Wochenpool nicht kennt – unter der Woche geholt (Befund Gegenprüfung)
    neu = 99_999_991
    pool_latest = dict(result["pool_latest"], players=result["pool_latest"]["players"] + [{"id": neu, "onTeamId": 2,
                                                                                          "status": "ONTEAM"}])
    ssn._memo["pool_latest"] = pool_latest
    base = keeper.compute_keeper(ssn, [1, 2], result["players"], names)
    weekly, keep = result["players"]["players"], app_export.player_selection(result)
    offense = [r["id"] for r in base["kader"] if r["pos"] in (1, 2, 3, 4)]
    daily = {p["id"]: p for p in result["pool_latest"]["players"]}
    free = [pid for pid in sorted(weekly) if pid not in keep and pid > 0 and pid in daily
            and not daily[pid].get("onTeamId") and daily[pid].get("status") in ("WAIVERS", "FREEAGENT")][:3]
    ids = offense + free
    value = {pid: 1000 + (pid * 7919) % 9000 for pid in ids}                         # erfunden, aus der ID abgeleitet
    value[neu] = 999                                                                # unter allen: Linie bleibt gleich
    order = sorted(ids, key=lambda pid: (-value[pid], pid)) + [neu]
    ssn._memo["marktwert"] = {"stand": "2026-10-01T0826Z", "spieler": {
        str(pid): {"wert": value[pid], "rang": i, "pos_rang": i, "trend30": pid % 50 - 25, "redraft": 0 if i % 2 else 99}
        for i, pid in enumerate(order, start=1)}}
    k = keeper.compute_keeper(ssn, [1, 2], result["players"], names)
    line = sorted((value[pid] for pid in offense), reverse=True)[119]
    assert (k["keeper_linie"], k["marktwert_stand"]) == (line, "2026-10-01T0826Z")
    for t in k["teams"]:
        mine = sorted((value[r["id"]] for r in k["kader"] if r["team"] == t["team_id"] and r["id"] in value), reverse=True)
        assert t["marktwert"]["kern"] == sum(mine[:12]) and t["marktwert"]["n"] == len(mine)
        assert t["marktwert"]["ueber_linie"] == sum(v - line for v in mine if v > line)
        assert t["marktwert"]["n_linie"] == sum(1 for v in mine if v >= line)
    assert k["liga"]["marktwert"]["n_linie"] >= 120 and k["liga"]["marktwert"]["n"] == len(offense) + 1
    assert set(k["werte"]) == set(ids) | {neu} and all(k["werte"][pid]["team"] == 0 for pid in free)
    assert (k["werte"][neu]["team"], k["werte"][neu]["wert"], k["werte"][neu]["alter"]) == (2, 999, None)
    assert all(k["werte"][pid]["wert_redraft"] is None for pid in order[::2])        # Redraft 0 = keiner
    fake = dict(result, keeper=k, pool_latest=pool_latest)
    kj = app_export.round_file("keeper.json", app_export.build_keeper(fake))
    assert all(set(t["marktwert"]) == KEEPER_WERT and isinstance(t["marktwert"]["kern"], int) for t in kj["teams"] + [kj["liga"]])
    assert all(r["wert"] == value[r["id"]] and r["wert_ue"] == value[r["id"]] - line for r in kj["kader"] if r["id"] in value)
    # waiver.json: die freien Spieler mit Wert stehen mit ESPN-Name darin, Spieler ohne Wert ohne Wertfelder
    w = app_export.round_file("waiver.json", app_export.build_waiver(fake))
    assert (w["wert_stand"], w["keeper_linie"]) == ("2026-10-01T0826Z", line)
    rows = {s["id"]: s for s in w["spieler"]}
    assert all(rows[pid]["name"] == weekly[pid]["name"] and rows[pid]["wert"] == value[pid] for pid in free)
    assert all(set(rows[pid]) >= WERT_KEYS for pid in ids + [neu]) and all("wert" not in s for s in w["spieler"] if s["id"] not in value)
    assert (rows[neu]["team"], rows[neu]["name"], rows[neu]["wert"]) == (2, None, 999)   # Wert auch ohne Wochenpool
    assert set(free) <= app_export.app_player_ids(fake) and not set(free) & {p["id"] for p in app_export.build_players(fake)["players"]}
    # claude_marktwert.json: Gesamtrangliste nach Rang, team = Kürzel oder Status, Texte unter der Grenze
    c = app_export.round_file("claude_marktwert.json", app_export.build_claude_marktwert(fake))
    assert c["spalten"] == list(app_export.MARKTWERT_COLS) and len(c["spieler"]) == len(ids) + 1
    col = {name: i for i, name in enumerate(c["spalten"])}
    assert [r[col["rang"]] for r in c["spieler"]] == list(range(1, len(ids) + 2))
    assert c["spieler"][-1][:4] == [f"Spieler {neu}", None, None, "HJS"]             # ohne Wochenpool: kein „None“-Text
    assert {r[col["team"]] for r in c["spieler"]} <= set(app_export.KUERZEL.values()) | {"WAIVERS", "FREEAGENT"}
    assert all(r[col["herkunft"]] is None for r in c["spieler"] if r[col["team"]] in ("WAIVERS", "FREEAGENT"))
    assert (c["keeper_linie"], c["keeper_zahl"], c["stand"]["marktwert"]) == (line, 12, "2026-10-01T0826Z")
    assert all(len(c[key]) <= check_public.MAX_TEXT for key in ("legende", "legende_spalten", "quelle"))
    assert "FantasyCalc" in c["quelle"] and "fantasycalc.com" in c["quelle"]
    findings = []
    check_public.check_json(c, "", findings, "claude_marktwert.json")
    assert findings == []
    assert app_export.build_claude_marktwert(result) is None or result["keeper"]["werte"]   # ohne Auszug keine Datei


MATCHUP_POS ={"z25", "z26", "n", "r25", "r26", "f", "f_vorwoche", "delta", "rang", "rang_vorwoche"}


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
    assert {"gegner_n1", "mu_n1"} <= set(c["spieler_spalten"]) and c["stand"]["matchup_woche"] == 3
    cols = {name: i for i, name in enumerate(c["spieler_spalten"])}
    kader = [r for team in c["kader"].values() for r in team]
    free = [r for pos in c["free_agents"].values() for r in pos]
    assert kader and all(len(r) == len(cols) for r in kader)
    assert all(len(r) == len(c["free_agents_spalten"]) for r in free)  # Free Agents zusätzlich status
    assert all((r[cols["gegner_n1"]] is None) == (r[cols["mu_n1"]] is None) for r in kader + free)
    assert any(isinstance(r[cols["mu_n1"]], float) for r in kader + free) and "mu_n1" in c["legende"]


def test_claude_vertrag(data):
    """claude.json: Schlüssel, stand mit dem Tagesstand (pool_stand wie im Manifest, pool_woche wie waiver.json),
    Spaltenköpfe, Legenden unter der Textgrenze des Öffentlichkeits-Checks. Auf dem echten Stand nur Invarianten,
    weil der Tagesstand stündlich wechselt."""
    c = data["claude.json"]
    assert set(c) == {"legende", "legende_stand", "legende_experten", "stand", "teams", "tabelle_spalten", "tabelle",
                      "spiele_spalten", "spiele", "spieler_spalten", "free_agents_spalten", "kader", "free_agents",
                      "dst_spalten", "dst", "transaktionen_spalten", "transaktionen"}
    assert set(c["stand"]) == {"saison", "nach_woche", "kader_quelle", "ros_nach_woche", "matchup_woche",
                               "pool_stand", "pool_woche", "experten_quellen", "experten_tiefe"}
    assert c["stand"]["pool_stand"] == data["manifest.json"]["datenstand"]["pool_stand"]
    assert c["stand"]["pool_woche"] == data.get("waiver.json", {}).get("woche")
    assert c["stand"]["experten_quellen"] == data.get("waiver.json", {}).get("experten_quellen")
    assert c["stand"]["experten_quellen"] == data["manifest.json"]["datenstand"]["experten_quellen"]
    assert c["spieler_spalten"] == list(app_export.CLAUDE_PLAYER_COLS)
    assert c["spieler_spalten"][0] == "id" and {"proj", "proj3", "exp", "exp_n"} <= set(c["spieler_spalten"])
    assert c["free_agents_spalten"] == c["spieler_spalten"] + ["status"]
    assert list(c["kader"]) == [app_export.KUERZEL[t] for t in sorted(app_export.KUERZEL)]
    assert all(len(c[k]) <= check_public.MAX_TEXT for k in ("legende", "legende_stand", "legende_experten"))
    status = c["free_agents_spalten"].index("status")
    assert all(r[status] in ("WAIVERS", "FREEAGENT") for rows in c["free_agents"].values() for r in rows)
    # id ist eindeutig: kein Spieler steht zweimal, keiner zugleich im Kader und frei
    ids = [r[0] for rows in [*c["kader"].values(), *c["free_agents"].values()] for r in rows]
    assert ids and all(isinstance(i, int) for i in ids) and len(ids) == len(set(ids))
    proj, proj3 = c["free_agents_spalten"].index("proj"), c["free_agents_spalten"].index("proj3")
    exp, exp_n = c["free_agents_spalten"].index("exp"), c["free_agents_spalten"].index("exp_n")
    if "waiver.json" in data:   # jeder Kaderspieler laut Tagesstand steht im Kader seines Teams
        daily = Counter(s["team"] for s in data["waiver.json"]["spieler"] if s["team"])
        assert all(len(c["kader"][kz]) >= daily[tid] for tid, kz in app_export.KUERZEL.items())
        # je id Team, Status und Wochenwerte wie in waiver.json (beide gleich gerundet); ohne Eintrag dort null
        tag = {s["id"]: s for s in data["waiver.json"]["spieler"]}
        team_id = {kz: tid for tid, kz in app_export.KUERZEL.items()}
        none = {"proj": None, "proj3": None, "exp": None, "exp_n": None}
        for kz, rows in c["kader"].items():
            for r in rows:
                s = tag.get(r[0], {"team": None} | none)
                assert s["team"] in (None, team_id[kz]) and (r[proj], r[proj3]) == (s["proj"], s["proj3"])
                assert (r[exp], r[exp_n]) == (s["exp"], s["exp_n"])
        for r in (r for rows in c["free_agents"].values() for r in rows):
            s = tag.get(r[0], {"status": r[status]} | none)
            assert (r[status], r[proj], r[proj3], r[exp], r[exp_n]) == (s["status"], s["proj"], s["proj3"], s["exp"], s["exp_n"])
    else:                       # ohne Tagesstand keine Wochenwerte
        assert all(r[proj] is None and r[proj3] is None and r[exp] is None
                   for rows in [*c["kader"].values(), *c["free_agents"].values()] for r in rows)


def test_claude_tagesstand(result):
    """claude.json mit erfundenen Spielern und erfundenem Tagesstand (IDs, Namen, Werte erfunden; nur Tabelle, Spiele
    und D/ST-Faktoren sind echt): Kader, Free Agents und D/ST-Besitzer folgen dem Tagesstand; Spieler ohne Eintrag
    dort und die ganze Datei ohne Tagesstand bleiben beim Wochenstand; proj und proj3 gibt es nur im Tagesstand, auch
    im Kader."""
    teams, schedule, dst = app_export.build_teams(result), app_export.build_schedule(result), app_export.build_dst(result)

    def woche(pid, name, pos, team, status, ros_g, nfl="KC"):
        # proj/proj3 hier erfunden: ein gleichnamiges Feld im Wochenstand darf nicht in claude.json durchrutschen
        return {"id": pid, "name": name, "pos": pos, "nfl": nfl, "team": team, "status": status, "inj": "ACTIVE",
                "avg": None, "form": None, "trend": None, "ros_g": Decimal(ros_g), "ros_rang": None, "mu": None,
                "proj": Decimal(99), "proj3": Decimal(99)}

    def tag(pid, team, status, **extra):
        return {"id": pid, "team": team, "status": status, "inj": "ACTIVE", "proj": None, "proj3": None} | extra

    players = {"players": [woche(-16001, "Falcons D/ST", "D/ST", 4, "ONTEAM", 14, nfl="ATL"),  # wird entlassen
                           woche(1, "Erfundener QB", "QB", 2, "ONTEAM", 20),          # wechselt zu Team 5, jetzt OUT
                           woche(2, "Erfundener RB Eins", "RB", 0, "FREEAGENT", 12),  # von Team 3 geholt
                           woche(3, "Erfundener RB Zwei", "RB", 0, "FREEAGENT", 10),  # frei, jetzt auf Waivers
                           woche(4, "Erfundener RB Drei", "RB", 0, "WAIVERS", 11),    # fehlt im Tagesstand
                           woche(5, "Erfundener RB Vier", "RB", 1, "ONTEAM", 9),      # von Team 1 entlassen
                           woche(6, "Erfundener WR Fünf", "WR", 6, "ONTEAM", 8)]}     # Kader, fehlt im Tagesstand
    waiver = {"stand": "2026-10-06T0845Z", "woche": 5,
              "spieler": [tag(-16001, 0, "FREEAGENT"), tag(1, 5, "ONTEAM", inj="OUT"),
                          tag(2, 3, "ONTEAM", proj=Decimal("14.125"), proj3=Decimal("41.205"), exp=Decimal("12.5"), exp_n=8),
                          tag(3, 0, "WAIVERS", proj=Decimal("11.456"), proj3=Decimal("30.1")),
                          tag(5, 0, "FREEAGENT"),
                          tag(99, 2, "ONTEAM", name="Erfundener Neuzugang", pos="WR", nfl="KC",  # nur Tagesstand
                              proj=Decimal("7.5")),
                          tag(97, 7, "ONTEAM", name=None, pos=None, nfl=None),                   # Name unbekannt
                          tag(98, 0, "FREEAGENT", name="Erfundener Freier", pos="WR", nfl="KC")]}  # frei: fehlt

    def claude(w):
        return app_export.round_file("claude.json",
                                     app_export.build_claude(result, teams, schedule, players, dst, None, w))

    cols = {name: i for i, name in enumerate(app_export.CLAUDE_FREE_COLS)}  # Kaderzeilen: dieselben ohne status

    def names(rows):
        return [r[cols["name"]] for r in rows]

    out, weekly = claude(waiver), claude(None)
    assert (out["stand"]["pool_stand"], out["stand"]["pool_woche"]) == ("2026-10-06T0845Z", 5)
    assert names(out["kader"]["TTY"]) == ["Erfundener QB"] and out["kader"]["TTY"][0][cols["inj"]] == "OUT"
    assert out["kader"]["TTY"][0][cols["proj"]] is None   # Wochenwerte nur aus dem Tagesstand (dort None)
    assert out["kader"]["4DS"] == [[2, "Erfundener RB Eins", "RB", "KC", "ACTIVE"] + [None] * 3 + [12.0]
                                   + [None] * 3 + [14.13, 41.21, 12.5, 8]]   # proj, proj3 round half up; exp, exp_n
    assert out["kader"]["HJS"] == [[99, "Erfundener Neuzugang", "WR", "KC", "ACTIVE"] + [None] * 7 + [7.5, None, None, None]]
    # Kaderspieler ohne Eintrag im Tagesstand: Wochenstand, aber keine Wochenwerte (proj 99 im Wochenstand bleibt draußen)
    assert [(r[cols["id"]], r[cols["name"]], r[cols["proj"]], r[cols["proj3"]]) for r in out["kader"]["SAM"]] == [
        (6, "Erfundener WR Fünf", None, None)]
    assert out["kader"]["RTZ"] == [[97, "Spieler 97", None, None, "ACTIVE"] + [None] * 11]
    assert out["kader"]["ACB"] == [] and out["kader"]["CRN"] == []
    assert [(r[cols["id"]], r[cols["name"]], r[cols["status"]], r[cols["proj"]], r[cols["proj3"]])
            for r in out["free_agents"]["RB"]] == [
        (4, "Erfundener RB Drei", "WAIVERS", None, None), (3, "Erfundener RB Zwei", "WAIVERS", 11.46, 30.1),
        (5, "Erfundener RB Vier", "FREEAGENT", None, None)]
    assert names(out["free_agents"]["D/ST"]) == ["Falcons D/ST"] and out["free_agents"]["D/ST"][0][0] == -16001
    assert out["free_agents"]["QB"] == []
    assert 98 not in {r[0] for rows in [*out["kader"].values(), *out["free_agents"].values()] for r in rows}
    atl = next(d for d in dst["teams"] if d["abbrev"] == "ATL")
    assert next(d for d in out["dst"] if d[0] == "ATL")[-1] == "FREEAGENT"
    assert [d for d in out["dst"] if d[0] != "ATL"] == [d for d in weekly["dst"] if d[0] != "ATL"]
    # ohne Tagesstand: Wochenstand wie bisher
    assert (weekly["stand"]["pool_stand"], weekly["stand"]["pool_woche"]) == (None, None)
    assert names(weekly["kader"]["HJS"]) == ["Erfundener QB"] and names(weekly["kader"]["ACB"]) == ["Erfundener RB Vier"]
    assert names(weekly["kader"]["CRN"]) == ["Falcons D/ST"] and weekly["free_agents"]["D/ST"] == []
    assert [(r[cols["name"]], r[cols["status"]]) for r in weekly["free_agents"]["RB"]] == [
        ("Erfundener RB Eins", "FREEAGENT"), ("Erfundener RB Drei", "WAIVERS"), ("Erfundener RB Zwei", "FREEAGENT")]
    assert all(r[cols["proj"]] is None and r[cols["proj3"]] is None   # proj 99 im Wochenstand bleibt draußen
               for rows in [*weekly["kader"].values(), *weekly["free_agents"].values()] for r in rows)
    assert next(d for d in weekly["dst"] if d[0] == "ATL")[-1] == \
        (app_export.KUERZEL[atl["besitzer"]] if atl["besitzer"] else atl["status"])


def test_claude_free_agents_woche():
    """Free Agents in claude.json (erfundene Spieler und Werte): je Position zuerst die 10 besten nach ROS/Spiel, dann
    die übrigen der 10 besten nach Wochenprojektion (proj_ue) ohne Spieler, deren Spiel zum Tagesstand schon lief;
    ohne Tagesstand nur nach ROS/Spiel."""
    # TE 100…111: ROS/Spiel fällt, proj_ue steigt; 111 (PHI) hat zum Stand schon gespielt; 112 ohne ROS/Spiel, aber
    # mit bester Wochenprojektion; 113 steht im Kader und zählt nie
    rows = [{"id": 100 + i, "pos": "TE", "nfl": "PHI" if i == 11 else "KC", "status": "FREEAGENT",
             "ros_g": Decimal(20 - i)} for i in range(12)]
    rows += [{"id": 112, "pos": "TE", "nfl": "KC", "status": "WAIVERS", "ros_g": None},
             {"id": 113, "pos": "TE", "nfl": "KC", "status": "ONTEAM", "ros_g": Decimal(30)}]
    stand = int(datetime(2026, 10, 6, 8, 45, tzinfo=timezone.utc).timestamp() * 1000)
    waiver = {"stand": "2026-10-06T0845Z", "anstoss": {"PHI": stand - 3_600_000, "KC": stand + 86_400_000},
              "spieler": [{"id": 100 + i, "proj_ue": Decimal(i)} for i in range(14)]}
    out = app_export.claude_free_agents(rows, waiver)
    assert list(out) == list(app_export.POSITION_NAMES.values()) and all(not v for k, v in out.items() if k != "TE")
    assert [p["id"] for p in out["TE"]] == [*range(100, 110), 112, 110]   # Woche: 112 (12) vor 110 (10), ohne 111
    assert [p["id"] for p in app_export.claude_free_agents(rows, None)["TE"]] == list(range(100, 110))


def app_known(data) -> set[int]:
    """Spieler mit Seite in der App wie merge() in app/js/v_spieler.js: players.json, dazu aus waiver.json die
    Kaderspieler laut Tagesstand und die Spieler mit Marktwert."""
    known = {p["id"] for p in data["players.json"]["players"]}
    return known | {s["id"] for s in data.get("waiver.json", {}).get("spieler", []) if s["team"] > 0 or "wert" in s}


def test_transaktionen_markieren_spieler_ohne_seite(data):
    """in_app stimmt mit den Spielern überein, die der Spieler-Tab kennt (app_known)."""
    t = data["transactions.json"]
    moves = [i for x in t["items"] for i in x["items"]]
    assert moves and all(i["in_app"] == (i["player_id"] in app_known(data)) for i in moves)


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
    # Ränge über alle Spieler des Wochenpools mit Wert > 0: Woche 10 (24,5) vor 11 (20) vor 31 (10); Summe 11 (55) vor
    # 10 (25,5) vor 30 (OUT in W4 = 0, Bye W5, W6 22 = 22); alle QB, deshalb gesamt = Position
    assert view["spieler"][10] == {"proj_ue": 2.25, "proj3": 25.5, "proj3_ue": -14.75,
                                   "rang_woche": 1, "rang_woche_ges": 1, "rang_3": 2, "rang_3_ges": 2}
    assert view["spieler"][12] == {"proj_ue": -22.25, "proj3": None, "proj3_ue": None,   # OUT: 0, ohne ROS-Eintrag
                                   "rang_woche": None, "rang_woche_ges": None, "rang_3": None, "rang_3_ges": None}
    assert (view["spieler"][30]["rang_woche"], view["spieler"][30]["rang_3"]) == (None, 3)
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


def test_profil_byes_ab_offener_woche():
    """Restwochen der Bye-Kosten im Profil: ab max(Wochenstand + 1, Woche des Tagesstands) bis W14, in den Playoffs bis
    W17. Dienstags vor dem Wochenabruf führt der Tagesstand schon N+2, die Woche N+1 ist gespielt (Beschluss 06.10.2026)."""
    f = app_export.profile_bye_weeks
    assert f(4, 5, "regular") == list(range(5, 15))      # Montag bzw. nach dem Wochenabruf
    assert f(4, 6, "regular") == list(range(6, 15))      # Di 13.10. vor dem Wochenabruf: W5 gespielt
    assert f(4, None, "regular") == list(range(5, 15))   # ohne Woche im Tagesstand gilt der Wochenstand
    assert f(13, 15, "regular") == []                    # Di nach W14 vor dem Wochenabruf: Regular Season vorbei
    assert f(14, 15, "playoffs") == [15, 16, 17] and f(15, 17, "playoffs") == [17]


def test_profil_und_zugewinn_echte_daten():
    """Profil und Zugewinn auf dem echten Stand. Der Tagesstand wechselt stündlich, deshalb nur Invarianten:
    sieben Gruppen je Team, Σ Gruppen = Gesamt, schwach und stark getrennt, Absicherung und Bye-Kosten ≤ 0,
    Zugewinn nur für freie Spieler mit brutto > 0 und netto ≤ brutto."""
    res = compute.compute_season(2026)
    if not res.get("pool_latest") or res["players"]["ros_after_week"] is None:
        pytest.skip("noch kein Tagesstand oder ROS-Auszug")
    out = app_export.build_waiver(res)
    if app_export.need_basis(res) is None:
        # Saisonende (ROS nach W17 ohne Restwoche, Stufe 4): kein Bedarf, kein Profil, kein Zugewinn – statt eines roten
        # Laufs den ganzen Winter (Befund Gegenprüfung 01.10.2026)
        assert out["bedarf_basis"] is None and out["bedarf"] is None and out["profil"] is None
        assert out["bedarf_ersatz"] is None and not any("zug" in s for s in out["spieler"])
        return
    assert out["bedarf_basis"] in ("regular", "playoffs") and set(out["profil"]) == set(range(1, 11))
    for p in out["profil"].values():
        assert list(p["gruppen"]) == ["QB", "RB", "WR", "TE", "FLEX", "D/ST", "K"]
        assert sum((g["wert"] for g in p["gruppen"].values()), Decimal(0)) == p["gesamt"]["wert"]
        assert set(p["schwach"]).isdisjoint(p["stark"]) and set(p["schwach"]) | set(p["stark"]) <= set(p["gruppen"])
        assert all(a is None or (a["wert"] <= 0 and (not a["frei_gleichwertig"] or a["wert"] == 0))
                   for a in p["absicherung"].values())
        assert all(b["kosten"] < 0 and b["ids"] for b in p["byes"])
        assert p["kader"]["spieler"] >= 13 and isinstance(p["kader"]["voll"], bool) and 0 <= p["kader"]["ir"] <= 1
    # Byes (Verlust) erst ab der nächsten offenen Woche: nach dem Wochenstand und nicht vor der Woche des Tagesstands
    after = res["players"]["ros_after_week"]
    assert all(b["woche"] >= max(after + 1, res["pool_latest"]["woche"]) for p in out["profil"].values() for b in p["byes"])
    if after + 2 <= app_export.players_module.LAST_REGULAR_WEEK:
        # Dienstag vor dem Wochenabruf nachgestellt: Der Tageslauf führt schon N+2, die Woche N+1 ist gespielt, aber
        # noch nicht gewertet – sie darf im Profil keine Bye-Kosten mehr tragen (Beschluss Stephan 06.10.2026)
        tue = app_export.build_waiver(dict(res, pool_latest=dict(res["pool_latest"], woche=after + 2)))
        early = sorted({b["woche"] for p in tue["profil"].values() for b in p["byes"] if b["woche"] < after + 2})
        assert not early, f"Bye-Kosten in gespielten Wochen {early}"
    # IR-Slot laut Tagesstand: ein Team mit 24 Spielern und einem davon im IR-Slot hat einen Platz frei
    small = next(t for t, p in out["profil"].items() if p["kader"]["spieler"] == 24)
    parked = next(p["id"] for p in res["pool_latest"]["players"] if p.get("onTeamId") == small)
    ir_out = app_export.build_waiver(dict(res, pool_latest=dict(res["pool_latest"], ir_slot={str(small): [parked]})))
    assert ir_out["profil"][small]["kader"]["ir"] == 1 and ir_out["profil"][small]["kader"]["voll"] is False
    zug = [s for s in out["spieler"] if "zug" in s]
    assert zug and all(s["status"] in ("WAIVERS", "FREEAGENT") for s in zug)
    assert all(set(s["zug"]) <= {"woche", "drei", "ros"} and v["b"] > 0 and v["n"] <= v["b"]
               for s in zug for h in s["zug"].values() for v in h.values())
