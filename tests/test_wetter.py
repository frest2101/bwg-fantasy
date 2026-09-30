"""Tests Wetter (scripts/wetter.py) und Stadion-Tabelle (data/raw/2026/nfl/stadien.json).

Offline: Open-Meteo wird durch eine Fake-Session ersetzt, der NFL-Spielplan durch eine erfundene Kurzfassung mit vier
Teams und drei Wochen (die Team-IDs sind echt, damit die echte Stadion-Tabelle passt). Die Werte der Fake-Antworten
sind erfunden (Breite + Stunde).
Aufruf: python -m pytest
"""

import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import available_timezones

import pytest

import espn_fetch as ef
import wetter

KC, DET, DEN, CHI = 12, 8, 7, 3          # Arrowhead (offen), Ford Field (fest), Empower Field (offen), Soldier Field (offen)
UTC = timezone.utc
ZONES = available_timezones()            # auf Windows ohne tzdata-Paket leer – dann nur die Schreibweise prüfen


def zone_ok(name: str) -> bool:
    return name in ZONES if ZONES else re.fullmatch(r"[A-Z][A-Za-z_]+(/[A-Z][A-Za-z_]+){1,2}", name) is not None


# ---------------------------------------------------------------- Stadion-Tabelle (echte Datei)

@pytest.fixture(scope="module")
def stadien():
    return ef.load_json(wetter.stadien_path(2026))


@pytest.fixture(scope="module")
def schedule():
    return ef.load_json(ef.season_files(2026)["schedule"])


def test_stadien_alle_32_teams(stadien, schedule):
    teams = {t["id"]: t for t in schedule["settings"]["proTeams"] if t.get("id")}
    assert set(map(int, stadien["stadien"])) == set(teams)
    for team_id, site in stadien["stadien"].items():
        assert site["abbrev"] == teams[int(team_id)]["abbrev"].upper(), team_id
        assert site["dach"] in wetter.DACH and zone_ok(site["zeitzone"]), team_id
        assert -90 <= site["lat"] <= 90 and -180 <= site["lon"] <= 180, team_id
        assert all(k in site for k in wetter.SITE_KEYS), team_id


def test_auslandsspiele_passen_zum_spielplan(stadien, schedule):
    games = {g["id"]: g for g in wetter.season_games(schedule)}
    assert len(stadien["auslandsspiele"]) == 9  # NFL-Liste 2026: Melbourne, Rio, London 3x, Paris, Madrid, München, Mexiko
    for a in stadien["auslandsspiele"]:
        g = games[a["spiel_id"]]
        assert (g["woche"], g["heim"], g["gast"]) == (a["woche"], a["heim"], a["gast"]), a["stadion"]
        assert a["dach"] in wetter.DACH and zone_ok(a["zeitzone"])


def test_load_stadien_prueft_dach(tmp_path, monkeypatch, stadien):
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path)
    bad = json.loads(json.dumps(stadien))
    bad["stadien"]["12"]["dach"] = "halb"
    path = wetter.stadien_path(2026)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ef.FetchError, match="Dach"):
        wetter.load_stadien(2026)


def test_season_games_nur_w1_bis_17(schedule):
    games = wetter.season_games(schedule)
    weeks = {g["woche"] for g in games}
    assert weeks == set(range(1, 18)) and len(games) == 256  # 272 Spiele minus 16 der NFL-W18
    assert games == sorted(games, key=lambda g: (g["woche"], g["kickoff"], g["id"]))
    assert all(g["kickoff"].tzinfo is UTC for g in games)
    assert {g["woche"] for g in games if g["tbd"]} <= {16, 17}  # Flex-Spiele mit offenem Anstoß


def test_game_site_heim_und_ausland(stadien, schedule):
    table = wetter.load_stadien(2026)
    games = {g["id"]: g for g in wetter.season_games(schedule)}
    london = games[401872965]  # W4 IND@WSH, Tottenham Hotspur Stadium
    site = wetter.game_site(london, table)
    assert site["neutral"] and site["stadion"] == "Tottenham Hotspur Stadium" and site["zeitzone"] == "Europe/London"
    home = next(g for g in games.values() if g["heim"] == KC and g["id"] not in table["auslandsspiele"])
    site = wetter.game_site(home, table)
    assert not site["neutral"] and site["stadion"].endswith("Arrowhead Stadium") and site["dach"] == "offen"
    with pytest.raises(ef.FetchError, match="kein Stadion"):
        wetter.game_site({"id": 1, "woche": 1, "heim": 99, "gast": KC}, table)


