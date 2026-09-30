"""Tests Positions-Matchup (scripts/matchup.py).

1. Z26 gegen ESPN positionAgainstOpponent (QB, RB, WR, TE, K; Stand W2 in der W3-Datei, siehe CLAUDE.md).
2. Innere Stimmigkeit mit echten Daten nach W3 (Auslöser, Ränge, Summen, Stand ohne Vorjahresauszug).
3. Randfälle mit einer Attrappe aus vier erfundenen NFL-Teams AAA–DDD und erfundenen Spielern (keine echten Ligadaten).
Aufruf: python -m pytest -q tests/test_matchup.py
"""

import statistics
from decimal import Decimal

import pytest

import dst
import espn_fetch as ef
import matchup
import rawdata
from lineup import DST, K, QB, RB, TE, WR
from rawdata import NflTeam, PoolRow
from zahlen import ONE, ZERO, dec, rounded

FILES = ef.season_files(2026)
TOL = Decimal("0.005")
TINY = Decimal("1e-20")
POS_KEYS = {"z25", "n25", "z26", "n", "r25", "r26", "f", "f_vorwoche", "delta", "rang", "rang_vorwoche", "ausloeser",
            "zugelassen", "f_verlauf"}


def real(through: int) -> dict:
    if not all((ef.week_dir(2026, w) / ef.KONA_FILE).exists() for w in range(1, through + 1)):
        pytest.skip(f"Spielerpool bis W{through} fehlt noch (holt der Wochenabruf)")
    return matchup.compute_matchup(rawdata.Season(2026, through), list(range(1, through + 1)))


@pytest.fixture(scope="module")
def w2():
    return real(2)


@pytest.fixture(scope="module")
def w3():
    return real(3)


# ---------------------------------------------------------------- 1. ESPN positionAgainstOpponent

def test_z26_gleich_espn(w2):
    """ratingsByOpponent[Defense].average je Position aus kona w03 (Stand W2, siehe test_dst) = eigenes Z26 nach W2,
    32 × 5; ESPN zählt wie matchup.py alle Spieler der Position mit 210 == 1 beim Team des Spiels."""
    espn = rawdata.Season(2026, 3).ratings(3)["positionalRatings"]
    for pos in matchup.POSITIONS:
        by_def = espn[str(pos)]["ratingsByOpponent"]
        assert len(by_def) == ef.NFL_TEAMS
        for d in w2["defenses"]:
            assert abs(d["pos"][matchup.NAMES[pos]]["z26"] - dec(by_def[str(d["id"])]["average"])) <= TOL, \
                (d["abbrev"], matchup.NAMES[pos])


# ---------------------------------------------------------------- 2. echte Daten nach W3

def test_echte_daten_ohne_warnung(w3):
    """Ohne basis/positionen_2025.json rechnet das Modul mit r25 = 1,00 (Ligamittel); mit Auszug aus dem Vorjahr."""
    expect = "basis" if FILES["prior_positions"].exists() else "ligamittel"
    assert w3["warnungen"] == [] and w3["vorjahr_quelle"] == expect
    assert w3["positionen"] == ["QB", "RB", "WR", "TE", "K"] and w3["through_week"] == 3
    assert w3["wochen"] == {"n1": 4, "naechste3": [4, 5, 6], "rest": list(range(4, 15)), "sos_po": [15, 16, 17]}
    if expect == "ligamittel":
        assert all(v["2025"] is None for v in w3["ligaschnitt"].values())
        assert all(p["r25"] == ONE and p["z25"] is p["n25"] is None for d in w3["defenses"] for p in d["pos"].values())


