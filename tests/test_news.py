"""Tests News je Spieler (scripts/news.py, Stufe 2 – vorbereitet, im Tageslauf aus).

Offline mit erfundenen Meldungen („Testmeldung“) und erfundenen Spielern; ESPN wird durch Fake-Sessions ersetzt.
Aufruf: python -m pytest
"""

import json
from datetime import datetime, timezone

import pytest

import espn_fetch as ef
import news
from test_fetch import FakeEspn, fake_pool, ok, topic, tx


def pool(*players):
    """Pool-Auszug mit (id, onTeamId, lastNewsDate) je Spieler."""
    return {"season": 2026, "woche": 4, "stand": "x",
            "players": [{"id": pid, "onTeamId": team, "lastNewsDate": date} for pid, team, date in players]}


def test_candidates_gegen_gemerkten_stand():
    now = pool((1, 2, 200), (2, 0, 100), (3, 5, 300), (4, 0, 200), (5, 0, 200), (6, 1, None))
    state = {1: 100, 2: 100, 4: 200}
    assert news.candidates(state, now, {1, 2, 3, 4, 6}) == [1, 3]    # 2 und 4 auf Stand, 5 uninteressant, 6 ohne Datum
    assert news.candidates({}, now, {1, 2, 3, 4, 5, 6}) == [1, 2, 3, 4, 5]  # erster Lauf: alle mit lastNewsDate


def test_extract_nur_verweise():
    feed = [{"id": 1, "type": "Rotowire", "headline": "Testmeldung 1", "published": "2026-09-27T20:54:17Z",
             "story": "langer Text", "playerId": 7, "links": {"api": {}, "mobile": {"href": "m"}}},
            {"id": 2, "type": "Story", "headline": "Testmeldung 2", "published": "2026-09-25T21:36:38Z",
             "links": {"web": {"href": "https://www.espn.com/x"}}},
            "kaputt"]
    rows = news.extract(feed, 7)
    assert rows == [{"player_id": 7, "id": 1, "typ": "Rotowire", "schlagzeile": "Testmeldung 1",
                     "datum": "2026-09-27T20:54:17Z", "link": None},
                    {"player_id": 7, "id": 2, "typ": "Story", "schlagzeile": "Testmeldung 2",
                     "datum": "2026-09-25T21:36:38Z", "link": "https://www.espn.com/x"}]
    assert all(set(r) == set(news.KEYS) for r in rows)  # nie „story“


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code, self.text = status_code, json.dumps(payload)

    def json(self):
        return json.loads(self.text)


class FakeNews:
    def __init__(self, feeds: dict[int, list]):
        self.feeds, self.calls, self.broken = feeds, [], set()

    def get(self, url, params=None, timeout=None):
        pid = params["playerId"]
        self.calls.append(pid)
        if pid in self.broken:
            return FakeResponse(500, {})
        return FakeResponse(200, {"feed": self.feeds.get(pid, [])})


def item(item_id, date="2026-09-27T20:54:17Z"):
    return {"id": item_id, "type": "Rotowire", "headline": f"Testmeldung {item_id}", "published": date, "links": {}}


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path)
    return tmp_path / "raw"


def news_files():
    return sorted(p.name for p in news.news_dir(2026).glob("????-??-??T????Z.json"))


def meldungen(name):
    return [(m["player_id"], m["id"]) for m in ef.load_json(news.news_dir(2026) / name)["meldungen"]]


def test_run_erstlauf_folgelauf_und_stand(raw):
    espn = FakeNews({1: [item("a"), item("b", "2026-09-28T10:00:00Z")], 2: [item("c")]})
    # erster Lauf: Stand leer, beide Kaderspieler werden abgefragt
    assert news.run(espn, 2026, pool((1, 2, 200), (2, 3, 100)), "2026-09-29T1140Z") == (0, [])
    assert news_files() == ["2026-09-29T1140Z.json"] and espn.calls == [1, 2]
    assert meldungen("2026-09-29T1140Z.json") == [(1, "a"), (2, "c"), (1, "b")]  # nach Datum sortiert
    assert news.load_state(2026) == {1: 200, 2: 100}
    # Folgelauf: nur Spieler 2 hat ein neues Datum; Meldung c ist für ihn schon archiviert, d ist neu
    espn.feeds[2] = [item("c"), item("d", "2026-09-29T09:00:00Z")]
    assert news.run(espn, 2026, pool((1, 2, 200), (2, 3, 300)), "2026-09-29T1540Z") == (0, [])
    assert meldungen("2026-09-29T1540Z.json") == [(2, "d")] and espn.calls == [1, 2, 2]
    assert news.load_state(2026) == {1: 200, 2: 300}
    # nichts Neues: keine Abfrage, keine Datei
    assert news.run(espn, 2026, pool((1, 2, 200), (2, 3, 300)), "2026-09-29T1640Z") == (0, [])
    assert len(news_files()) == 2 and espn.calls == [1, 2, 2]