# ---------------------------------------------------------------- Fake-Open-Meteo und erfundener Spielplan

class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return json.loads(self.text)


class FakeMeteo:
    """Antwortet wie Open-Meteo mit erfundenen Werten (Breite + Stunde); merkt sich jede Anfrage."""

    def __init__(self):
        self.calls: list[dict] = []
        self.broken = False
        self.offset = 0.0  # verschiebt alle Werte, um eine geänderte Prognose zu simulieren

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        if self.broken:
            return FakeResponse(503, {"error": True, "reason": "down"})
        start = datetime.strptime(params["start_hour"], "%Y-%m-%dT%H:%M")
        hourly = {"time": [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(wetter.HOURS)]}
        for var in params["hourly"].split(","):
            hourly[var] = [round(params["latitude"] + i + self.offset, 1) for i in range(wetter.HOURS)]
        return FakeResponse(200, {"hourly": hourly})


def game(game_id, week, home, away, kickoff, tbd=False):
    return {"id": game_id, "scoringPeriodId": week, "homeProTeamId": home, "awayProTeamId": away,
            "date": int(kickoff.timestamp() * 1000), "startTimeTBD": tbd}


GAMES = [
    game(1001, 1, KC, DEN, datetime(2026, 9, 13, 17, 0, tzinfo=UTC)),
    game(1002, 1, DET, CHI, datetime(2026, 9, 13, 20, 25, tzinfo=UTC)),       # Dachspiel (Ford Field, fest)
    game(1003, 2, DEN, KC, datetime(2026, 9, 20, 20, 25, tzinfo=UTC)),
    game(1004, 2, CHI, DET, datetime(2026, 9, 20, 17, 0, tzinfo=UTC)),
    game(1005, 3, DET, DEN, datetime(2026, 9, 27, 8, 1, tzinfo=UTC), tbd=True),  # Anstoß noch offen
    game(1006, 3, KC, CHI, datetime(2026, 9, 29, 0, 20, tzinfo=UTC)),      # MNF: Dienstag 00:20 UTC, gehört zu W3
    game(1007, 4, DEN, KC, datetime(2026, 10, 4, 17, 0, tzinfo=UTC)),          # W4: DET und CHI haben Bye
    game(1099, 18, KC, DEN, datetime(2027, 1, 10, 18, 0, tzinfo=UTC)),           # NFL-W18: zählt nicht
]


def fake_schedule() -> dict:
    """Erfundener Spielplan: jedes Spiel steht wie bei ESPN bei beiden Teams."""
    teams = {tid: {"id": tid, "abbrev": ab, "byeWeek": 0, "proGamesByScoringPeriod": {}}
             for tid, ab in ((KC, "KC"), (DET, "DET"), (DEN, "DEN"), (CHI, "CHI"))}
    for g in GAMES:
        for tid in (g["homeProTeamId"], g["awayProTeamId"]):
            teams[tid]["proGamesByScoringPeriod"].setdefault(str(g["scoringPeriodId"]), []).append(g)
    return {"settings": {"proTeams": list(teams.values())}}


@pytest.fixture
def raw(tmp_path, monkeypatch, stadien):
    """Temp-Rohdaten mit erfundenem Spielplan und der echten Stadion-Tabelle."""
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path)
    nfl = tmp_path / "raw" / "2026" / "nfl"
    nfl.mkdir(parents=True)
    (nfl / "proTeamSchedules_wl.json").write_text(json.dumps(fake_schedule()), encoding="utf-8")
    (nfl / "stadien.json").write_text(json.dumps(stadien), encoding="utf-8")
    return tmp_path / "raw"


def prognose_files():
    return sorted(p.name for p in wetter.prognose_dir(2026).glob("*.json"))


