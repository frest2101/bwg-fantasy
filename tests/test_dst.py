"""Tests D/ST-Faktoren (scripts/dst.py).

1. Datenkette mit der alten Formel gegen docs/referenz_dst.md (Notion-Board, Stand W2).
2. Off. zugelassen 2026 gegen ESPN positionAgainstOpponent (nur N ≥ 2: die nachgeholte W1-Datei trägt schon den W2-Stand).
3. Neue Formel nach W2 gegen den Befund im Auftrag (docs/auftraege/session4.md, „Befund 29.09.“).
4. Randfälle mit einer Attrappe aus vier erfundenen NFL-Teams AAA–DDD (keine echten Ligadaten).
Aufruf: python -m pytest -q tests/test_dst.py
"""

import json
import statistics
from decimal import Decimal

import pytest

import dst
import espn_fetch as ef
import rawdata
from lineup import DST, QB
from rawdata import NflTeam, PoolRow
from zahlen import ONE, ZERO, dec, rounded

REFERENZ = ef.REPO_DIR / "docs" / "referenz_dst.md"
FILES = ef.season_files(2026)
# Neue Formel nach W2, laut Befund im Auftrag Session 4 (nicht in referenz_dst.md, die nur die alte Formel führt)
NEU_W2 = {"LV": "1.200", "ATL": "1.181", "SF": "0.812", "CAR": "0.994"}
TOL_2, TOL_F, TOL_PLAN = Decimal("0.005"), Decimal("0.001"), Decimal("0.0015")  # Plan: Notion rundete Zwischenwerte
TEAM_KEYS = {"id", "abbrev", "bye", "player_id", "name", "z25", "n25", "z26", "n", "r25", "r26", "f", "f_alt",
             "f_vorwoche", "delta", "rang", "rang_vorwoche", "z_last3", "naechste3",
             "rest", "sos_po", "naechste3_alt", "rest_alt", "naechste", "besitzer", "status", "gegner", "punkte_dst",
             "zugelassen", "f_verlauf"}


def table(heading: str) -> list[list[str]]:
    """Datenzeilen der Markdown-Tabelle unter „## <heading>“ (ohne Kopf und Trennlinie)."""
    for block in REFERENZ.read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        if title.startswith(heading):
            rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                    for line in body.splitlines() if line.startswith("|")]
            return rows[2:]
    raise LookupError(f"Abschnitt „{heading}“ fehlt in {REFERENZ.name}")


