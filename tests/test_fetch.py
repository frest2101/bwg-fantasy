"""Tests Abruf-Logik der Automatisierung (Baustein 3): Wochenkalender, fällige Wochen, Abruf, Transaktions-Archiv.

Alles offline: Wochen sind Temp-Kopien von W1 mit gesetztem Matchup-Status, ESPN wird durch Fakes ersetzt.
Die Archiv-Antworten sind erfundene Testdaten (IDs wie „t1“, „k1“ – keine echten Transaktionen).
Aufruf: python -m pytest
"""

import gzip
import importlib.util
import itertools
import json
import shutil
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

import compute
import espn_fetch as ef
import fantasypros
import nflverse
import rawdata

SOURCE_WEEK = ef.week_dir(2026, 1)  # echte, abgeschlossene Woche als Vorlage (Spielplan enthält alle Perioden 1–14)


@pytest.fixture
def raw(tmp_path, monkeypatch):
    """Leeres Rohdaten-Verzeichnis statt data/raw – der Repo-Stand wächst jede Woche."""
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path)
    return tmp_path / "raw"


def week_views(week: int, final: bool) -> dict[str, dict]:
    """Die vier Views von W1, umgeschrieben auf Woche week; deren Paarungen abgeschlossen oder laufend."""
    views = {view: json.loads((SOURCE_WEEK / f"{view}.json").read_bytes()) for view in ef.VIEWS}
    for data in views.values():
        data["scoringPeriodId"] = week
    for m in views["mMatchupScore"]["schedule"]:
        if m["matchupPeriodId"] == week:
            m["winner"] = "HOME" if final else "UNDECIDED"
    return views


def make_week(week: int, final: bool, views=tuple(ef.VIEWS)) -> None:
    """Legt Woche week im Temp-Verzeichnis an."""
    target = ef.week_dir(2026, week)
    target.mkdir(parents=True)
    for view, data in week_views(week, final).items():
        if view in views:
            (target / f"{view}.json").write_text(json.dumps(data), encoding="utf-8")


def add_playoff_week(week: int, games_final: bool, bye_winner: str | None) -> None:
    """Hängt an den Spielplan einer angelegten Woche eine Playoff-Periode an: ein Spiel und optional ein Bye."""
    path = ef.week_dir(2026, week) / "mMatchupScore.json"
    data = json.loads(path.read_bytes())
    template = next(m for m in data["schedule"] if m["matchupPeriodId"] == 1)
    game = dict(template, id=9001, matchupPeriodId=week, winner="HOME" if games_final else "UNDECIDED")
    data["schedule"].append(game)
    if bye_winner is not None:
        bye = {k: v for k, v in template.items() if k != "away"}
        data["schedule"].append(dict(bye, id=9002, matchupPeriodId=week, winner=bye_winner))
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------- Wochenkalender und fällige Wochen

@pytest.mark.parametrize("day, week", [
    (date(2026, 9, 7), 0),    # Montag vor dem Saisonstart
    (date(2026, 9, 8), 1),    # Di, Beginn W1
    (date(2026, 9, 14), 1),   # Mo, MNF W1
    (date(2026, 9, 15), 2),
    (date(2026, 9, 28), 3),   # Mo, MNF W3
    (date(2026, 9, 29), 4),
    (date(2027, 1, 4), 17),   # Mo, letzter Tag W17
])
def test_calendar_week(day, week):
    assert ef.calendar_week(2026, day) == week


def test_calendar_week_unbekannte_saison():
    with pytest.raises(ef.FetchError, match="Wochenkalender"):
        ef.calendar_week(2031, date(2031, 9, 9))


def test_due_weeks_laufende_woche_und_dienstag(raw):
    make_week(1, final=True)
    make_week(2, final=True)
    make_week(3, final=False)
    assert ef.due_weeks(2026, date(2026, 9, 28)) == []      # Mo: W3 läuft noch, W1–2 final
    assert ef.due_weeks(2026, date(2026, 9, 29)) == [3]     # Di nach dem MNF
    assert ef.due_weeks(2026, date(2026, 10, 6)) == [3, 4]  # Dienstag verpasst: holt nach, W4 fehlt


def test_due_weeks_final_bleibt_unangetastet(raw):
    for week in (1, 2, 3):
        make_week(week, final=True)
    assert ef.due_weeks(2026, date(2026, 9, 29)) == []
    assert ef.due_weeks(2026, date(2026, 9, 30)) == []      # Nachlauf Mi: nichts mehr zu tun


def test_due_weeks_unvollstaendige_woche(raw):
    make_week(1, final=True, views=("mSettings", "mTeam", "mMatchupScore"))  # mRoster fehlt
    assert ef.due_weeks(2026, date(2026, 9, 15)) == [1]


def test_due_weeks_saisongrenzen(raw):
    assert ef.due_weeks(2026, date(2026, 9, 1)) == []                       # vor dem Saisonstart
    assert ef.due_weeks(2026, date(2027, 2, 1)) == list(range(1, 18))       # nach der Saison: höchstens W17


def test_playoff_woche_ohne_paarungen_ist_nicht_final(raw):
    make_week(15, final=True)  # W1-Spielplan hat keine Einträge für Periode 15 (Bracket noch nicht angelegt)
    assert not ef.is_final(2026, 15)


@pytest.mark.parametrize("games_final, bye_winner, final", [
    (True, "UNDECIDED", True),   # Bye ohne Sieger hält die Woche nicht offen
    (True, None, True),
    (False, "HOME", False),      # laufendes Spiel: nicht final, egal was beim Bye steht
])
def test_playoff_woche_mit_bye(raw, games_final, bye_winner, final):
    make_week(15, final=True)
    add_playoff_week(15, games_final, bye_winner)
    assert ef.is_final(2026, 15) is final


def test_saison_vorbei(raw):
    ef.check_season_open(2026, date(2027, 7, 31))
    with pytest.raises(ef.FetchError, match="umstellen"):
        ef.check_season_open(2026, date(2027, 8, 1))
    assert ef.cmd_due(2026, date(2027, 8, 4)) == 1


# ---------------------------------------------------------------- Abruf (Fake-ESPN statt Netz, erfundene Spieler)

class FakeResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code, self.content = status_code, content
        self.text = content.decode("utf-8", errors="replace")


def ok(data) -> FakeResponse:
    return FakeResponse(200, json.dumps(data).encode())


def fake_pool(weeks, with_actual=False, dst_games=None) -> dict:
    """Erfundener Spielerpool: „Testspieler 1…300“, die ersten 32 sind D/ST, der Rest RB.

    weeks: Wochen mit Projektion (und bei with_actual auch Ist). dst_games: Vorjahresspiele je D/ST.
    """
    players = []
    for pid in range(1, 301):
        stats = [{"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": w,
                  "appliedTotal": round(pid / 10 + w, 2)} for w in weeks]
        stats.append({"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 18,
                      "appliedTotal": 99.0})  # NFL-W18 gibt es in Fantasy nicht
        stats.append({"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 0, "scoringPeriodId": 0,
                      "appliedTotal": 500.0})  # Saisonwert: soll nicht in den ROS-Auszug
        if with_actual:
            stats += [{"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 1, "scoringPeriodId": w,
                       "appliedTotal": 10.0, "stats": {"210": 1}} for w in weeks]
        if dst_games is not None and pid <= 32:
            stats += [{"seasonId": 2025, "statSourceId": 0, "statSplitTypeId": 1, "scoringPeriodId": w,
                       "appliedTotal": 8.0, "stats": {"210": 1}} for w in range(1, dst_games(pid) + 1)]
        players.append({"id": pid, "onTeamId": 0, "player": {
            "id": pid, "fullName": f"Testspieler {pid}", "defaultPositionId": 16 if pid <= 32 else 2, "stats": stats}})
    if dst_games is not None:
        players = players[:32]
    return {"players": players, "positionAgainstOpponent": {}}


def only_actual(pool: dict) -> dict:
    """Spielerpool nur mit dem Wochen-Ist (wie die Ist-Abfrage der Stat-Korrekturen: Quelle 0, Split 1)."""
    return dict(pool, players=[dict(e, player=dict(e["player"], stats=[
        s for s in e["player"].get("stats", []) if (s["statSourceId"], s["statSplitTypeId"]) == (0, 1)]))
        for e in pool["players"]])


def stat(week: int, team: int, stats: dict, season: int = 2025, source: int = 0) -> dict:
    """Erfundener Wochen-Eintrag (Vorjahr 2025, Ist) mit dem NFL-Team des Spiels; appliedTotal ist bewusst Unsinn
    (ESPN-Standard, darf nicht zählen)."""
    return {"seasonId": season, "statSourceId": source, "statSplitTypeId": 1, "scoringPeriodId": week,
            "proTeamId": team, "appliedTotal": 99.0, "stats": stats}


def spieler(pid: int, pos: int, stats: list[dict]) -> dict:
    return {"id": pid, "player": {"id": pid, "fullName": f"Testspieler {pid}", "defaultPositionId": pos, "stats": stats}}


def fake_prior_positions(teams: int = 32, qb_games=lambda team: 17) -> dict:
    """Erfundene leaguedefaults-Antwort 2025: je NFL-Team ein QB-„Testspieler“ mit erfundenen Rohstats
    (200 + Team Passing Yards, 1 Passing TD je Spiel), dazu Füllspieler ohne Stats bis zur Mindestgröße des Pools."""
    players = [spieler(100 + team, 1, [stat(w, team, {"210": 1.0, "3": 200.0 + team, "4": 1.0})
                                       for w in range(1, qb_games(team) + 1)])
               for team in range(1, teams + 1)]
    return {"players": players + [spieler(1000 + i, 2, []) for i in range(ef.MIN_POOL)]}


class FakeLeague:
    """Ersetzt requests.Session: beantwortet Liga-Views, Spielerpool, Spielplan und Draft mit erfundenen Daten.

    week_answers[(view, woche)] überschreibt einzelne Antworten; requests merkt sich jede Anfrage als Schlüssel.
    """

    def __init__(self, final_week: int):
        self.final_week = final_week
        self.week_answers = {(view, final_week): ok(data) for view, data in week_views(final_week, final=True).items()}
        self.requests: list[tuple] = []
        self.drafted = True
        self.dst_games = lambda pid: 17
        self.prior_answer = fake_prior_positions   # leaguedefaults-Antwort des Vorjahrs (Positions-Grundlage)
        self.schedule_teams = 33          # inkl. Team 0 (Free Agent)
        self.standings_echo = None        # abweichende Woche im mStandings-Echo
        self.pool_without_week: set[int] = set()  # Wochen, für die der Spielerpool keine Werte liefert
        self.fantasypros_status = 200     # Antwort der FantasyPros-Sitemaps
        self.nflverse_status = 200        # Antwort der nflverse-Spielerliste
        self.ist_status = 200             # Antwort der Ist-Abfrage (Stat-Korrekturen)

    def current_schedule(self) -> dict:
        """Spielplan von heute (mMatchupScore ohne scoringPeriodId): der Vorlage-Spielplan, alle Perioden bis zur
        jüngsten Woche mit Antwort abgeschlossen wie in make_week (Sieger HOME) – also ohne Stat-Korrektur."""
        latest = max(week for view, week in self.week_answers if view == "mMatchupScore")
        data = json.loads((SOURCE_WEEK / "mMatchupScore.json").read_bytes())
        for m in data["schedule"]:
            if m["matchupPeriodId"] <= latest:
                m["winner"] = "HOME"
        return dict(data, scoringPeriodId=latest + 1)

    def ist_answer(self, weeks) -> dict:
        """Wochen-Ist aller erfundenen Spieler, dieselben Werte wie im gespeicherten Spielerpool (ohne Korrektur)."""
        return only_actual(fake_pool(weeks, with_actual=True))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        if url == fantasypros.SITEMAP_URL:  # erfundene Sitemap mit genau der Mindestzahl Spieler
            self.requests.append(("fantasypros", params["position"]))
            slugs = [f"testspieler-{params['position'].lower()}-{i}" for i in range(fantasypros.MIN_PLAYERS[params["position"]])]
            return FakeResponse(self.fantasypros_status, "".join(
                f"<loc>https://www.fantasypros.com/nfl/players/{s}.php</loc>" for s in slugs).encode())
        if url == nflverse.URL:             # erfundene Spielerliste: die 300 Testspieler des Spielerpools
            self.requests.append(("nflverse",))
            rows = ["espn_id,birth_date,rookie_season,draft_year,draft_round,draft_pick,last_season"]
            rows += [f"{pid},2000-01-{pid % 28 + 1:02d},2022,2022,1,{pid},2026" for pid in range(1, 301)]
            return FakeResponse(self.nflverse_status, gzip.compress("\n".join(rows).encode()))
        view, week = params["view"], params.get("scoringPeriodId")
        if view == ef.KONA_VIEW:
            flt = json.loads(headers["X-Fantasy-Filter"])["players"]
            if "filterStatsForSourceIds" in flt:
                assert flt["filterStatsForSplitTypeIds"]["value"] == [1] and "sortPercOwned" in flt
                if "/leaguedefaults/" in url:
                    self.requests.append(("positionen_vorjahr", url))
                    return ok(self.prior_answer())
                assert url == ef.league_url(2026) and flt["filterStatsForSourceIds"]["value"] == [0]
                weeks = flt["filterStatsForCurrentSeasonScoringPeriodId"]["value"]
                self.requests.append(("ist", tuple(weeks)))   # Stat-Korrekturen: Wochen-Ist aller finalen Wochen
                return ok(self.ist_answer(weeks)) if self.ist_status == 200 else FakeResponse(self.ist_status, b"down")
            if "filterStatsForTopScoringPeriodIds" in flt:
                self.requests.append(("dst_vorjahr",))
                return ok(fake_pool([], dst_games=self.dst_games))
            stat_weeks = flt["filterStatsForCurrentSeasonScoringPeriodId"]["value"]
            if "filterRanksForScoringPeriodIds" in flt:
                self.requests.append(("kona", stat_weeks[0]))
                return ok(fake_pool([] if stat_weeks[0] in self.pool_without_week else stat_weeks, with_actual=True))
            self.requests.append(("ros", stat_weeks[0], stat_weeks[-1]))
            return ok(fake_pool(stat_weeks))
        if view == "proTeamSchedules_wl":
            season = int(url.rstrip("/").rsplit("/", 1)[-1])
            self.requests.append(("spielplan", season))
            return ok({"settings": {"proTeams": [{"id": i, "byeWeek": 5 + i % 9} for i in range(self.schedule_teams)]}})
        if view == "mDraftDetail":
            self.requests.append(("draft",))
            return ok({"id": ef.LEAGUE_ID, "seasonId": 2026,
                       "draftDetail": {"drafted": self.drafted, "picks": [{"overallPickNumber": 1}] if self.drafted else []}})
        if view == "mMatchupScore" and week is None:   # Spielplan von heute (Stat-Korrekturen)
            self.requests.append(("spielplan_aktuell",))
            return ok(self.current_schedule())
        if view == "mSettings" and week is None:   # Liga-Scoring für die Positions-Grundlage (echtes W1-mSettings)
            self.requests.append(("scoring",))
            return self.week_answers[("mSettings", self.final_week)]
        self.requests.append((view, week))
        if view == "mStandings":
            return ok({"id": ef.LEAGUE_ID, "seasonId": 2026, "scoringPeriodId": self.standings_echo or week,
                       "teams": [{"id": 1}]})
        return self.week_answers[(view, week)]