def test_echte_daten_struktur(w3):
    defenses = w3["defenses"]
    assert [d["id"] for d in defenses] == sorted(d["id"] for d in defenses) and len(defenses) == ef.NFL_TEAMS
    nfl = rawdata.Season(2026, 3).nfl()
    for d in defenses:
        assert set(d) == {"id", "abbrev", "bye", "pos"} and d["bye"] == nfl[d["id"]].bye
        assert list(d["pos"]) == w3["positionen"] and all(set(p) == POS_KEYS for p in d["pos"].values())
    assert set(w3["spielplan"]) == set(nfl) and w3["spielplan"][12] == nfl[12].opponents
    for name in w3["positionen"]:
        assert sorted(w3["f"][name]) == sorted(nfl) and w3["rang"][name] == {d["id"]: d["pos"][name]["rang"] for d in defenses}
        r26 = [d["pos"][name]["r26"] for d in defenses if d["pos"][name]["n"]]
        assert abs(statistics.mean(r26) - ONE) < TINY


def test_echte_daten_summen(w3):
    """Σ zugelassen je Woche und Position = Σ Punkte aller Spieler der Position mit Einsatz (jeder zählt genau einmal)."""
    ssn = rawdata.Season(2026, 3)
    for week in (1, 2, 3):
        for pos in matchup.POSITIONS:
            played = sum((r.actual or ZERO for r in ssn.pool(week) if r.pos == pos and r.played), ZERO)
            allowed = sum((d["pos"][matchup.NAMES[pos]]["zugelassen"][week - 1] or ZERO for d in w3["defenses"]), ZERO)
            assert played == allowed, (week, pos)


def test_echte_daten_ausloeser(w3):
    """Auslöser wie D/ST ohne z: |ΔF| ≥ 0,10 und Rangsprung ≥ 5; nach W3 kommen beide vor."""
    seen = set()
    for d in w3["defenses"]:
        for p in d["pos"].values():
            assert p["delta"] == p["f"] - p["f_vorwoche"] and p["f_verlauf"][-1] == p["f"]
            assert ("delta" in p["ausloeser"]) == (abs(p["delta"]) >= Decimal("0.10"))
            assert ("rang" in p["ausloeser"]) == (abs(p["rang_vorwoche"] - p["rang"]) >= 5)
            assert "z" not in p["ausloeser"]
            seen |= set(p["ausloeser"])
    assert seen == {"delta", "rang"}


def test_ohne_vorjahr_kein_rangsprung_vom_gleichstand():
    """Ohne Vorjahresauszug teilen sich vor der Saison alle 32 Defenses Rang 1 (F = 1,00): nach W1 gibt es dann keinen
    Rang-Auslöser (ein Sprung vom Gleichstand aus ist keiner), ΔF zählt weiter."""
    if not (ef.week_dir(2026, 1) / ef.KONA_FILE).exists():
        pytest.skip("Spielerpool W1 fehlt noch (holt der Wochenabruf)")
    ssn = rawdata.Season(2026, 1)
    ssn._memo["prior_positions"] = None  # Stand vor dem ersten Abruf des Auszugs, auch wenn er im Repo liegt
    result = matchup.compute_matchup(ssn, [1])
    assert result["vorjahr_quelle"] == "ligamittel"
    cells = [p for d in result["defenses"] for p in d["pos"].values()]
    assert {p["rang_vorwoche"] for p in cells} == {1} and max(p["rang"] for p in cells) >= 6
    assert not any("rang" in p["ausloeser"] for p in cells)
    assert all(("delta" in p["ausloeser"]) == (abs(p["delta"]) >= Decimal("0.10")) for p in cells)


def test_echte_daten_json_stellen(w3):
    data = rounded(w3, precision=matchup.PRECISION)
    qb = data["defenses"][0]["pos"]["QB"]
    assert all(len(str(qb[k]).split(".")[-1]) <= 3 for k in ("f", "r26", "delta"))
    assert isinstance(qb["rang"], int) and isinstance(qb["n"], int)


