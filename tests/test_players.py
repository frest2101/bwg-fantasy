"""Tests Spieler-Kennzahlen (players.py): Stat 210, Wochenreihe, Trend, Sparkline, ROS, Ersatzniveau, Kader-Projektion.

Teil 1 läuft gegen die echten Wochen W1–W2. ROS und Kader-Projektion prüfen erfundene Mini-Daten
(„Testspieler“, NFL-Teams AAA/BBB/CCC mit erfundenen Byes); die echte w03/ros.json wird geprüft, sobald der
Wochenabruf W3 sie geholt hat, vorher übersprungen.
Aufruf: python -m pytest tests/test_players.py
"""

import json
import statistics
from decimal import Decimal

import pytest

import compute
import espn_fetch as ef
import players
import rawdata
from lineup import DST, QB, RB, SLOT_BENCH, SLOT_IR, SLOT_OP, SLOT_QB, SLOT_RB, TE, WR, is_starter
from rawdata import NflTeam, PoolRow, RosterRow
from zahlen import rounded

D = Decimal


# ---------------------------------------------------------------- echte Wochen W1–W2

@pytest.fixture(scope="module")
def ssn2():
    return rawdata.Season(2026, 2)


@pytest.fixture(scope="module")
def real(ssn2):
    return players.compute_players(ssn2, [1, 2])


def test_210_regel_w1(ssn2, real):
    """W1: 665 Ist-Einträge, davon 498 mit stats["210"] == 1; ohne 210 hat kein Eintrag Punkte ≠ 0."""
    pool = ssn2.pool(1)
    assert sum(1 for r in pool if r.actual is not None) == 665
    assert sum(1 for r in pool if r.played) == 498
    assert all(r.actual == 0 for r in pool if r.actual is not None and not r.played)
    assert sum(1 for p in real["players"].values() if p["weeks"][0]["actual"] is not None) == 498


def test_echter_spieler_von_hand(real):
    """Patrick Mahomes (KC, Hugh Jass): W1 Bank 30,18 (Proj. 25,16919111), W2 OP 48,44 (Proj. 29,50070201)."""
    p = real["players"][3139477]
    assert (p["name"], p["pos"], p["nfl"], p["bye_week"], p["team_id"]) == ("Patrick Mahomes", QB, "KC", 5, 2)
    assert [(w["week"], w["actual"], w["projection"], w["bye"], w["team_id"], w["slot"]) for w in p["weeks"]] == [
        (1, D("30.18"), D("25.16919111"), False, 2, SLOT_BENCH), (2, D("48.44"), D("29.50070201"), False, 2, SLOT_OP)]
    assert (p["games"], p["pts"], p["avg"], p["floor"], p["ceiling"]) == (2, D("78.62"), D("39.31"), D("30.18"), D("48.44"))
    assert abs(p["sd"] - D("18.26") / D(2).sqrt()) < D("1e-20")          # zwei Werte: |a − b| / √2
    assert (p["form"], p["form_delta"], p["trend"], p["trend_schwelle"]) == (D("39.31"), 0, None, None)
    assert (p["starts"], p["bench_pts"]) == (1, D("30.18"))
    assert p["proj_delta"] == D("78.62") - D("25.16919111") - D("29.50070201")   # 23,95010688
    assert p["sparkline"] == "▅█"                                                  # 30,18/48,44·7 = 4,36 → Stufe 4


@pytest.fixture(scope="module")
def alle():
    """Alle gerechneten Wochen im Stand des Repos: Saison bis zur jüngsten Woche, Wochen und Spielerwerte."""
    weeks = compute.completed_weeks(2026)
    ssn = rawdata.Season(2026, weeks[-1])
    return ssn, weeks, players.compute_players(ssn, weeks)


def test_summen_gegen_team_wochen(alle):
    """Σ Bank-Punkte und Σ Starter-Punkte aller Spieler (Wochenwerte aus dem Spielerpool) = Werte der Team-Wochen (aus
    mRoster); Σ Starts = Starter-Plätze – in allen gerechneten Wochen. Fängt eine Stat-Korrektur ab, die nur in einer
    der beiden Quellen ankäme (sie gilt für Kader und Spielerpool gemeinsam, Beschluss 06.10.2026)."""
    ssn, weeks, real = alle
    team_weeks = compute.compute_team_weeks(ssn, weeks)
    ps = list(real["players"].values())
    assert sum(p["bench_pts"] for p in ps) == sum(r["bench"] for r in team_weeks)
    starter_points = sum(w["actual"] or 0 for p in ps for w in p["weeks"] if w["slot"] is not None and is_starter(w["slot"]))
    assert starter_points == sum(r["starter_sum"] for r in team_weeks)
    assert sum(p["starts"] for p in ps) == sum(1 for w in weeks for r in ssn.roster(w) if is_starter(r.slot))
    assert sum(p["games"] for p in ps) == sum(1 for w in weeks for r in ssn.pool(w) if r.played)


def test_ligafaktor_nach_w2(ssn2):
    assert abs(players.ligafaktor(compute.compute_team_weeks(ssn2, [1, 2])) - D("0.9767")) < D("0.00005")


def test_ohne_ros_und_export(real, ssn2):
    """Vor W3 gibt es keine ros.json: ROS-Felder None, Ersatz leer, keine Kader-Projektion; Export rundbar."""
    assert real["ros_after_week"] is None and real["ersatz"] == {} and real["wochen_ohne_pool"] == []
    assert all(p[key] is None for p in real["players"].values() for key in players.ROS_KEYS)
    assert players.kader_projection(ssn2, D(1)) is None
    assert list(real["players"]) == sorted(real["players"])
    assert set(real["cv"]) == {QB, RB, WR, TE, players.K, DST}
    json.dumps(rounded(real), ensure_ascii=False)


