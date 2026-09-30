"""Tests Keeper-Bilanz (scripts/keeper.py): Zeitleisten aus Draft und Archiv, Herkunft, Punkte nach Herkunft.

Konstruierte Fälle mit erfundenen Spielern (IDs 1–9, Teams 1–3) und die echten Daten bis W3.
Aufruf: python -m pytest
"""

from decimal import Decimal

import pytest

import compute
import keeper
import rawdata
from lineup import DST, QB, SLOT_BENCH, SLOT_DST, SLOT_IR, SLOT_QB, SLOT_WR, WR
from rawdata import RosterRow

D = Decimal
DRAFT_END = 1000
R2 = lambda v: v.quantize(D("0.01"))  # noqa: E731 – Vergleich auf zwei Stellen wie in der Ausgabe


def pick(no, team, player, keeper_pick=False):
    return {"overallPickNumber": no, "roundId": (no - 1) // 3 + 1, "roundPickNumber": (no - 1) % 3 + 1, "teamId": team,
            "playerId": player, "keeper": keeper_pick}


def move(kind, date, period, *items, status="EXECUTED"):
    """Archiv-Eintrag; items = (ADD|DROP, Spieler, Team)."""
    return {"id": f"{kind}-{date}", "type": kind, "status": status, "scoringPeriodId": period,
            "processDate" if kind == "WAIVER" else "proposedDate": date,
            "items": [{"type": t, "playerId": pid, "fromTeamId": team if t == "DROP" else 0,
                       "toTeamId": team if t == "ADD" else 0} for t, pid, team in items]}


# Erfundener Mini-Draft: Spieler 1 Keeper bei Team 1, Spieler 2 und 3 gedraftet von Team 1 und 2
PICKS = [pick(1, 1, 2), pick(2, 2, 3), pick(4, 1, 1, keeper_pick=True)]
MOVES = [
    move("ROSTER", 500, 0, ("DROP", 9, 1)),                       # Vorsaison: zählt nicht
    move("FREEAGENT", 900, 0, ("ADD", 8, 2)),                     # Vorsaison: zählt nicht
    move("WAIVER", 2000, 1, ("ADD", 4, 1), ("DROP", 2, 1)),       # Claim: Spieler 4 kommt, Draft-Pick 2 geht
    move("FREEAGENT", 3000, 2, ("ADD", 2, 3)),                    # Spieler 2 geht als Free Agent zu Team 3
    move("WAIVER", 3500, 2, ("ADD", 7, 2), status="CANCELED"),    # zurückgezogen: zählt nicht
    move("ROSTER", 4000, 3, ("DROP", 4, 1)),                      # Spieler 4 wieder entlassen
    move("FREEAGENT", 5000, 4, ("ADD", 4, 1)),                    # und von demselben Team zurückgeholt
    {"id": "trade", "type": "TRADE_ACCEPT", "proposedDate": 2500, "scoringPeriodId": 1, "teamId": 2, "items": []},
]


@pytest.fixture(scope="module")
def lines():
    return keeper.timelines(PICKS, MOVES, DRAFT_END)


def test_zeitleisten_konstruiert(lines):
    assert set(lines) == {1, 2, 3, 4}                             # Vorsaison und zurückgezogener Claim fehlen
    assert lines[1] == [{"team": 1, "art": "keeper", "datum": DRAFT_END, "periode": 0, "pick": 4, "ende": None}]
    assert [(s["team"], s["art"], s["periode"], s["ende"], s["pick"]) for s in lines[2]] == [
        (1, "draft", 0, 1, 1), (3, "free_agent", 2, None, None)]
    assert [(s["team"], s["art"], s["datum"], s["periode"], s["ende"]) for s in lines[4]] == [
        (1, "waiver", 2000, 1, 3), (1, "free_agent", 5000, 4, None)]