def num(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def by_abbrev(result: dict) -> dict[str, dict]:
    return {t["abbrev"]: t for t in result["teams"]}


def real(through: int) -> dict:
    if not (FILES["prior_dst"].exists() and FILES["prior_schedule"].exists()):
        pytest.skip("D/ST-Grundlage 2025 noch nicht abgerufen (holt der Wochenabruf)")
    return dst.compute_dst(rawdata.Season(2026, through), list(range(1, through + 1)))


@pytest.fixture(scope="module")
def w1():
    return real(1)


@pytest.fixture(scope="module")
def w2():
    return real(2)


LIGASCHNITT = dict((r[0], r[1]) for r in table("Ligaschnitt"))


# ---------------------------------------------------------------- 1. Datenkette gegen Notion (alte Formel)

def test_ligaschnitt_2025(w2):
    assert abs(w2["ligaschnitt"]["2025"] - num(LIGASCHNITT["Ligaschnitt 2025"])) <= TOL_2


@pytest.mark.parametrize("week", [1, 2])
def test_ligaschnitt_2026(request, week):
    result = request.getfixturevalue(f"w{week}")
    assert abs(result["ligaschnitt"]["2026"] - num(LIGASCHNITT[f"Ligaschnitt 2026 nach W{week}"])) <= TOL_2


@pytest.mark.parametrize("row", table("Stichprobe"), ids=lambda r: r[0])
def test_stichprobe_alte_formel(w2, row):
    """Z25, Z26 (n = 2), F alt, Restspielplan und nächste 3 mit der alten Formel wie im Notion-Board."""
    offense, z25, z26, f_alt, rest, next3 = row
    t = by_abbrev(w2)[offense]
    assert t["n"] == 2
    assert abs(t["z25"] - num(z25)) <= TOL_2
    assert abs(t["z26"] - num(z26)) <= TOL_2
    assert abs(t["f_alt"] - num(f_alt)) <= TOL_F
    assert abs(t["rest_alt"] - num(rest)) <= TOL_PLAN
    assert abs(t["naechste3_alt"] - num(next3)) <= TOL_PLAN


def test_car_bye_in_naechsten_3(w2):
    """CAR hat in W5 Bye: nächste 3 mittelt nur die Gegner aus W3 und W4."""
    car = by_abbrev(w2)["CAR"]
    assert car["bye"] == 5 and car["naechste"][2] == {"week": 5}
    assert car["naechste3"] == statistics.mean(g["f"] for g in car["naechste"][:2])


# ---------------------------------------------------------------- 2. ESPN positionAgainstOpponent

@pytest.mark.parametrize("through", [2, 3])
def test_z26_gleich_espn(through):
    """ratingsByOpponent[Offense].average aus kona wN = eigenes Z26 nach Woche N oder N−1, 32/32.

    ESPN aktualisiert die Ratings dienstags erst im Lauf des Tages; der Wochenabruf trifft deshalb oft noch den Stand
    der Vorwoche (w03 vom 29.09. 07:30 UTC: Stand W2, 32/32). Das Gesamtfeld „average“ ist nicht der Ligaschnitt.
    """
    if not (ef.week_dir(2026, through) / ef.KONA_FILE).exists():
        pytest.skip(f"Spielerpool W{through} fehlt noch (holt der Wochenabruf)")
    espn = rawdata.Season(2026, through).ratings(through)["positionalRatings"][str(DST)]["ratingsByOpponent"]
    assert len(espn) == ef.NFL_TEAMS

    def matches(week):
        teams = real(week)["teams"]
        return len(teams) == ef.NFL_TEAMS and all(abs(t["z26"] - dec(espn[str(t["id"])]["average"])) <= TOL_F
                                                 for t in teams)
    assert any(matches(week) for week in (through, through - 1) if week >= 1)


# ---------------------------------------------------------------- 3. neue Formel nach W2

@pytest.mark.parametrize("offense", sorted(NEU_W2))
def test_neue_formel_w2(w2, offense):
    assert abs(by_abbrev(w2)[offense]["f"] - Decimal(NEU_W2[offense])) <= TOL_F


# ---------------------------------------------------------------- innere Stimmigkeit mit echten Daten

def test_mittel_r26_ist_eins(w2):
    r26 = [t["r26"] for t in w2["teams"] if t["n"] > 0]
    assert len(r26) == ef.NFL_TEAMS
    assert abs(statistics.mean(r26) - ONE) < Decimal("1e-20")


def test_teamliste(w2):
    teams = w2["teams"]
    assert [t["id"] for t in teams] == sorted(t["id"] for t in teams) and len(teams) == ef.NFL_TEAMS
    assert all(set(t) == TEAM_KEYS for t in teams)  # nur Ligafelder, keine Manager-Daten
    assert sorted(t["rang"] for t in teams) == list(range(1, ef.NFL_TEAMS + 1))
    assert w2["through_week"] == 2 and w2["wochen"] == {"naechste3": [3, 4, 5], "rest": list(range(3, 15)),
                                                        "sos_po": [15, 16, 17]}


def test_spielplan_aus_nfl(w2):
    """Gegner W1–17 aus dem NFL-Spielplan; die einzige Woche ohne Gegner ist ESPNs byeWeek."""
    nfl = rawdata.Season(2026, 2).nfl()
    for t in w2["teams"]:
        assert len(t["gegner"]) == 17 and t["n25"] == 17
        assert [w for w, g in enumerate(t["gegner"], start=1) if g is None] == [nfl[t["id"]].bye] == [t["bye"]]


def test_faktorreihe_ohne_zwischenstand(w1, w2):
    """Die Reihe je Woche ist aus den Rohdaten neu gerechnet: W1-Wert der Reihe = Lauf bis W1."""
    one = {t["id"]: t for t in w1["teams"]}
    assert w2["ligaschnitt_verlauf"] == [w1["ligaschnitt"]["2026"], w2["ligaschnitt"]["2026"]]
    for t in w2["teams"]:
        assert t["f_verlauf"] == [one[t["id"]]["f"], t["f"]]
        assert t["f_vorwoche"] == one[t["id"]]["f"] and t["rang_vorwoche"] == one[t["id"]]["rang"]
        assert t["delta"] == t["f"] - t["f_vorwoche"]


def test_keine_ausloeser(w2):
    """Keine Auslöser-Fähnchen mehr (Beschluss Stephan 30.09.2026): weder je Offense noch als Legende."""
    assert "ausloeser_legende" not in w2
    assert all(not {"ausloeser", "beobachten", "z"} & set(t) for t in w2["teams"])


def test_besitzer(w2):
    for t in w2["teams"]:
        assert t["status"] in ("ONTEAM", "WAIVERS", "FREEAGENT")
        assert (t["besitzer"] is not None) == (t["status"] == "ONTEAM")
        assert t["besitzer"] is None or 1 <= t["besitzer"] <= 10
        assert t["player_id"] < 0 and t["name"].endswith("D/ST")


def test_punkte_und_zugelassen(w2):
    """Σ D/ST-Punkte = Σ zugelassen (jede gespielte D/ST-Woche zählt genau bei einer Offense)."""
    points = [p for t in w2["teams"] for p in t["punkte_dst"] if p is not None]
    allowed = [p for t in w2["teams"] for p in t["zugelassen"] if p is not None]
    assert len(points) == len(allowed) == 64 and sum(points) == sum(allowed)


def test_json_stellen(w2):
    data = rounded(w2, precision=dst.PRECISION)
    json.dumps(data, ensure_ascii=False)
    lv = by_abbrev(data)["LV"]
    assert lv["f"] == 1.2 and lv["f_alt"] == 1.343 and lv["z25"] == 23.71 and data["ligaschnitt"]["2026"] == 15.55


# ---------------------------------------------------------------- 4. Randfälle (reine Funktionen)

def test_faktor_formeln():
    assert dst.factor(2, Decimal(2), ONE) == Decimal(14) / 12              # (2·2 + 5·1 + 5)/(2 + 10)
    assert dst.factor(2, Decimal(2), ONE, new=False) == Decimal(9) / 7     # (2·2 + 5·1)/(2 + 5)


def test_faktor_n0():
    """n = 0: F = (5·r25 + 5)/10, alt F = r25; r26 zählt nicht."""
    assert dst.factor(0, None, Decimal("1.2")) == Decimal("1.1")
    assert dst.factor(0, None, Decimal("1.2"), new=False) == Decimal("1.2")


def test_spielplanfaktor_bye():
    f = {10: Decimal("1.2"), 11: Decimal("0.9"), 12: Decimal(5)}
    assert dst.schedule_factor(f, {3: 10, 4: 11, 6: 12}, [3, 4, 5]) == Decimal("1.05")
    assert dst.schedule_factor(f, {3: 10}, [4, 5]) is None


def test_rang_gleichstand():
    assert dst.ranks({1: Decimal("1.1"), 2: Decimal("1.2"), 3: Decimal("1.1")}) == {1: 2, 2: 1, 3: 2}


def test_stand_vor_der_saison_und_mittel():
    r25 = {1: Decimal("0.8"), 2: Decimal("1.2")}
    before = dst.season_state({1: {1: Decimal(3)}, 2: {1: Decimal(9)}}, 0, r25)
    assert before["n"] == {1: 0, 2: 0} and before["ls26"] is None
    assert before["f"] == {1: Decimal("0.9"), 2: Decimal("1.1")}
    after = dst.season_state({1: {1: Decimal(3)}, 2: {1: Decimal(9)}}, 1, r25)
    assert after["ls26"] == 6 and statistics.mean(after["r26"].values()) == ONE


def test_bye_mit_punkten_ist_fehler():
    nfl = {1: NflTeam(1, "AAA", 2, {1: 2}), 2: NflTeam(2, "BBB", 2, {1: 1})}
    with pytest.raises(ValueError, match="Bye"):
        dst.allowed({1: {2: Decimal(5)}}, nfl)


# ---------------------------------------------------------------- 4. Randfälle (ganzer Lauf mit Attrappe)
# Vier erfundene NFL-Teams; Paarungen reihum nach Woche % 3. AAA und CCC haben in W7 Bye (in den nächsten 3 nach W5).
# Die D/ST gegen DDD spielt nie (210 fehlt): DDD hat n = 0. AAA lässt zuletzt viel zu (Z letzte 3 = 20).

FAKE = {1: "AAA", 2: "BBB", 3: "CCC", 4: "DDD"}
PAIRS = {0: ((1, 2), (3, 4)), 1: ((1, 3), (2, 4)), 2: ((1, 4), (2, 3))}
ALLOWED26 = {1: [2, 2, 20, 20, 20], 2: [10] * 5, 3: [8, 12, 8, 12, 8], 4: [None] * 5}  # je Offense, W1–5, dann reihum
Z25 = {1: 10, 2: 10, 3: 10, 4: 20}                                                       # LS25 = 12,5
OWNERS = {1: (3, "ONTEAM"), 2: (0, "WAIVERS"), 3: (0, "FREEAGENT"), 4: (7, "ONTEAM")}
SETTINGS = {"scheduleSettings": {"matchupPeriodCount": 14,
                                 "matchupPeriods": {str(w): [w] for w in range(1, 18)}}}


def fake_schedule(last_week: int, byes=()) -> dict[int, NflTeam]:
    opponents = {t: {} for t in FAKE}
    for w in range(1, last_week + 1):
        for a, b in PAIRS[w % 3]:
            if (w, a, b) not in byes:
                opponents[a][w], opponents[b][w] = b, a
    return {t: NflTeam(t, FAKE[t], next((w for w in range(1, 18) if w not in opponents[t]), 0), opponents[t])
            for t in FAKE}


def fake_prior(prior_nfl: dict) -> dict:
    """Rohantwort wie basis/kona_dst_<Jahr>.json; dazu Einträge, die nicht zählen dürfen."""
    def stat(season, week, points, played=True, source=0):
        return {"seasonId": season, "scoringPeriodId": week, "statSourceId": source, "statSplitTypeId": 1,
                "appliedTotal": points, "stats": {"210": 1} if played else {}}
    players = []
    for d in FAKE:
        stats = [stat(2025, w, Z25[prior_nfl[d].opponents[w]]) for w in (1, 2, 3)]
        stats += [stat(2025, 4, 0, played=False), stat(2026, 1, 99), stat(2025, 1, 99, source=1)]
        players.append({"id": -16000 - d, "player": {"id": -16000 - d, "defaultPositionId": DST, "proTeamId": d,
                                                     "stats": stats}})
    return {"players": players}


def fake_pool(nfl: dict, week: int) -> list[PoolRow]:
    rows = [PoolRow(1, "QB Attrappe", QB, 1, 3, "ONTEAM", None, None, Decimal(30), None, True)]
    for d in FAKE:
        offense = nfl[d].opponents.get(week)
        points = ALLOWED26[offense][(week - 1) % 5] if offense else None
        on_team, status = OWNERS[d]
        rows.append(PoolRow(-16000 - d, f"{FAKE[d]} D/ST", DST, d, on_team, status, None, None,
                            ZERO if points is None else Decimal(points), None, points is not None))
    return rows


class FakeSeason:
    """Attrappe von rawdata.Season mit den Methoden, die dst.compute_dst braucht."""

    season = 2026

    def __init__(self, through: int = 5, prior: bool = True):
        self.through = through
        self._nfl = fake_schedule(18, byes={(7, 1, 3)})
        self._prior_nfl = fake_schedule(3) if prior else None
        self._prior = fake_prior(self._prior_nfl) if prior else None

    def nfl(self):
        return self._nfl

    def prior_nfl(self):
        return self._prior_nfl

    def prior_dst(self):
        return self._prior

    def settings(self):
        return SETTINGS

    def pool(self, week):
        return fake_pool(self._nfl, week) if week <= self.through else None


@pytest.fixture(scope="module")
def fake5():
    return {t["abbrev"]: t for t in dst.compute_dst(FakeSeason(), [1, 2, 3, 4, 5])["teams"]}


def test_attrappe_vorjahr_und_mittel(fake5):
    """Nur Ist-Wochen des Vorjahrs mit 210 == 1 zählen (sonst Fehler: W4 hat im Vorjahres-Spielplan keinen Gegner)."""
    assert [fake5[a]["r25"] for a in FAKE.values()] == [Decimal("0.8")] * 3 + [Decimal("1.6")]
    assert all(t["n25"] == 3 for t in fake5.values())
    assert abs(statistics.mean(t["r26"] for t in fake5.values() if t["n"]) - ONE) < Decimal("1e-20")


def test_attrappe_n0(fake5):
    """DDD ohne Spiel: F = (5·1,6 + 5)/10 = 1,3, alt F = r25; keine Z26-, r26- und Z-letzte-3-Werte."""
    ddd = fake5["DDD"]
    assert ddd["n"] == 0 and ddd["z26"] is ddd["r26"] is ddd["z_last3"] is None
    assert ddd["f"] == Decimal("1.3") and ddd["f_alt"] == Decimal("1.6")
    assert ddd["zugelassen"] == [None] * 5 and ddd["f_verlauf"] == [Decimal("1.3")] * 5


def test_attrappe_bye_in_naechsten_3(fake5):
    """AAA: Bye in W7, nächste 3 (W6–8) mittelt nur W6 und W8; Rest W6–14 ohne W7."""
    aaa = fake5["AAA"]
    f = {t["id"]: t["f"] for t in fake5.values()}
    assert aaa["bye"] == 7 and aaa["gegner"][6] is None
    assert aaa["naechste"][1] == {"week": 7}
    assert aaa["naechste3"] == statistics.mean([aaa["naechste"][0]["f"], aaa["naechste"][2]["f"]])
    assert aaa["rest"] == statistics.mean(f[g] for g in aaa["gegner"][5:14] if g is not None)
    assert aaa["sos_po"] == statistics.mean(f[g] for g in aaa["gegner"][14:17])


def test_attrappe_faktor_von_hand(fake5):
    """AAA: Z26 = 12,8, LS26 = 10,8, F = (5·12,8/10,8 + 5·0,8 + 5)/15 ≈ 0,99506."""
    aaa = fake5["AAA"]
    assert aaa["z26"] == Decimal("12.8") and aaa["n"] == 5
    assert abs(aaa["f"] - Decimal("0.99506")) < Decimal("0.00001")


def test_attrappe_z_letzte_3(fake5):
    """Nach W5: Z letzte 3 = Ø der letzten drei Spiele (AAA 20 gegen Z26 12,8; CCC 9,33…), DDD ohne Spiel None."""
    assert fake5["AAA"]["z_last3"] == 20 and fake5["BBB"]["z_last3"] == 10
    assert abs(fake5["CCC"]["z_last3"] - Decimal(28) / 3) < Decimal("1e-20") and fake5["DDD"]["z_last3"] is None


def test_attrappe_reihe_und_besitzer(fake5):
    """f_verlauf[w] = Lauf bis Woche w; Besitzer nur bei ONTEAM."""
    for week in range(1, 6):
        run = {t["abbrev"]: t for t in dst.compute_dst(FakeSeason(week), list(range(1, week + 1)))["teams"]}
        assert all(fake5[a]["f_verlauf"][week - 1] == run[a]["f"] for a in FAKE.values())
    assert [(fake5[a]["besitzer"], fake5[a]["status"]) for a in FAKE.values()] == \
        [(3, "ONTEAM"), (None, "WAIVERS"), (None, "FREEAGENT"), (7, "ONTEAM")]


class FakeSeasonBesitzwechsel(FakeSeason):
    """Wie FakeSeason, aber vor der Woche through sind alle D/ST frei: Besitz gilt nur laut pool(N)."""

    def pool(self, week):
        rows = super().pool(week)
        if rows is None or week == self.through:
            return rows
        return [r._replace(on_team=0, status="FREEAGENT") if r.pos == DST else r for r in rows]


def test_attrappe_besitz_aus_woche_n():
    teams = {t["abbrev"]: t for t in dst.compute_dst(FakeSeasonBesitzwechsel(), [1, 2, 3, 4, 5])["teams"]}
    assert [(teams[a]["besitzer"], teams[a]["status"]) for a in FAKE.values()] == \
        [(3, "ONTEAM"), (None, "WAIVERS"), (None, "FREEAGENT"), (7, "ONTEAM")]


def test_attrappe_saisonende():
    """Nach W13 reicht „nächste 3“ in die Playoffs (W14–16); nach W14 gibt es keinen Rest mehr (None)."""
    r13 = dst.compute_dst(FakeSeason(13), list(range(1, 14)))
    assert r13["wochen"] == {"naechste3": [14, 15, 16], "rest": [14], "sos_po": [15, 16, 17]}
    f13 = {t["id"]: t["f"] for t in r13["teams"]}
    for t in r13["teams"]:
        assert t["rest"] == f13[t["gegner"][13]]
    r14 = dst.compute_dst(FakeSeason(14), list(range(1, 15)))
    assert r14["wochen"] == {"naechste3": [15, 16, 17], "rest": [], "sos_po": [15, 16, 17]}
    for t in r14["teams"]:
        assert t["rest"] is None and t["rest_alt"] is None and t["naechste3"] == t["sos_po"]
        assert len(t["f_verlauf"]) == len(t["punkte_dst"]) == len(t["zugelassen"]) == 14 and len(t["gegner"]) == 17


def test_attrappe_fehlende_daten():
    with pytest.raises(ef.FetchError, match="Spielerpool"):
        dst.compute_dst(FakeSeason(2), [1, 2, 3])
    with pytest.raises(ef.FetchError, match="Grundlage"):
        dst.compute_dst(FakeSeason(prior=False), [1, 2])
    with pytest.raises(ValueError, match="ohne Lücke"):
        dst.compute_dst(FakeSeason(), [1, 3])