# ---------------------------------------------------------------- Trend, Sparkline, Kennzahlen (konstruiert)

def test_trend_bis_drei_spiele_kein_pfeil():
    assert players.trend([], WR) == (None, None)
    assert players.trend([D(10), D(10), D(30)], WR) == (None, None)


def test_trend_vier_bis_fuenf_spiele_mit_cv():
    """n = 4: Ø 12,5, Form 14,67, Δ 2,17. QB: max(1; 1,875; 0,45·12,5·√(1/12) = 1,62) = 1,875 → ↑.
    WR: 0,75·12,5·√(1/12) = 2,71 > 2,17 → →. Die Std-Abw. (8,7 → 2,51) zählt unter 6 Spielen nicht."""
    values = [D(6), D(4), D(20), D(20)]
    assert players.trend(values, QB) == ("↑", D("1.875"))
    arrow, threshold = players.trend(values, WR)
    assert arrow == "→"
    assert threshold == D("0.75") * D("12.5") * (D(1) / 3 - D(1) / 4).sqrt()
    # n = 5: Ø 10,8, Form 4,67; Schwelle WR 0,75·10,8·√(1/3 − 1/5) = 2,96 → ↓
    assert players.trend([D(20), D(20), D(4), D(4), D(6)], WR)[0] == "↓"
    assert players.trend([D(0)] * 4, players.K) == ("→", D(1))                     # Mindestschwelle 1 Punkt


def test_trend_ab_sechs_spielen_mit_sd():
    values = [D(2), D(2), D(2), D(10), D(10), D(10)]                               # Ø 6, Form 10
    arrow, threshold = players.trend(values, WR)
    assert arrow == "↑" and threshold == statistics.stdev(values) * (D(1) / 3 - D(1) / 6).sqrt()   # 1,79
    # große Streuung: s·√(1/6) = 13,42·0,41 = 5,48 > Δ 5 → kein Pfeil (mit CV wären es 4,59 und ↑)
    assert players.trend([D(0), D(30), D(0), D(30), D(15), D(15)], WR)[0] == "→"


def test_trend_grenzfaelle():
    """Gleichheit mit der Schwelle gibt keinen Pfeil; n = 5 nimmt noch den Positions-CV; der CV-Anteil rechnet mit |Ø|."""
    assert players.trend([D(0), D(4), D(4), D(4)], players.K) == ("→", D(1))       # Ø 3, Form 4: Δ 1 = Schwelle 1
    # WR n = 5: Ø 14,8, Form 18, Δ 3,2. CV: 0,75·14,8·√(1/3 − 1/5) = 4,05 → →; mit der Std-Abw. wären es 2,22 → ↑
    arrow, threshold = players.trend([D(10), D(10), D(18), D(18), D(18)], WR)
    assert arrow == "→" and threshold == D("0.75") * D("14.8") * (D(1) / 3 - D(1) / 5).sqrt()
    # D/ST mit Ø −10, Form −8,45, Δ 1,55: Schwelle 0,55·10·√(1/12) = 1,59 → →; ohne |Ø| wären es 1,5 → ↑
    arrow, threshold = players.trend([D("-14.65"), D("-8.45"), D("-8.45"), D("-8.45")], DST)
    assert arrow == "→" and threshold == D("0.55") * 10 * (D(1) / 3 - D(1) / 4).sqrt()


def week(nr, actual=None, projection=None, bye=False, slot=None, team_id=None):
    return {"week": nr, "actual": None if actual is None else D(actual),
            "projection": None if projection is None else D(projection), "bye": bye, "team_id": team_id, "slot": slot}


def test_sparkline_bye_negativ_inaktiv():
    series = [week(1, 10), week(2, bye=True), week(3), week(4, "-2"), week(5, 0), week(6, 20)]
    assert players.sparkline(series) == "▅·–▁▁█"                                   # 10/20·7 = 3,5 → Stufe 4
    assert players.sparkline([week(1, -1), week(2, 0)]) == "▁▁"
    assert players.sparkline([week(1), week(2)]) == "––"
    assert players.sparkline([week(1, 5), week(2, 14)]) == "▄█"                    # 5/14·7 = 2,5 → Stufe 3 (half up)


def test_kennzahlen_starts_bank_projektion():
    series = [week(1, 10, 8, slot=SLOT_BENCH), week(2, 20, 15, slot=SLOT_RB), week(3, bye=True, slot=SLOT_BENCH),
              week(4, projection=5, slot=SLOT_IR), week(5, projection=12, slot=SLOT_RB)]  # W5 inaktiv im Starter-Slot
    s = players.player_stats(series, RB)
    assert (s["games"], s["pts"], s["avg"], s["floor"], s["ceiling"]) == (2, 30, 15, 10, 20)
    assert (s["starts"], s["bench_pts"], s["proj_delta"]) == (2, 10, 30 - 23)       # nur gespielte Wochen
    assert (s["form"], s["form_delta"], s["sparkline"]) == (15, 0, "▅█·––")
    none = players.player_stats([week(1)], RB)
    assert (none["games"], none["pts"], none["avg"], none["sd"], none["trend"]) == (0, 0, None, None, None)
    ir = players.player_stats([week(1, 7, 5, slot=SLOT_IR), week(2, 3, 2, slot=SLOT_BENCH)], RB)
    assert (ir["games"], ir["starts"], ir["bench_pts"]) == (2, 0, 3)                # IR ist weder Start noch Bank