@pytest.fixture
def espn_week3(raw, monkeypatch):
    """W1–2 final (nur Kern-Views), W3 lokal noch laufend; ESPN meldet W3 inzwischen abgeschlossen."""
    make_week(1, final=True)
    make_week(2, final=True)
    make_week(3, final=False)
    session = FakeLeague(final_week=3)
    monkeypatch.setattr(ef.requests, "Session", lambda: session)
    monkeypatch.setattr(fantasypros, "PAUSE", 0)
    return session


def snapshot(week: int, names=tuple(f"{view}.json" for view in ef.VIEWS)) -> dict[str, bytes]:
    folder = ef.week_dir(2026, week)
    return {name: (folder / name).read_bytes() for name in names if (folder / name).exists()}


def test_cmd_due_faellige_woche_mit_stand_dateien(espn_week3):
    before = {week: snapshot(week) for week in (1, 2)}
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert ef.is_final(2026, 3)
    core = {week for key in espn_week3.requests if key[0] in ef.VIEWS for week in [key[1]]}
    assert core == {3}                                              # Kern-Views nur für die fällige Woche
    assert {week: snapshot(week) for week in (1, 2)} == before      # finale Wochen byte-gleich
    w3 = ef.week_dir(2026, 3)
    for name in (ef.KONA_FILE, ef.ROS_FILE, ef.STANDINGS_FILE):
        assert (w3 / name).exists(), name
    assert ("ros", 4, 17) in espn_week3.requests


def test_neue_datei_je_woche_ueberschreibt_finale_wochen_nicht(espn_week3):
    """Befund Prüfung 28.09.: früher galt eine Woche mit fehlender neuer Datei als nicht final und wurde neu geholt."""
    ef.cmd_due(2026, date(2026, 9, 29))
    for week in (1, 2):
        assert ef.is_final(2026, week)
        assert (ef.week_dir(2026, week) / ef.KONA_FILE).exists()     # Spielerpool nachgeholt …
        assert not (ef.week_dir(2026, week) / ef.ROS_FILE).exists()  # … ROS/Standings nicht (nur „jetzt“ zu haben)
    assert ("kona", 1) in espn_week3.requests and ("kona", 2) in espn_week3.requests
    espn_week3.requests.clear()
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0   # Nachlauf: Spielplan, FantasyPros, nflverse, Stat-Korrekturen
    assert espn_week3.requests == [("spielplan", 2026)] + [("fantasypros", p) for p in fantasypros.POSITIONS] \
        + [("nflverse",), ("spielplan_aktuell",), ("ist", (1, 2, 3))]
    assert not any((ef.week_dir(2026, week) / ef.STATKORREKTUR_FILE).exists() for week in (1, 2, 3))


def test_cmd_fetch_teilfehler_schreibt_nichts(espn_week3):
    espn_week3.week_answers[("mRoster", 3)] = FakeResponse(503, b"Service Unavailable")
    before = snapshot(3)
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 1
    assert snapshot(3) == before          # auch das neue, finale mMatchupScore nicht
    assert not (ef.week_dir(2026, 3) / ef.KONA_FILE).exists()
    assert not ef.is_final(2026, 3)       # der nächste Lauf holt die Woche erneut


def test_cmd_fetch_falsche_woche_wird_abgelehnt(espn_week3):
    wrong = week_views(3, final=True)["mTeam"]
    wrong["scoringPeriodId"] = 2
    espn_week3.week_answers[("mTeam", 3)] = ok(wrong)
    before = snapshot(3)
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 1
    assert snapshot(3) == before


def test_mteam_wird_als_auszug_gespeichert(espn_week3, capsys):
    """Entscheidung 01.10.2026: tradeBlock, draftStrategy und notificationSettings kommen nicht ins öffentliche Repo;
    Felder, die ESPN neu ergänzt, fallen weg und werden am Lauf gemeldet (nur der Feldname). Alle hier gesetzten
    Werte sind erfunden."""
    answer = week_views(3, final=True)["mTeam"]
    echt = json.loads(json.dumps(answer))   # Stand vor den erfundenen Zusätzen
    answer["erfundenOben"] = {"absicht": "erfundener Testwert"}
    for t in answer["teams"]:
        t["tradeBlock"] = {"players": {"erfundene-id-1": "ON_THE_BLOCK"}}
        t["draftStrategy"] = {"keeperPlayerIds": ["erfundene-id-2"], "futureKeeperPlayerIds": ["erfundene-id-3"]}
        t["erfundenesFeld"] = {"absicht": "erfundener Testwert"}
    for m in answer["members"]:
        m["notificationSettings"] = [{"enabled": True, "id": "erfundene-id-4", "type": "TRADE"}]
        m["erfundeneAdresse"] = "erfunden@example.invalid"
    espn_week3.week_answers[("mTeam", 3)] = ok(answer)
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    raw_bytes = (ef.week_dir(2026, 3) / "mTeam.json").read_bytes()
    saved = json.loads(raw_bytes)
    # Vergleiche als Liste oder Wahrheitswert, damit ein Fehlschlag keinen Dateiinhalt (Manager-Namen) ins öffentliche Log druckt
    gefunden = [n.decode() for n in (b"tradeBlock", b"draftStrategy", b"notificationSettings", b"KeeperPlayerIds",
                                     b"erfunden") if n in raw_bytes]
    assert gefunden == []
    assert set(saved) <= ef.TOP_KEEP
    assert all(set(t) <= ef.TEAM_KEEP for t in saved["teams"])
    assert all(set(m) == ef.MEMBER_KEEP for m in saved["members"])
    # was Rechenwerk (rawdata.teams), Summary und Öffentlichkeits-Check lesen, bleibt wie geliefert
    teams_gleich = saved["teams"] == [{k: v for k, v in t.items() if k in ef.TEAM_KEEP} for t in echt["teams"]]
    members_gleich = saved["members"] == [{k: m[k] for k in ("displayName", "firstName", "id", "lastName")}
                                          for m in echt["members"]]
    rest_gleich = ({k: v for k, v in saved.items() if k not in ("teams", "members")}
                   == {k: v for k, v in echt.items() if k not in ("teams", "members")})
    assert (teams_gleich, members_gleich, rest_gleich) == (True, True, True)
    rechenwerk = ("id", "name", "abbrev", "divisionId", "waiverRank", "transactionCounter", "playoffSeed")
    assert all(k in t for t in saved["teams"] for k in rechenwerk)
    out = capsys.readouterr().out
    assert "unbekannte Felder nicht gespeichert (erfundenOben, members.erfundeneAdresse, teams.erfundenesFeld)" in out
    assert "tradeBlock" not in out and "notificationSettings" not in out  # bekannte Felder fallen still weg


def test_team_extract_ist_stabil_und_prueft_die_form():
    """Ein Auszug bleibt beim erneuten Anwenden byte-gleich (nichts Unbekanntes); ohne Team-Liste gibt es einen Fehler."""
    first, unknown = ef.team_extract(json.loads((SOURCE_WEEK / "mTeam.json").read_bytes()))
    stabil = ef.team_extract(json.loads(first)) == (first, [])   # als Wahrheitswert: kein Dateiinhalt im Log
    assert unknown == [] and stabil
    assert list(json.loads(first)) == list(json.loads((SOURCE_WEEK / "mTeam.json").read_bytes()))  # Reihenfolge von ESPN
    assert ef.team_extract({"id": 1, "teams": []}) == (b'{"id":1,"teams":[]}', [])               # members fehlt: bleibt weg
    for broken in ({}, {"teams": {"1": {}}}, {"teams": [1]}, {"teams": [], "members": "x"}):
        with pytest.raises(ef.FetchError, match="ohne Liste"):
            ef.team_extract(broken)
    with pytest.raises(ef.FetchError, match="UTF-8"):   # erfundener Name mit einzelnem Surrogat
        ef.team_extract({"teams": [{"id": 1, "name": "\ud800"}]})
    # die bekannten Absichts- und Einstellungsfelder stehen in keiner Positivliste
    assert not (ef.TOP_KEEP | ef.TEAM_KEEP | ef.MEMBER_KEEP) & (ef.TEAM_DROP | ef.MEMBER_DROP)
    assert {"tradeBlock", "draftStrategy"} <= ef.TEAM_DROP and "notificationSettings" in ef.MEMBER_DROP


def test_saisondateien(espn_week3):
    files = ef.season_files(2026)
    espn_week3.drafted = False
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert files["schedule"].exists() and files["prior_schedule"].exists() and files["prior_dst"].exists()
    assert files["prior_positions"].exists()
    assert not files["draft"].exists()                               # vor dem Draft: nichts, kein Fehler
    sitemap = ef.load_json(fantasypros.path(2026))["positionen"]
    assert set(sitemap) == set(fantasypros.POSITIONS) and len(sitemap["QB"]) == fantasypros.MIN_PLAYERS["QB"]
    espn_week3.drafted = True
    espn_week3.requests.clear()
    before = files["schedule"].stat().st_mtime_ns
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0
    assert files["draft"].exists()
    assert ("dst_vorjahr",) not in espn_week3.requests               # einmalig
    assert not any(key[0] in ("positionen_vorjahr", "scoring") for key in espn_week3.requests)  # einmalig
    assert files["schedule"].stat().st_mtime_ns == before            # unverändert → nicht neu geschrieben
    assert [r for r in espn_week3.requests if r[0] == "fantasypros"] == [("fantasypros", p) for p in fantasypros.POSITIONS]


def test_fantasypros_ausfall_blockiert_die_woche_nicht(espn_week3, capsys):
    """Nebenteil wie der Spielplan: FantasyPros nicht erreichbar → Warnung, keine Datei, die fällige Woche kommt trotzdem."""
    espn_week3.fantasypros_status = 503
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert not fantasypros.path(2026).exists()
    assert ef.is_final(2026, 3)
    out = capsys.readouterr()
    assert "FantasyPros-Sitemap QB: HTTP 503" in out.err and "Fehler bei Saisondateien" in out.out


def test_nflverse_auszug_und_ausfall(espn_week3, capsys):
    """Stammdaten von nflverse: Der erste Lauf hat noch keinen Spielerpool (kein Abruf), der Nachlauf legt den Auszug
    für die Pool-Spieler an; ein Ausfall warnt nur und lässt den Auszug stehen."""
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert ("nflverse",) not in espn_week3.requests and not nflverse.path(2026).exists()
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0
    saved = nflverse.path(2026).read_bytes()
    data = json.loads(saved)
    assert len(data["spieler"]) == 300 and data["spieler"]["7"] == {"geb": "2000-01-08", "rookie": 2022, "draft": [2022, 1, 7]}
    assert "CC BY 4.0" in data["lizenz"]
    capsys.readouterr()
    espn_week3.nflverse_status = 503
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0 and nflverse.path(2026).read_bytes() == saved
    out = capsys.readouterr()
    assert "nflverse players: HTTP 503" in out.err and "Fehler bei Saisondateien" in out.out


def test_skriptaufruf_fantasypros_ausfall_nur_warnung(espn_week3, monkeypatch, capsys):
    """Wie in der Action (python scripts/espn_fetch.py): Das Skript ist ein zweites espn_fetch-Modul neben dem, das fantasypros
    importiert, mit eigener FetchError-Klasse. Ein FantasyPros-Ausfall darf trotzdem nur warnen (Befund Gegenprüfung
    30.09.2026: vorher Abbruch mit Traceback, und die fällige Woche wurde nicht geholt)."""
    spec = importlib.util.spec_from_file_location("espn_fetch_als_skript", ef.__file__)
    skript = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skript)
    monkeypatch.setattr(skript, "RAW_DIR", ef.RAW_DIR)
    monkeypatch.setattr(skript, "REPO_DIR", ef.REPO_DIR)
    assert skript.FetchError is not ef.FetchError
    espn_week3.fantasypros_status = 503
    assert skript.cmd_due(2026, date(2026, 9, 29)) == 0
    assert skript.is_final(2026, 3) and not fantasypros.path(2026).exists()
    assert "FantasyPros-Sitemap QB: HTTP 503" in capsys.readouterr().err


def test_dst_vorjahr_braucht_alle_17_spiele(espn_week3, capsys):
    """Nebenteil: nicht speichern, warnen – aber die fällige Woche wird trotzdem geschrieben (Lauf grün)."""
    espn_week3.dst_games = lambda pid: 16 if pid == 7 else 17
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert not ef.season_files(2026)["prior_dst"].exists()
    assert ef.is_final(2026, 3)
    assert "Fehler bei Saisondateien oder beim Nachholen" in capsys.readouterr().out  # Präfix je nach Umgebung