def test_zugang_ohne_drop_im_archiv_schliesst_den_alten_abschnitt():
    lines = keeper.timelines([pick(1, 1, 5)], [move("FREEAGENT", 2000, 2, ("ADD", 5, 2))], DRAFT_END)
    assert [(s["team"], s["ende"]) for s in lines[5]] == [(1, 2), (2, None)]


def test_ohne_draft_ende_zaehlt_jede_bewegung():
    lines = keeper.timelines([], [move("FREEAGENT", 900, 0, ("ADD", 8, 2))], None)
    assert [(s["team"], s["art"]) for s in lines[8]] == [(2, "free_agent")]


def test_herkunft_je_woche_und_heute(lines):
    art = lambda pid, team, week=None: (keeper.origin(lines.get(pid, []), team, week) or {}).get("art")  # noqa: E731
    assert art(1, 1, 1) == art(1, 1) == "keeper"
    # Draft-Pick 2: in Woche 1 noch bei Team 1 (Abgang in Periode 1 beendet den Abschnitt erst nach der Woche)
    assert art(2, 1, 1) == "draft" and art(2, 1, 2) is None and art(2, 1) is None
    assert art(2, 3, 1) is None and art(2, 3, 2) == "free_agent" and art(2, 3) == "free_agent"
    # Spieler 4: Claim ab Woche 1, entlassen in Periode 3, zurück ab Woche 4 als Free Agent
    assert [art(4, 1, w) for w in (1, 2, 3, 4, 5)] == ["waiver", "waiver", "waiver", "free_agent", "free_agent"]
    assert art(4, 1) == "free_agent"
    # Spieler 3 steht im Archiv bei Team 2; bei Team 3 gibt es keinen Abschnitt – er kam per Trade
    assert art(3, 3, 2) is None and keeper.traded_pick(lines[3])["pick"] == 2
    assert keeper.traded_pick(lines[2]) is None and keeper.traded_pick([]) is None


def test_kader_herkunft(lines):
    picks = {p["overallPickNumber"]: p for p in PICKS}
    roster = {1: 1, 4: 1, 2: 3, 3: 3, 6: 2}                       # Spieler 3 per Trade bei Team 3, Spieler 6 unbekannt
    prior = {1: (D("100"), 10), 2: (D("0"), 0), 3: (None, None)}
    rows, warnings = keeper.roster_origins(roster, lines, picks, {3: (3, 2600)}, prior, DRAFT_END)
    by_id = {r["id"]: r for r in rows}
    assert [(r["team"], r["id"]) for r in rows] == [(1, 1), (1, 4), (2, 6), (3, 2), (3, 3)]
    assert (by_id[1]["art"], by_id[1]["pick"], by_id[1]["runde"], by_id[1]["von"], by_id[1]["seit"]) == ("keeper", 4, 2, 1, None)
    assert (by_id[4]["art"], by_id[4]["pick"], by_id[4]["seit"]) == ("free_agent", None, 5000)
    assert (by_id[2]["art"], by_id[2]["pick"], by_id[2]["seit"]) == ("free_agent", None, 3000)
    # Trade: Datum von ESPN, Pick und abgebendes Team aus dem offenen Draft-Abschnitt
    assert (by_id[3]["art"], by_id[3]["pick"], by_id[3]["von"], by_id[3]["seit"]) == ("trade", 2, 2, 2600)
    # ohne Zugang im Archiv und ohne ESPN-Trade: Trade ohne Datum, aber mit Warnung
    assert (by_id[6]["art"], by_id[6]["seit"], by_id[6]["pick"]) == ("trade", None, None)
    assert len(warnings) == 1 and "Spieler 6" in warnings[0]
    # Vorjahr: Punkte je Spiel, ohne Spiele None; Rookie = Kaderspieler ohne Vorjahres-Eintrag; unbekannt = None
    assert (by_id[1]["vj_pts"], by_id[1]["vj_g"], by_id[1]["vj_avg"], by_id[1]["rookie"]) == (D("100"), 10, D("10"), False)
    assert (by_id[2]["vj_avg"], by_id[2]["rookie"]) == (None, False)
    assert (by_id[3]["vj_pts"], by_id[3]["rookie"]) == (None, True)
    assert (by_id[4]["vj_pts"], by_id[4]["rookie"]) == (None, None)