# ---------------------------------------------------------------- ROS, Ersatzniveau, Kader-Projektion (erfunden)

def nfl_team(tid, abbrev, bye):
    return NflTeam(tid, abbrev, bye, {w: 99 for w in range(1, 19) if w != bye})


NFL = {1: nfl_team(1, "AAA", 5), 2: nfl_team(2, "BBB", 15), 3: nfl_team(3, "CCC", 4)}

# Testspieler: (pid, Position, NFL-Team, Fantasy-Team, Status, Verletzung, Projektion je Restwoche oder None)
TESTSPIELER = [
    (10, QB, 1, 1, "ONTEAM", "ACTIVE", 20),
    (20, QB, 2, 1, "ONTEAM", "OUT", 15),
    (15, RB, 2, 1, "ONTEAM", "ACTIVE", 9),
    (-1, DST, 3, 1, "ONTEAM", None, 8),            # ESPN projiziert auch in der Bye-Woche W4
    (30, WR, 1, 2, "ONTEAM", "INJURY_RESERVE", 12),
    (11, RB, 2, 0, "WAIVERS", "ACTIVE", 10),
    (12, RB, 2, 0, "FREEAGENT", None, 8),
    (13, RB, 2, 0, "FREEAGENT", "OUT", 12),        # verletzt: zählt nicht fürs Ersatzniveau
    (14, RB, 2, 0, "WAIVERS", "QUESTIONABLE", 6),
    (16, RB, 2, 0, "FREEAGENT", "ACTIVE", 4),      # nur Vierter
    (40, WR, 0, 0, "FREEAGENT", "ACTIVE", 5),      # ohne NFL-Team: kein Restspiel
    (41, WR, 3, 0, "FREEAGENT", "ACTIVE", 7),
    (50, TE, 1, 0, "FREEAGENT", "ACTIVE", None),   # nicht im ROS-Auszug
]


def pool_row(pid, pos, pro, team, status, injury, week_nr):
    actual = D(15 + week_nr) if pid == 10 else None                  # nur QB 10 hat W1–W3 gespielt: 16, 17, 18
    return PoolRow(pid, f"Testspieler {pid}", pos, pro, team, status, injury, 50.0, actual, D(20), actual is not None)


def roster_rows(week_nr):
    return [RosterRow(team, SLOT_QB if pid == 10 else SLOT_BENCH, pid, pos, f"Testspieler {pid}", pro,
                      D(15 + week_nr) if pid == 10 else D(0), D(20), pid == 10, injury)
            for pid, pos, pro, team, _, injury, _ in TESTSPIELER if team]


def ros_extract(after_week=3):
    return {"season": 2026, "after_week": after_week, "weeks": list(range(after_week + 1, 18)),
            "players": {str(pid): {str(w): float(proj) for w in range(after_week + 1, 18)}
                        for pid, *_, proj in TESTSPIELER if proj is not None}}


class FakeSeason:
    """Erfundene Mini-Saison mit pool/roster/ros/nfl wie rawdata.Season."""

    def __init__(self, through=3, ros=None, missing_pool=()):
        self.through, self._ros, self.missing_pool = through, ros, missing_pool

    def pool(self, week_nr):
        if week_nr in self.missing_pool:
            return None
        return [pool_row(pid, pos, pro, team, status, injury, week_nr) for pid, pos, pro, team, status, injury, _ in TESTSPIELER]

    def roster(self, week_nr):
        return roster_rows(week_nr)

    def ros(self):
        return self._ros

    def nfl(self):
        return NFL


@pytest.fixture(scope="module")
def fake():
    return players.compute_players(FakeSeason(ros=ros_extract()), [1, 2, 3])


def test_ros_restspiele_bye_playoffs(fake):
    """Restwochen W4–14; eine Woche ohne Spiel des NFL-Teams zählt 0, auch wenn ESPN projiziert."""
    p = fake["players"]
    assert fake["ros_after_week"] == 3
    #            ROS   Restspiele  ROS/Spiel  ROS PO
    assert [(p[pid]["ros"], p[pid]["restspiele"], p[pid]["ros_pro_spiel"], p[pid]["ros_po"]) for pid in (10, 20, -1, 40)] == [
        (200, 10, 20, 60),       # AAA: Bye W5
        (165, 11, 15, 30),       # BBB: Bye W15 (Playoffs)
        (80, 10, 8, 24),         # CCC: Bye W4, ESPN-Projektion in der Bye-Woche zählt 0
        (0, 0, None, 0),         # ohne NFL-Team
    ]
    assert all(p[50][key] is None for key in players.ROS_KEYS)   # keine ESPN-Projektion
    assert p[40]["sparkline"] == "–––" and p[40]["nfl"] is None  # ohne NFL-Team: nie Bye


def test_ersatzniveau_und_ros_ueber_ersatz(fake):
    """RB: verfügbar 11 (10), 12 (8), 14 (6), 16 (4); 13 ist OUT, 15 im Kader → Ø(10, 8, 6) = 8."""
    assert fake["ersatz"][RB] == 8
    assert fake["ersatz"][WR] == 7            # nur 41 hat ROS/Spiel (40 ohne Restspiel)
    assert fake["ersatz"][QB] is None and fake["ersatz"][TE] is None
    p = fake["players"]
    assert p[15]["ros_ueber_ersatz"] == (9 - 8) * 11
    assert p[16]["ros_ueber_ersatz"] == (4 - 8) * 11
    assert p[30]["ros_ueber_ersatz"] == (12 - 7) * 10
    assert p[10]["ros_ueber_ersatz"] is None   # kein Ersatz-QB