# ---------------------------------------------------------------- 3. Attrappe
# Vier erfundene NFL-Teams; Paarungen reihum nach Woche % 3: W1 AAA–CCC, BBB–DDD · W2 AAA–DDD (BBB, CCC Bye) ·
# W3 AAA–BBB, CCC–DDD; in W7 haben AAA und CCC Bye. Alle Spieler und Punkte sind erfunden.

FAKE = {1: "AAA", 2: "BBB", 3: "CCC", 4: "DDD"}
PAIRS = {0: ((1, 2), (3, 4)), 1: ((1, 3), (2, 4)), 2: ((1, 4), (2, 3))}
SETTINGS = {"scheduleSettings": {"matchupPeriodCount": 14, "matchupPeriods": {str(w): [w] for w in range(1, 18)}},
            "scoringSettings": {"scoringItems": [{"statId": 3, "points": 0.04},
                                                 {"statId": 53, "points": 1.0, "pointsOverrides": {"16": 0.0}}]}}
# je Woche: (ID, Name, Position, NFL-Team heute, NFL-Team im Spiel, Punkte, gespielt)
POOL = {
    1: [(1, "QB Alpha", QB, 1, 1, 20, True), (2, "QB Bravo", QB, 2, 2, 14, True), (3, "QB Charlie", QB, 3, 3, 12, True),
        (4, "QB Delta", QB, 4, 4, 16, True),
        (5, "RB Echo", RB, 4, 1, 10, True),       # damals AAA (Trade), heute DDD: zählt gegen CCC, nicht gegen BBB
        (7, "RB Golf", RB, 1, 1, 8, True),        # zweiter RB von AAA: Summe gegen CCC = 18
        (8, "RB Hotel", RB, 2, 2, None, True),    # gespielt ohne Punkte: Spiel mit 0 gegen DDD
        (10, "K Juliet", K, 1, 1, 9, True),
        (-16001, "AAA D/ST", DST, 1, 1, 5, True)],  # D/ST zählt hier nicht
    2: [(1, "QB Alpha", QB, 1, 1, 10, True), (2, "QB Bravo", QB, 2, 0, None, False),  # Bye: kein Ist-Eintrag
        (4, "QB Delta", QB, 4, 4, 22, True),
        (6, "RB Foxtrot", RB, 0, 0, 5, True),     # ohne NFL-Team: Warnung
        (9, "WR India", WR, 2, 2, 4, True)],      # BBB hat Bye: Warnung
    3: [(1, "QB Alpha", QB, 1, 1, 30, True), (2, "QB Bravo", QB, 2, 2, 18, True),
        (3, "QB Charlie", QB, 3, 3, 0, False),    # nicht gespielt: DDD hat in W3 kein QB-Spiel
        (4, "QB Delta", QB, 4, 4, 8, True), (5, "RB Echo", RB, 4, 4, 7, True)],
}
WARNUNGEN = ["W2: RB Foxtrot (RB) hat gespielt, Team 0 laut Spielplan ohne Spiel – übersprungen",
             "W2: WR India (WR) hat gespielt, Team BBB laut Spielplan ohne Spiel – übersprungen"]


def fake_schedule(last_week: int, byes=()) -> dict[int, NflTeam]:
    opponents = {t: {} for t in FAKE}
    for w in range(1, last_week + 1):
        for a, b in PAIRS[w % 3]:
            if (w, a, b) not in byes:
                opponents[a][w], opponents[b][w] = b, a
    return {t: NflTeam(t, FAKE[t], next((w for w in range(1, 18) if w not in opponents[t]), 0), opponents[t])
            for t in FAKE}


def fake_pool(week: int) -> list[PoolRow]:
    """Spielerpool der Woche; nach W3 leer (niemand spielt, der Stand bleibt)."""
    return [PoolRow(pid, name, pos, team, 0, "FREEAGENT", None, None, dec(pts) if pts is not None else None, None,
                    played, game) for pid, name, pos, team, game, pts, played in POOL.get(week, [])]