def test_kader_herkunft_ohne_tagesstand(lines):
    """Ohne trades (Tageslauf lieferte das Feld noch nicht): Trade ohne Datum und ohne Warnung. ESPN schlägt das
    Archiv: Nennt der Tagesstand einen Spieler als Trade, gilt das auch gegen einen offenen Abschnitt."""
    picks = {p["overallPickNumber"]: p for p in PICKS}
    rows, warnings = keeper.roster_origins({3: 3}, lines, picks, None, {}, DRAFT_END)
    assert (rows[0]["art"], rows[0]["seit"], rows[0]["pick"], warnings) == ("trade", None, 2, [])
    rows, warnings = keeper.roster_origins({1: 1}, lines, picks, {1: (1, 7000)}, {}, DRAFT_END)
    assert (rows[0]["art"], rows[0]["seit"], rows[0]["pick"], warnings) == ("trade", 7000, None, [])
    # ein ESPN-Trade zu einem anderen Team als dem heutigen zählt nicht
    rows, _ = keeper.roster_origins({1: 1}, lines, picks, {1: (2, 7000)}, {}, DRAFT_END)
    assert rows[0]["art"] == "keeper"


def test_kader_aelter_als_das_archiv(lines):
    """Kaderstand vor dem Abgang, das Archiv kennt ihn schon (Pool-Abruf gescheitert oder Wochenstand): Es gilt der
    jüngste geschlossene Abschnitt beim Team, nicht „trade“ – und keine Warnung, auch mit ESPN-Trades."""
    picks = {p["overallPickNumber"]: p for p in PICKS}
    assert keeper.last_at(lines[2], 1)["art"] == "draft" and keeper.last_at(lines[2], 2) is None
    rows, warnings = keeper.roster_origins({2: 1, 4: 1}, lines, picks, {}, {}, DRAFT_END)
    by_id = {r["id"]: r for r in rows}
    assert (by_id[2]["art"], by_id[2]["pick"], by_id[2]["seit"]) == ("draft", 1, DRAFT_END)   # im Archiv schon bei Team 3
    assert (by_id[4]["art"], by_id[4]["seit"]) == ("free_agent", 5000) and warnings == []


def test_echte_daten_ohne_tagesstand():
    """Ohne pool/latest.json gilt der Kader des Wochenpools W3 (Stand Dienstag); das Archiv reicht weiter. Wer
    seitdem entlassen wurde, behält seine Herkunft – als Trade bleiben nur die zwei getauschten Spieler."""
    import players
    import records
    ssn = rawdata.Season(2026, 3)
    ssn._memo["pool_latest"] = None
    weeks = [1, 2, 3]
    k = keeper.compute_keeper(ssn, weeks, players.compute_players(ssn, weeks), records.player_names(ssn))
    assert k["stand"] is None and k["warnungen"] == []
    assert sorted(r["id"] for r in k["kader"] if r["art"] == "trade") == [4429059, 4596334]
    assert k["liga"]["kader"]["trade"] == 2 and sum(k["liga"]["kader"].values()) == 245


def test_ohne_abgeschlossenen_draft_keine_bilanz():
    class OhneDraft:
        def draft(self):
            return []

        def draft_end(self):
            return None
    assert keeper.compute_keeper(OhneDraft(), [1], {}, {}) is None