def test_positionen_vorjahr_einmalig(espn_week3):
    """basis/positionen_2025.json: Scoring aus mSettings der laufenden Saison, Antwort von leaguedefaults 2025,
    gespeichert wird nur der Auszug; der nächste Lauf fragt nicht erneut."""
    path = ef.season_files(2026)["prior_positions"]
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert ("positionen_vorjahr", ef.LEAGUE_DEFAULTS_URL.format(season=2025)) in espn_week3.requests
    assert ("scoring",) in espn_week3.requests
    saved = json.loads(path.read_bytes())
    assert (saved["saison"], len(saved["teams"]), saved["wochen"]) == (2025, 32, list(range(1, 18)))
    # erfundene Rohstats von Team 1 (201 Passing Yards, 1 Passing TD) im echten Liga-Scoring der W1-Datei
    table = ef.scoring_table(week_views(1, final=True)["mSettings"]["settings"])
    expected = float(ef.to_points(ef.league_points({"3": 201.0, "4": 1.0}, table, "0")))
    assert saved["teams"]["1"]["QB"] == {"pts": [expected] * 17, "n": [1] * 17}
    assert saved["scoring"] == {str(k): float(v[0]) for k, v in sorted(table.items())}
    assert b"Testspieler" not in path.read_bytes()
    assert path.stat().st_size < 50_000                              # Auszug (echt rund 25 KB), nicht die 4-MB-Rohantwort
    espn_week3.requests.clear()
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0   # Nachlauf: Spielplan, FantasyPros, nflverse, Stat-Korrekturen
    assert espn_week3.requests == [("spielplan", 2026)] + [("fantasypros", p) for p in fantasypros.POSITIONS] \
        + [("nflverse",), ("spielplan_aktuell",), ("ist", (1, 2, 3))]


def test_positionen_vorjahr_fehler_nur_warnung(espn_week3, capsys):
    """Teil-Antwort oder unbrauchbare Antwort: nichts speichern, warnen, Woche trotzdem schreiben; der nächste
    Lauf versucht es erneut."""
    path = ef.season_files(2026)["prior_positions"]

    def without_team():
        data = fake_prior_positions()
        del data["players"][0]["player"]["stats"][3]["proTeamId"]
        return data

    bad = {"31 statt 32 NFL-Teams": lambda: fake_prior_positions(teams=31),
           "16 statt 17 Wochen bei Team 7": lambda: fake_prior_positions(qb_games=lambda team: 16 if team == 7 else 17),
           "unvollständig (40 Spieler)": lambda: {"players": fake_prior_positions()["players"][:40]},
           "unbrauchbar": without_team}
    for match, answer in bad.items():
        espn_week3.prior_answer = answer
        assert ef.cmd_due(2026, date(2026, 9, 29)) == 0, match
        assert not path.exists() and ef.is_final(2026, 3)
        out, err = capsys.readouterr()
        assert match in err and "Fehler bei Saisondateien oder beim Nachholen" in out
    espn_week3.prior_answer = fake_prior_positions
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0
    assert path.exists()


def test_spielplan_fehler_blockiert_die_woche_nicht(espn_week3):
    espn_week3.schedule_teams = 32   # nur 31 NFL-Teams
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert not ef.season_files(2026)["schedule"].exists()
    assert ef.is_final(2026, 3)


def test_nachholen_ohne_wochenwerte_wird_nicht_gespeichert(espn_week3):
    espn_week3.pool_without_week = {1}
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert not (ef.week_dir(2026, 1) / ef.KONA_FILE).exists()      # der nächste Lauf versucht es erneut
    assert (ef.week_dir(2026, 2) / ef.KONA_FILE).exists()


def test_nachholen_nur_vergangene_wochen(espn_week3):
    ef.cmd_due(2026, date(2026, 9, 29))
    assert not ef.week_dir(2026, 4).exists()                        # laufende Woche 4 bleibt unberührt


def test_standings_mit_falscher_woche_blockieren_die_woche(espn_week3):
    espn_week3.standings_echo = 2
    before = snapshot(3)
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 1
    assert snapshot(3) == before


def test_catch_up_stand_dateien_nur_fuer_juengste_woche(espn_week3):
    """Di 06.10. mit offener W3 und fehlender W4: ROS/Standings nur für W4, W3 bekommt Kern und Spielerpool."""
    espn_week3.week_answers.update({(view, 4): ok(data) for view, data in week_views(4, final=True).items()})
    assert ef.cmd_due(2026, date(2026, 10, 6)) == 0
    w3, w4 = ef.week_dir(2026, 3), ef.week_dir(2026, 4)
    assert ef.is_final(2026, 3) and ef.is_final(2026, 4)
    assert (w3 / ef.KONA_FILE).exists() and not (w3 / ef.ROS_FILE).exists() and not (w3 / ef.STANDINGS_FILE).exists()
    assert (w4 / ef.ROS_FILE).exists() and (w4 / ef.STANDINGS_FILE).exists()
    assert ("ros", 5, 17) in espn_week3.requests and ("ros", 4, 17) not in espn_week3.requests


# ---------------------------------------------------------------- Stat-Korrekturen finaler Wochen (Beschluss 06.10.2026)
# Rein: erfundene Mini-Paarungen und Ist-Einträge. Ablauf: echte W1-Dateien als Vorlage, darauf eine erfundene
# Korrektur – ESPN hat W1 nie korrigiert, alle Abweichungen in diesen Tests sind erfunden.

def spiel(gid: int, home: int, away: int, h, a, winner: str = "HOME") -> dict:
    """Erfundene Paarung der Periode 3."""
    return {"id": gid, "matchupPeriodId": 3, "winner": winner,
            "home": {"teamId": home, "totalPoints": h}, "away": {"teamId": away, "totalPoints": a}}


def ist(points, played: int = 1, team: int = 18, **raw) -> dict:
    """Erfundener Ist-Eintrag der Woche 3 mit allen Feldern, die ESPN am 06.10.2026 lieferte; raw: Rohstats als s58=…"""
    return {"appliedTotal": points, "externalId": "401", "id": "0401", "proTeamId": team, "scoringPeriodId": 3,
            "seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 1,
            "stats": {"210": played, **{k[1:]: v for k, v in raw.items()}}}


def test_ist_filter():
    """Ist-Abfrage: ganzer Pool (sortPercOwned, sonst HTTP 400), nur Wochen-Ist (Quelle 0, Split 1) aller Wochen."""
    flt = json.loads(ef.ist_filter([1, 2, 3])["X-Fantasy-Filter"])["players"]
    assert flt["filterStatsForCurrentSeasonScoringPeriodId"]["value"] == [1, 2, 3]
    assert (flt["filterStatsForSourceIds"]["value"], flt["filterStatsForSplitTypeIds"]["value"]) == ([0], [1])
    assert "sortPercOwned" in flt and flt["limit"] == 2000 and "filterRanksForScoringPeriodIds" not in flt


def test_statkorrektur_extract_ohne_abweichung():
    games = [spiel(11, 5, 2, 199.56, 251.91), spiel(12, 9, 1, 178.92, 187.0)]
    stored = [{101: ist(15.0), 102: ist(7.5)}]
    assert ef.statkorrektur_extract(games, json.loads(json.dumps(games))[::-1], stored, {101: ist(15.0)}) == (None, [])


def test_statkorrektur_extract_spiel_und_spieler():
    """Wie der echte W3-Fall vom 06.10.2026 (Werte hier erfunden): Team-Summe und D/ST-Punkte je −1, Sieger bleibt."""
    body, unknown = ef.statkorrektur_extract(
        [spiel(11, 5, 2, 199.56, 251.91, "AWAY"), spiel(12, 9, 1, 178.92, 187.0, "AWAY")],
        [spiel(11, 5, 2, 199.56, 250.91, "AWAY"), spiel(12, 9, 1, 178.92, 187.0, "AWAY")],
        [{-16018: ist(15.0, s106=3), 4: ist(7.0)}], {-16018: ist(14.0, s106=2), 4: ist(7.0)})
    assert unknown == []
    assert body["spiele"] == [{"id": 11, "home": 5, "away": 2, "totalPoints": [199.56, 250.91], "winner": "AWAY",
                               "vorher": {"totalPoints": [199.56, 251.91], "winner": "AWAY"}}]
    assert body["spieler"] == [{"id": -16018, "vorher": {"appliedTotal": 15.0, "gespielt": True, "proTeamId": 18},
                                "ist": ist(14.0, s106=2)}]
    assert ef.sieger_wechsel(3, body["spiele"]) == []


def test_statkorrektur_extract_nur_rohstats_zaehlt_nicht():
    """Rohstat-Änderung ohne Punktwirkung (06.10.2026: sieben in W3, z. B. Stat 58) löst nichts aus."""
    games = [spiel(11, 5, 2, 199.56, 251.91)]
    assert ef.statkorrektur_extract(games, games, [{7: ist(9.0, s58=13)}], {7: ist(9.0, s58=14)}) == (None, [])


@pytest.mark.parametrize("before, after", [(ist(0.0, played=0), ist(0.0, played=1)),    # Einsatz nachgetragen
                                           (ist(5.0, team=18), ist(5.0, team=11))])     # anderes NFL-Team im Spiel
def test_statkorrektur_extract_einsatz_und_team_zaehlen(before, after):
    games = [spiel(11, 5, 2, 199.56, 251.91)]
    body, _ = ef.statkorrektur_extract(games, games, [{7: before}], {7: after})
    assert [s["id"] for s in body["spieler"]] == [7] and body["spiele"] == [] and body["spieler"][0]["ist"] == after


def test_statkorrektur_extract_fehlender_spieler_und_quellen():
    """Wer heute fehlt (filterActive) oder vorher keinen Eintrag hatte, bleibt außen vor; ein Spieler zählt, wenn
    mindestens eine Quelle abweicht (z. B. ein später nachgeholter Spielerpool mit anderem Stand als mRoster)."""
    games = [spiel(11, 5, 2, 199.56, 251.91)]
    assert ef.statkorrektur_extract(games, games, [{1: ist(3.0)}], {2: ist(4.0)}) == (None, [])
    body, _ = ef.statkorrektur_extract(games, games, [{1: ist(3.0)}, {1: ist(2.0)}], {1: ist(2.0)})
    assert body["spieler"][0]["vorher"]["appliedTotal"] == 3.0


def test_statkorrektur_extract_neuer_eintrag_nur_mit_neu():
    """Ein Ist-Eintrag, den es am Dienstag nicht gab, zählt nur beim Rückgriff auf mRoster (neu) und nur punktwirksam;
    „vorher“ ist dann leer (erfundene Werte)."""
    games = [spiel(11, 5, 2, 199.56, 251.91)]
    assert ef.statkorrektur_extract(games, games, [{}], {5: ist(12.0)}) == (None, [])
    assert ef.statkorrektur_extract(games, games, [{}], {5: ist(0.0, played=0)}, neu={5}) == (None, [])
    body, _ = ef.statkorrektur_extract(games, games, [{}], {5: ist(12.0)}, neu={5})
    assert body["spieler"] == [{"id": 5, "vorher": {"appliedTotal": None, "gespielt": False, "proTeamId": None},
                                "ist": ist(12.0)}]


def test_statkorrektur_extract_ohne_freilos():
    """Freilose der Playoffs (ohne Gegner) bleiben wie bei is_final außen vor: dass ESPN dort später einen Sieger oder
    Punkte setzt, ist keine Stat-Korrektur und dreht kein Ergebnis (erfundene Paarung)."""
    freilos = {"id": 12, "matchupPeriodId": 3, "winner": "UNDECIDED", "home": {"teamId": 7, "totalPoints": 0}}
    jetzt = dict(freilos, winner="HOME", home={"teamId": 7, "totalPoints": 120.5})
    assert ef.statkorrektur_extract([spiel(11, 5, 2, 1, 2), freilos], [spiel(11, 5, 2, 1, 2), jetzt], [{}], {}) \
        == (None, [])


def test_statkorrektur_extract_andere_paarungen():
    with pytest.raises(ef.FetchError, match="weichen"):
        ef.statkorrektur_extract([spiel(11, 5, 2, 1, 2)], [spiel(12, 5, 2, 1, 2)], [{}], {})
    with pytest.raises(ef.FetchError, match="andere Teams"):
        ef.statkorrektur_extract([spiel(11, 5, 2, 1, 2)], [spiel(11, 5, 3, 1, 2)], [{}], {})


@pytest.mark.parametrize("after, dreht", [
    (spiel(11, 5, 2, 199.56, 250.91, "AWAY"), False),
    (spiel(11, 5, 2, 199.56, 199.0, "HOME"), True),     # Punkte und Sieger gedreht
    (spiel(11, 5, 2, 199.56, 199.0, "AWAY"), True),     # nur nach Punkten gedreht (zählt in der Regular Season)
    (spiel(11, 5, 2, 199.56, 199.56, "TIE"), True),
])
def test_statkorrektur_sieger_wechsel(after, dreht):
    body, _ = ef.statkorrektur_extract([spiel(11, 5, 2, 199.56, 251.91, "AWAY")], [after], [{}], {})
    warnings = ef.sieger_wechsel(3, body["spiele"])
    assert bool(warnings) is dreht
    if dreht:
        assert warnings[0].startswith("Stat-Korrektur dreht das Ergebnis: W3 Spiel 11 (Team 5 gegen Team 2)")


def test_ist_positivliste():
    """Unbekannte Felder im Ist-Eintrag fallen weg und werden gemeldet; appliedStats (mRoster) fällt still weg."""
    neu = dict(ist(14.0), appliedStats={"106": -1.0}, erfundenesFeld="erfundener Testwert")
    games = [spiel(11, 5, 2, 199.56, 251.91)]
    body, unknown = ef.statkorrektur_extract(games, games, [{1: ist(15.0)}], {1: neu})
    assert unknown == ["erfundenesFeld"] and set(body["spieler"][0]["ist"]) == ef.IST_KEEP


def kader(team: int, *entries) -> dict:
    """Erfundener mRoster-Kader: entries = (Spieler-ID, Slot, Ist-Punkte oder None)."""
    return {"id": team, "roster": {"entries": [
        {"playerId": pid, "lineupSlotId": slot, "playerPoolEntry": {"player": {
            "id": pid, "stats": [] if points is None else [ist(points)]}}} for pid, slot, points in entries]}}