def fake_extract(prior_nfl: dict, scoring=None) -> dict:
    """Auszug im Format von espn_fetch.positions_extract (Vorjahr W1–3 plus W4 ohne Spielplan-Eintrag).

    QB: jede Offense erzielt Z25 ihres Gegners (Z25 = AAA 10, BBB 10, CCC 10, DDD 20; LS25 = 12,5), außer DDD in W3
    (kein QB mit Einsatz: CCC hat 2 Spiele); AAA hat in W4 einen QB-Einsatz ohne Gegner (Warnung).
    TE: nur AAA (12 gegen CCC) und BBB (6 gegen DDD) in W1: Z25 CCC 12, DDD 6, LS25 9; AAA und BBB ohne Spiel.
    """
    z25 = {1: 10, 2: 10, 3: 10, 4: 20}
    teams = {}
    for t in FAKE:
        qb = [(z25[prior_nfl[t].opponents[w]], 1) for w in (1, 2, 3)] + [(7, 1) if t == 1 else (None, 0)]
        if t == 4:
            qb[2] = (None, 0)
        te = [({1: 12, 2: 6}.get(t), 1 if t in (1, 2) else 0)] + [(None, 0)] * 3
        empty = {"pts": [None] * 4, "n": [0] * 4}
        teams[str(t)] = {"QB": {"pts": [p for p, _ in qb], "n": [n for _, n in qb]}, "RB": empty, "WR": empty,
                         "TE": {"pts": [p for p, _ in te], "n": [n for _, n in te]}, "K": empty}
    return {"saison": 2025, "quelle": "erfunden", "positionen": {"1": "QB", "2": "RB", "3": "WR", "4": "TE", "5": "K"},
            "wochen": [1, 2, 3, 4], "scoring": scoring or {"3": 0.04, "53": 1.0}, "teams": teams}


class FakeSeason:
    """Attrappe von rawdata.Season mit den Methoden, die matchup.compute_matchup braucht."""

    season = 2026

    def __init__(self, through: int = 3, prior: bool = False, scoring=None):
        self.through = through
        self._nfl = fake_schedule(18, byes={(2, 2, 3), (7, 1, 3)})
        self._prior_nfl = fake_schedule(3) if prior else None
        self._prior = fake_extract(self._prior_nfl, scoring) if prior else None

    def nfl(self):
        return self._nfl

    def prior_nfl(self):
        return self._prior_nfl

    def prior_positions(self):
        return self._prior

    def settings(self):
        return SETTINGS

    def pool(self, week):
        return fake_pool(week) if week <= self.through else None


def run(through: int = 3, **kwargs) -> dict:
    return matchup.compute_matchup(FakeSeason(through, **kwargs), list(range(1, through + 1)))


def pos_of(result: dict, name: str) -> dict[str, dict]:
    return {d["abbrev"]: d["pos"][name] for d in result["defenses"]}


@pytest.fixture(scope="module")
def fake3():
    return run()


def test_attrappe_qb_von_hand(fake3):
    """QB nach W3: Z26 AAA 52/3 (3 Spiele), BBB 23, CCC 14, DDD 12 (2 Spiele: Bye bzw. CCC ohne QB-Einsatz in W3);
    LS26 = 199/12; ohne Vorjahr F = (n·r26 + 10)/(n + 10)."""
    qb = pos_of(fake3, "QB")
    assert [(qb[a]["z26"], qb[a]["n"]) for a in FAKE.values()] == \
        [(Decimal(52) / 3, 3), (Decimal(23), 2), (Decimal(14), 2), (Decimal(12), 2)]
    assert qb["DDD"]["zugelassen"] == [Decimal(14), Decimal(10), None] and qb["BBB"]["zugelassen"][1] is None
    assert abs(fake3["ligaschnitt"]["QB"]["2026"] - Decimal(199) / 12) < TINY and fake3["ligaschnitt"]["QB"]["2025"] is None
    expect = {"AAA": Decimal(2614) / 2587, "BBB": Decimal(2542) / 2388, "CCC": Decimal(2326) / 2388, "DDD": Decimal(2278) / 2388}
    for abbrev, f in expect.items():
        assert abs(qb[abbrev]["f"] - f) < TINY, abbrev
        assert qb[abbrev]["r25"] == ONE and qb[abbrev]["z25"] is qb[abbrev]["n25"] is None
    assert [qb[a]["rang"] for a in FAKE.values()] == [2, 1, 3, 4]
    assert fake3["vorjahr_quelle"] == "ligamittel"