def test_ros_rang(fake):
    p = fake["players"]
    assert [p[pid]["ros_rang"] for pid in (13, 11, 15, 12, 14, 16)] == [1, 2, 3, 4, 5, 6]
    assert (p[10]["ros_rang"], p[20]["ros_rang"], p[40]["ros_rang"]) == (1, 2, None)
    assert players.ros_ranks({1: (RB, D(10)), 2: (RB, D(10)), 3: (RB, D(5)), 4: (WR, None)}) == {1: 1, 2: 1, 3: 3}


def test_kader_projektion():
    """Team 1: QB 20 (Bye W5), QB 15 (OUT: W4 = 0), RB 9, D/ST 8 (Bye W4); Team 2: WR 12 (IR: W4 = 0, Bye W5).
    Team 1: W4 = 20 + 9 + 0 = 29; W5 = 15 + 9 + 8 = 32; W6–14 = 20 + 9 + 8 + QB2 15 im OP = 52. × Ligafaktor 0,9."""
    result = players.kader_projection(FakeSeason(ros=ros_extract()), D("0.9"))
    assert list(result["wochen"]) == [1, 2]
    one = result["wochen"][1]
    assert list(one) == list(range(4, 15))
    assert (one[4], one[5]) == (D("26.1"), D("28.8")) and all(one[w] == D("46.8") for w in range(6, 15))
    assert result["teams"][1] == (D("26.1") + D("28.8") + 9 * D("46.8")) / 11
    assert result["wochen"][2] == {w: (D(0) if w in (4, 5) else D("10.8")) for w in range(4, 15)}
    for tid in (1, 2):
        dev = result["dev"][tid]
        assert abs(sum(dev[w] for w in range(4, 15))) < D("1e-20")          # Ø über die Regular Season
        assert dev[4] == result["wochen"][tid][4] - result["teams"][tid]
        # Playoff-Wochen nur in dev (Endplatz-Simulation), gegen dasselbe Ø; das Ø selbst bleibt bei W4–14
        assert list(dev) == list(range(4, 18))
    fake = FakeSeason(ros=ros_extract())
    rows1 = [r for r in fake.pool(3) if r.on_team == 1]
    w16 = players.team_week_projection(rows1, 16, 4, ros_extract()["players"], NFL) * D("0.9")
    assert result["dev"][1][16] == w16 - result["teams"][1]


def test_kader_projektion_randfaelle():
    assert players.kader_projection(FakeSeason(ros=None), D(1)) is None
    # nach W14 zählen die Playoff-Wochen 15–17 (Schlusstabelle); nach W17 gibt es keinen ROS-Auszug mehr
    late = players.kader_projection(FakeSeason(through=14, ros=ros_extract(after_week=14)), D(1))
    assert late is not None and all(list(w) == [15, 16, 17] for w in late["wochen"].values())
    with pytest.raises(ef.FetchError, match="kein Spielerpool"):
        players.kader_projection(FakeSeason(ros=ros_extract(), missing_pool=(3,)), D(1))


def test_ros_passt_nicht_zur_woche():
    """Der ROS-Auszug muss zur Stand-Woche passen (ssn.through; in den Playoffs die letzte finale Woche, Stufe 4)."""
    with pytest.raises(ef.FetchError, match="passt nicht"):
        players.compute_players(FakeSeason(through=2, ros=ros_extract(after_week=3)), [1, 2])
    # Playoff-Stand: Wochenreihe bis W3, ROS nach der Stand-Woche – hier nach W15 (nur noch W16–17 offen)
    po = players.compute_players(FakeSeason(through=15, ros=ros_extract(after_week=15)), [1, 2, 3])
    assert po["ros_after_week"] == 15 and po["players"][10]["ros"] == 0 and po["players"][10]["ros_po"] > 0


def test_nach_w17_keine_restwoche():
    """Nach W17 legt der Wochenabruf keinen ROS-Auszug mehr ab: ROS nach W17 ohne Werte statt „noch kein Auszug“
    (App: „Nach W17 gibt es keinen Bedarf mehr“)."""
    end = players.compute_players(FakeSeason(through=17, ros=None), [1, 2, 3])
    assert end["ros_after_week"] == 17 and end["ersatz"] == {} and end["ersatz_po"] == {}
    assert all(p[key] is None for p in end["players"].values() for key in players.ROS_KEYS)
    assert players.compute_players(FakeSeason(through=16, ros=None), [1, 2, 3])["ros_after_week"] is None


def test_fehlender_pool_nimmt_kader_werte():
    """Ohne Pool W2 kommen Ist und Projektion der Kaderspieler aus mRoster; Spieler ohne Kader bleiben leer."""
    result = players.compute_players(FakeSeason(missing_pool=(2,)), [1, 2, 3])
    assert result["wochen_ohne_pool"] == [2]
    p = result["players"]
    assert [w["actual"] for w in p[10]["weeks"]] == [16, 17, 18] and p[10]["games"] == 3
    assert p[11]["weeks"][1] == {"week": 2, "actual": None, "projection": None, "bye": False, "team_id": None, "slot": None}