def test_anteile():
    s = keeper.shares({"keeper": D("75"), "draft": D("20"), "zugang": D("5"), "trade": D("0")})
    assert s["summe"] == D("100") and s["anteil"] == {"keeper": D("75"), "draft": D("20"), "zugang": D("5"), "trade": D("0")}
    leer = keeper.shares(dict.fromkeys(keeper.GRUPPEN, D("0")))
    assert leer["summe"] == 0 and set(leer["anteil"].values()) == {None}


class FakeSeason:
    """Nur roster(week): Team 1 mit Keeper 1 (QB), Claim 4 (WR) und D/ST 9 ohne Abschnitt (Trade); Bank und IR zählen nicht."""

    def roster(self, week):
        row = lambda slot, pid, pos, pts: RosterRow(1, slot, pid, pos, "", 0, D(pts), D(0), True, None)  # noqa: E731
        return [row(SLOT_QB, 1, QB, "20"), row(SLOT_WR, 4, WR, "10"), row(SLOT_DST, 9, DST, "5"),
                row(SLOT_BENCH, 2, WR, "99"), row(SLOT_IR, 3, WR, "99")]


def test_punkte_nach_herkunft_konstruiert(lines):
    pf, kern, ertrag = keeper.points_by_origin(FakeSeason(), [1, 2, 3, 4], lines)
    # Spieler 4: Wochen 1–3 Claim, Woche 4 Free Agent – beides „zugang“; die D/ST zählt als Trade und nicht zum Kern
    assert pf[1] == {"keeper": D("80"), "draft": D("0"), "zugang": D("40"), "trade": D("20")}
    assert kern[1] == {"keeper": D("80"), "draft": D("0"), "zugang": D("40"), "trade": D("0")}
    assert ertrag == {4: {"starts": 4, "pf": D("80")}}            # nur der Keeper-Pick hat einen Draft-Abschnitt


# ---------------------------------------------------------------- echte Daten

@pytest.fixture(scope="module")
def result():
    return compute.compute_season(2026, through=3)


def test_echte_daten_summe_gleich_pf(result):
    """Die vier Gruppen summieren sich je Team zur PF (wie der Positions-Breakdown); der Kern ist ein Teil davon."""
    k = result["keeper"]
    pf = {t["team_id"]: t["pf"] for t in result["teams"]}
    assert [t["team_id"] for t in k["teams"]] == sorted(pf) and len(pf) == 10
    for t in k["teams"]:
        assert t["pf"]["summe"] == sum(t["pf"]["pts"].values()) and R2(t["pf"]["summe"]) == R2(pf[t["team_id"]])
        assert D(0) < t["kern"]["summe"] < t["pf"]["summe"]
        assert all(t["kern"]["pts"][g] <= t["pf"]["pts"][g] for g in keeper.GRUPPEN)
        assert abs(sum(t["pf"]["anteil"].values()) - 100) < D("1e-20")
    assert R2(k["liga"]["pf"]["summe"]) == R2(sum(pf.values()))


def test_echte_daten_w3(result):
    """Referenz W1–W3 (Inventur 30.09.2026, zweifach gerechnet): Keeper 75,8 % der Liga-PF, im Kern 88,9 %;
    die zwei getauschten Spieler brachten 5,00 Punkte (Rotzleffe). Wochenwerte ändern sich nicht mehr."""
    liga = result["keeper"]["liga"]
    r1 = lambda v: v.quantize(D("0.1"))  # noqa: E731
    assert R2(liga["pf"]["summe"]) == D("6126.20")
    assert {g: r1(v) for g, v in liga["pf"]["anteil"].items()} == {
        "keeper": D("75.8"), "draft": D("23.3"), "zugang": D("0.9"), "trade": D("0.1")}
    assert R2(liga["pf"]["pts"]["trade"]) == D("5.00") and R2(liga["pf"]["pts"]["keeper"]) == D("4644.55")
    assert r1(liga["kern"]["anteil"]["keeper"]) == D("88.9") and R2(liga["kern"]["summe"]) == D("4934.20")
    teams = {t["team_id"]: t for t in result["keeper"]["teams"]}
    assert r1(teams[1]["pf"]["anteil"]["keeper"]) == D("87.0") and r1(teams[9]["pf"]["anteil"]["keeper"]) == D("60.3")
    assert R2(teams[7]["pf"]["pts"]["trade"]) == D("5.00")