def test_attrappe_trade_summe_und_gleichstand(fake3):
    """RB: der Trade zählt beim Team des Spiels (CCC W1 = 10 + 8), ein Einsatz ohne Punkte als Spiel mit 0 (DDD);
    AAA und BBB ohne RB-Spiel: n = 0, F = 1 – Gleichstand teilt sich den besseren Rang."""
    rb = pos_of(fake3, "RB")
    assert rb["CCC"]["zugelassen"] == [Decimal(18), None, Decimal(7)] and rb["DDD"]["zugelassen"] == [ZERO, None, None]
    assert rb["BBB"]["zugelassen"] == [None] * 3 and rb["BBB"]["n"] == 0 and rb["BBB"]["z26"] is rb["BBB"]["r26"] is None
    assert fake3["ligaschnitt"]["RB"]["2026"] == Decimal("6.25") and rb["CCC"]["r26"] == 2 and rb["DDD"]["r26"] == 0
    assert (rb["CCC"]["f"], rb["AAA"]["f"], rb["BBB"]["f"], rb["DDD"]["f"]) == (Decimal(14) / 12, ONE, ONE, Decimal(10) / 11)
    assert [rb[a]["rang"] for a in FAKE.values()] == [2, 2, 1, 4]


def test_attrappe_position_ohne_spiel(fake3):
    """WR nur mit übersprungenem Einsatz, TE ganz ohne Spieler: kein Ligaschnitt, F = 1 und Rang 1 für alle;
    K mit einem Spiel: r26 = 1. D/ST zählt im Positions-Matchup nicht."""
    for name in ("WR", "TE"):
        assert fake3["ligaschnitt"][name]["2026"] is None
        assert all(p["f"] == ONE and p["rang"] == 1 and p["n"] == 0 for p in pos_of(fake3, name).values())
    k = pos_of(fake3, "K")
    assert k["CCC"]["zugelassen"] == [Decimal(9), None, None] and k["CCC"]["r26"] == ONE
    assert all(p["f"] == ONE for p in k.values())
    assert "D/ST" not in fake3["f"] and set(fake3["f"]) == {"QB", "RB", "WR", "TE", "K"}


def test_attrappe_warnungen(fake3):
    assert fake3["warnungen"] == WARNUNGEN


def test_attrappe_reihe_und_vorwoche(fake3):
    """f_verlauf[w] = Lauf bis Woche w; Vorwoche von W1 ist der Stand vor der Saison (ohne Vorjahr F = 1, Rang 1)."""
    for week in (1, 2, 3):
        now = run(week)
        for name in fake3["positionen"]:
            assert all(pos_of(fake3, name)[a]["f_verlauf"][week - 1] == pos_of(now, name)[a]["f"] for a in FAKE.values())
    w1 = pos_of(run(1), "QB")
    assert all(p["f_vorwoche"] == ONE and p["rang_vorwoche"] == 1 and p["delta"] == p["f"] - 1 for p in w1.values())
    qb = pos_of(fake3, "QB")
    assert all(p["f_vorwoche"] == p["f_verlauf"][1] for p in qb.values())
    assert all(p["ausloeser"] == [] for p in qb.values())  # |ΔF| < 0,10, Rangsprung < 5 (nur vier Teams)