def test_check_statkorrektur():
    """Σ Starter (ohne Bank und IR, Ist aus der Korrektur, sonst aus der Datei) = Team-Summe für alle Teams mit Gegner."""
    roster = {"teams": [kader(5, (1, 0, 20.0), (2, 20, 99.0), (3, 21, 50.0), (4, 2, None)),
                        kader(2, (11, 16, 15.0), (12, 4, 10.5))]}
    games = [spiel(11, 5, 2, 20.0, 24.5)]
    korr = [{"id": 11, "ist": ist(14.0)}]
    assert ef.check_statkorrektur(roster, 2026, 3, games, korr) == []
    assert ef.check_statkorrektur(roster, 2026, 3, games, []) == ["Team 2: Starter 25.50, Spielstand 24.50"]
    bye = [spiel(11, 5, 2, 20.0, 24.5), {"id": 12, "matchupPeriodId": 3, "home": {"teamId": 7, "totalPoints": 1.0}}]
    assert ef.check_statkorrektur(roster, 2026, 3, bye, korr) == []          # Freilos: nichts zu prüfen
    assert ef.check_statkorrektur(roster, 2026, 3, [spiel(12, 7, 5, 1, 20.0)], []) == [f"Team 7 fehlt in {ef.ROSTER_VIEW}"]


def test_statkorrektur_dumps_deterministisch():
    body, _ = ef.statkorrektur_extract([spiel(11, 5, 2, 199.56, 251.91), spiel(14, 3, 7, 191.58, 219.54)],
                                       [spiel(11, 5, 2, 199.56, 250.91), spiel(14, 3, 7, 190.58, 219.54)],
                                       [{-16018: ist(15.0), -16011: ist(17.0)}], {-16011: ist(16.0), -16018: ist(14.0)})
    doc = ef.statkorrektur_doc(2026, 3, "2026-10-13T0830Z", body)
    raw = ef.statkorrektur_dumps(doc)
    assert json.loads(raw) == doc and raw.endswith(b"]\n}\n")
    assert list(doc) == ["season", "woche", "stand", "quelle", "spiele", "spieler"]
    rows = [json.loads(line.rstrip(",")) for line in raw.decode("utf-8").splitlines() if line.startswith('{"id":')]
    assert [r["id"] for r in rows] == [11, 14, -16018, -16011]                        # eine Zeile je Spiel und Spieler
    assert [s["id"] for s in doc["spieler"]] == [-16018, -16011]                     # nach id sortiert
    leer = ef.statkorrektur_dumps(dict(doc, spieler=[]))
    assert json.loads(leer)["spieler"] == [] and b'"spieler":[]' in leer
    assert ef.same_pool(doc, dict(json.loads(raw), stand="2026-10-14T0830Z"))       # Vergleich ohne stand


DI_W2 = date(2026, 9, 15)   # Dienstag nach W1: letzte vergangene Woche ist W1
W1_DATEIEN = tuple(f"{view}.json" for view in ef.VIEWS) + (ef.KONA_FILE,)


class FakeKorrektur(FakeLeague):
    """FakeLeague auf der echten, finalen W1 (byte-genau kopiert): Spielplan von heute, Wochen-Ist (kona) und mRoster
    der Woche antworten mit den echten W1-Werten; korrigiere() legt eine erfundene Stat-Korrektur darüber."""

    def __init__(self):
        super().__init__(final_week=1)
        self.schedule = json.loads((SOURCE_WEEK / "mMatchupScore.json").read_bytes())
        self.roster = json.loads((SOURCE_WEEK / "mRoster.json").read_bytes())
        self.ist = only_actual(json.loads((SOURCE_WEEK / ef.KONA_FILE).read_bytes()))

    def current_schedule(self) -> dict:
        return dict(self.schedule, scoringPeriodId=2)

    def ist_answer(self, weeks) -> dict:
        return self.ist

    def get(self, url, params=None, headers=None, timeout=None):
        if params.get("view") == ef.ROSTER_VIEW and params.get("scoringPeriodId") == 1:
            self.requests.append((ef.ROSTER_VIEW, 1))
            return ok(self.roster)
        return super().get(url, params, headers, timeout)

    def starter(self, ohne_dst: bool = False, bank: bool = False) -> tuple[int, int, str]:
        """Erster Starter (nach Team und Spieler-ID) mit mindestens 2 Ist-Punkten, der auch im Spielerpool steht:
        (Team, Spieler-ID, Name); ohne_dst: keine D/ST (die stehen immer im Pool); bank: Bankspieler statt Starter."""
        in_pool = {e["id"] for e in self.ist["players"] if e["player"]["stats"]}
        for team in sorted(self.roster["teams"], key=lambda t: t["id"]):
            for e in sorted(team["roster"]["entries"], key=lambda e: e["playerId"]):
                player = e["playerPoolEntry"]["player"]
                stat = ef.ist_eintrag(player, 2026, 1)
                if (e["lineupSlotId"] == 20 if bank else e["lineupSlotId"] not in (20, 21)) and e["playerId"] in in_pool \
                        and stat and stat["appliedTotal"] >= 2 \
                        and not (ohne_dst and player["defaultPositionId"] == ef.DST_POSITION):
                    return team["id"], e["playerId"], player["fullName"]
        raise AssertionError("kein Spieler gefunden")

    def korrigiere(self, team: int, pid: int, spieler: bool = True, kader: bool = True, spielplan: bool = True) -> int:
        """Erfundene Korrektur: Ist des Spielers pid im Spielerpool (spieler) und in mRoster (kader) um 1 kleiner,
        ebenso die Summe seines Teams im Spielplan von heute (spielplan); gibt die Spiel-ID zurück."""
        minus_eins = lambda value: float(Decimal(str(value)) - 1)  # noqa: E731 (ohne Binär-Artefakte)
        if spieler:
            stat = ef.ist_eintrag(next(e for e in self.ist["players"] if e["id"] == pid)["player"], 2026, 1)
            stat["appliedTotal"] = minus_eins(stat["appliedTotal"])
        if kader:
            for t in self.roster["teams"]:
                for e in t["roster"]["entries"]:
                    if e["playerId"] == pid:
                        stat = ef.ist_eintrag(e["playerPoolEntry"]["player"], 2026, 1)
                        stat["appliedTotal"] = minus_eins(stat["appliedTotal"])
        game = next(m for m in self.schedule["schedule"] if m["matchupPeriodId"] == 1
                    and team in (m["home"]["teamId"], m["away"]["teamId"]))
        if spielplan:
            side = game["home"] if game["home"]["teamId"] == team else game["away"]
            side["totalPoints"] = minus_eins(side["totalPoints"])
        return game["id"]


@pytest.fixture
def korrektur(raw, monkeypatch):
    """Echte W1 (alle Kern-Views und Spielerpool, byte-genau) im Temp-Verzeichnis; ESPN antwortet ohne Korrektur."""
    folder = ef.week_dir(2026, 1)
    folder.mkdir(parents=True)
    for name in W1_DATEIEN:
        shutil.copyfile(SOURCE_WEEK / name, folder / name)
    session = FakeKorrektur()
    monkeypatch.setattr(ef.requests, "Session", lambda: session)
    monkeypatch.setattr(fantasypros, "PAUSE", 0)
    return session


def korr_path():
    return ef.week_dir(2026, 1) / ef.STATKORREKTUR_FILE


def test_statkorrektur_ohne_abweichung(korrektur, capsys):
    """Echte W1 gegen dieselben Werte: zwei Aufrufe, keine Datei, kein mRoster-Rückgriff."""
    assert ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z") == 0
    assert korrektur.requests == [("spielplan_aktuell",), ("ist", (1,))] and not korr_path().exists()
    assert "W01  keine Abweichung" in capsys.readouterr().out


def test_statkorrektur_uebernommen(korrektur, capsys):
    """Erfundene Korrektur −1 auf einen Starter samt Team-Summe: Die Woche bekommt statkorrektur.json, alle
    Wochendateien bleiben byte-gleich; Spielstand, Kader und Spielerpool gelten mit Korrektur, Σ Starter = PF."""
    team, pid, name = korrektur.starter()
    gid = korrektur.korrigiere(team, pid)
    before = snapshot(1, W1_DATEIEN)
    assert ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z") == 0
    assert snapshot(1, W1_DATEIEN) == before and (ef.ROSTER_VIEW, 1) not in korrektur.requests
    raw_bytes = korr_path().read_bytes()
    doc = json.loads(raw_bytes)
    assert (doc["season"], doc["woche"], doc["stand"]) == (2026, 1, "2026-09-15T0830Z")
    assert [g["id"] for g in doc["spiele"]] == [gid] and [s["id"] for s in doc["spieler"]] == [pid]
    s = doc["spieler"][0]
    assert round(s["vorher"]["appliedTotal"] - s["ist"]["appliedTotal"], 6) == 1 and set(s["ist"]) <= ef.IST_KEEP
    assert name.encode("utf-8") not in raw_bytes and b"fullName" not in raw_bytes      # nur IDs und Zahlen
    out = capsys.readouterr().out
    # Präfix je nach Umgebung („Warnung: “ lokal, „::warning::“ in der Action)
    assert "Stat-Korrektur übernommen: W1 – 1 Spiel, 1 Spieler (raw/2026/w01/statkorrektur.json)" in out
    assert "dreht das Ergebnis" not in out
    # Leser: Spielstand und Ist-Werte mit Korrektur, Felder mit Stand des Abrufs unverändert
    row = next(m for m in ef.load_week_matchups(2026, 1) if m["id"] == gid)
    side = "home" if row["home_id"] == team else "away"
    game = next(m for m in korrektur.schedule["schedule"] if m["id"] == gid)
    assert row[f"{side}_points"] == ef.to_points(game[side]["totalPoints"]) and row["final"]
    ssn = rawdata.Season(2026, 1)
    rows = compute.compute_team_weeks(ssn, [1])
    assert [r["team_id"] for r in rows if ef.to_points(r["abweichung"]) != 0] == []
    assert next(r for r in rows if r["team_id"] == team)["pf"] == ef.to_points(game[side]["totalPoints"])


def test_rawdata_statkorrektur_aendert_keine_standfelder(korrektur):
    """Nur Ist-Punkte, Einsatz und NFL-Team des Spiels kommen aus der Korrektur; Verletzung, Status, Besitz,
    Fantasy-Team, NFL-Team des Spielers, Slot und Projektion bleiben beim Stand der Wochendatei (erfundene Korrektur)."""
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid)
    ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z")
    ssn = rawdata.Season(2026, 1)
    folder = ef.week_dir(2026, 1)
    pool_alt = {r.player_id: r for r in rawdata.pool_rows(ef.load_json(folder / ef.KONA_FILE), 2026, 1)}
    kader_alt = {(r.team_id, r.player_id): r for r in rawdata.roster_rows(ef.load_json(folder / "mRoster.json"), 2026, 1)}
    neu, alt = next(r for r in ssn.pool(1) if r.player_id == pid), pool_alt[pid]
    assert neu.actual == alt.actual - 1 and neu._replace(actual=alt.actual) == alt
    assert [r for r in ssn.pool(1) if r.player_id != pid] == [r for r in pool_alt.values() if r.player_id != pid]
    neu, alt = next(r for r in ssn.roster(1) if r.player_id == pid), kader_alt[(team, pid)]
    assert neu.actual == alt.actual - 1 and neu._replace(actual=alt.actual) == alt
    # NFL-Team des Spiels aus der Korrektur (erfundener Wechsel des Ist-Eintrags)
    korr = ef.load_json(korr_path())
    korr["spieler"][0]["ist"]["proTeamId"] = 99
    row = rawdata.pool_rows(ef.load_json(folder / ef.KONA_FILE), 2026, 1, {pid: korr["spieler"][0]["ist"]})
    assert next(r for r in row if r.player_id == pid).game_team == 99


def test_statkorrektur_zweiter_lauf_schreibt_nicht(korrektur):
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid)
    ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z")
    first = korr_path().read_bytes()
    assert ef.update_statkorrekturen(korrektur, 2026, date(2026, 9, 16), "2026-09-16T0830Z") == 0
    assert korr_path().read_bytes() == first and json.loads(first)["stand"] == "2026-09-15T0830Z"


def test_statkorrektur_zurueckgenommen_loescht_datei(korrektur, capsys):
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid)
    ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z")
    assert korr_path().exists()
    capsys.readouterr()
    ruecknahme = FakeKorrektur()   # ESPN führt wieder die Werte der Wochendateien
    assert ef.update_statkorrekturen(ruecknahme, 2026, date(2026, 9, 22), "2026-09-22T0830Z") == 0
    assert not korr_path().exists()
    assert "Stat-Korrektur zurückgenommen: W1" in capsys.readouterr().out


def test_statkorrektur_unstimmig(korrektur, capsys):
    """Team-Summe geändert, aber kein Spieler (z. B. ein Ausgleich des Commissioners): mRoster wird nachgefragt, die
    Woche bleibt unverändert, Warnung; der Wochenabruf bleibt grün."""
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid, spieler=False, kader=False)
    assert ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z") == 1
    assert (ef.ROSTER_VIEW, 1) in korrektur.requests and not korr_path().exists()
    out = capsys.readouterr().out
    assert f"Stat-Korrektur W1 nicht übernommen (unstimmig auch mit mRoster der Woche (Team {team}: Starter" in out
    korrektur.requests.clear()
    assert ef.cmd_due(2026, DI_W2) == 0 and not korr_path().exists()
    assert "Fehler bei Saisondateien oder beim Nachholen (auch Stat-Korrekturen)" in capsys.readouterr().out


def test_statkorrektur_aus_mroster(korrektur):
    """Ein korrigierter Starter fehlt heute im Spielerpool (filterActive): erst unstimmig, dann trägt mRoster der Woche
    seinen neuen Ist-Wert nach (erfundene Korrektur)."""
    team, pid, _ = korrektur.starter(ohne_dst=True)
    gid = korrektur.korrigiere(team, pid, spieler=False)
    korrektur.ist["players"] = [e for e in korrektur.ist["players"] if e["id"] != pid]
    assert ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z") == 0
    assert (ef.ROSTER_VIEW, 1) in korrektur.requests
    doc = ef.load_json(korr_path())
    assert [g["id"] for g in doc["spiele"]] == [gid] and [s["id"] for s in doc["spieler"]] == [pid]
    assert set(doc["spieler"][0]["ist"]) <= ef.IST_KEEP     # appliedStats aus mRoster fällt weg