def test_gleiche_meldung_bei_zwei_spielern(raw):
    """Eine Meldung (z. B. Trade) zu zwei Spielern wird je Spieler archiviert – auch in getrennten Läufen."""
    espn = FakeNews({1: [item("t")], 2: [item("t")]})
    news.run(espn, 2026, pool((1, 2, 100), (2, 3, None)), "2026-09-29T1140Z")
    news.run(espn, 2026, pool((1, 2, 100), (2, 3, 100)), "2026-09-29T1240Z")
    assert meldungen("2026-09-29T1140Z.json") == [(1, "t")] and meldungen("2026-09-29T1240Z.json") == [(2, "t")]


def test_fehler_und_grenze_werden_nachgeholt(raw, monkeypatch):
    monkeypatch.setattr(news, "MAX_PLAYERS", 2)
    espn = FakeNews({pid: [item(f"m{pid}")] for pid in (1, 2, 3)})
    espn.broken.add(2)
    errors, warnings = news.run(espn, 2026, pool((1, 2, 100), (2, 3, 100), (3, 4, 100)), "2026-09-29T1140Z")
    assert errors == 0 and len(warnings) == 2  # ein Fehler, ein zurückgestellter Spieler
    assert meldungen("2026-09-29T1140Z.json") == [(1, "m1")] and news.load_state(2026) == {1: 100}
    # nächster Lauf ohne neue Daten: Spieler 2 (Fehler) und 3 (zurückgestellt) kommen dran
    espn.broken.clear()
    assert news.run(espn, 2026, pool((1, 2, 100), (2, 3, 100), (3, 4, 100)), "2026-09-29T1240Z") == (0, [])
    assert meldungen("2026-09-29T1240Z.json") == [(2, "m2"), (3, "m3")] and news.load_state(2026) == {1: 100, 2: 100, 3: 100}
    assert espn.calls == [1, 2, 2, 3]


def test_interesting_ids_mit_app_spielern(raw):
    assert news.interesting_ids(2026, pool((1, 2, 1), (2, 0, 1))) == {1}
    app = ef.REPO_DIR / "app" / "data"
    app.mkdir(parents=True)
    (app / "players.json").write_text(json.dumps({"players": [{"id": 2}, {"id": 9}]}), encoding="utf-8")
    assert news.interesting_ids(2026, pool((1, 2, 1), (2, 0, 1))) == {1, 2, 9}


class FakeTageslauf:
    """Tageslauf-Fake für --pool --news: Spielerpool (erfundene Testspieler, Spieler 1 im Kader mit lastNewsDate),
    Transaktionen über FakeEspn und der News-Endpunkt."""

    def __init__(self):
        self.espn = FakeEspn({0: tx("t0")}, topics=[topic("k1")], current=1)
        self.news = FakeNews({1: [item("n1")]})
        self.pool_broken = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        if url == news.NEWS_URL:
            return self.news.get(url, params, timeout)
        if params["view"] == ef.KONA_VIEW:
            if self.pool_broken:
                raise ef.requests.ConnectionError("down")
            data = fake_pool([4])
            data["players"][0]["onTeamId"] = 2
            data["players"][0]["player"]["lastNewsDate"] = 100
            return ok(data)
        content, _ = self.espn.fetch(params)
        from test_fetch import FakeResponse as EspnResponse
        return EspnResponse(200, content)


def test_cmd_daily_mit_news(raw, monkeypatch):
    session = FakeTageslauf()
    monkeypatch.setattr(ef.requests, "Session", lambda: session)
    now = datetime(2026, 9, 29, 11, 45, tzinfo=timezone.utc)
    assert ef.cmd_daily(2026, now, transactions=True, pool=True, news=True) == 0
    assert news_files() == ["2026-09-29T1145Z.json"] and meldungen("2026-09-29T1145Z.json") == [(1, "n1")]
    assert session.news.calls == [1] and news.load_state(2026) == {1: 100}
    # ohne --news läuft nichts; bei Pool-Fehler wird News übersprungen (kein Auszug)
    assert ef.cmd_daily(2026, now, pool=True) == 0 and session.news.calls == [1]
    session.pool_broken = True
    assert ef.cmd_daily(2026, now, pool=True, news=True) == 1 and session.news.calls == [1]


def test_parse_args_news_nur_mit_pool():
    with pytest.raises(SystemExit):
        ef.parse_args(["--news"])
    assert ef.parse_args(["--pool", "--news"]).news