def test_attrappe_mit_vorjahr():
    """Vorjahresauszug: Z25 aus Wochen mit Einsatz (n > 0), Woche ohne Gegner = Warnung; Defense ohne Vorjahresspiel
    der Position: z25 None, r25 = 1."""
    result = run(prior=True)
    assert result["vorjahr_quelle"] == "basis"
    assert result["warnungen"] == ["Vorjahr W4: QB von AAA ohne Gegner laut Spielplan – übersprungen"] + WARNUNGEN
    qb = pos_of(result, "QB")
    assert [(qb[a]["z25"], qb[a]["n25"], qb[a]["r25"]) for a in FAKE.values()] == \
        [(10, 3, Decimal("0.8")), (10, 3, Decimal("0.8")), (10, 2, Decimal("0.8")), (20, 3, Decimal("1.6"))]
    assert result["ligaschnitt"]["QB"]["2025"] == Decimal("12.5")
    assert abs(result["ligaschnitt"]["QB"]["2026"] - Decimal(199) / 12) < TINY  # die Saison hängt nicht am Vorjahr
    # F = (n·r26 + 5·r25 + 5)/(n + 10): AAA (3·208/199 + 4 + 5)/13, DDD (2·144/199 + 8 + 5)/12
    assert abs(qb["AAA"]["f"] - Decimal(2415) / 2587) < TINY and abs(qb["DDD"]["f"] - Decimal(2875) / 2388) < TINY
    te = pos_of(result, "TE")
    assert result["ligaschnitt"]["TE"]["2025"] == 9
    assert [(te[a]["z25"], te[a]["n25"], te[a]["r25"]) for a in FAKE.values()] == \
        [(None, 0, ONE), (None, 0, ONE), (12, 1, Decimal(4) / 3), (6, 1, Decimal(2) / 3)]
    assert abs(te["CCC"]["f"] - Decimal(7) / 6) < TINY  # n = 0: F = (5·4/3 + 5)/10 = 7/6
    rb = pos_of(result, "RB")
    assert result["ligaschnitt"]["RB"]["2025"] is None and all(p["r25"] == ONE and p["z25"] is None for p in rb.values())


def test_attrappe_scoring_warnung():
    """Weicht das Scoring des Auszugs von mSettings ab, warnt das Modul und rechnet weiter."""
    result = run(prior=True, scoring={"3": 0.05, "53": 1.0})
    assert result["warnungen"][1] == "Liga-Scoring geändert – basis/positionen_2025.json löschen, der Wochenabruf holt sie neu"
    assert result["vorjahr_quelle"] == "basis" and pos_of(result, "QB")["DDD"]["r25"] == Decimal("1.6")
    assert not any("Scoring" in w for w in run(prior=True, scoring={"3": 0.040, "53": 1})["warnungen"])


def test_attrappe_wochen_und_bye(fake3):
    assert fake3["wochen"] == {"n1": 4, "naechste3": [4, 5, 6], "rest": list(range(4, 15)), "sos_po": [15, 16, 17]}
    assert [d["bye"] for d in fake3["defenses"]] == [7, 2, 2, None]
    assert fake3["spielplan"][1][4] == 3 and 7 not in fake3["spielplan"][1]
    end = run(14)
    assert end["wochen"] == {"n1": 15, "naechste3": [15, 16, 17], "rest": [], "sos_po": [15, 16, 17]}
    assert run(17)["wochen"]["n1"] is None


def test_attrappe_fehlende_daten():
    with pytest.raises(ef.FetchError, match="Spielerpool"):
        matchup.compute_matchup(FakeSeason(2), [1, 2, 3])
    with pytest.raises(ValueError, match="ohne Lücke"):
        matchup.compute_matchup(FakeSeason(), [1, 3])


# ---------------------------------------------------------------- player_mu

