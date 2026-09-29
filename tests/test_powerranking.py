"""Tests Power Ranking (Stärke μ) und Playoff-Simulation (scripts/powerranking.py).

Echte Daten bis W2 mit Vorjahres-Prior. Kader-Projektion (P je Woche), Wochenabweichungen und die ESPN-Simulation
werden mit konstruierten Daten geprüft, solange ros.json und mStandings fehlen (kommen mit dem Wochenabruf W3);
der Test auf die echte w03/mStandings.json wird bis dahin übersprungen.
Aufruf: python -m pytest -q tests/test_powerranking.py
"""

import json
import math
from decimal import Decimal

import pytest

import compute
import espn_fetch as ef
import powerranking as pr
import rawdata
from zahlen import rounded

TOL = Decimal("0.005")
EPS = Decimal("1E-6")
# Sollwerte nach W2 mit Vorjahres-Prior: team_id → (μ, E, Rang, Trend W1 → W2). Asse's und TeamTy aus dem Bauplan
# Session 4; alle Werte in der Prüfung unabhängig aus den Rohdateien nachgerechnet (Φ über statistics.NormalDist).
SOLL_W2 = {1: (Decimal("235.825"), Decimal("0.7503"), 1, 0),     # Asse's Cowboys
           2: (Decimal("218.766"), Decimal("0.6213"), 3, 0),
           3: (Decimal("189.982"), Decimal("0.3833"), 8, -1),
           4: (Decimal("199.450"), Decimal("0.4613"), 6, 0),
           5: (Decimal("178.898"), Decimal("0.2967"), 10, 0),    # TeamTy
           6: (Decimal("224.164"), Decimal("0.6640"), 2, 0),
           7: (Decimal("194.664"), Decimal("0.4216"), 7, 1),
           8: (Decimal("205.154"), Decimal("0.5090"), 5, 0),
           9: (Decimal("205.232"), Decimal("0.5096"), 4, 0),
           10: (Decimal("189.930"), Decimal("0.3829"), 9, 0)}
L_BAR_W2, L_BAR_2025 = Decimal("204.21"), Decimal("201.54")
OFFENE_SPIELE_W2 = 60                                   # Perioden 3–14 mit je 5 Paarungen


@pytest.fixture(scope="module")
def season():
    return compute.compute_season(2026, through=2)


@pytest.fixture(scope="module")
def ssn():
    return rawdata.Season(2026, 2)


@pytest.fixture(scope="module")
def weeks():
    return compute.completed_weeks(2026, 2)


@pytest.fixture(scope="module")
def result(season, ssn, weeks):
    return pr.compute_power_ranking(ssn, weeks, season["team_weeks"], season["teams"], season["sigma"], runs=2000)


def run(season, ssn, weeks, **kwargs):
    """Power Ranking mit wenigen Simulationsläufen (für Tests, die die Simulation nicht prüfen)."""
    kwargs.setdefault("runs", 20)
    return pr.compute_power_ranking(ssn, weeks, season["team_weeks"], season["teams"], season["sigma"], **kwargs)


def ids_of(season) -> list[int]:
    return sorted(t["team_id"] for t in season["teams"])


# ---------------------------------------------------------------- Stärke μ, Prior, E

def test_ligaschnitte(result):
    assert abs(result["l_bar"] - L_BAR_W2) <= TOL
    assert abs(result["l_bar_2025"] - L_BAR_2025) <= TOL
    assert result["vorjahr"] == 2025


def test_mu_und_e_nach_w2_mit_prior(result):
    assert sorted(result["teams"]) == sorted(SOLL_W2)
    for team_id, (mu, e, rang, trend) in SOLL_W2.items():
        team = result["teams"][team_id]
        assert abs(team["mu"] - mu) <= TOL, team_id
        assert abs(team["e"] - e) <= Decimal("0.0005"), team_id
        assert (team["rang"], team["trend"]) == (rang, trend), team_id
    assert {t["p_quelle"] for t in result["teams"].values()} == {pr.QUELLE_VORJAHR}