def test_statkorrektur_bleibt_wenn_spieler_heute_fehlt(korrektur, capsys):
    """Ein schon korrigierter Spieler fehlt im nächsten Lauf in der Ist-Antwort (filterActive, Teilantwort): Seine
    Korrektur bleibt, keine Rücknahme und kein Hin und Her in den Commits (erfundene Korrektur an einem Bankspieler –
    sie ändert keine Team-Summe, die Konsistenzprüfung fiele also nicht auf)."""
    team, pid, _ = korrektur.starter(ohne_dst=True, bank=True)
    korrektur.korrigiere(team, pid, spielplan=False)
    assert ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z") == 0
    first = korr_path().read_bytes()
    assert ([s["id"] for s in json.loads(first)["spieler"]], json.loads(first)["spiele"]) == ([pid], [])
    korrektur.ist["players"] = [e for e in korrektur.ist["players"] if e["id"] != pid]
    capsys.readouterr()
    assert ef.update_statkorrekturen(korrektur, 2026, date(2026, 9, 22), "2026-09-22T0830Z") == 0
    assert korr_path().read_bytes() == first
    out = capsys.readouterr().out
    assert "1 korrigierte Spieler heute ohne Ist-Eintrag – ihre Korrektur bleibt" in out and "zurückgenommen" not in out


def test_statkorrektur_neuer_eintrag_aus_mroster(korrektur):
    """Ein Starter hatte am Dienstag keinen Ist-Eintrag (Team-Summe ohne ihn), ESPN führt ihn heute samt Team-Summe:
    Der Rückgriff auf mRoster übernimmt ihn mit leerem „vorher“, statt die Woche dauerhaft unstimmig zu lassen
    (erfundener Dienstags-Stand auf der echten W1, nur im Temp-Verzeichnis)."""
    team, pid, _ = korrektur.starter(ohne_dst=True)
    folder = ef.week_dir(2026, 1)
    roster, kona = ef.load_json(folder / "mRoster.json"), ef.load_json(folder / ef.KONA_FILE)
    players = [e["playerPoolEntry"]["player"] for t in roster["teams"] for e in t["roster"]["entries"]
               if e["playerId"] == pid] + [e["player"] for e in kona["players"] if e["id"] == pid]
    punkte = Decimal(str(ef.ist_eintrag(players[0], 2026, 1)["appliedTotal"]))
    for player in players:
        stat = ef.ist_eintrag(player, 2026, 1)
        player["stats"] = [s for s in player["stats"] if s is not stat]
    spielplan = ef.load_json(folder / "mMatchupScore.json")
    game = next(m for m in spielplan["schedule"]
                if m["matchupPeriodId"] == 1 and team in (m["home"]["teamId"], m["away"]["teamId"]))
    side = game["home"] if game["home"]["teamId"] == team else game["away"]
    side["totalPoints"] = float(Decimal(str(side["totalPoints"])) - punkte)
    for name, data in (("mRoster.json", roster), (ef.KONA_FILE, kona), ("mMatchupScore.json", spielplan)):
        (folder / name).write_text(json.dumps(data), encoding="utf-8")
    assert ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z") == 0
    assert (ef.ROSTER_VIEW, 1) in korrektur.requests
    doc = ef.load_json(korr_path())
    assert [g["id"] for g in doc["spiele"]] == [game["id"]]
    assert [(s["id"], s["vorher"]["appliedTotal"]) for s in doc["spieler"]] == [(pid, None)]
    assert rawdata.Season(2026, 1).statkorrektur(1)[pid]["appliedTotal"] == float(punkte)
    first = korr_path().read_bytes()
    korrektur.requests.clear()   # nächster Lauf: der übernommene Eintrag zählt ohne erneuten Rückgriff
    assert ef.update_statkorrekturen(korrektur, 2026, date(2026, 9, 22), "2026-09-22T0830Z") == 0
    assert korrektur.requests == [("spielplan_aktuell",), ("ist", (1,))] and korr_path().read_bytes() == first


def test_unlesbare_statkorrektur_holt_die_woche_nicht_neu(korrektur, capsys):
    """Eine unlesbare statkorrektur.json (etwa von Hand bearbeitet) macht die Woche nicht „nicht final“ – sonst holte
    --due sie neu und überschriebe die Dienstags-Dateien. Das Rechenwerk scheitert laut, der nächste Wochenabruf
    schreibt die Datei neu (erfundene Korrektur)."""
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid)
    ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z")
    good = korr_path().read_bytes()
    korr_path().write_bytes(good[:-20])
    before = snapshot(1, W1_DATEIEN)
    assert ef.is_final(2026, 1) and ef.due_weeks(2026, DI_W2) == []
    with pytest.raises(ef.FetchError, match="kein gültiges JSON"):
        ef.load_week_matchups(2026, 1)
    capsys.readouterr()
    assert ef.update_statkorrekturen(korrektur, 2026, date(2026, 9, 16), "2026-09-15T0830Z") == 0
    assert korr_path().read_bytes() == good and snapshot(1, W1_DATEIEN) == before
    assert "statkorrektur.json unlesbar" in capsys.readouterr().out


def test_statkorrektur_unerwartete_antwort_nur_warnung(korrektur, capsys):
    """Eine unerwartete Form der Antwort (erfunden: ein Spielplan-Eintrag, der kein Objekt ist) ist nur eine Warnung
    je Woche, kein Abbruch mit Traceback – der Wochenabruf bleibt grün."""
    korrektur.schedule["schedule"].append(5)
    assert ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z") == 1
    assert "Stat-Korrektur W1 nicht übernommen" in capsys.readouterr().out and not korr_path().exists()
    assert ef.cmd_due(2026, DI_W2) == 0


def test_statkorrektur_ausfall_nur_warnung(korrektur, capsys):
    """Ist-Abfrage scheitert (HTTP 503): vorhandene Korrektur bleibt, Warnung, der Wochenabruf bleibt grün."""
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid)
    ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z")
    before = korr_path().read_bytes()
    korrektur.ist_status = 503
    capsys.readouterr()
    assert ef.update_statkorrekturen(korrektur, 2026, date(2026, 9, 22), "2026-09-22T0830Z") == 1
    assert korr_path().read_bytes() == before
    assert "Stat-Korrekturen nicht geprüft (HTTP 503" in capsys.readouterr().out
    assert ef.cmd_due(2026, DI_W2) == 0 and korr_path().read_bytes() == before


def test_statkorrektur_ruht_in_der_offseason(korrektur):
    """Drei Kalenderwochen nach W17 wird noch geprüft (Di 19.01.2027), danach ruht die Prüfung (keine Aufrufe)."""
    assert ef.update_statkorrekturen(korrektur, 2026, date(2027, 1, 19), "x") == 0
    assert korrektur.requests == [("spielplan_aktuell",), ("ist", (1,))]
    korrektur.requests.clear()
    assert ef.update_statkorrekturen(korrektur, 2026, date(2027, 1, 26), "x") == 0 and korrektur.requests == []
    assert ef.update_statkorrekturen(korrektur, 2026, date(2026, 9, 8), "x") == 0 and korrektur.requests == []  # vor W1


def test_handabruf_mit_force_loescht_statkorrektur(korrektur):
    """Wer eine finale Woche von Hand neu holt (--force), ersetzt die Grundlage: die Korrektur fällt weg."""
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid)
    ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z")
    assert korr_path().exists()
    assert ef.cmd_fetch(2026, [1], force=True) == 0 and not korr_path().exists()


def test_league_games_still_nach_uebernahme_und_warnt_ohne(korrektur, capsys):
    """Spielplan der App: Mit übernommener Korrektur ist die Warnung still – gleich, ob der Spielplan der Stand-Woche
    die Korrektur schon trägt (jüngere Woche) oder noch den alten Wert (die Woche selbst); ohne Übernahme warnt sie
    (erfundene Korrektur)."""
    team, pid, _ = korrektur.starter()
    gid = korrektur.korrigiere(team, pid)
    ef.update_statkorrekturen(korrektur, 2026, DI_W2, "2026-09-15T0830Z")
    w2 = ef.week_dir(2026, 2)   # jüngere Stand-Woche, deren Spielplan die Korrektur schon trägt
    w2.mkdir()
    shutil.copyfile(SOURCE_WEEK / "mSettings.json", w2 / "mSettings.json")
    (w2 / "mMatchupScore.json").write_text(json.dumps(korrektur.schedule), encoding="utf-8")
    korrigiert = next(m for m in ef.load_week_matchups(2026, 1) if m["id"] == gid)
    capsys.readouterr()
    for stand in (1, 2):
        game = next(g for g in compute.league_games(rawdata.Season(2026, stand), [1]) if g["id"] == gid)
        assert (game["home_pf"], game["away_pf"]) == (korrigiert["home_points"], korrigiert["away_points"])
        spielplan = next(m for m in rawdata.Season(2026, stand).schedule() if m["id"] == gid)
        assert [ef.to_points(spielplan[s]["totalPoints"]) for s in ("home", "away")] \
            == [korrigiert["home_points"], korrigiert["away_points"]]
    assert "Stat-Korrektur noch nicht übernommen" not in capsys.readouterr().out
    korr_path().unlink()
    compute.league_games(rawdata.Season(2026, 2), [1])
    assert f"W1 Spiel {gid}: Spielplan der Stand-Woche" in capsys.readouterr().out


def test_skriptaufruf_statkorrektur_als_hinweis_am_lauf(korrektur, monkeypatch, capsys):
    """Wie in der Action (python scripts/espn_fetch.py --due, GITHUB_ACTIONS=true): Das Skript ist ein zweites
    espn_fetch-Modul; die übernommene Korrektur erscheint als ::warning:: am Lauf, der Lauf bleibt grün (Lehre aus
    PR #45/#46). Erfundene Korrektur."""
    spec = importlib.util.spec_from_file_location("espn_fetch_als_skript", ef.__file__)
    skript = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skript)
    monkeypatch.setattr(skript, "RAW_DIR", ef.RAW_DIR)
    monkeypatch.setattr(skript, "REPO_DIR", ef.REPO_DIR)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    team, pid, _ = korrektur.starter()
    korrektur.korrigiere(team, pid)
    assert skript.cmd_due(2026, DI_W2, "2026-09-15T0830Z") == 0
    out = capsys.readouterr().out
    assert "::warning::Stat-Korrektur übernommen: W1 – 1 Spiel, 1 Spieler (raw/2026/w01/statkorrektur.json)" in out
    assert json.loads(korr_path().read_bytes())["stand"] == "2026-09-15T0830Z"


class StubSession:
    """Antwortet auf jede Anfrage mit denselben erfundenen Daten."""

    def __init__(self, data):
        self.data = data

    def get(self, url, params=None, headers=None, timeout=None):
        return ok(self.data)


@pytest.mark.parametrize("call, data, match", [
    (lambda s: ef.fetch_schedule(s, 2026), {"settings": {"proTeams": [{"id": i} for i in range(32)]}}, "Teams"),
    (lambda s: ef.fetch_draft(s, 2026), {"id": ef.LEAGUE_ID, "seasonId": 2026,
                                         "draftDetail": {"drafted": True, "picks": []}}, "Picks"),
    (lambda s: ef.fetch_draft(s, 2026), {"id": ef.LEAGUE_ID, "seasonId": 2025,
                                         "draftDetail": {"drafted": True, "picks": [1]}}, "Saison"),
    (lambda s: ef.fetch_prior_dst(s, 2026, date(2026, 9, 29)), fake_pool([], dst_games=lambda pid: 17)
     | {"players": fake_pool([], dst_games=lambda pid: 17)["players"][:31]}, "31 statt 32"),
    (lambda s: ef.fetch_ros(s, 2026, 3), {"players": fake_pool(range(4, 18))["players"][:40]}, "unvollständig"),
    (lambda s: ef.fetch_prior_positions(s, 2026), {"id": ef.LEAGUE_ID, "seasonId": 2025}, "Liga und Saison"),
    (lambda s: ef.fetch_prior_positions(s, 2026), {"id": ef.LEAGUE_ID, "seasonId": 2026, "settings": {}}, "scoringItems"),
])
def test_pruefungen_der_abrufe(call, data, match):
    with pytest.raises(ef.FetchError, match=match):
        call(StubSession(data))


def test_ros_auszug():
    extract = json.loads(ef.ros_extract(fake_pool(range(4, 18)), 2026, after_week=3))
    assert extract["after_week"] == 3 and extract["weeks"] == list(range(4, 18))
    first = extract["players"]["1"]
    assert list(first) == [str(w) for w in range(4, 18)]             # Wochen aufsteigend, W18 und Saisonwert fehlen
    assert first["4"] == 4.1
    assert list(extract["players"]) == [str(i) for i in range(1, 301)]


def test_ros_nach_letzter_woche():
    assert ef.fetch_ros(session=None, season=2026, week=17) is None


def test_spielerpool_pruefung():
    pool = fake_pool([3])
    ef.check_pool(pool)
    with pytest.raises(ef.FetchError, match="unvollständig"):
        ef.check_pool({"players": pool["players"][:299]})
    with pytest.raises(ef.FetchError, match="D/ST"):
        ef.check_pool({"players": pool["players"][1:] + pool["players"][40:41]})


def test_kona_filter_mit_sortierung():
    """Ohne sortPercOwned antwortet ESPN auf limit mit HTTP 400 – das alte Beispiel in CLAUDE.md hatte den Fehler."""
    flt = json.loads(ef.kona_filter([3], rank_week=3)["X-Fantasy-Filter"])["players"]
    assert "sortPercOwned" in flt and flt["filterStatsForCurrentSeasonScoringPeriodId"]["value"] == [3]


# ---------------------------------------------------------------- Positions-Grundlage des Vorjahrs (Session 8)

SCORING = {"scoringSettings": {"scoringItems": [   # erfundenes Mini-Scoring; das echte steht in mSettings
    {"statId": 3, "points": 0.04}, {"statId": 4, "points": 4.0}, {"statId": 53, "points": 1.0},
    {"statId": 72, "points": -2.0, "pointsOverrides": {"16": 0.0}}]}}


