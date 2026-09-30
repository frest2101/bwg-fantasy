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
    immer = {"manifest.json", "teams.json", "schedule.json", "players.json", "dst.json", "history.json",
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
    assert set(out) == {"stand", "woche", "reihenfolge", "reihenfolge_quelle", "reihenfolge_stand", "bedarf", "spieler"}
    # ohne Reihenfolge im Pool-Auszug: Wochenstand (waiver_prio aus mTeam des Wochenabrufs); ohne ROS kein Bedarf
    weekly = sorted(result["teams"], key=lambda t: t["waiver_prio"])
    assert out["reihenfolge"] == [t["team_id"] for t in weekly] and out["reihenfolge_quelle"] == "wochenabruf"
    assert len(out["reihenfolge"]) == 10 and out["bedarf"] is None and out["reihenfolge_stand"] is None
    daily = dict(pool, waiver_reihenfolge={str(i): r for i, r in zip(range(1, 11), [6, 10, 5, 7, 3, 1, 4, 8, 9, 2])},
                 waiver_reihenfolge_stand="2026-09-28T1540Z")
    out_daily = app_export.build_waiver(dict(result, pool_latest=daily))
    assert out_daily["reihenfolge"] == [6, 10, 5, 7, 3, 1, 4, 8, 9, 2] and out_daily["reihenfolge_quelle"] == "tageslauf"
    assert out_daily["reihenfolge_stand"] == "2026-09-28T1540Z"   # Stand der Reihenfolge, nicht des Pool-Auszugs
    assert app_export.build_waiver(dict(result, pool_latest=dict(daily, waiver_reihenfolge_stand=None)))["reihenfolge_stand"] == "2026-09-29T0645Z"
    assert [p["id"] for p in out["spieler"]] == [inside, outside]
    first = out["spieler"][0]
    assert set(first) == {"id", "team", "status", "inj", "own", "own_d", "started", "waiver_bis", "proj", "news"}
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
    result = {"players": {"players": weekly, "ros_after_week": 3,
                          "ersatz": {QB: Decimal(18), RB: Decimal(10), WR: Decimal(7), DST: None}}}
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
    assert app_export.team_needs(pool, {"players": dict(result["players"], ros_after_week=14)}) is None


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
                         "temp", "wind", "boeen", "regen_wahrsch", "niederschlag", "schnee"}


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