def test_strength_week_ohne_spiel():
    """Randfall n = 0 (konstruiert): μ = P; bei gleichem μ zählt PF/Spiel dann als 0."""
    team_weeks = [{"team_id": t, "week": 1, "pf": Decimal(pf)} for t, pf in ((1, 210), (2, 190), (4, 200))]
    res = pr.strength_week(team_weeks, 1, [1, 2, 3, 4], {}, None)
    assert res["l_bar"] == 200 and res["p_quelle"] == pr.QUELLE_VORJAHR
    t1, t2, t3, t4 = (res["teams"][t] for t in (1, 2, 3, 4))
    assert (t3["n"], t3["pf_mean"], t3["p"], t3["mu"]) == (0, None, 200, 200)   # ohne Vorjahr: P = L̄
    assert (t1["mu"], t2["mu"], t4["mu"]) == (202, 198, 200)                   # (1·PF + 4·200)/5
    assert [t1["rang"], t4["rang"], t3["rang"], t2["rang"]] == [1, 2, 3, 4]    # 4 vor 3: PF/Spiel 200 > 0
    assert pr.strength(0, None, Decimal(180)) == 180


def test_prior_formel(result, ssn):
    """P = L̄ + 0,6·(PF/Spiel 2025 − L̄ 2025), PF/Spiel 2025 = pf/(w + l) aus team_seasons."""
    rows = {int(r["slot"]): r for r in ssn.history("team_seasons") if r["season"] == "2025"}
    for team_id, team in result["teams"].items():
        r = rows[team_id]
        pf_2025 = Decimal(r["pf"]) / (int(r["w"]) + int(r["l"]))
        assert team["p"] == result["l_bar"] + Decimal("0.6") * (pf_2025 - result["l_bar_2025"])


def test_mu_zwischen_pf_und_p(result, season):
    for t in season["teams"]:
        team = result["teams"][t["team_id"]]
        low, high = sorted((t["pf_per_game"], team["p"]))
        assert low <= team["mu"] <= high
        assert team["mu"] == (t["games"] * t["pf_per_game"] + 4 * team["p"]) / (t["games"] + 4)


def test_unsicherheit(result, season):
    for t in season["teams"]:
        assert result["teams"][t["team_id"]]["se"] == season["sigma"] / Decimal(t["games"] + 4).sqrt()


def test_summe_e_und_monotonie(result):
    teams = result["teams"]
    assert abs(sum(t["e"] for t in teams.values()) - 5) <= EPS
    by_mu = sorted(teams.values(), key=lambda t: t["mu"])
    assert all(a["e"] < b["e"] for a, b in zip(by_mu, by_mu[1:]))
    assert all(0 < t["e"] < 1 for t in teams.values())


def test_e_bei_gleicher_staerke():
    mu = {t: Decimal(200) for t in range(1, 11)}
    assert all(e == Decimal("0.5") for e in pr.expected_allplay(mu, Decimal(35)).values())


def test_rang_nach_mu(result):
    teams = result["teams"]
    assert sorted(t["rang"] for t in teams.values()) == list(range(1, 11))
    by_rang = sorted(teams.values(), key=lambda t: t["rang"])
    assert all(a["mu"] >= b["mu"] for a, b in zip(by_rang, by_rang[1:]))


def test_rang_gleichstand_nach_pf_pro_spiel():
    mu = {1: Decimal(200), 2: Decimal(200), 3: Decimal(210)}
    assert pr.rank_teams(mu, {1: Decimal(190), 2: Decimal(195), 3: Decimal(180)}) == {3: 1, 2: 2, 1: 3}


def test_verlauf_neu_gerechnet(result, season):
    """Die Reihe W1…N wird je Woche nur aus den Daten bis dahin gerechnet – gleich einem Lauf mit --through 1."""
    season_1 = compute.compute_season(2026, through=1)
    result_1 = pr.compute_power_ranking(rawdata.Season(2026, 1), [1], season_1["team_weeks"], season_1["teams"],
                                        season_1["sigma"], runs=10)
    for team_id, team in result["teams"].items():
        assert [v["week"] for v in team["verlauf"]] == [1, 2]
        w1, w2 = team["verlauf"]
        assert (w2["mu"], w2["rang"], w2["p_quelle"]) == (team["mu"], team["rang"], team["p_quelle"])
        assert (w1["mu"], w1["rang"]) == (result_1["teams"][team_id]["mu"], result_1["teams"][team_id]["rang"])
        assert team["rang_vorwoche"] == w1["rang"]
        assert team["trend"] == w1["rang"] - w2["rang"]   # beide Wochen mit Vorjahres-Prior
        assert result_1["teams"][team_id]["rang_vorwoche"] is None and result_1["teams"][team_id]["trend"] is None