def test_player_mu_aus_lauf(fake3):
    """QB bei AAA nach W3: Gegner W4 CCC, nächste 3 = CCC, DDD, BBB; Rest W4–14 ohne den Bye in W7; SoS W15–17."""
    f, rang = fake3["f"]["QB"], fake3["rang"]["QB"]
    mu = matchup.player_mu(fake3, None, QB, 1)
    assert mu["n1"] == {"week": 4, "opp": "CCC", "f": f[3], "rang": rang[3]}
    assert mu["naechste3"] == statistics.mean([f[3], f[4], f[2]])
    opponents = fake3["spielplan"][1]
    assert mu["rest"] == statistics.mean(f[opponents[w]] for w in range(4, 15) if w != 7)
    assert mu["sos_po"] == statistics.mean([f[2], f[3], f[4]])  # W15 BBB, W16 CCC, W17 DDD


def test_player_mu_bye_und_randfaelle():
    """Hand-Attrappe: Gegner in N+1 hat Bye; ohne Daten, ohne NFL-Team oder für Position 9 None; D/ST aus dst."""
    m = {"spielplan": {1: {5: 2, 6: 3, 15: 2}, 2: {4: 1}}, "defenses": [{"id": 1, "abbrev": "AAA"},
                                                                          {"id": 2, "abbrev": "BBB"}, {"id": 3, "abbrev": "CCC"}],
         "wochen": {"n1": 4, "naechste3": [4, 5, 6], "rest": [4, 5, 6], "sos_po": [15, 16, 17]},
         "f": {n: {1: Decimal("0.9"), 2: Decimal("1.2"), 3: Decimal("0.8")} for n in ("QB", "RB", "WR", "TE", "K")},
         "rang": {n: {1: 2, 2: 1, 3: 3} for n in ("QB", "RB", "WR", "TE", "K")}}
    mu = matchup.player_mu(m, None, WR, 1)
    assert mu == {"n1": {"week": 4, "opp": None, "f": None, "rang": None}, "naechste3": Decimal("1.0"),
                  "rest": Decimal("1.0"), "sos_po": Decimal("1.2")}
    assert matchup.player_mu(m, None, TE, 2)["n1"] == {"week": 4, "opp": "AAA", "f": Decimal("0.9"), "rang": 2}
    assert matchup.player_mu(m, None, K, 2)["naechste3"] == Decimal("0.9") and matchup.player_mu(m, None, K, 2)["sos_po"] is None
    assert matchup.player_mu(None, None, QB, 1) is None
    assert matchup.player_mu(m, None, QB, 0) is None          # ohne NFL-Team
    assert matchup.player_mu(m, None, 9, 1) is None           # Position ohne Faktor
    assert matchup.player_mu(m, None, DST, 1) is None         # D/ST ohne D/ST-Faktoren
    dst_result = {"teams": [{"id": 2, "f": Decimal("1.5"), "rang": 1}, {"id": 3, "f": Decimal("0.5"), "rang": 3},
                            {"id": 1, "f": ONE, "rang": 2}]}
    mu_dst = matchup.player_mu(m, dst_result, DST, 1)
    assert mu_dst["naechste3"] == ONE and mu_dst["sos_po"] == Decimal("1.5") and mu_dst["n1"]["opp"] is None
    assert matchup.player_mu(dict(m, wochen=dict(m["wochen"], n1=None)), None, QB, 2)["n1"] is None


def test_player_mu_dst_gleich_dst_modul():
    """Für eine D/ST entsprechen die Spielplan-Faktoren denen des D/ST-Moduls (dieselben F der Offenses)."""
    m = run()
    nfl = FakeSeason().nfl()
    f = {1: Decimal("1.1"), 2: Decimal("0.9"), 3: ONE, 4: Decimal("1.3")}
    dst_result = {"teams": [{"id": t, "f": f[t], "rang": dst.ranks(f)[t]} for t in FAKE]}
    for t in FAKE:
        mu = matchup.player_mu(m, dst_result, DST, t)
        assert mu["rest"] == dst.schedule_factor(f, nfl[t].opponents, m["wochen"]["rest"])