def test_formkurve_mit_bye_aus_nfl_spielplan():
    """D/ST -1 (CCC, Bye W4): die Wochenreihe W1–W5 markiert W4 als Bye."""
    result = players.compute_players(FakeSeason(through=5), [1, 2, 3, 4, 5])
    p = result["players"]
    assert [w["bye"] for w in p[-1]["weeks"]] == [False, False, False, True, False]
    assert p[-1]["sparkline"] == "–––·–"
    assert p[10]["sparkline"] == "▇▇▇██"            # 16…20 auf 0…20: 5,6 · 5,95 · 6,3 · 6,65 · 7


class TradeSeason(FakeSeason):
    """Erfunden: WR 41 spielt W1–W3 als Free Agent für CCC (Bye W4) und steht ab W5 bei AAA (Bye W5) auf der Bank
    von Team 2."""

    def pool(self, week_nr):
        return [r._replace(actual=D(week_nr), played=True) if r.player_id == 41 and week_nr <= 3
                else r._replace(pro_team=1, on_team=2, status="ONTEAM", injury="QUESTIONABLE")
                if r.player_id == 41 and week_nr >= 5 else r
                for r in super().pool(week_nr)]

    def roster(self, week_nr):
        extra = [RosterRow(2, SLOT_BENCH, 41, WR, "Testspieler 41", 1, D(0), D(0), False, None)] if week_nr >= 5 else []
        return super().roster(week_nr) + extra


def test_wechsel_stammdaten_und_bye_je_woche():
    """Stammdaten = Stand der jüngsten Woche; der Bye jeder Woche kommt vom NFL-Team laut Pool dieser Woche."""
    p = players.compute_players(TradeSeason(through=5), [1, 2, 3, 4, 5])["players"][41]
    assert (p["pro_team"], p["nfl"], p["bye_week"], p["team_id"], p["status"], p["injury"]) == \
        (1, "AAA", 5, 2, "ONTEAM", "QUESTIONABLE")
    assert [(w["bye"], w["team_id"], w["slot"]) for w in p["weeks"]] == [
        (False, None, None), (False, None, None), (False, None, None), (True, None, None), (True, 2, SLOT_BENCH)]
    assert (p["games"], p["pts"], p["sparkline"]) == (3, 6, "▃▆█··")   # 1, 2, 3 auf 0…3: 2,33 · 4,67 · 7


def test_ros_aus_espn_auszug():
    """Das Format von espn_fetch.ros_extract (Schlüssel als Text, Werte als Float) liest ros_player direkt."""
    stats = lambda pid: [{"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": w,
                          "appliedTotal": 2.5} for w in range(4, 19)]
    data = {"players": [{"id": pid, "onTeamId": 0, "player": {"id": pid, "defaultPositionId": 16 if pid <= 32 else 2,
                                                                "stats": stats(pid)}} for pid in range(1, 301)]}
    extract = json.loads(ef.ros_extract(data, 2026, after_week=3))
    result = players.ros_player(extract["players"]["1"], 3, NFL, extract["after_week"])
    assert result == {"ros": D("25.0"), "restspiele": 10, "ros_pro_spiel": D("2.5"), "ros_po": D("7.5"),
                      "restspiele_po": 3, "ros_po_pro_spiel": D("2.5")}


# ---------------------------------------------------------------- echte W3-Daten (nach dem Wochenabruf W3)

@pytest.fixture(scope="module")
def ssn3():
    ssn = rawdata.Season(2026, 3)
    if ssn.ros() is None or ssn.pool(3) is None:
        pytest.skip("w03/ros.json oder w03/kona_player_info.json fehlt noch (holt der Wochenabruf W3)")
    return ssn


def test_w03_ros_echt(ssn3):
    result = players.compute_players(ssn3, [1, 2, 3])
    assert result["ros_after_week"] == 3
    ps = [p for p in result["players"].values() if p["restspiele"] is not None]
    assert ps and all(0 <= p["restspiele"] <= 11 for p in ps)
    assert all(p["ros"] == 0 for p in ps if p["restspiele"] == 0)            # ROS = 0 ohne Restspiel
    assert set(result["ersatz"]) == set(players.POSITION_CV)
    free = {p["pos"] for p in ps if p["status"] in players.REPLACEMENT_STATUS and p["injury"] not in players.INJURED
            and p["ros_pro_spiel"] is not None}
    assert {pos for pos, v in result["ersatz"].items() if v is not None} == free   # D/ST: nach W2 alle 32 im Kader
    for pos in players.POSITION_CV:
        assert any(p["ros_rang"] == 1 for p in ps if p["pos"] == pos)
    nfl = ssn3.nfl()
    for p in ps:                                                              # Byes W4–14 kosten ein Restspiel
        if p["pro_team"] in nfl:
            assert p["restspiele"] == sum(1 for w in range(4, 15) if w in nfl[p["pro_team"]].opponents)


def test_w03_kader_projektion_echt(ssn3):
    result = players.kader_projection(ssn3, D("0.98"))
    assert sorted(result["teams"]) == list(range(1, 11))
    for tid, values in result["wochen"].items():
        assert list(values) == list(range(4, 15))
        assert all(v > 0 for v in values.values())
        assert abs(sum(result["dev"][tid][w] for w in values)) < D("1e-18")
        assert list(result["dev"][tid]) == list(range(4, 18))              # dazu W15–17 für die Endplatz-Simulation


# ---------------------------------------------------------------- Bedarf je Team (Waiver-Tab, Session 7)