def ist_games():
    path = wetter.ist_path(2026)
    return ef.load_json(path)["spiele"] if path.exists() else []


def test_bye_teams_haben_kein_spiel(raw):
    """W4 des erfundenen Spielplans: nur DEN und KC spielen, DET und CHI (Bye) bekommen keinen Eintrag."""
    games = wetter.season_games(ef.load_json(ef.season_files(2026)["schedule"]))
    w4 = [g for g in games if g["woche"] == 4]
    assert [(g["id"], g["heim"], g["gast"]) for g in w4] == [(1007, DEN, KC)]
    assert wetter.run(FakeMeteo(), 2026, datetime(2026, 9, 29, 7, 0, tzinfo=UTC), "2026-09-29T0700Z") == (0, [])
    prognose = ef.load_json(wetter.prognose_dir(2026) / "w04_2026-09-29T0700Z.json")
    assert {s["id"] for s in prognose["spiele"]} == {1007} and {s["heim"] for s in prognose["spiele"]} == {DEN}


def test_fetch_hours_fenster_und_felder():
    meteo = FakeMeteo()
    kickoff = datetime(2026, 10, 2, 0, 15, tzinfo=UTC)
    hours = wetter.fetch_hours(meteo, 41.5, -81.7, kickoff)
    assert meteo.calls[-1]["start_hour"] == "2026-10-02T00:00" and meteo.calls[-1]["end_hour"] == "2026-10-02T03:00"
    assert hours["zeit"] == ["2026-10-02T00:00Z", "2026-10-02T01:00Z", "2026-10-02T02:00Z", "2026-10-02T03:00Z"]
    assert set(hours) == {"zeit", "temp", "wind", "boeen", "regen_wahrsch", "niederschlag", "schnee"}
    assert hours["temp"] == [41.5, 42.5, 43.5, 44.5]
    ist = wetter.fetch_hours(meteo, 41.5, -81.7, kickoff, forecast=False)
    assert "regen_wahrsch" not in ist and "precipitation_probability" not in meteo.calls[-1]["hourly"]
    meteo.broken = True
    with pytest.raises(ef.FetchError, match="HTTP 503"):
        wetter.fetch_hours(meteo, 41.5, -81.7, kickoff)


