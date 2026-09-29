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
    assert set(data) == {"manifest.json", "teams.json", "schedule.json", "players.json", "dst.json",
                         "history.json", "transactions.json", "claude.json"}


def test_manifest(content, data):
    m = data["manifest.json"]
    assert (m["schema"], m["season"], m["through_week"]) == (app_export.SCHEMA, 2026, 2)
    assert set(m["files"]) == set(content) - {"manifest.json"}
    for name, info in m["files"].items():
        assert info["v"] == hashlib.sha256(content[name]).hexdigest()[:12]
        assert info["bytes"] == len(content[name])
        assert info["lazy"] == (name not in FIRST_LOAD)


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
                                    "allplay_t", "allplay_pct", "median_win", "median_abstand", "matchup_glueck",
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
    assert {p["pos"] for p in rows.values()} <= {"QB", "RB", "WR", "TE", "K", "D/ST"}


def test_dst_und_transaktionen(data):
    d = data["dst.json"]
    assert len(d["teams"]) == ef.NFL_TEAMS
    lv = next(t for t in d["teams"] if t["abbrev"] == "LV")
    assert abs(Decimal(str(lv["f"])) - Decimal("1.200")) <= Decimal("0.001")
    assert all(isinstance(n.get("opp", ""), str) for t in d["teams"] for n in t["naechste"])
    assert set(data["transactions.json"]) == {"spieler", "items", "aufstellungswechsel", "draft"}


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