def test_echte_daten_draft(result):
    k = result["keeper"]
    picks = k["picks"]
    assert (k["keeper_zahl"], k["kader_plaetze"], k["through_week"]) == (12, 24, 3)
    assert [p["pick"] for p in picks] == list(range(1, 241))
    assert (k["liga"]["keeper"], k["liga"]["picks"]) == (119, 121)
    teams = {t["team_id"]: t for t in k["teams"]}
    assert {tid: t["keeper"] for tid, t in teams.items()} == {tid: 11 if tid == 6 else 12 for tid in teams}
    assert all(t["keeper"] + t["picks"] == 24 and t["keeper_da"] <= t["keeper"] and t["picks_da"] <= t["picks"]
               for t in teams.values())
    assert all(p["name"] and p["pos"] for p in picks)
    # Pick 1 (W1–W3 jeweils gestartet): Ertrag für das Team = Saisonpunkte des Spielers
    first = picks[0]
    assert (first["team_id"], first["keeper"], first["starts"], R2(first["pf"]), R2(first["pts"])) == (5, False, 3, D("25.30"), D("25.30"))
    # Ertrag je Pick summiert sich zu den Keeper- und Draft-Punkten der Liga
    assert sum(p["pf"] for p in picks if p["keeper"]) == k["liga"]["pf"]["pts"]["keeper"]
    assert sum(p["pf"] for p in picks if not p["keeper"]) == k["liga"]["pf"]["pts"]["draft"]


def test_echte_daten_kader_heute(result):
    """Der Kader heute wechselt täglich – nur Invarianten: jede Art bekannt, Zählungen passen, „da“ heißt im Kader
    des Pick-Teams."""
    k = result["keeper"]
    kader = k["kader"]
    assert kader and {r["art"] for r in kader} <= set(keeper.ARTEN)
    assert [(r["team"], r["id"]) for r in kader] == sorted((r["team"], r["id"]) for r in kader)
    assert sum(k["liga"]["kader"].values()) == len(kader)
    for t in k["teams"]:
        mine = [r for r in kader if r["team"] == t["team_id"]]
        assert t["kader"] == {art: sum(1 for r in mine if r["art"] == art) for art in keeper.ARTEN}
        assert t["kader"]["keeper"] == t["keeper_da"] and t["kader"]["draft"] == t["picks_da"]
    roster = {r["id"]: r for r in kader}
    for p in k["picks"]:
        assert p["team_jetzt"] == (roster[p["player_id"]]["team"] if p["player_id"] in roster else 0)
        if p["da"]:
            assert roster[p["player_id"]]["team"] == p["team_id"] and roster[p["player_id"]]["pick"] == p["pick"]
    for r in kader:
        assert (r["art"] in ("keeper", "draft")) <= (r["pick"] is not None and r["von"] == r["team"])
        assert r["art"] != "keeper" or r["seit"] is None
        assert r["art"] not in ("draft", "waiver", "free_agent") or r["seit"] >= k["draft_datum"]
        assert r["rookie"] is None or r["rookie"] == (r["vj_pts"] is None)


# ---------------------------------------------------------------- Altersprofil (Stufe 2)

def zeile(pid, team, pos, alter, nfl_jahr):
    return {"id": pid, "team": team, "pos": pos, "alter": None if alter is None else D(alter), "nfl_jahr": nfl_jahr}