def test_prognose_und_ist_ueber_drei_wochen(raw):
    meteo = FakeMeteo()
    # Dienstag W2, 07:00 UTC: Prognose W2, Ist-Wetter der beiden W1-Spiele
    now = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)
    assert wetter.run(meteo, 2026, now, "2026-09-15T0700Z") == (0, [])
    assert prognose_files() == ["w02_2026-09-15T0700Z.json"]
    prognose = ef.load_json(wetter.prognose_dir(2026) / "w02_2026-09-15T0700Z.json")
    assert prognose["woche"] == 2 and [s["id"] for s in prognose["spiele"]] == [1004, 1003]  # nach Anstoß sortiert
    assert all(len(s["stunden"]["temp"]) == 4 for s in prognose["spiele"])
    assert [g["id"] for g in ist_games()] == [1001, 1002]
    dome = next(s for s in ist_games() if s["id"] == 1002)
    assert dome["dach"] == "fest" and "regen_wahrsch" not in dome["stunden"] and dome["abgerufen"] == "2026-09-15T0700Z"
    assert dome["kickoff"] == "2026-09-13T20:25Z" and dome["stunden"]["zeit"][0] == "2026-09-13T20:00Z"

    # eine Stunde später, gleiche Prognose: keine neue Datei, Ist unverändert
    assert wetter.run(meteo, 2026, now + timedelta(hours=1), "2026-09-15T0800Z") == (0, [])
    assert prognose_files() == ["w02_2026-09-15T0700Z.json"] and len(ist_games()) == 2

    # geänderte Prognose: zweite Datei derselben Woche
    meteo.offset = 1.0
    assert wetter.run(meteo, 2026, now + timedelta(hours=2), "2026-09-15T0900Z") == (0, [])
    assert prognose_files() == ["w02_2026-09-15T0700Z.json", "w02_2026-09-15T0900Z.json"]

    # Ist-Wetter nie überschreiben: Eintrag von Hand ändern, erneut laufen lassen
    path = wetter.ist_path(2026)
    data = ef.load_json(path)
    data["spiele"][0]["stunden"]["temp"] = [-99, -99, -99, -99]
    path.write_text(json.dumps(data), encoding="utf-8")
    wetter.run(meteo, 2026, now + timedelta(hours=3), "2026-09-15T1000Z")
    assert ist_games()[0]["stunden"]["temp"] == [-99, -99, -99, -99]

    # Dienstag W3: Vorwoche gelöscht, W3-Prognose (TBD-Spiel ohne Werte), Ist um W2 ergänzt
    now3 = datetime(2026, 9, 22, 7, 0, tzinfo=UTC)
    assert wetter.run(meteo, 2026, now3, "2026-09-22T0700Z") == (0, [])
    assert prognose_files() == ["w03_2026-09-22T0700Z.json"]
    prognose = ef.load_json(wetter.prognose_dir(2026) / "w03_2026-09-22T0700Z.json")
    by_id = {s["id"]: s for s in prognose["spiele"]}
    assert by_id[1005]["stunden"] is None and by_id[1005]["tbd"] and by_id[1006]["stunden"] is not None
    assert [g["id"] for g in ist_games()] == [1001, 1002, 1004, 1003]

    # Montagnacht (MNF läuft, Dienstag 01:00 UTC): die Woche bleibt W3, die Prognose wird nicht gelöscht
    assert wetter.run(meteo, 2026, datetime(2026, 9, 29, 1, 0, tzinfo=UTC), "2026-09-29T0100Z") == (0, [])
    assert prognose_files() == ["w03_2026-09-22T0700Z.json"]
    # das TBD-Spiel kommt nie ins Ist-Archiv, das MNF-Spiel erst vier Stunden nach dem Anstoß
    games = wetter.season_games(fake_schedule())
    assert wetter.ist_due(games, {1001, 1002, 1003, 1004}, datetime(2026, 9, 29, 4, 0, tzinfo=UTC)) == []
    assert [g["id"] for g in wetter.ist_due(games, {1001, 1002, 1003, 1004}, datetime(2026, 9, 29, 4, 20, tzinfo=UTC))] == [1006]
    assert wetter.prognose_week(games, datetime(2026, 9, 29, 4, 20, tzinfo=UTC)) == 4


def test_open_meteo_ausfall_ist_nur_warnung(raw):
    meteo = FakeMeteo()
    now = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)
    wetter.run(meteo, 2026, now, "2026-09-15T0700Z")
    meteo.broken, meteo.offset = True, 1.0
    errors, warnings = wetter.run(meteo, 2026, datetime(2026, 9, 22, 7, 0, tzinfo=UTC), "2026-09-22T0700Z")
    assert errors == 0 and len(warnings) == 2  # Prognose W3 und Ist W2
    # die alte Prognose bleibt stehen, bis eine neue gelingt; das Ist-Archiv wächst nicht
    assert prognose_files() == ["w02_2026-09-15T0700Z.json"] and [g["id"] for g in ist_games()] == [1001, 1002]
    meteo.broken = False
    assert wetter.run(meteo, 2026, datetime(2026, 9, 22, 8, 0, tzinfo=UTC), "2026-09-22T0800Z") == (0, [])
    assert prognose_files() == ["w03_2026-09-22T0800Z.json"] and len(ist_games()) == 4  # nachgeholt, Vorwoche gelöscht


def test_fehlende_stadion_tabelle_ist_fehler(raw):
    wetter.stadien_path(2026).unlink()
    assert wetter.run(FakeMeteo(), 2026, datetime(2026, 9, 15, 7, 0, tzinfo=UTC), "x")[0] == 1


