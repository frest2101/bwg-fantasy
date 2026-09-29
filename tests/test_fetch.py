"""Tests Abruf-Logik der Automatisierung (Baustein 3): Wochenkalender, fällige Wochen, Abruf, Transaktions-Archiv.

Alles offline: Wochen sind Temp-Kopien von W1 mit gesetztem Matchup-Status, ESPN wird durch Fakes ersetzt.
Die Archiv-Antworten sind erfundene Testdaten (IDs wie „t1“, „k1“ – keine echten Transaktionen).
Aufruf: python -m pytest
"""

import itertools
import json
import shutil
from datetime import date, datetime, timedelta, timezone

import pytest

import espn_fetch as ef

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


class FakeLeague:
    """Ersetzt requests.Session: beantwortet Liga-Views, Spielerpool, Spielplan und Draft mit erfundenen Daten.

    week_answers[(view, woche)] überschreibt einzelne Antworten; requests merkt sich jede Anfrage als Schlüssel.
    """

    def __init__(self, final_week: int):
        self.week_answers = {(view, final_week): ok(data) for view, data in week_views(final_week, final=True).items()}
        self.requests: list[tuple] = []
        self.drafted = True
        self.dst_games = lambda pid: 17
        self.schedule_teams = 33          # inkl. Team 0 (Free Agent)
        self.standings_echo = None        # abweichende Woche im mStandings-Echo
        self.pool_without_week: set[int] = set()  # Wochen, für die der Spielerpool keine Werte liefert

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        view, week = params["view"], params.get("scoringPeriodId")
        if view == ef.KONA_VIEW:
            flt = json.loads(headers["X-Fantasy-Filter"])["players"]
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
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0                 # Nachlauf: nur der Spielplan wird geprüft
    assert espn_week3.requests == [("spielplan", 2026)]


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


def test_saisondateien(espn_week3):
    files = ef.season_files(2026)
    espn_week3.drafted = False
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert files["schedule"].exists() and files["prior_schedule"].exists() and files["prior_dst"].exists()
    assert not files["draft"].exists()                               # vor dem Draft: nichts, kein Fehler
    espn_week3.drafted = True
    espn_week3.requests.clear()
    before = files["schedule"].stat().st_mtime_ns
    assert ef.cmd_due(2026, date(2026, 9, 30)) == 0
    assert files["draft"].exists()
    assert ("dst_vorjahr",) not in espn_week3.requests               # einmalig
    assert files["schedule"].stat().st_mtime_ns == before            # unverändert → nicht neu geschrieben


def test_dst_vorjahr_braucht_alle_17_spiele(espn_week3, capsys):
    """Nebenteil: nicht speichern, warnen – aber die fällige Woche wird trotzdem geschrieben (Lauf grün)."""
    espn_week3.dst_games = lambda pid: 16 if pid == 7 else 17
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert not ef.season_files(2026)["prior_dst"].exists()
    assert ef.is_final(2026, 3)
    assert "Fehler bei Saisondateien oder beim Nachholen" in capsys.readouterr().out  # Präfix je nach Umgebung


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


class FakePoolSession:
    """Beantwortet nur den Spielerpool (kona) mit erfundenen Spielern; owned setzt den Besitz von Spieler 1."""

    def __init__(self):
        self.owned, self.broken, self.weeks = None, False, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        assert params["view"] == ef.KONA_VIEW
        if self.broken:
            return FakeResponse(503, b"down")
        week = json.loads(headers["X-Fantasy-Filter"])["players"]["filterStatsForCurrentSeasonScoringPeriodId"]["value"][0]
        self.weeks.append(week)
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
        if params["view"] == ef.KONA_VIEW:
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


def test_pool_extract_verlangt_32_dst():
    data = fake_pool([4])
    data["players"][0]["player"]["defaultPositionId"] = 2  # nur noch 31 D/ST
    with pytest.raises(ef.FetchError, match="31 statt 32"):
        ef.pool_extract(data, 2026, 4, "x")