def test_altersprofil_konstruiert():
    """Erfundene Kader: Team 1 mit QB (30) und WR (22), Team 2 mit QB und WR (je 26), einer D/ST ohne Alter und einem
    Spieler ohne Position (zählt nicht, weil es für ihn keinen Positionsschnitt gibt)."""
    rows = [zeile(1, 1, QB, "30", 8), zeile(2, 1, WR, "22", 1), zeile(3, 2, QB, "26", 4), zeile(4, 2, WR, "26", 2),
            zeile(5, 2, DST, None, None), zeile(6, 2, None, "40", None)]
    pos_age = keeper.position_ages(rows)
    assert pos_age == {QB: {"n": 2, "alter": D("28")}, WR: {"n": 2, "alter": D("24")}}
    weight = {1: D("300"), 2: D("100"), 3: D("100")}                # Spieler 4 ohne Projektion
    t1 = keeper.age_profile(rows[:2], weight, pos_age)
    assert t1 == {"n": 2, "kader": D("26"), "ros": D("28"), "bereinigt": D("0"), "bereinigt_ros": D("1"),
                  "jung": 1, "alt": 1, "rookies": 1, "zweites_jahr": 0}
    t2 = keeper.age_profile(rows[2:], weight, pos_age)
    assert t2 == {"n": 2, "kader": D("26"), "ros": D("26"), "bereinigt": D("0"), "bereinigt_ros": D("-2"),
                  "jung": 0, "alt": 0, "rookies": 0, "zweites_jahr": 1}
    ohne = keeper.age_profile(rows[:2], {}, pos_age)                # ohne Gewichte (kein ROS-Auszug)
    assert (ohne["kader"], ohne["ros"], ohne["bereinigt_ros"]) == (D("26"), None, None)
    assert keeper.age_profile(rows[4:5], weight, pos_age) is None   # nur die D/ST: kein Profil


def test_alter_je_kaderzeile():
    """add_ages: Alter zum Stichtag und NFL-Jahr aus den Stammdaten; die Rookie-Saison ersetzt die Rookie-Näherung."""
    from datetime import date
    kader = [{"id": 1, "rookie": None}, {"id": 2, "rookie": True}, {"id": 3, "rookie": True}, {"id": 4, "rookie": False}]
    stamm = {1: {"geb": date(2005, 1, 19), "rookie": 2026}, 2: {"geb": date(1999, 12, 27), "rookie": 2022},
             3: {"geb": None, "rookie": None}}
    keeper.add_ages(kader, stamm, date(2026, 9, 29), 2026)
    assert [k["nfl_jahr"] for k in kader] == [1, 5, None, None]
    assert [k["rookie"] for k in kader] == [True, False, True, False]   # 3 und 4: ohne Rookie-Saison bleibt die Näherung
    assert R2(kader[0]["alter"]) == D("21.69") and R2(kader[1]["alter"]) == D("26.76")
    assert kader[2]["alter"] is None and kader[3]["alter"] is None


def test_ros_gewichte():
    pool = {1: {"ros": D("100"), "ros_po": D("30")}, 2: {"ros": None, "ros_po": None}}
    assert keeper.ros_weights({"ros_after_week": 3, "players": pool}) == ({1: D("100")}, "ros")
    assert keeper.ros_weights({"ros_after_week": 14, "players": pool}) == ({1: D("30")}, "ros_po")
    assert keeper.ros_weights({"ros_after_week": None, "players": pool}) == ({}, None)
    assert keeper.ros_weights({"ros_after_week": 17, "players": pool}) == ({}, None)


def keeper_mit_stammdaten(stammdaten):
    import players
    import records
    ssn = rawdata.Season(2026, 3)
    ssn._memo["nflverse"] = stammdaten
    weeks = [1, 2, 3]
    return keeper.compute_keeper(ssn, weeks, players.compute_players(ssn, weeks), records.player_names(ssn))


def test_echte_daten_ohne_stammdaten():
    k = keeper_mit_stammdaten(None)
    assert (k["alter_stichtag"], k["alter_gewicht"]) == (None, None)
    assert all(t["altersprofil"] is None for t in k["teams"]) and k["liga"]["altersprofil"] is None
    assert all(r["alter"] is None and r["nfl_jahr"] is None for r in k["kader"])