def test_ausserhalb_der_saison_nur_ist(raw):
    meteo = FakeMeteo()
    wetter.run(meteo, 2026, datetime(2026, 9, 29, 7, 0, tzinfo=UTC), "2026-09-29T0700Z")
    assert prognose_files() == ["w04_2026-09-29T0700Z.json"]
    errors, warnings = wetter.run(meteo, 2026, datetime(2027, 1, 20, 7, 0, tzinfo=UTC), "2027-01-20T0700Z")
    assert (errors, warnings) == (0, []) and prognose_files() == []  # nach dem letzten Spiel: Prognosen gelöscht
    assert [g["id"] for g in ist_games()] == [1001, 1002, 1004, 1003, 1006, 1007]  # alle festen Spiele W1–17, nicht W18
    assert wetter.prognose_week(wetter.season_games(fake_schedule()), datetime(2026, 8, 1, tzinfo=UTC)) == 1


# ---------------------------------------------------------------- Verdichtung für die App

def test_aggregate():
    stunden = {"temp": [10.0, 11.0, 12.0, 13.0], "wind": [20.0, 30.0, 20.0, 30.0], "boeen": [40.0, 55.0, 50.0, 45.0],
               "regen_wahrsch": [10, 60, 30, None], "niederschlag": [0.1, 0.2, 0.0, 0.3], "schnee": [0.0, 0.0, 0.0, 0.0]}
    out = wetter.aggregate(stunden)
    assert out == {"temp": Decimal("11.5"), "wind": Decimal("25"), "boeen": Decimal("55"), "regen_wahrsch": Decimal("60"),
                   "niederschlag": Decimal("0.6"), "schnee": Decimal("0")}
    assert wetter.aggregate(None) == dict.fromkeys(wetter.AGG)


def test_compute_wetter():
    site = {"stadion": "S", "ort": "O", "lat": 1, "lon": 2, "dach": "offen", "zeitzone": "UTC", "neutral": False}
    stunden = {"zeit": ["a"] * 4, "temp": [1, 2, 3, 4], "wind": [1, 1, 1, 1], "boeen": [2, 3, 2, 3],
               "regen_wahrsch": [5, 6, 7, 8], "niederschlag": [0, 0, 0, 0.5], "schnee": [0, 0, 0, 0]}
    prognose = {"woche": 4, "stand": "2026-09-29T0645Z", "spiele": [
        dict(site, id=1, woche=4, kickoff="2026-10-02T00:15Z", heim=KC, gast=DEN, stunden=stunden),
        dict(site, id=2, woche=4, kickoff="2026-10-04T08:01Z", tbd=True, heim=DET, gast=CHI, stunden=None)]}
    ist = {"spiele": [dict(site, id=3, woche=3, kickoff="2026-09-27T17:00Z", heim=DEN, gast=KC, abgerufen="2026-09-29T0745Z",
                           stunden={k: v for k, v in stunden.items() if k != "regen_wahrsch"})]}
    out = wetter.compute_wetter(prognose, ist, {KC: "KC", DEN: "DEN", DET: "DET", CHI: "CHI"})
    assert out["stand"] == "2026-09-29T0745Z" and out["woche"] == 4
    first = out["prognose"][0]
    assert (first["heim"], first["gast"], first["temp"], first["boeen"], first["regen_wahrsch"], first["niederschlag"]) \
        == ("KC", "DEN", Decimal("2.5"), Decimal(3), Decimal(8), Decimal("0.5"))
    assert out["prognose"][1]["temp"] is None and out["prognose"][1]["kickoff"] is None and out["prognose"][1]["tbd"]
    assert first["tbd"] is False and out["ist"][0]["tbd"] is False and "regen_wahrsch" not in out["ist"][0]
    assert wetter.compute_wetter(None, None, {}) is None
    assert wetter.compute_wetter(None, {"season": 2026, "spiele": []}, {}) is None
    assert wetter.compute_wetter(None, ist, {})["stand"] == "2026-09-29T0745Z"
    assert out["schwellen"] == {"wind": 25, "boeen": 40, "regen_wahrsch": 60, "schnee": 0}
    assert [s["markierung"] for s in out["prognose"] + out["ist"]] == [[], [], []]  # alles unter der Schwelle, tbd


# ---------------------------------------------------------------- Markierung (Schwellen als Faustregel)