# ---------------------------------------------------------------- P aus der Kader-Projektion, Trend

def test_trend_regel():
    assert pr.trend(5, 3, pr.QUELLE_VORJAHR, pr.QUELLE_VORJAHR) == 2
    assert pr.trend(1, 4, pr.QUELLE_PROJEKTION, pr.QUELLE_PROJEKTION) == -3
    assert pr.trend(5, 3, pr.QUELLE_VORJAHR, pr.QUELLE_PROJEKTION) is None
    assert pr.trend(None, 3, None, pr.QUELLE_VORJAHR) is None


def test_trend_none_bei_quellwechsel(season, ssn, weeks):
    """P aus der Projektion nur in W2 (konstruiert, P = 200 für alle): W1 Vorjahr, W2 Projektion → Trend „neu“."""
    p = {t: Decimal(200) for t in ids_of(season)}
    res = run(season, ssn, weeks, p_by_week={2: p})
    for t in season["teams"]:
        team = res["teams"][t["team_id"]]
        assert [v["p_quelle"] for v in team["verlauf"]] == [pr.QUELLE_VORJAHR, pr.QUELLE_PROJEKTION]
        assert team["p_quelle"] == pr.QUELLE_PROJEKTION and team["p"] == 200
        assert team["mu"] == (2 * t["pf_per_game"] + 4 * 200) / 6
        assert team["rang_vorwoche"] is not None and team["trend"] is None


def test_trend_bei_gleicher_quelle(season, ssn, weeks):
    ids = ids_of(season)
    res = run(season, ssn, weeks, p_by_week={1: {t: Decimal(190 + t) for t in ids}, 2: {t: Decimal(200) for t in ids}})
    for team in res["teams"].values():
        assert team["trend"] == team["rang_vorwoche"] - team["rang"]


def test_p_by_week_unvollstaendig(season, ssn, weeks):
    with pytest.raises(ValueError, match="ohne P"):
        run(season, ssn, weeks, p_by_week={2: {1: Decimal(200)}})


def test_season_stand_passt(season, weeks):
    with pytest.raises(ValueError, match="passt nicht"):
        run(season, rawdata.Season(2026, 1), weeks)


# ---------------------------------------------------------------- Kernsätze