def test_scoring_table_und_league_points():
    table = ef.scoring_table(SCORING)
    assert table[72] == (Decimal("-2"), {"16": Decimal("0")}) and table[3] == (Decimal("0.04"), {})
    stats = {"3": 250.0, "4": 2.0, "53": 5.0, "72": 1.0, "999": 7.0, "210": 1.0}
    assert ef.league_points(stats, table, "0") == Decimal("21")      # 10 + 8 + 5 − 2; 999 und 210 zählen nicht
    assert ef.league_points(stats, table, "16") == Decimal("23")     # D/ST-Slot: Override 0 statt −2
    assert ef.league_points({}, table, "2") == 0
    for settings in (None, {}, {"scoringSettings": {}}, {"scoringSettings": {"scoringItems": []}}):
        with pytest.raises(ef.FetchError, match="scoringItems"):
            ef.scoring_table(settings)
    with pytest.raises(ef.FetchError, match="unbrauchbar"):
        ef.scoring_table({"scoringSettings": {"scoringItems": [{"statId": 3}]}})


def test_league_points_trifft_espn_im_liga_scoring():
    """Echte W1: Die Rohstats jedes Ist-Eintrags ergeben im Liga-Scoring genau ESPNs appliedTotal (alle Positionen,
    D/ST mit den Overrides für Slot 16) – Grundlage dafür, die Vorjahrespunkte aus Rohstats neu zu rechnen."""
    table = ef.scoring_table(week_views(1, final=True)["mSettings"]["settings"])
    pool = json.loads((SOURCE_WEEK / ef.KONA_FILE).read_bytes())
    checked = 0
    for entry in pool["players"]:
        pos = entry["player"]["defaultPositionId"]
        for s in entry["player"].get("stats", []):
            if (s["seasonId"], s["statSourceId"], s["statSplitTypeId"]) == (2026, 0, 1) and s.get("stats") \
                    and pos in ef.POSITION_SLOTS:
                assert ef.to_points(ef.league_points(s["stats"], table, ef.POSITION_SLOTS[pos])) \
                    == ef.to_points(s["appliedTotal"]), entry["player"]["fullName"]
                checked += 1
    assert checked > 400


MINI = {"players": [   # erfundene Spieler und Werte: NFL-Teams 1 und 2, Wochen 1 und 2 der Saison 2025
    spieler(1, 1, [stat(1, 1, {"210": 1.0, "3": 250.0, "4": 2.0}),        # QB Team 1: 10 + 8 = 18
                   stat(2, 1, {"210": 1.0, "3": 100.0, "72": 1.0}),        # 4 − 2 = 2
                   stat(4, 1, {"210": 1.0, "3": 999.0}, source=1),         # Projektion: zählt nicht
                   stat(3, 1, {"210": 1.0, "3": 999.0}, season=2024)]),     # andere Saison: zählt nicht
    spieler(2, 1, [stat(1, 1, {"210": 1.0, "3": 25.0}),                    # zweiter QB Team 1 in W1: 1
                   stat(2, 1, {"3": 50.0})]),                             # ohne Stat 210: zählt nicht
    spieler(3, 3, [stat(1, 1, {"210": 1.0, "53": 3.0}),                    # WR, Trade nach W1: W1 bei Team 1 …
                   stat(2, 2, {"210": 1.0, "53": 4.0})]),                   # … W2 beim neuen Team 2
    spieler(4, 2, [stat(1, 2, {"210": 0.0, "53": 9.0})]),                  # RB mit 210 = 0: zählt nicht
    spieler(5, 16, [stat(1, 2, {"210": 1.0, "53": 5.0})]),                 # D/ST: nicht Teil der Grundlage
    spieler(6, 9, [stat(1, 2, {"210": 1.0, "53": 1.0})]),                  # Position 9: ignoriert
    spieler(7, 1, [stat(2, 2, {"210": 1.0, "4": 1.0})]),                   # QB Team 2 nur in W2: 4
    spieler(8, 5, [stat(1, 1, {"210": 1.0, "72": 0.0})]),                  # K Team 1 in W1 mit 0 Punkten
]}


def test_positions_extract():
    extract = ef.positions_extract(MINI, 2025, ef.scoring_table(SCORING))
    assert list(extract) == ["saison", "quelle", "positionen", "wochen", "scoring", "teams"]
    assert (extract["saison"], extract["wochen"]) == (2025, [1, 2])
    assert extract["positionen"] == {"1": "QB", "2": "RB", "3": "WR", "4": "TE", "5": "K"}
    assert extract["scoring"] == {"3": 0.04, "4": 4.0, "53": 1.0, "72": -2.0}
    empty = {"pts": [None, None], "n": [0, 0]}
    assert extract["teams"] == {
        "1": {"QB": {"pts": [19.0, 2.0], "n": [2, 1]}, "RB": empty, "WR": {"pts": [3.0, None], "n": [1, 0]},
              "TE": empty, "K": {"pts": [0.0, None], "n": [1, 0]}},
        "2": {"QB": {"pts": [None, 4.0], "n": [0, 1]}, "RB": empty, "WR": {"pts": [None, 4.0], "n": [0, 1]},
              "TE": empty, "K": empty}}


def test_positions_dumps_deterministisch():
    """Gleicher Inhalt in anderer Reihenfolge ergibt dieselben Bytes; eine Zeile je NFL-Team, keine Spielernamen."""
    table = ef.scoring_table(SCORING)
    raw = ef.positions_dumps(ef.positions_extract(MINI, 2025, table))
    shuffled = {"players": [spieler(e["id"], e["player"]["defaultPositionId"], e["player"]["stats"][::-1])
                            for e in MINI["players"][::-1]]}
    assert ef.positions_dumps(ef.positions_extract(shuffled, 2025, table)) == raw
    assert json.loads(raw) == ef.positions_extract(MINI, 2025, table)
    lines = raw.decode("utf-8").split("\n")
    assert [line[:4] for line in lines if line.startswith('"') and line[1].isdigit()] == ['"1":', '"2":']
    assert raw.endswith(b"}\n}\n") and b"Testspieler" not in raw and b"-0.0" not in raw


def test_check_positions():
    table = ef.scoring_table(SCORING)
    ef.check_positions(ef.positions_extract(fake_prior_positions(), 2025, table))
    with pytest.raises(ef.FetchError, match="31 statt 32 NFL-Teams"):
        ef.check_positions(ef.positions_extract(fake_prior_positions(teams=31), 2025, table))
    with pytest.raises(ef.FetchError, match="16 statt 17 Wochen bei Team 5"):
        ef.check_positions(ef.positions_extract(fake_prior_positions(qb_games=lambda t: 16 if t == 5 else 17), 2025, table))
    # 32 Teams, aber eines nur mit RB-Einsätzen: QB-Wochen fehlen
    data = fake_prior_positions()
    data["players"][8]["player"]["defaultPositionId"] = 2
    with pytest.raises(ef.FetchError, match="0 statt 17 Wochen bei Team 9"):
        ef.check_positions(ef.positions_extract(data, 2025, table))


# ---------------------------------------------------------------- Archiv-Vergleich

def test_archive_state():
    a, b = {"id": "t1", "status": "PENDING"}, {"id": "t2", "status": "EXECUTED"}
    assert ef.archive_state(None, [a]) == "neu"
    assert ef.archive_state([a, b], [b, a]) == "gleich"              # Reihenfolge zählt nicht
    assert ef.archive_state([a], [a, b]) == "geändert"               # neuer Eintrag
    assert ef.archive_state([a], [dict(a, status="EXECUTED")]) == "geändert"  # Statuswechsel
    assert ef.archive_state([a, b], [b]) == "geschrumpft"            # ESPN hat t1 gelöscht
    assert ef.archive_state([], []) == "gleich"


def test_current_period():
    data = {"id": ef.LEAGUE_ID, "seasonId": 2026, "scoringPeriodId": 3,
            "status": {"latestScoringPeriod": 3, "transactionScoringPeriod": 4, "finalScoringPeriod": 17}}
    assert ef.current_period(data, 2026) == 3          # transactionScoringPeriod läuft vor: zählt nicht
    data["status"]["latestScoringPeriod"] = 20
    assert ef.current_period(data, 2026) == 17
    del data["status"]["latestScoringPeriod"]
    assert ef.current_period(data, 2026) == 3          # Rückfall auf scoringPeriodId
    with pytest.raises(ef.FetchError):
        ef.current_period(dict(data, seasonId=2025), 2026)


# ---------------------------------------------------------------- Archiv fortschreiben (erfundene Antworten)

class FakeEspn:
    """Erfundene ESPN-Antworten; fetch(params) wie get_json. Der status-Block ändert sich bei jedem Aufruf –
    wie bei ESPN –, damit „nur bei Änderung schreiben“ wirklich geprüft wird."""

    def __init__(self, periods: dict[int, list[dict]], topics: list[dict], current: int):
        self.periods, self.topics, self.current = periods, topics, current
        self.answer_latest = None  # abweichende laufende Periode in den mTransactions2-Antworten
        self.broken: set[int] = set()
        self.without_list: set[int] = set()  # Perioden, für die ESPN die Liste „transactions“ weglässt
        self.calls = itertools.count()

    def fetch(self, params):
        view = params["view"]
        status = {"latestScoringPeriod": self.current, "finalScoringPeriod": 17,
                  "standingsUpdateDate": 1790000000000 + next(self.calls)}
        if view == "mStatus":
            data = {"id": ef.LEAGUE_ID, "seasonId": 2026, "scoringPeriodId": self.current, "status": status}
        elif view == ef.TX_VIEW:
            period = params["scoringPeriodId"]
            if period in self.broken:
                raise ef.FetchError("HTTP 503")
            if self.answer_latest is not None:
                status["latestScoringPeriod"] = self.answer_latest
            data = {"id": ef.LEAGUE_ID, "seasonId": 2026, "scoringPeriodId": period, "status": status,
                    "transactions": self.periods.get(period, [])}
            if period in self.without_list:
                del data["transactions"]
        else:
            data = {"communication": {"topics": self.topics}}
        return json.dumps(data).encode(), data


def tx(*ids):
    return [{"id": i, "status": "EXECUTED"} for i in ids]


def topic(topic_id, kind="ACTIVITY_TRANSACTIONS", text=None):
    message = {"id": f"{topic_id}-m", "messageTypeId": 178} if text is None else {"id": f"{topic_id}-m", "content": text}
    return {"id": topic_id, "type": kind, "messages": [message]}


def files(folder):
    return sorted(p.name for p in folder.iterdir())


def read(path):
    return json.loads(path.read_bytes())


def test_archiv_erster_lauf_und_wiederholung(raw):
    espn = FakeEspn({0: tx("t0"), 1: tx("t1", "t2"), 2: []}, topics=[topic("k1")], current=2)
    assert ef.archive_transactions(2026, espn.fetch, "2026-09-29T0517Z") == (0, [])
    folder = ef.tx_dir(2026)
    assert files(folder) == ["kona_league_communication_2026-09-29T0517Z.json",
                             "mTransactions2_p00.json", "mTransactions2_p01.json", "mTransactions2_p02.json"]
    assert read(folder / "mTransactions2_p01.json")["transactions"] == tx("t1", "t2")

    before = {name: (folder / name).read_bytes() for name in files(folder)}
    assert ef.archive_transactions(2026, espn.fetch, "2026-09-30T0517Z") == (0, [])  # nur status anders
    assert {name: (folder / name).read_bytes() for name in files(folder)} == before


def test_archiv_aenderung_schrumpfung_und_neue_periode(raw):
    espn = FakeEspn({0: tx("t0"), 1: tx("t1", "t2"), 2: tx("t3")}, topics=[topic("k1")], current=2)
    ef.archive_transactions(2026, espn.fetch, "2026-09-29T0517Z")
    folder = ef.tx_dir(2026)

    espn.periods = {0: tx("t0"), 1: tx("t2"), 2: tx("t3", "t4"), 3: tx("t5")}  # t1 weg, t4 neu, Periode 3 neu
    espn.topics, espn.current = [topic("k2")], 3
    errors, warnings = ef.archive_transactions(2026, espn.fetch, "2026-09-30T0517Z")
    assert errors == 0 and len(warnings) == 1 and "p1" in warnings[0]
    assert read(folder / "mTransactions2_p01.json")["transactions"] == tx("t1", "t2")  # bleibt stehen
    assert read(folder / "mTransactions2_p01_2026-09-30T0517Z.json")["transactions"] == tx("t2")
    assert read(folder / "mTransactions2_p02.json")["transactions"] == tx("t3", "t4")
    assert (folder / "mTransactions2_p03.json").exists()
    assert (folder / "kona_league_communication_2026-09-30T0517Z.json").exists()

    # gleiche Lage am Folgetag: Warnung bleibt, aber keine weitere Datei daneben
    count = len(files(folder))
    errors, warnings = ef.archive_transactions(2026, espn.fetch, "2026-10-01T0517Z")
    assert (errors, len(warnings)) == (0, 1)
    assert len(files(folder)) == count


def test_archiv_ohne_chat(raw):
    """Chat-Themen (Texte der Manager) landen nie im Archiv; Änderungen nur im Chat erzeugen keine Datei."""
    espn = FakeEspn({0: []}, current=0, topics=[
        topic("k1"), topic("k2", "ACTIVITY_SETTINGS"), topic("c1", "CHAT_ALL_MEMBERS", text="erfundener Chat-Text")])
    ef.archive_transactions(2026, espn.fetch, "2026-09-29T0517Z")
    stored = ef.tx_dir(2026) / "kona_league_communication_2026-09-29T0517Z.json"
    assert [t["id"] for t in read(stored)["communication"]["topics"]] == ["k1", "k2"]
    assert b"erfundener Chat-Text" not in stored.read_bytes()

    espn.topics = espn.topics[:2] + [topic("c2", "CHAT_ALL_MEMBERS", text="noch ein erfundener Text")]
    ef.archive_transactions(2026, espn.fetch, "2026-09-30T0517Z")
    assert len(list(ef.tx_dir(2026).glob("kona_league_communication_*.json"))) == 1