def test_team_needs_von_hand():
    """Team 1: QB 20/15, RB 9/4, WR 12/7/ohne, TE ohne, ein D/ST 8, K 6; Ersatz QB 18 · RB 8 · WR 7 · TE 5 · K 7.
    Aufstellung: QB 20, RB 9 und 4, WR 12, 7 und 0, TE 0, D/ST 8 und leer, K 6, FLEX leer, OP = QB2 15 (Reste leer).
    Lücken: RB 4 < 8, WR ohne Projektion, TE ohne, zweiter D/ST leer, K 6 < 7, zwei FLEX leer, OP 15 < 18;
    WR 7 = Ersatz ist keine Lücke. Team 2 hat einen tiefen Kader ohne Lücke."""
    from lineup import K
    rosters = {1: [(10, QB), (20, QB), (15, RB), (16, RB), (30, WR), (41, WR), (42, WR), (50, TE), (-1, DST), (60, K)],
               2: [(70, QB), (71, QB), (72, RB), (73, RB), (74, RB), (75, WR), (76, WR), (77, WR), (78, WR),
                   (79, TE), (80, TE), (-2, DST), (-3, DST), (81, K)]}
    per_game = {10: D(20), 20: D(15), 15: D(9), 16: D(4), 30: D(12), 41: D(7), 42: None, 50: None, -1: D(8), 60: D(6),
                70: D(25), 71: D(22), 72: D(10), 73: D(10), 74: D(9), 75: D(9), 76: D(9), 77: D(8), 78: D(8),
                79: D(6), 80: D(6), -2: D(7), -3: D(5), 81: D(9)}
    levels = {QB: D(18), RB: D(8), WR: D(7), TE: D(5), K: D(7), DST: None}
    needs = players.team_needs(rosters, per_game, levels)
    assert list(needs) == [1, 2]
    assert needs[1]["luecken"] == [
        {"slot": "RB", "id": 16, "pos": RB, "ros_g": D(4)}, {"slot": "WR", "id": 42, "pos": WR, "ros_g": None},
        {"slot": "TE", "id": 50, "pos": TE, "ros_g": None}, {"slot": "D/ST", "id": None, "pos": None, "ros_g": None},
        {"slot": "K", "id": 60, "pos": K, "ros_g": D(6)}, {"slot": "FLEX", "id": None, "pos": None, "ros_g": None},
        {"slot": "FLEX", "id": None, "pos": None, "ros_g": None}, {"slot": "OP", "id": 20, "pos": QB, "ros_g": D(15)}]
    assert needs[1]["ueber_ersatz"] == {QB: 1, RB: 1, WR: 1, TE: 0, K: 0, DST: None}
    assert needs[2]["luecken"] == [] and needs[2]["ueber_ersatz"] == {QB: 2, RB: 3, WR: 4, TE: 2, K: 1, DST: None}
    assert players.team_needs({}, per_game, levels) == {}


# ---------------------------------------------------------------- Wochensicht (Waiver-Tab, Beschluss 30.09.2026)

def test_week_value_und_horizont():
    """Wochenwert N+1: Bye und OUT/IR/gesperrt 0 mit Grund, fraglich mit Projektion; Σ N+1…N+3 mit Bye = 0."""
    assert players.week_value(12.5, "ACTIVE", True) == (D("12.5"), None)
    assert players.week_value(12.5, "QUESTIONABLE", True) == (D("12.5"), None)   # fraglich zählt mit Projektion
    assert players.week_value(12.5, "DOUBTFUL", True) == (D("12.5"), None)
    assert players.week_value(12.5, "OUT", True) == (D(0), "OUT")
    assert players.week_value(12.5, "INJURY_RESERVE", True) == (D(0), "INJURY_RESERVE")
    assert players.week_value(12.5, "SUSPENSION", True) == (D(0), "SUSPENSION")
    assert players.week_value(12.5, "OUT", False) == (D(0), "BYE")               # Bye vor Verletzung
    assert players.week_value(None, None, True) == (D(0), None)                  # ohne Projektion 0
    assert players.horizon_weeks(4) == [4, 5, 6] and players.horizon_weeks(16) == [16, 17]   # W18 zählt nicht
    nfl = {1: NflTeam(1, "AAA", 5, {4: 2, 6: 2}), 2: NflTeam(2, "BBB", 5, {4: 1, 6: 1})}
    proj = {"4": 9, "5": 11, "6": 7.5}
    assert players.horizon_sum(D(10), proj, 1, nfl, [4, 5, 6]) == D("17.5")      # W5 Bye (ESPN projiziert trotzdem)
    assert players.horizon_sum(D(10), None, 1, nfl, [4, 5, 6]) is None
    assert players.week_replacement_levels([(QB, D(24)), (QB, D(20)), (QB, D(1)), (QB, D(0)), (RB, D(9))]) \
        == {QB: D(15), RB: D(9), WR: None, TE: None, players.K: None, DST: None}