def test_echte_kader_mit_erfundenen_stammdaten():
    """Die echten Kader mit erfundenen Geburtsdaten (aus der ID abgeleitet): Stichtag ist der Dienstag nach W3, jedes
    Team hat ein Profil, die Teams summieren sich zur Liga, und positionsbereinigt liegt die Liga bei 0."""
    from datetime import date
    alle = keeper_mit_stammdaten(None)["kader"]
    erfunden = {"spieler": {str(r["id"]): {"geb": date(1992 + r["id"] % 12, 1 + r["id"] % 12, 1 + r["id"] % 28).isoformat(),
                                           "rookie": 2015 + r["id"] % 12, "draft": None}
                            for r in alle if r["id"] > 0}}
    k = keeper_mit_stammdaten(erfunden)
    assert (k["alter_stichtag"], k["alter_gewicht"]) == ("2026-09-29", "ros")
    mit = [r for r in k["kader"] if r["alter"] is not None]
    assert len(mit) == sum(1 for r in k["kader"] if r["id"] > 0) and all(r["nfl_jahr"] >= 1 for r in mit)
    assert all(r["alter"] is None for r in k["kader"] if r["id"] < 0)          # D/ST
    liga = k["liga"]["altersprofil"]
    assert liga["n"] == len(mit) == sum(t["altersprofil"]["n"] for t in k["teams"])
    assert abs(liga["bereinigt"]) < D("1e-20") and set(liga["positionen"]) == {1, 2, 3, 4, 5}
    assert sum(p["n"] for p in liga["positionen"].values()) == liga["n"]
    for key in ("jung", "alt", "rookies", "zweites_jahr"):
        assert liga[key] == sum(t["altersprofil"][key] for t in k["teams"])
    for t in k["teams"]:
        p = t["altersprofil"]
        assert set(p) == {"n", "kader", "ros", "bereinigt", "bereinigt_ros", "jung", "alt", "rookies", "zweites_jahr"}
        assert D(18) < p["kader"] < D(40) and D(18) < p["ros"] < D(40)
    assert all(r["rookie"] == (r["nfl_jahr"] == 1) for r in mit)


def test_vorjahr_aus_mroster():
    """Saison-Ist des Vorjahrs je Kaderzeile (rawdata.roster_rows): Punkte und Spiele, None ohne Eintrag."""
    def player(pid, stats):
        return {"playerId": pid, "lineupSlotId": 20, "playerPoolEntry": {"player": {
            "id": pid, "defaultPositionId": 3, "fullName": f"Testspieler {pid}", "stats": stats}}}
    season = lambda year, pts, games: {"seasonId": year, "scoringPeriodId": 0, "statSourceId": 0, "statSplitTypeId": 0,  # noqa: E731
                                       "appliedTotal": pts, "stats": {"210": games}}
    data = {"teams": [{"id": 1, "roster": {"entries": [
        player(1, [season(2025, 123.45, 17.0), season(2026, 30.0, 3.0),
                   {"seasonId": 2025, "scoringPeriodId": 0, "statSourceId": 1, "statSplitTypeId": 0, "appliedTotal": 999.0}]),
        player(2, [season(2025, 0.0, None)]),                     # Vorjahr verletzt: Eintrag ohne Spiele
        player(3, [season(2026, 10.0, 1.0)])]}}]}                 # Rookie: kein Vorjahres-Eintrag
    rows = {r.player_id: r for r in rawdata.roster_rows(data, 2026, 3)}
    assert (rows[1].prior_pts, rows[1].prior_games) == (D("123.45"), 17)
    assert (rows[2].prior_pts, rows[2].prior_games) == (D("0.0"), 0)
    assert (rows[3].prior_pts, rows[3].prior_games) == (None, None)