def test_archiv_speichert_keine_zukunftsperiode(raw):
    """Meldet eine mTransactions2-Antwort eine frühere laufende Periode, wird die angefragte nicht gespeichert."""
    espn = FakeEspn({0: tx("t0"), 1: tx("t1")}, topics=[topic("k1")], current=1)
    espn.answer_latest = 0
    assert ef.archive_transactions(2026, espn.fetch, "2026-09-29T0517Z") == (0, [])
    assert not (ef.tx_dir(2026) / "mTransactions2_p01.json").exists()
    assert (ef.tx_dir(2026) / "mTransactions2_p00.json").exists()


def test_archiv_periode_ohne_liste(raw):
    """Direkt nach dem Periodenwechsel lässt ESPN die Liste weg (29.09.2026, p4): kein Fehler, keine Datei;
    eine schon archivierte Periode mit Einträgen bleibt stehen und erzeugt eine Warnung."""
    espn = FakeEspn({0: tx("t0"), 1: tx("t1")}, topics=[topic("k1")], current=2)
    espn.without_list = {2}
    assert ef.archive_transactions(2026, espn.fetch, "2026-09-29T0517Z") == (0, [])
    folder = ef.tx_dir(2026)
    assert not (folder / "mTransactions2_p02.json").exists()

    espn.without_list = {1}
    before = (folder / "mTransactions2_p01.json").read_bytes()
    errors, warnings = ef.archive_transactions(2026, espn.fetch, "2026-09-30T0517Z")
    assert errors == 0 and len(warnings) == 1 and "p1" in warnings[0]
    assert (folder / "mTransactions2_p01.json").read_bytes() == before
    assert (folder / "mTransactions2_p02.json").exists()  # p2 hat jetzt eine (leere) Liste


def test_archiv_fehler_einer_periode_stoppt_die_anderen_nicht(raw):
    espn = FakeEspn({0: tx("t0"), 1: tx("t1"), 2: tx("t2")}, topics=[topic("k1")], current=2)
    espn.broken = {1}
    errors, _ = ef.archive_transactions(2026, espn.fetch, "2026-09-29T0517Z")
    assert errors == 1
    assert files(ef.tx_dir(2026)) == ["kona_league_communication_2026-09-29T0517Z.json",
                                      "mTransactions2_p00.json", "mTransactions2_p02.json"]


def test_archiv_falsche_periode_wird_nicht_gespeichert(raw):
    espn = FakeEspn({0: tx("t0")}, topics=[topic("k1")], current=0)
    original = espn.fetch

    def wrong_echo(params):
        content, data = original(params)
        if params["view"] == ef.TX_VIEW:
            data = dict(data, scoringPeriodId=5)
        return content, data

    errors, _ = ef.archive_transactions(2026, wrong_echo, "2026-09-29T0517Z")
    assert errors == 1
    assert not (ef.tx_dir(2026) / "mTransactions2_p00.json").exists()


def test_cmd_transactions_nach_saisonende(raw):
    assert ef.cmd_transactions(2026, datetime(2027, 8, 2, 5, 17, tzinfo=timezone.utc)) == 1


# ---------------------------------------------------------------- Aufruf-Optionen

@pytest.mark.parametrize("argv", [
    ["--due", "--weeks", "3"],
    ["--transactions", "--force"],
    ["--due", "--transactions"],
    ["--summary", "--due"],
    [],
])
def test_parse_args_ungueltig(argv):
    with pytest.raises(SystemExit):
        ef.parse_args(argv)


def test_parse_args_gueltig():
    assert ef.parse_args(["--due"]).due
    assert ef.parse_args(["--transactions"]).transactions
    assert ef.parse_args(["--weeks", "3", "1", "3"]).weeks == [1, 3]


# ---------------------------------------------------------------- Pool-Auszug und Tageslauf (Session 6)

@pytest.mark.parametrize("day, week", [(date(2026, 9, 1), 1), (date(2026, 9, 29), 4), (date(2027, 2, 1), 17)])
def test_pool_week(day, week):
    assert ef.pool_week(2026, day) == week


def test_pool_extract_felder():
    data = fake_pool([4])
    first = data["players"][0]
    first.update(status="WAIVERS", waiverProcessDate=1790751600000)
    first["player"].update(ownership={"percentOwned": 64.66, "percentChange": -0.07, "percentStarted": 58.81},
                           injuryStatus="ACTIVE", lastNewsDate=1790569213000)
    extract = ef.pool_extract(data, 2026, 4, "2026-09-29T0645Z")
    assert (extract["season"], extract["woche"], extract["stand"]) == (2026, 4, "2026-09-29T0645Z")
    assert [p["id"] for p in extract["players"]] == list(range(1, 301))
    row = extract["players"][0]
    assert tuple(row) == ef.POOL_KEYS
    assert (row["status"], row["onTeamId"], row["injuryStatus"], row["percentOwned"], row["percentChange"],
            row["percentStarted"], row["waiverProcessDate"], row["lastNewsDate"], row["proj_naechste_woche"]) \
        == ("WAIVERS", 0, "ACTIVE", 64.66, -0.07, 58.81, 1790751600000, 1790569213000, 4.1)
    second = extract["players"][1]
    assert second["percentOwned"] is None and second["status"] is None and second["proj_naechste_woche"] == 4.2
    # ohne Projektion der Woche: None; unvollständiger Pool: Fehler
    assert all(p["proj_naechste_woche"] is None for p in ef.pool_extract(fake_pool([5]), 2026, 4, "x")["players"])
    with pytest.raises(ef.FetchError, match="unvollständig"):
        ef.pool_extract({"players": data["players"][:10]}, 2026, 4, "x")


def test_pool_extract_experten():
    """Expertenränge im Pool-Auszug (Beschluss 09.10.2026; Ränge erfunden, Felder wie bei ESPN am 09.10.2026): je Spieler
    die veröffentlichten PPR-Ränge in der Liste der eigenen Position, aufsteigend und ohne Quellen-IDs; nicht dabei sind
    Quelle 0 (ESPNs Durchschnitt), published=false (Fortsetzung unter der Veröffentlichungstiefe), andere Wochen und
    Typen, fremde Slots und ein zweiter Eintrag derselben Quelle. Kopf experten_quellen = Experten mit Liste."""
    def rank(source, value, slot=2, published=True, week="4", typ="PPR"):
        return week, {"auctionValue": 0, "published": published, "rank": value, "rankSourceId": source,
                      "rankType": typ, "slotId": slot}

    data = fake_pool([4])
    entries = [rank(5, 12), rank(3, 9), rank(7, 14), rank(3, 30),                      # Quelle 3 doppelt: der erste zählt
               rank(0, 0), rank(6, 61, published=False), rank(9, 2, slot=14),         # Durchschnitt, unveröffentlicht, DB
               rank(10, 1, week="5"), rank(11, 4, typ="SUPERFLEX")]                     # andere Woche, anderer Typ
    data["players"][40]["player"]["rankings"] = {}
    for week, entry in entries:
        data["players"][40]["player"]["rankings"].setdefault(week, []).append(entry)
    data["players"][41]["player"]["rankings"] = {"4": [rank(12, 3)[1]]}
    data["players"][0]["player"]["rankings"] = {"4": [rank(5, 7, slot=16)[1]]}       # D/ST in Slot 16
    data["players"][1]["player"]["rankings"] = {"4": []}
    extract = ef.pool_extract(data, 2026, 4, "2026-10-09T0845Z")
    rows = {p["id"]: p for p in extract["players"]}
    assert rows[41]["experten"] == [9, 12, 14] and rows[42]["experten"] == [3] and rows[1]["experten"] == [7]
    assert rows[2]["experten"] is None and rows[300]["experten"] is None
    assert extract["experten_quellen"] == 4                                             # 3, 5, 7, 12
    assert "experten_quellen" in ef.pool_dumps(extract).decode("utf-8").split('"players"')[0]
    # ESPN hat die Woche noch nicht veröffentlicht: keine Ränge, 0 Quellen
    empty = ef.pool_extract(fake_pool([4]), 2026, 4, "x")
    assert empty["experten_quellen"] == 0 and all(p["experten"] is None for p in empty["players"])
    # Abruf: nur die Ränge der Pool-Woche, nur PPR
    flt = json.loads(ef.kona_filter([4], rank_week=4)["X-Fantasy-Filter"])["players"]
    assert (flt["filterRanksForScoringPeriodIds"], flt["filterRanksForRankTypes"]) == ({"value": [4]}, {"value": ["PPR"]})


def test_pool_dumps_und_same_pool():
    extract = ef.pool_extract(fake_pool([4]), 2026, 4, "2026-09-29T0645Z")
    raw = ef.pool_dumps(extract)
    assert json.loads(raw) == extract
    assert sum(1 for line in raw.decode("utf-8").splitlines() if line.startswith('{"id":')) == 300
    later = dict(extract, stand="2026-09-29T0745Z")
    assert ef.same_pool(extract, later) and not ef.same_pool(None, extract)
    changed = json.loads(raw)
    changed["players"][0]["percentOwned"] = 1.0
    assert not ef.same_pool(extract, changed)


RANKS = [6, 10, 5, 7, 3, 1, 4, 8, 9, 2]   # erfundene Waiver-Reihenfolge: Team 1 auf Platz 6, Team 6 zuerst


def fake_mteam(ranks=RANKS) -> dict:
    """mTeam-Antwort mit zehn Teams und waiverRank; Namen und members sind erfunden und dürfen nie im Auszug landen."""
    return {"id": ef.LEAGUE_ID, "seasonId": 2026, "members": [{"id": "{m1}", "displayName": "Testmanager"}],
            "teams": [{"id": i, "name": f"Testteam {i}", "waiverRank": r} for i, r in zip(range(1, 11), ranks)]}


IR = {1: [101], 7: [701]}   # erfundene IR-Slots: Team 1 Spieler 101, Team 7 Spieler 701


def fake_mroster(ir=IR, trades=None) -> dict:
    """mRoster-Antwort mit zehn Teams und je zwei Einträgen (Bank und – laut ir – IR), dazu laut trades (team_id →
    [(Spieler, Datum)]) per Trade gekommene Spieler; Namen sind erfunden und dürfen nie im Auszug landen."""
    return {"id": ef.LEAGUE_ID, "seasonId": 2026,
            "teams": [{"id": i, "roster": {"entries": [
                {"playerId": i * 100 + 50, "lineupSlotId": 20, "playerPoolEntry": {"player": {"fullName": "Testspieler"}}}]
                + [{"playerId": pid, "lineupSlotId": ef.SLOT_IR_ID} for pid in ir.get(i, [])]
                + [{"playerId": pid, "lineupSlotId": 20, "acquisitionType": "TRADE", "acquisitionDate": date}
                   for pid, date in (trades or {}).get(i, [])]}} for i in range(1, 11)]}