def test_team_week_needs_von_hand():
    """Team 1: QB 20 und QB2 OUT, RB 9 (fraglich) und RB auf Bye, WR 12/8/7, TE 6, D/ST 5/4, K 8.
    Wochenaufstellung: RB2 = Bye → Lücke; WR 7 = Ersatz 7 keine Lücke; D/ST ohne Ersatzniveau keine Lücke; FLEX
    zweimal und OP leer (QB2 mit 0 verliert gegen leere Reste). Kandidaten je Slot nur mit mehr Wert als die Besetzung.
    Ausfälle aus der ROS-Aufstellung (OP = QB2 mit ROS 18): RB fraglich, RB Bye, OP OUT; Byes N+2…N+3 nach Woche."""
    from lineup import K
    rosters = {1: [(10, QB), (20, QB), (15, RB), (16, RB), (30, WR), (41, WR), (42, WR), (50, TE), (-1, DST), (-2, DST),
                   (60, K)]}
    value = {10: (D(20), None), 20: (D(0), "OUT"), 15: (D(9), None), 16: (D(0), "BYE"), 30: (D(12), None),
             41: (D(7), None), 42: (D(8), None), 50: (D(6), None), -1: (D(5), None), -2: (D(4), None), 60: (D(8), None)}
    injury = {15: "QUESTIONABLE", 20: "OUT"}
    levels = {QB: D(16), RB: D(8), WR: D(7), TE: D(5), K: D(7), DST: None}
    free = [(QB, D(18), 102), (RB, D(11), 100), (WR, D(10), 101), (TE, D(7), 104), (RB, D(5), 103)]
    per_game = {10: D(20), 20: D(18), 15: D(10), 16: D(9), 30: D(12), 41: D(6), 42: D(7), 50: D(5), -1: D(6), -2: D(5),
                60: D(8)}
    needs = players.team_week_needs(rosters, value, injury, levels, free, per_game, {30: [6], 10: [5]})
    assert needs[1]["luecken"] == [
        {"slot": "RB", "id": 16, "pos": RB, "proj": D(0), "grund": "BYE", "kandidaten": [100, 103]},
        {"slot": "FLEX", "id": None, "pos": None, "proj": None, "grund": None, "kandidaten": [100, 101, 104]},
        {"slot": "FLEX", "id": None, "pos": None, "proj": None, "grund": None, "kandidaten": [100, 101, 104]},
        {"slot": "OP", "id": None, "pos": None, "proj": None, "grund": None, "kandidaten": [102, 100, 101]}]
    assert needs[1]["ausfaelle"] == [{"slot": "RB", "id": 15, "pos": RB, "grund": "QUESTIONABLE"},
                                     {"slot": "RB", "id": 16, "pos": RB, "grund": "BYE"},
                                     {"slot": "OP", "id": 20, "pos": QB, "grund": "OUT"}]
    assert needs[1]["byes"] == [{"woche": 5, "slot": "QB", "id": 10, "pos": QB},
                                {"woche": 6, "slot": "WR", "id": 30, "pos": WR}]
    # schwacher Starter: K 6 unter Ersatz 7 → Lücke mit Kandidaten nur über 6; ohne ROS keine Ausfälle und Byes
    weak = players.team_week_needs(rosters, value | {60: (D(6), None)}, injury, levels, free + [(K, D(9), 105), (K, D(6), 106)],
                                   None, {30: [6]})
    assert {"slot": "K", "id": 60, "pos": K, "proj": D(6), "grund": None, "kandidaten": [105]} in weak[1]["luecken"]
    assert weak[1]["ausfaelle"] == [] and weak[1]["byes"] == []


# ---------------------------------------------------------------- Profil je Team (Beschluss 30.09.2026)

def base_roster(t: int, wr=(10, 10, 10), te=8) -> tuple[list, dict]:
    """Erfundener Kader von Team t (IDs t·100 + n): QB 20/15, RB 10/10/5, WR wr + 5/5, TE te, D/ST 6/6, K 8.
    Beste Aufstellung: QB 20 · RB 10, 10 · WR wr · TE · D/ST 6, 6 · K 8 · FLEX 5, 5 · OP = QB2 15."""
    ids = [t * 100 + n for n in range(1, 15)]
    spec = [(QB, 20), (QB, 15), (RB, 10), (RB, 10), (RB, 5), (WR, wr[0]), (WR, wr[1]), (WR, wr[2]), (WR, 5), (WR, 5),
            (TE, te), (DST, 6), (DST, 6), (players.K, 8)]
    return [(pid, pos) for pid, (pos, _) in zip(ids, spec)], {pid: D(v) for pid, (_, v) in zip(ids, spec)}


def test_team_profiles_von_hand():
    """Zehn gleiche Kader, nur Team 1 mit WR 6/6/6 (−12, Ligaschnitt −1,2 → Abstand −10,8, Rang 10 → schwach) und
    Team 2 mit TE 12 (+4, Abstand +3,6, Rang 1 → stark). Die übrigen WR sind Rang 1, aber nur +1,2 über dem Schnitt
    (< 3 Slots × 1 Pkt) → keine Wertung; QB-Gruppe = QB + OP (Superflex)."""
    rosters, value = {}, {}
    for t in range(1, 11):
        roster, vals = base_roster(t, wr=(6, 6, 6) if t == 1 else (10, 10, 10), te=12 if t == 2 else 8)
        rosters[t], value = roster, value | vals
    prof = players.team_profiles(rosters, value)
    assert prof[1]["schwach"] == ["WR"] and prof[1]["stark"] == []
    assert prof[2]["stark"] == ["TE"] and prof[2]["schwach"] == []
    assert all(prof[t]["schwach"] == [] and prof[t]["stark"] == [] for t in range(3, 11))
    wr = prof[1]["gruppen"]["WR"]
    assert (wr["wert"], wr["abstand"], wr["rang"], wr["wertung"]) == (D(18), D("-10.8"), 10, "schwach")
    assert prof[3]["gruppen"]["WR"]["rang"] == 1 and prof[3]["gruppen"]["WR"]["wertung"] is None   # geteilter Rang 1
    qb = prof[5]["gruppen"]["QB"]
    assert qb["wert"] == D(35) and qb["ids"] == [501, 502]            # QB-Slot und OP
    assert prof[5]["gruppen"]["FLEX"]["wert"] == D(10) and prof[5]["gesamt"]["wert"] == D(123)
    assert prof[1]["gesamt"]["rang"] == 10 and prof[2]["gesamt"]["rang"] == 1
    assert sum((g["wert"] for g in prof[7]["gruppen"].values()), D(0)) == prof[7]["gesamt"]["wert"]
    assert players.team_profiles({}, value) == {}


