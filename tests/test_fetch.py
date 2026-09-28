"""Tests Abruf-Logik der Automatisierung (Baustein 3): Wochenkalender, fällige Wochen, Abruf, Transaktions-Archiv.

Alles offline: Wochen sind Temp-Kopien von W1 mit gesetztem Matchup-Status, ESPN wird durch Fakes ersetzt.
Die Archiv-Antworten sind erfundene Testdaten (IDs wie „t1“, „k1“ – keine echten Transaktionen).
Aufruf: python -m pytest
"""

import itertools
import json
import shutil
from datetime import date, datetime, timezone

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


# ---------------------------------------------------------------- Abruf einer fälligen Woche (Fake-Session statt ESPN)

class FakeResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code, self.content = status_code, content
        self.text = content.decode("utf-8", errors="replace")


class FakeSession:
    """Ersetzt requests.Session: liefert je (View, Woche) vorbereitete Antworten und merkt sich die Anfragen."""

    def __init__(self, answers: dict[tuple[str, int], FakeResponse]):
        self.answers, self.requests = answers, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, timeout=None):
        key = (params["view"], params.get("scoringPeriodId"))
        self.requests.append(key)
        return self.answers[key]


@pytest.fixture
def espn_week3(raw, monkeypatch):
    """W1–2 final, W3 lokal noch laufend; ESPN meldet W3 inzwischen abgeschlossen."""
    make_week(1, final=True)
    make_week(2, final=True)
    make_week(3, final=False)
    answers = {(view, 3): FakeResponse(200, json.dumps(data).encode())
               for view, data in week_views(3, final=True).items()}
    session = FakeSession(answers)
    monkeypatch.setattr(ef.requests, "Session", lambda: session)
    return session


def snapshot(week: int) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(ef.week_dir(2026, week).iterdir())}


def test_cmd_due_holt_nur_die_faellige_woche(espn_week3):
    before = {week: snapshot(week) for week in (1, 2)}
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 0
    assert ef.is_final(2026, 3)
    assert {week for _, week in espn_week3.requests} == {3}
    assert {week: snapshot(week) for week in (1, 2)} == before   # finale Wochen byte-gleich


def test_cmd_fetch_teilfehler_schreibt_nichts(espn_week3):
    espn_week3.answers[("mRoster", 3)] = FakeResponse(503, b"Service Unavailable")
    before = snapshot(3)
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 1
    assert snapshot(3) == before          # auch das neue, finale mMatchupScore nicht
    assert not ef.is_final(2026, 3)       # der nächste Lauf holt die Woche erneut


def test_cmd_fetch_falsche_woche_wird_abgelehnt(espn_week3):
    wrong = week_views(3, final=True)["mTeam"]
    wrong["scoringPeriodId"] = 2
    espn_week3.answers[("mTeam", 3)] = FakeResponse(200, json.dumps(wrong).encode())
    before = snapshot(3)
    assert ef.cmd_due(2026, date(2026, 9, 29)) == 1
    assert snapshot(3) == before


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