class FakePoolSession:
    """Beantwortet den Spielerpool (kona) mit erfundenen Spielern, mTeam mit erfundenen Waiver-Rängen und mRoster
    mit erfundenen IR-Slots; owned setzt den Besitz von Spieler 1, ranks die Reihenfolge, ir die IR-Slots,
    mteam_broken bzw. roster_broken lassen nur mTeam bzw. mRoster scheitern."""

    def __init__(self):
        self.owned, self.broken, self.weeks, self.filters = None, False, [], []
        self.ranks, self.mteam_broken, self.mteam_calls = list(RANKS), False, 0
        self.ir, self.roster_broken, self.trades = dict(IR), False, {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        if params["view"] == ef.TEAM_VIEW:
            self.mteam_calls += 1
            return FakeResponse(503, b"down") if self.mteam_broken else ok(fake_mteam(self.ranks))
        if params["view"] == ef.ROSTER_VIEW:
            return FakeResponse(503, b"down") if self.roster_broken else ok(fake_mroster(self.ir, self.trades))
        assert params["view"] == ef.KONA_VIEW
        if self.broken:
            return FakeResponse(503, b"down")
        flt = json.loads(headers["X-Fantasy-Filter"])["players"]
        week = flt["filterStatsForCurrentSeasonScoringPeriodId"]["value"][0]
        self.weeks.append(week)
        self.filters.append(flt)
        data = fake_pool([week])
        if self.owned is not None:
            data["players"][0]["player"]["ownership"] = {"percentOwned": self.owned}
        return ok(data)


def test_update_pool_schreibt_nur_bei_aenderung(raw):
    session = FakePoolSession()
    now = datetime(2026, 9, 29, 6, 45, tzinfo=timezone.utc)
    path = ef.pool_dir(2026) / ef.POOL_FILE
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0645Z")
    assert (errors, current["stand"], session.weeks) == (0, "2026-09-29T0645Z", [4])
    first = path.read_bytes()
    assert json.loads(first)["woche"] == 4
    # unverändert: keine neue Datei, der alte Stand bleibt (stand = letzte Änderung)
    errors, current = ef.update_pool(session, 2026, now + timedelta(hours=1), "2026-09-29T0745Z")
    assert errors == 0 and path.read_bytes() == first and current["stand"] == "2026-09-29T0645Z"
    # Besitz ändert sich: neue Datei mit neuem Stand
    session.owned = 50.0
    errors, current = ef.update_pool(session, 2026, now + timedelta(hours=2), "2026-09-29T0845Z")
    assert errors == 0 and json.loads(path.read_bytes())["stand"] == "2026-09-29T0845Z"
    assert current["players"][0]["percentOwned"] == 50.0
    # ESPN-Fehler: Datei bleibt, kein aktueller Auszug
    session.broken = True
    errors, current = ef.update_pool(session, 2026, now, "x")
    assert errors == 1 and current is None and json.loads(path.read_bytes())["stand"] == "2026-09-29T0845Z"


class FakeDailySession(FakePoolSession):
    """Tageslauf-Fake: Spielerpool wie FakePoolSession, Transaktionen und Aktivitäten über FakeEspn."""

    def __init__(self, espn: FakeEspn):
        super().__init__()
        self.espn = espn

    def get(self, url, params=None, headers=None, timeout=None):
        if params["view"] in (ef.KONA_VIEW, ef.TEAM_VIEW, ef.ROSTER_VIEW):
            return super().get(url, params, headers, timeout)
        content, _ = self.espn.fetch(params)
        return FakeResponse(200, content)


def test_cmd_daily_transaktionen_und_pool(raw, monkeypatch):
    session = FakeDailySession(FakeEspn({0: tx("t0"), 1: tx("t1")}, topics=[topic("k1")], current=1))
    monkeypatch.setattr(ef.requests, "Session", lambda: session)
    now = datetime(2026, 9, 29, 6, 45, tzinfo=timezone.utc)
    assert ef.cmd_daily(2026, now, transactions=True, pool=True) == 0
    assert (ef.pool_dir(2026) / ef.POOL_FILE).exists()
    assert files(ef.tx_dir(2026)) == ["kona_league_communication_2026-09-29T0645Z.json",
                                      "mTransactions2_p00.json", "mTransactions2_p01.json"]
    # Pool-Fehler macht den Lauf rot, das Archiv wird trotzdem fortgeschrieben
    session.broken = True
    session.espn.periods[1] = tx("t1", "t2")
    assert ef.cmd_daily(2026, now, transactions=True, pool=True) == 1
    assert len(read(ef.tx_dir(2026) / "mTransactions2_p01.json")["transactions"]) == 2
    # nur --transactions: kein Pool-Aufruf
    session.broken = False
    calls = len(session.weeks)
    assert ef.cmd_daily(2026, now, transactions=True) == 0 and len(session.weeks) == calls


def test_cmd_daily_nach_saisonende(raw):
    assert ef.cmd_daily(2026, datetime(2027, 8, 2, 5, 17, tzinfo=timezone.utc), pool=True) == 1


def test_parse_args_tageslauf():
    args = ef.parse_args(["--transactions", "--pool", "--wetter"])
    assert (args.transactions, args.pool, args.wetter, args.news) == (True, True, True, False)
    assert ef.parse_args(["--pool", "--news"]).news and ef.parse_args(["--wetter"]).wetter
    for argv in (["--news"], ["--pool", "--due"], ["--wetter", "--weeks", "1"], ["--summary", "--pool"]):
        with pytest.raises(SystemExit):
            ef.parse_args(argv)


def test_update_pool_unlesbare_datei_wird_ersetzt(raw, capsys):
    path = ef.pool_dir(2026) / ef.POOL_FILE
    path.parent.mkdir(parents=True)
    path.write_text("{kaputt", encoding="utf-8")
    errors, current = ef.update_pool(FakePoolSession(), 2026, datetime(2026, 9, 29, 6, 45, tzinfo=timezone.utc), "x")
    assert errors == 0 and current["woche"] == 4 and json.loads(path.read_bytes())["woche"] == 4
    assert "unlesbar" in capsys.readouterr().out


def test_update_pool_faengt_alle_fehler(raw, capsys):
    """Unbekannter Saisonkalender und Datei mit falscher Struktur enden als FEHLER-Zeile bzw. Neuschreiben, nie als Traceback."""
    assert ef.update_pool(FakePoolSession(), 2031, datetime(2031, 9, 9, tzinfo=timezone.utc), "x") == (1, None)
    assert "Wochenkalender" in capsys.readouterr().err
    path = ef.pool_dir(2026) / ef.POOL_FILE
    path.parent.mkdir(parents=True)
    for content in ("[1, 2, 3]", "null", '{"players": {}}', '{"players": []}'):
        path.write_text(content, encoding="utf-8")
        errors, current = ef.update_pool(FakePoolSession(), 2026, datetime(2026, 9, 29, 6, 45, tzinfo=timezone.utc), "x")
        assert errors == 0 and current["woche"] == 4 and json.loads(path.read_bytes())["woche"] == 4, content


def test_fetch_waiver_order():
    """waiverRank je Team als Text-Schlüssel (wie im JSON), nach team_id sortiert; unbrauchbare Antworten sind Fehler."""
    session = FakePoolSession()
    order = ef.fetch_waiver_order(session, 2026)
    assert order == {str(i): r for i, r in zip(range(1, 11), RANKS)} and list(order) == [str(i) for i in range(1, 11)]
    session.mteam_broken = True
    with pytest.raises(ef.FetchError, match="HTTP 503"):
        ef.fetch_waiver_order(session, 2026)
    session.mteam_broken = False
    session.ranks = [1, 1, 3, 4, 5, 6, 7, 8, 9, 10]          # zwei Teams auf Platz 1
    with pytest.raises(ef.FetchError, match="keine Reihenfolge"):
        ef.fetch_waiver_order(session, 2026)
    session.ranks = [None] + RANKS[1:]                       # Rang fehlt
    with pytest.raises(ef.FetchError, match="ohne waiverRank"):
        ef.fetch_waiver_order(session, 2026)
    with pytest.raises(ef.FetchError, match="ohne Teams"):
        ef.fetch_waiver_order(StubSession(dict(fake_mteam(), teams=[])), 2026)
    with pytest.raises(ef.FetchError, match="Liga und Saison"):
        ef.fetch_waiver_order(StubSession(dict(fake_mteam(), seasonId=2025)), 2026)


def test_update_pool_mit_waiver_reihenfolge(raw, capsys):
    """Der Auszug trägt die Reihenfolge; ändert nur sie sich, gibt es eine neue Datei; scheitert mTeam, bleibt die
    Reihenfolge des letzten Laufs (Warnung), beim ersten Lauf None. Namen und members aus mTeam landen nie im Auszug."""
    session = FakePoolSession()
    now = datetime(2026, 9, 29, 6, 45, tzinfo=timezone.utc)
    path = ef.pool_dir(2026) / ef.POOL_FILE
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0645Z")
    assert errors == 0 and current["waiver_reihenfolge"] == {str(i): r for i, r in zip(range(1, 11), RANKS)}
    saved, text = json.loads(path.read_bytes()), path.read_text(encoding="utf-8")
    assert saved["waiver_reihenfolge"]["6"] == 1 and "Testteam" not in text and "Testmanager" not in text
    assert saved["waiver_reihenfolge_stand"] == "2026-09-29T0645Z"
    assert list(saved) == ["season", "woche", "stand", "experten_quellen", "quelle", "waiver_reihenfolge",
                           "waiver_reihenfolge_stand", "ir_slot", "ir_slot_stand", "trades", "players"]
    # der Pool-Abruf holt die Expertenränge der Pool-Woche (nur PPR), nicht die aller Wochen
    assert all(f["filterRanksForScoringPeriodIds"] == {"value": [f["filterStatsForCurrentSeasonScoringPeriodId"]["value"][0]]}
               and f["filterRanksForRankTypes"] == {"value": ["PPR"]} for f in session.filters) and session.filters
    # unverändert (auch die Reihenfolge): keine neue Datei, kein neuer Stand der Reihenfolge
    errors, current = ef.update_pool(session, 2026, now + timedelta(minutes=30), "2026-09-29T0715Z")
    assert errors == 0 and current["stand"] == "2026-09-29T0645Z" and current["waiver_reihenfolge_stand"] == "2026-09-29T0645Z"
    # nur die Reihenfolge ändert sich (Waiver verarbeitet): neue Datei mit neuem Stand, auch für die Reihenfolge
    session.ranks = RANKS[1:] + RANKS[:1]
    errors, current = ef.update_pool(session, 2026, now + timedelta(hours=1), "2026-09-29T0745Z")
    assert errors == 0 and json.loads(path.read_bytes())["stand"] == "2026-09-29T0745Z"
    assert current["waiver_reihenfolge"]["1"] == 10 and current["waiver_reihenfolge_stand"] == "2026-09-29T0745Z"
    # mTeam scheitert: Warnung, Reihenfolge des letzten Laufs, Datei unverändert
    session.mteam_broken = True
    errors, current = ef.update_pool(session, 2026, now + timedelta(hours=2), "2026-09-29T0845Z")
    assert errors == 0 and current["waiver_reihenfolge"]["1"] == 10
    assert json.loads(path.read_bytes())["stand"] == "2026-09-29T0745Z"
    assert "Waiver-Reihenfolge (mTeam) nicht abrufbar" in capsys.readouterr().out
    # mTeam scheitert und der Besitz ändert sich: neuer Pool-Stand, die Reihenfolge behält ihren alten Stand
    session.owned = 50.0
    errors, current = ef.update_pool(session, 2026, now + timedelta(hours=3), "2026-09-29T0945Z")
    saved = json.loads(path.read_bytes())
    assert errors == 0 and saved["stand"] == "2026-09-29T0945Z" and saved["waiver_reihenfolge_stand"] == "2026-09-29T0745Z"
    assert saved["waiver_reihenfolge"]["1"] == 10
    # erster Lauf ohne mTeam: Reihenfolge und Stand None, der Auszug wird trotzdem geschrieben
    path.unlink()
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T1045Z")
    assert errors == 0 and current["waiver_reihenfolge"] is None and current["waiver_reihenfolge_stand"] is None
    assert json.loads(path.read_bytes())["waiver_reihenfolge"] is None and session.mteam_calls == 6


def test_pool_extract_verlangt_32_dst():
    data = fake_pool([4])
    data["players"][0]["player"]["defaultPositionId"] = 2  # nur noch 31 D/ST
    with pytest.raises(ef.FetchError, match="31 statt 32"):
        ef.pool_extract(data, 2026, 4, "x")


def test_fetch_ir_slots():
    """IR-Slots je Team als Text-Schlüssel, sortierte IDs, Teams ohne IR mit leerer Liste; unbrauchbare Antworten
    sind Fehler."""
    session = FakePoolSession()
    ir = ef.fetch_ir_slots(session, 2026)
    assert ir == {str(i): IR.get(i, []) for i in range(1, 11)} and list(ir) == [str(i) for i in range(1, 11)]
    session.roster_broken = True
    with pytest.raises(ef.FetchError, match="HTTP 503"):
        ef.fetch_ir_slots(session, 2026)
    with pytest.raises(ef.FetchError, match="ohne Teams"):
        ef.fetch_ir_slots(StubSession(dict(fake_mroster(), teams=[])), 2026)
    with pytest.raises(ef.FetchError, match="Liga und Saison"):
        ef.fetch_ir_slots(StubSession(dict(fake_mroster(), seasonId=2025)), 2026)
    broken = fake_mroster()
    broken["teams"][0]["roster"]["entries"][0].pop("lineupSlotId")
    with pytest.raises(ef.FetchError, match="ohne Slot"):
        ef.fetch_ir_slots(StubSession(broken), 2026)


def test_update_pool_mit_ir_slots(raw, capsys):
    """IR-Slots im Kopf des Pool-Auszugs mit Stand ihrer letzten Änderung; scheitert mRoster, bleibt der alte Stand
    (Warnung); keine Namen im Auszug."""
    session = FakePoolSession()
    now = datetime(2026, 9, 29, 6, 45, tzinfo=timezone.utc)
    path = ef.pool_dir(2026) / ef.POOL_FILE
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0645Z")
    assert errors == 0 and current["ir_slot"]["7"] == [701] and current["ir_slot_stand"] == "2026-09-29T0645Z"
    assert "Testspieler" not in path.read_text(encoding="utf-8")
    session.ir = {1: [101], 7: []}                          # Spieler 701 kommt vom IR zurück
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0745Z")
    assert current["ir_slot"]["7"] == [] and current["ir_slot_stand"] == "2026-09-29T0745Z"
    session.roster_broken, session.owned = True, 12.0       # mRoster fällt aus, der Pool ändert sich trotzdem
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0845Z")
    assert errors == 0 and current["ir_slot"]["7"] == [] and current["ir_slot_stand"] == "2026-09-29T0745Z"
    assert "IR-Slots" in capsys.readouterr().out


def test_fetch_roster_state_trades():
    """Per Trade gekommene Spieler aus mRoster (acquisitionType TRADE): Spieler-ID als Text → [team_id, Datum], nach
    ID sortiert; Draft und Zugänge bleiben draußen, ein fehlendes Datum wird None. Die IR-Slots kommen aus demselben
    Aufruf. Erfundene Spieler."""
    data = fake_mroster()
    data["teams"][6]["roster"]["entries"] += [
        {"playerId": 9002, "lineupSlotId": 20, "acquisitionType": "TRADE", "acquisitionDate": 1788287280000},
        {"playerId": 9001, "lineupSlotId": 2, "acquisitionType": "TRADE"},
        {"playerId": 9003, "lineupSlotId": 20, "acquisitionType": "ADD", "acquisitionDate": 1788287280001},
        {"playerId": 9004, "lineupSlotId": 20, "acquisitionType": "DRAFT", "acquisitionDate": 1788110942930}]
    ir, trades = ef.fetch_roster_state(StubSession(data), 2026)
    assert ir == ef.fetch_ir_slots(StubSession(data), 2026) and ir["7"] == [701]
    assert trades == {"9001": [7, None], "9002": [7, 1788287280000]} and list(trades) == ["9001", "9002"]
    assert ef.fetch_roster_state(StubSession(fake_mroster()), 2026)[1] == {}


def test_update_pool_mit_trades(raw):
    """Trades im Kopf des Pool-Auszugs; scheitert mRoster, bleiben die Trades des letzten Laufs, beim ersten Lauf None."""
    session = FakePoolSession()
    now = datetime(2026, 9, 29, 6, 45, tzinfo=timezone.utc)
    path = ef.pool_dir(2026) / ef.POOL_FILE
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0645Z")
    assert errors == 0 and current["trades"] == {} and json.loads(path.read_bytes())["trades"] == {}
    session.trades = {7: [(9002, 1788287280000)]}           # erfundener Spieler 9002 kommt per Trade zu Team 7
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0715Z")
    expected = {"9002": [7, 1788287280000]}
    assert errors == 0 and current["trades"] == expected and current["stand"] == "2026-09-29T0715Z"
    assert json.loads(path.read_bytes())["trades"] == expected
    session.roster_broken, session.owned = True, 12.0       # mRoster fällt aus, der Pool ändert sich trotzdem
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0745Z")
    assert errors == 0 and current["trades"] == expected and json.loads(path.read_bytes())["trades"] == expected
    path.unlink()
    errors, current = ef.update_pool(session, 2026, now, "2026-09-29T0845Z")
    assert errors == 0 and current["trades"] is None and current["ir_slot"] is None