def test_absicherung_und_byes_von_hand():
    """Absicherung: fällt QB 20 aus, rückt QB2 15 auf QB, auf OP ein freier QB 12 (−8) bzw. ohne freien QB der dritte
    Rest 5 (−15); RB/WR −5 (ein Rest 5 rückt nach); TE, K und D/ST ohne Ersatz −8, −8, −6 (Slot leer); eine
    fehlende Position None.
    Byes: WR 10 in W5 spielfrei → WR 5 rückt nach (−5); in W6 hat der FLEX-Spieler RB 5 Bye, der gleich gute WR 5
    springt ein (0, Woche fehlt); in W7 fehlt eine D/ST (−6)."""
    roster, value = base_roster(1)
    loss = players.cover_loss(roster, value, {QB: D(12)})
    assert {pos: v["wert"] for pos, v in loss.items()} == {QB: D(-8), RB: D(-5), WR: D(-5), TE: D(-8), players.K: D(-8),
                                                            DST: D(-6)}
    assert not any(v["frei_gleichwertig"] for v in loss.values())
    assert players.cover_loss(roster, value, {})[QB]["wert"] == D(-15)
    assert players.cover_loss([(p, pos) for p, pos in roster if pos != TE], value, {})[TE] is None
    # freier TE 9 besser als der eigene 8 (bzw. gleich gut): kein Verlust, als gleichwertig gekennzeichnet
    assert players.cover_loss(roster, value, {TE: D(9)})[TE] == {"wert": D(0), "frei_gleichwertig": True}
    assert players.cover_loss(roster, value, {TE: D(8)})[TE] == {"wert": D(0), "frei_gleichwertig": True}
    costs = players.bye_costs(roster, value, {106: {5}, 105: {6}, 112: {7}}, [5, 6, 7])
    assert costs == [{"woche": 5, "kosten": D(-5), "ids": [106]}, {"woche": 7, "kosten": D(-6), "ids": [112]}]


def test_kaderregeln_und_drop():
    """roster_rules aus mSettings; must_drop: voll bei 24 Spielern, wenn niemand im IR-Slot steht (24 Plätze außer
    IR), nicht voll, wenn einer der 24 laut ESPN im IR-Slot steht; der Status allein zählt nicht (Korrektur Stephan:
    OUT darf nicht auf IR); WR am Limit 8."""
    settings = {"rosterSettings": {"lineupSlotCounts": {"0": 1, "2": 2, "4": 3, "6": 1, "7": 1, "16": 2, "17": 1,
                                                        "20": 11, "21": 1, "23": 2},
                                   "positionLimits": {"0": 0, "1": 5, "2": 8, "3": 8, "4": 4, "5": 3, "16": 4, "17": -1}}}
    rules = players.roster_rules(settings)
    assert rules == {"plaetze": 25, "ir": 1, "limits": {QB: 5, RB: 8, WR: 8, TE: 4, players.K: 3, DST: 4}}
    roster = [(i, WR) for i in range(8)] + [(100 + i, RB) for i in range(16)]
    assert players.must_drop(roster, set(), rules) == (True, {WR, RB})   # 16 RB > Limit 8
    assert players.must_drop(roster, {100}, rules) == (False, {WR, RB})  # 100 steht im IR-Slot
    assert players.must_drop(roster, {100, 101}, rules)[0] is False      # zwei gemeldet, ein IR-Slot: zählt einmal
    assert players.must_drop(roster + [(999, TE)], {100, 101}, rules)[0] is True
    assert players.must_drop(roster[:15], set(), rules) == (False, {WR})


def test_team_gains_brutto_netto():
    """Zugewinn = Differenz der besten Aufstellungen. WR 12 für den Grundkader: WR 12/10/10 (+2), WR 10 wandert auf
    FLEX 10/5 (+5) → +7; nicht voll → netto = brutto. K mit Limit 1 über zwei Wochen: K 8 spielt W1, hat W2 Bye;
    der freie K 9 hat W1 Bye → brutto 0 + 9 = 9, netto muss K 8 gehen → −8 + 9 = 1. Werte ≤ 0 zählen nicht."""
    roster, value = base_roster(1)
    gains = players.team_gains({1: roster}, [value], [(900, WR, [D(12)]), (901, WR, [D(4)]), (902, TE, [D(0)])],
                               {1: (False, set())})
    assert gains == {900: {1: {"b": D(7), "n": D(7)}}}
    full = players.team_gains({1: roster}, [value], [(900, WR, [D(12)])], {1: (True, set())})
    assert full[900][1] == {"b": D(7), "n": D(7)}          # ein Bankspieler (WR 5) geht ohne Verlust
    week2 = dict(value) | {114: D(0)}                      # K 8 (ID 114) in W2 spielfrei
    k = players.team_gains({1: roster}, [value, week2], [(903, players.K, [D(0), D(9)])], {1: (False, {players.K})})
    assert k[903][1] == {"b": D(9), "n": D(1)}