def test_kernsaetze_lesen(tmp_path):
    assert pr.read_kernsaetze(tmp_path / "fehlt.csv") == {}
    path = tmp_path / "power_ranking_2026.csv"
    # Die Texte sind erfunden (Testdaten), keine freigegebenen Kernsätze.
    path.write_text("﻿woche,slot,kernsatz\n3,1,Erfundener Testsatz eins\n3,2,\n4,1,\"Erfunden, mit Komma\"\n",
                    encoding="utf-8")
    assert pr.read_kernsaetze(path) == {(3, 1): "Erfundener Testsatz eins", (4, 1): "Erfunden, mit Komma"}
    path.write_text("woche,slot,kernsatz\n3,1,Erfunden A\n3,1,Erfunden B\n", encoding="utf-8")
    with pytest.raises(ValueError, match="doppelt"):
        pr.read_kernsaetze(path)
    path.write_text("woche,kernsatz\n3,Erfunden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="slot"):
        pr.read_kernsaetze(path)
    path.write_text("woche,slot,kernsatz\ndrei,1,Erfunden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ganze Zahlen"):
        pr.read_kernsaetze(path)


def test_kernsaetze_angehaengt(season, ssn, weeks, tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "REDAKTION_DIR", tmp_path)
    # Die Texte sind erfunden (Testdaten), keine freigegebenen Kernsätze.
    (tmp_path / "power_ranking_2026.csv").write_text(
        "woche,slot,kernsatz\n2,1,Erfundener Satz W2\n1,5,Erfundener Satz W1\n", encoding="utf-8")
    res = run(season, ssn, weeks)
    assert res["teams"][1]["kernsatz"] == "Erfundener Satz W2"
    assert res["teams"][5]["kernsatz"] is None
    assert [v["kernsatz"] for v in res["teams"][5]["verlauf"]] == ["Erfundener Satz W1", None]
    (tmp_path / "power_ranking_2026.csv").write_text("woche,slot,kernsatz\n2,11,Erfunden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unbekannte Slots"):
        run(season, ssn, weeks)


# ---------------------------------------------------------------- Playoff-Simulation

def test_offene_spiele(ssn):
    games = pr.open_games(ssn.schedule(), ssn.settings(), 2)
    assert len(games) == OFFENE_SPIELE_W2
    assert sorted({g["period"] for g in games}) == list(range(3, 15))
    for period in range(3, 15):
        teams = [t for g in games if g["period"] == period for t in (g["home"], g["away"])]
        assert sorted(teams) == list(range(1, 11))
    assert all(g["weeks"] == [g["period"]] for g in games)


def test_simulation_summen(result):
    """Σ Playoff = 6, Σ Division = 2, Σ Bye = 2, Σ Restsiege = offene Spiele (jedes verteilt genau einen Sieg)."""
    assert result["sim_info"] == {"runs": 2000, "seed": 202602, "offene_spiele": OFFENE_SPIELE_W2,
                                  "playoff_teams": 6, "byes": 2}
    for name in pr.SEEDINGS:
        sim = result["sim"][name]
        assert sorted(sim) == list(range(1, 11))
        assert sum(t["playoff"] for t in sim.values()) == 6
        assert sum(t["division"] for t in sim.values()) == 2
        assert sum(t["bye"] for t in sim.values()) == 2
        assert sum(t["restsiege"] for t in sim.values()) == OFFENE_SPIELE_W2
        for pos in range(6):
            assert sum(t["seeds"][pos] for t in sim.values()) == 1


def test_simulation_stimmig(result):
    espn, div = result["sim"]["espn"], result["sim"]["div"]
    for team_id in espn:
        for sim in (espn[team_id], div[team_id]):
            assert sim["playoff"] == sum(sim["seeds"])
            assert sim["bye"] == sum(sim["seeds"][:2])
            assert all(0 <= v <= 1 for v in (sim["playoff"], sim["division"], sim["bye"], *sim["seeds"]))
            assert 0 <= sim["restsiege"] <= 12
        # dieselben Läufe: Division und Restsiege hängen nicht vom Seeding ab; bei „div“ haben genau die
        # Divisionssieger ein Freilos
        assert espn[team_id]["division"] == div[team_id]["division"]
        assert espn[team_id]["restsiege"] == div[team_id]["restsiege"]
        assert div[team_id]["bye"] == div[team_id]["division"]


def test_simulation_staerke_zaehlt(result):
    """Das stärkste Team (Rang 1 nach μ, 2-0) kommt häufiger in die Playoffs als das schwächste (0-2)."""
    by_rang = {t["rang"]: team_id for team_id, t in result["teams"].items()}
    espn = result["sim"]["espn"]
    assert espn[by_rang[1]]["playoff"] > espn[by_rang[10]]["playoff"]
    assert espn[by_rang[1]]["restsiege"] > espn[by_rang[10]]["restsiege"]


# Unabhängige Prüfer-Simulation nach W2 (eigener Code, 20 000 Läufe, anderer Zufallsweg): team_id → (Playoff,
# Division, Bye ESPN). simulate() mit 2 000 Läufen muss innerhalb von 0,04 liegen (≈ 3,5 Standardfehler).
REFERENZ_SIM_W2 = {1: (0.9901, 0.8740, 0.7823), 2: (0.9502, 0.4577, 0.4788), 3: (0.3500, 0.0199, 0.0204),
                   4: (0.6891, 0.1003, 0.1104), 5: (0.1096, 0.0027, 0.0026), 6: (0.9256, 0.3597, 0.3886),
                   7: (0.3981, 0.0160, 0.0226), 8: (0.6526, 0.0727, 0.0823), 9: (0.7164, 0.0873, 0.1031),
                   10: (0.2182, 0.0096, 0.0088)}


def test_simulation_gegen_referenz(result):
    espn = result["sim"]["espn"]
    for team_id, soll in REFERENZ_SIM_W2.items():
        ist = (espn[team_id]["playoff"], espn[team_id]["division"], espn[team_id]["bye"])
        assert all(abs(float(i) - s) <= 0.04 for i, s in zip(ist, soll)), team_id


def test_simulation_deterministisch(season, ssn, result):
    games = pr.open_games(ssn.schedule(), ssn.settings(), 2)
    mu = {t: v["mu"] for t, v in result["teams"].items()}
    a = pr.simulate(season["teams"], games, mu, season["sigma"], runs=300, seed=7)
    b = pr.simulate(season["teams"], games, mu, season["sigma"], runs=300, seed=7)
    c = pr.simulate(season["teams"], games, mu, season["sigma"], runs=300, seed=8)
    assert a == b
    assert a != c


def konstruiert(wins: dict[int, int], division: dict[int, int]) -> list[dict]:
    """Erfundener Tabellenstand (Testdaten): 10 Teams, 2 Spiele, W laut wins, PF absteigend nach team_id."""
    return [{"team_id": t, "division": division[t], "games": 2, "w": w, "l": 2 - w, "t": 0,
             "pf": Decimal(500 - t)} for t, w in wins.items()]


def test_seeding_div_setzt_divisionssieger_auf_1_und_2():
    """Konstruiert: Division 1 (ungerade IDs) gewinnt alles, der Beste von Division 2 steht nach W erst auf Platz 6."""
    division = {t: 1 if t % 2 else 2 for t in range(1, 11)}
    wins = {t: 2 if t % 2 else 0 for t in range(1, 11)}
    wins[10] = 1   # Divisionssieger 2 trotz schlechterer PF als Team 2
    teams = konstruiert(wins, division)
    mu = {t: Decimal(200) for t in range(1, 11)}
    res = pr.simulate(teams, [], mu, Decimal(35), runs=5, seed=1)   # keine offenen Spiele: Stand ist endgültig
    espn, div = res["espn"], res["div"]
    # ESPN: 1, 3, 5, 7, 9 (2-0, nach PF), dann 10 (1-1); Divisionssieger 1 und 10
    assert [next(t for t in espn if espn[t]["seeds"][pos] == 1) for pos in range(6)] == [1, 3, 5, 7, 9, 10]
    assert [next(t for t in div if div[t]["seeds"][pos] == 1) for pos in range(6)] == [1, 10, 3, 5, 7, 9]
    assert espn[10]["bye"] == 0 and div[10]["bye"] == 1 and div[3]["bye"] == 0 and espn[3]["bye"] == 1
    assert {t for t in div if div[t]["division"] == 1} == {1, 10}
    assert espn[2]["playoff"] == 0 and all(v["restsiege"] == 0 for v in espn.values())


def test_seeding_gleichstand_nach_pf_und_unentschieden():
    """W + 0,5·T vor PF: 1-0-1 (1,5) liegt vor 1-1 (1,0) trotz weniger PF."""
    teams = [{"team_id": 1, "division": 1, "games": 2, "w": 1, "l": 1, "t": 0, "pf": Decimal(400)},
             {"team_id": 2, "division": 1, "games": 2, "w": 1, "l": 0, "t": 1, "pf": Decimal(300)},
             {"team_id": 3, "division": 2, "games": 2, "w": 1, "l": 1, "t": 0, "pf": Decimal(350)},
             {"team_id": 4, "division": 2, "games": 2, "w": 0, "l": 2, "t": 0, "pf": Decimal(500)}]
    mu = {t: Decimal(200) for t in range(1, 5)}
    res = pr.simulate(teams, [], mu, Decimal(35), runs=1, seed=1, playoff_teams=2)
    assert res["espn"][2]["seeds"] == [1, 0] and res["espn"][1]["seeds"] == [0, 1]
    assert res["div"][2]["seeds"] == [1, 0] and res["div"][3]["seeds"] == [0, 1]


def test_seeding_pf_und_unentschieden_halb():
    """Konstruiert: Unentschieden zählt 0,5 (nicht 1), bei gleichem W + 0,5·T entscheidet PF, nicht die team_id."""
    teams = [{"team_id": 1, "division": 1, "games": 2, "w": 1, "l": 1, "t": 0, "pf": Decimal(300)},
             {"team_id": 2, "division": 1, "games": 2, "w": 1, "l": 1, "t": 0, "pf": Decimal(400)},
             {"team_id": 3, "division": 2, "games": 2, "w": 1, "l": 0, "t": 1, "pf": Decimal(500)},
             {"team_id": 4, "division": 2, "games": 2, "w": 2, "l": 0, "t": 0, "pf": Decimal(250)}]
    mu = {t: Decimal(200) for t in range(1, 5)}
    res = pr.simulate(teams, [], mu, Decimal(35), runs=1, seed=1, playoff_teams=4)
    seeds = {name: [next(t for t, v in res[name].items() if v["seeds"][pos] == 1) for pos in range(4)]
             for name in pr.SEEDINGS}
    assert seeds == {"espn": [4, 3, 2, 1], "div": [4, 2, 3, 1]}   # 2,0 > 1,5 > 1,0 (400 PF) > 1,0 (300 PF)
    assert {t for t, v in res["espn"].items() if v["division"] == 1} == {2, 4}


def test_restsiege_analytisch():
    """Konstruiert, zwei Teams, 12 Duelle: E[Restsiege] = Σ_w Φ((μ₁ + dev₁,w − μ₂ − dev₂,w)/(σ·√(2 + 1/(n₁+k) + 1/(n₂+k)))).

    Prüft die Streuung beider Stufen der Simulation (μ̃ je Lauf und PF je Woche) und dev beim Auswärtsteam. Mit
    20 000 Läufen streut der Mittelwert um ≈ 0,012; ohne μ̃-Streuung oder mit σ²/(n + k)² läge er um 0,15–0,19 höher.
    """
    sigma, n = Decimal(35), 2
    teams = [{"team_id": t, "division": t, "games": n, "w": 1, "l": 1, "t": 0, "pf": Decimal(400)} for t in (1, 2)]
    games = [{"id": w, "period": w, "weeks": [w], "home": 1 if w % 2 else 2, "away": 2 if w % 2 else 1}
             for w in range(3, 15)]
    mu = {1: Decimal("252.5"), 2: Decimal(200)}              # Abstand 1,5·σ
    p_dev = {2: {3: Decimal("52.5"), 4: Decimal("52.5")}}    # W3 und W4 (einmal heim, einmal auswärts): gleich stark
    res = pr.simulate(teams, games, mu, sigma, p_dev=p_dev, runs=20000, seed=11, playoff_teams=1)["espn"]
    sd = float(sigma) * math.sqrt(2 + 2 / (n + pr.K))
    soll = sum(pr.phi((52.5 - float(p_dev[2].get(w, 0))) / sd) for w in range(3, 15))
    assert abs(float(res[1]["restsiege"]) - soll) <= 0.05
    assert res[1]["restsiege"] + res[2]["restsiege"] == 12


def test_restsiege_echt_analytisch(result, season):
    """Echte Daten nach W2: simulierte Restsiege (2 000 Läufe) ≈ Σ der Siegchancen mit μ-Unsicherheit je Spiel."""
    n = {t["team_id"]: t["games"] for t in season["teams"]}
    sigma = float(season["sigma"])
    soll = {t: 0.0 for t in n}
    for g in result["spiele"]:
        h, a = g["home"], g["away"]
        sd = sigma * math.sqrt(2 + 1 / (n[h] + pr.K) + 1 / (n[a] + pr.K))
        p = pr.phi(float(result["teams"][h]["mu"] - result["teams"][a]["mu"]) / sd)
        soll[h] += p
        soll[a] += 1 - p
    for t, v in result["sim"]["espn"].items():
        assert abs(float(v["restsiege"]) - soll[t]) <= 0.15, t


def test_wochenabweichung_p_dev(ssn):
    """Konstruiert: gleiche μ, Team 4 mit devᵢ,w = +100 in allen offenen Wochen gewinnt fast jedes Restspiel."""
    division = {t: 1 if t % 2 else 2 for t in range(1, 11)}
    teams = konstruiert({t: 1 for t in range(1, 11)}, division)
    games = pr.open_games(ssn.schedule(), ssn.settings(), 2)
    mu = {t: Decimal(200) for t in range(1, 11)}
    p_dev = {4: {w: Decimal(100) for w in range(3, 15)}}
    res = pr.simulate(teams, games, mu, Decimal(35), p_dev=p_dev, runs=400, seed=3)["espn"]
    assert res[4]["restsiege"] > 11 and res[4]["playoff"] == 1
    assert sum(v["restsiege"] for v in res.values()) == OFFENE_SPIELE_W2


def test_bye_count():
    assert [pr.bye_count(n) for n in (2, 4, 5, 6, 8, 12)] == [0, 0, 3, 2, 0, 4]


def test_siegchance(result):
    a, b, sigma = Decimal(220), Decimal(200), result["sigma"]
    assert pr.win_probability(a, a, sigma) == Decimal("0.5")
    assert abs(pr.win_probability(a, b, sigma) + pr.win_probability(b, a, sigma) - 1) <= EPS
    assert len(result["spiele"]) == OFFENE_SPIELE_W2
    for g in result["spiele"]:
        mu_home, mu_away = result["teams"][g["home"]]["mu"], result["teams"][g["away"]]["mu"]
        assert (g["p_home"] > Decimal("0.5")) == (mu_home > mu_away)


# ---------------------------------------------------------------- ESPN-Vergleich (mStandings)

class StubSeason:
    """Erfundene mStandings-Antwort (Testdaten) mit der vermuteten Struktur teams[].currentSimulationResults."""

    def __init__(self, sims: dict[int, dict] | None):
        self.sims = sims

    def standings(self):
        if self.sims is None:
            return None
        return {"teams": [{"id": t, "currentSimulationResults": s} for t, s in self.sims.items()]}

    def settings(self):
        return {"scheduleSettings": {"playoffTeamCount": 6, "divisions": [{"id": 1}, {"id": 2}]}}


def anteile(scale: float) -> dict[int, dict]:
    playoff = [1, 1, 1, 0.9, 0.8, 0.5, 0.4, 0.2, 0.1, 0.1]
    division = [0.6, 0.4, 0.3, 0.3, 0.2, 0.1, 0.05, 0.05, 0, 0]
    return {t: {"playoffPct": round(playoff[t - 1] * scale, 6), "divisionWinPct": round(division[t - 1] * scale, 6)}
            for t in range(1, 11)}


def test_espn_simulation_fehlt(ssn):
    if (ef.week_dir(2026, 2) / ef.STANDINGS_FILE).exists():
        pytest.skip("w02/mStandings.json liegt vor")
    assert pr.espn_simulation(ssn) is None
    assert pr.espn_simulation(StubSeason(None)) is None


@pytest.mark.parametrize("scale", [1, 100])
def test_espn_simulation_anteil_oder_prozent(scale):
    res = pr.espn_simulation(StubSeason(anteile(scale)))
    assert sorted(res) == list(range(1, 11))
    assert abs(sum(t["playoff"] for t in res.values()) - 6) <= EPS
    assert abs(sum(t["division"] for t in res.values()) - 2) <= EPS
    assert res[4] == {"playoff": Decimal("0.9"), "division": Decimal("0.3")}


def test_espn_simulation_unbekannte_struktur():
    assert pr.espn_simulation(StubSeason({t: {"rank": t} for t in range(1, 11)})) is None
    assert pr.espn_simulation(StubSeason({t: {"playoffPct": 0.3} for t in range(1, 11)})) is None  # Σ = 3 ≠ 6
    sims = anteile(1)
    for s in sims.values():
        del s["divisionWinPct"]
    assert all(t["division"] is None for t in pr.espn_simulation(StubSeason(sims)).values())


def test_espn_simulation_w03_echt():
    """Echte ESPN-Simulation nach W3 – Feldnamen und Skala am JSON prüfen (Teil B4)."""
    if not (ef.week_dir(2026, 3) / ef.STANDINGS_FILE).exists():
        pytest.skip("w03/mStandings.json fehlt noch (Wochenabruf W3)")
    res = pr.espn_simulation(rawdata.Season(2026, 3))
    assert res is not None, "Struktur von currentSimulationResults unbekannt – ESPN_SIM_FIELDS anpassen"
    assert sorted(res) == list(range(1, 11))
    assert abs(sum(t["playoff"] for t in res.values()) - 6) <= Decimal("0.12")


# ---------------------------------------------------------------- Ausgabeform

def test_ausgabe_decimal_und_json(result):
    """Keine float-Werte in der Ausgabe (gerundet wird erst beim Export) und JSON-fähig nach zahlen.rounded."""
    def walk(value):
        if isinstance(value, dict):
            for v in value.values():
                yield from walk(v)
        elif isinstance(value, list):
            for v in value:
                yield from walk(v)
        else:
            yield value
    assert not any(isinstance(v, float) for v in walk(result))
    team = result["teams"][1]
    assert set(team) == {"mu", "se", "p", "p_quelle", "e", "rang", "rang_vorwoche", "trend", "kernsatz", "verlauf"}
    assert set(result) >= {"l_bar", "l_bar_2025", "sigma", "teams", "sim", "espn_sim"}
    json.dumps(rounded(result), ensure_ascii=False)