def spiel(**values) -> dict:
    """Verdichtetes Spiel unter freiem Himmel mit erfundenen Werten unter allen Schwellen; values überschreibt."""
    base = {"tbd": False, "dach": "offen", "temp": Decimal(12), "wind": Decimal(10), "boeen": Decimal(20),
            "regen_wahrsch": Decimal(10), "niederschlag": Decimal(0), "schnee": Decimal(0)}
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    return base | {k: Decimal(str(v)) if number(v) else v for k, v in values.items()}


@pytest.mark.parametrize("wind, marked", [(24.4, False), (24.44, False), (24.45, True), (24.5, True), (25, True),
                                          (40, True)])
def test_markierung_wind_wie_angezeigt(wind, marked):
    """Wind ganzzahlig wie in der App (erst eine Stelle wie wetter.json, dann ganze Zahl, je round half up):
    24,4 → 24 nicht markiert, 24,5 → 25 markiert; 24,45 steht als 24,5 in wetter.json und wird als 25 angezeigt."""
    assert wetter.markierung(spiel(wind=wind)) == (["wind"] if marked else [])


def test_markierung_schwellen_und_reihenfolge():
    assert wetter.markierung(spiel(boeen=39.4)) == [] and wetter.markierung(spiel(boeen=39.5)) == ["boeen"]
    assert wetter.markierung(spiel(regen_wahrsch=59)) == [] and wetter.markierung(spiel(regen_wahrsch=60)) == ["regen_wahrsch"]
    assert wetter.markierung(spiel(schnee=0.0)) == [] and wetter.markierung(spiel(schnee=0.04)) == []
    assert wetter.markierung(spiel(schnee=0.05)) == ["schnee"] and wetter.markierung(spiel(schnee=0.1)) == ["schnee"]
    assert wetter.markierung(spiel(schnee=1, regen_wahrsch=80, boeen=55, wind=30)) == ["wind", "boeen", "regen_wahrsch", "schnee"]


def test_markierung_dach_tbd_und_ist():
    """Dachspiele (fest, beweglich) und Spiele mit offenem Anstoß nie; Ist ohne Regenwahrscheinlichkeit, None zählt nicht."""
    storm = {"wind": 30, "boeen": 60, "regen_wahrsch": 90, "schnee": 2}
    assert wetter.markierung(spiel(dach="fest", **storm)) == [] and wetter.markierung(spiel(dach="beweglich", **storm)) == []
    assert wetter.markierung(spiel(tbd=True, **storm)) == []
    ist = {k: v for k, v in spiel(wind=26).items() if k != "regen_wahrsch"}
    assert wetter.markierung(ist) == ["wind"]
    assert wetter.markierung(spiel(wind=None, boeen=None, regen_wahrsch=None, schnee=None)) == []


def test_compute_wetter_markiert_prognose_und_ist():
    site = {"stadion": "S", "ort": "O", "lat": 1, "lon": 2, "zeitzone": "UTC", "neutral": False}
    windig = {"zeit": ["a"] * 4, "temp": [5] * 4, "wind": [24.4, 24.5, 24.5, 24.4], "boeen": [30, 41, 35, 30],
              "regen_wahrsch": [50, 50, 50, 50], "niederschlag": [0, 0, 0, 0], "schnee": [0, 0.1, 0, 0]}
    prognose = {"woche": 4, "stand": "2026-09-29T0645Z", "spiele": [
        dict(site, dach="offen", id=1, woche=4, kickoff="2026-10-02T00:15Z", heim=KC, gast=DEN, stunden=windig),
        dict(site, dach="fest", id=2, woche=4, kickoff="2026-10-04T17:00Z", heim=DET, gast=CHI, stunden=windig)]}
    ist = {"spiele": [dict(site, dach="offen", id=3, woche=3, kickoff="2026-09-27T17:00Z", heim=DEN, gast=KC,
                           abgerufen="2026-09-29T0745Z",
                           stunden={k: v for k, v in windig.items() if k != "regen_wahrsch"})]}
    out = wetter.compute_wetter(prognose, ist, {})
    # Ø Wind 24,45 → angezeigt 25; Böen 41; Schnee 0,1; Dachspiel ohne Markierung
    assert [s["markierung"] for s in out["prognose"]] == [["wind", "boeen", "schnee"], []]
    assert out["ist"][0]["markierung"] == ["wind", "boeen", "schnee"]
