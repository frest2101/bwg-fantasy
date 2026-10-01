"""Marktwerte von FantasyCalc (scripts/fantasycalc.py): Auszug, Prüfungen, Tagessperre im Tageslauf.

Offline mit Fake-Sitzungen. Alle Spieler, Werte und Picks hier sind erfunden („Testspieler“, IDs aus der Laufnummer).
Aufruf: python -m pytest
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

import espn_fetch as ef
import fantasycalc as fc
from test_fetch import FakeDailySession, FakeEspn, topic, tx

STAND = "2026-10-01T0826Z"


def liste(n: int = 210, picks: int = 3, ohne_espn=(5,), espn=lambda i: i * 7) -> list[dict]:
    """Erfundene Antwort von values/current: n Spieler mit Rang 1 … n, dazu Picks dazwischen (Rang des nächsten
    Spielers, wie bei FantasyCalc); Spieler i hat die ESPN-ID espn(i) als Text, außer den Laufnummern in ohne_espn."""
    rows = [{"value": 10_000 - 10 * i, "overallRank": i, "positionRank": i, "trend30Day": 5 - i % 11,
             "redraftValue": 0 if i % 2 else 500 + i, "starter": False, "maybeTier": 1,
             "player": {"id": 9000 + i, "name": f"Testspieler {i}", "position": "WR", "maybeAge": 25.0,
                        "espnId": None if i in ohne_espn else str(espn(i))}}
            for i in range(1, n + 1)]
    for k in range(picks):
        rank = 11 + 20 * k
        rows.insert(rank - 1 + k, {"value": 4000, "overallRank": rank, "positionRank": k + 1, "trend30Day": 0,
                                   "redraftValue": 0, "player": {"id": 15000 + k, "name": f"2027 Testpick {k}",
                                                                 "position": "PICK", "espnId": None}})
    return rows


def pool_ids(n: int = 210) -> set[int]:
    return {i * 7 for i in range(1, n + 1)}


def test_auszug():
    ext = fc.extract(liste(), pool_ids(), STAND)
    assert (ext["quelle"], ext["stand"], ext["parameter"]) == (fc.QUELLE, STAND, fc.PARAMETER)
    ids = [int(k) for k in ext["spieler"]]
    assert ids == sorted(ids) and len(ids) == 209 and 35 not in ids          # Laufnummer 5 ohne espnId
    assert ids[:3] == [7, 14, 21]                                          # numerisch sortiert (7 vor 14)
    assert ext["spieler"]["7"] == {"wert": 9990, "rang": 1, "pos_rang": 1, "trend30": 4, "redraft": 0}
    assert ext["spieler"]["14"] == {"wert": 9980, "rang": 2, "pos_rang": 2, "trend30": 3, "redraft": 502}
    raw = fc.dumps(ext)
    assert json.loads(raw) == ext and raw.count(b"\n") == 7 + 209          # Kopf und Klammern, eine Zeile je Spieler
    text = raw.decode("utf-8")
    assert "Testspieler" not in text and "Testpick" not in text and "maybe" not in text and "starter" not in text


def test_auszug_nur_pool_spieler_und_doppelte_espn_id():
    """Spieler außerhalb des ESPN-Pools fallen weg; bei doppelter espnId gilt der besser gerankte Eintrag."""
    rows = liste(espn=lambda i: 21 if i == 9 else i * 7)                  # Laufnummer 9 trägt dieselbe ID wie 3
    ext = fc.extract(rows, pool_ids(), STAND)
    assert ext["spieler"]["21"]["rang"] == 3 and "63" not in ext["spieler"]
    few = fc.extract(liste(), pool_ids() - {7, 14}, STAND)
    assert "7" not in few["spieler"] and len(few["spieler"]) == 207


def kaputt(fn):
    rows = liste()
    fn(rows)
    return rows


def spieler_nr(rows, i):
    return next(r for r in rows if r["player"]["position"] != fc.PICK and r["overallRank"] == i)


@pytest.mark.parametrize("rows, text", [
    ({"error": "x"}, "keine Liste"),
    (kaputt(lambda r: r.append({"value": 1})), "ohne player"),
    (liste(n=150), "nur 150 Spieler"),
    (kaputt(lambda r: spieler_nr(r, 7).update(overallRank=8)), "Ränge"),                 # Doppel und Lücke
    (kaputt(lambda r: spieler_nr(r, 210).update(overallRank=212)), "Ränge"),             # Lücke am Ende
    (kaputt(lambda r: spieler_nr(r, 4).pop("value")), "1 Spieler ohne Wert"),
    (kaputt(lambda r: spieler_nr(r, 4).update(trend30Day=None)), "1 Spieler ohne"),
    (kaputt(lambda r: spieler_nr(r, 4).update(value=12.5)), "1 Spieler ohne"),
    (kaputt(lambda r: spieler_nr(r, 4).update(positionRank=True)), "1 Spieler ohne"),
    (kaputt(lambda r: spieler_nr(r, 4).update(redraftValue="viel")), "1 Spieler ohne"),
])
def test_auszug_unbrauchbar(rows, text):
    with pytest.raises(ef.FetchError, match=text):
        fc.extract(rows, pool_ids(), STAND)


def test_auszug_zu_wenige_treffer_und_ohne_redraft():
    with pytest.raises(ef.FetchError, match="nur 0 von 209"):
        fc.extract(liste(), set(), STAND)
    with pytest.raises(ef.FetchError, match="nur 159 von 209"):
        fc.extract(liste(), {i * 7 for i in range(1, 161)}, STAND)           # Laufnummer 5 ohne espnId; 159 < 0,8 × 209
    # Grenze: 0,8 × 209 = 167,2 – 168 Treffer reichen, 167 nicht
    assert len(fc.extract(liste(), {i * 7 for i in range(1, 170)}, STAND)["spieler"]) == 168
    with pytest.raises(ef.FetchError, match="nur 167 von 209"):
        fc.extract(liste(), {i * 7 for i in range(1, 169)}, STAND)
    rows = kaputt(lambda r: [spieler_nr(r, i).pop("redraftValue") for i in (1, 2)])
    assert fc.extract(rows, pool_ids(), STAND)["spieler"]["7"]["redraft"] is None   # redraftValue darf fehlen


def test_espn_id():
    assert [fc.espn_id({"espnId": v}) for v in ("4429795", " 12 ", 7, None, "", "abc", "0", "-3", True)] \
        == [4429795, 12, 7, None, None, None, None, None, None]
    assert fc.espn_id({}) is None


def test_werte():
    ext = fc.extract(liste(), pool_ids(), STAND)
    w = fc.werte(ext)
    assert w[7] == {"wert": 9990, "rang": 1, "pos_rang": 1, "trend30": 4, "redraft": None}   # 0 = kein Redraft-Wert
    assert w[14]["redraft"] == 502 and fc.werte(None) == {} and fc.werte({"spieler": None}) == {}


# ---------------------------------------------------------------- Tagessperre und Tageslauf

class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code, self.payload = status_code, payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeCalc:
    """Beantwortet values/current mit einer erfundenen Liste; status = HTTP-Status oder "netz" (Verbindungsfehler)
    bzw. "json" (HTTP 200, aber kein JSON); calls zählt die Abfragen."""

    def __init__(self, rows=None):
        self.rows, self.status, self.calls = rows or liste(espn=lambda i: i), 200, []

    def get(self, url, params=None, timeout=None):
        assert url == fc.URL and params == fc.PARAMETER
        self.calls.append(params)
        if self.status == "netz":
            raise ef.requests.ConnectionError("down")
        if self.status == "json":
            return FakeResponse(200, ValueError("kein JSON"))
        return FakeResponse(self.status, self.rows)


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path)
    return tmp_path / "raw"


def pool(ids) -> None:
    """Erfundener Tagesstand mit den Spieler-IDs ids."""
    path = ef.pool_dir(2026) / ef.POOL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"players": [{"id": i} for i in ids]}), encoding="utf-8")


def at(day: int, hour: int) -> datetime:
    return datetime(2026, 10, day, hour, 45, tzinfo=timezone.utc)


def stand() -> str:
    return json.loads(fc.path(2026).read_bytes())["stand"]


def test_update_ein_abruf_je_tag(raw, capsys):
    calc = FakeCalc()
    assert fc.update(calc, 2026, at(1, 6)) == [] and calc.calls == []      # ohne Spielerpool: kein Abruf, keine Warnung
    assert "noch kein Spielerpool" in capsys.readouterr().out and not fc.path(2026).exists()
    pool(range(1, 301))
    assert fc.update(calc, 2026, at(1, 6)) == [] and len(calc.calls) == 1 and stand() == "2026-10-01T0645Z"
    first = fc.path(2026).read_bytes()
    assert fc.update(calc, 2026, at(1, 21)) == [] and len(calc.calls) == 1  # derselbe UTC-Tag: kein zweiter Abruf
    assert "heute schon abgerufen" in capsys.readouterr().out
    # nächster Tag: neuer Abruf; stand wird neu geschrieben, auch wenn sich kein Wert geändert hat (Tagessperre)
    assert fc.update(calc, 2026, at(2, 6)) == [] and len(calc.calls) == 2 and stand() == "2026-10-02T0645Z"
    after = json.loads(fc.path(2026).read_bytes())
    assert after["spieler"] == json.loads(first)["spieler"] and fc.path(2026).read_bytes() != first


@pytest.mark.parametrize("status, text", [(503, "HTTP 503"), ("json", "nicht lesbar"), ("netz", "Netzwerkfehler"),
                                          ("ränge", "Ränge")])
def test_update_fehler_lassen_den_alten_auszug_stehen(raw, capsys, status, text):
    pool(range(1, 301))
    calc = FakeCalc()
    assert fc.update(calc, 2026, at(1, 6)) == []
    saved = fc.path(2026).read_bytes()
    if status == "ränge":
        spieler_nr(calc.rows, 3).update(overallRank=4)
    else:
        calc.status = status
    warnings = fc.update(calc, 2026, at(2, 6))
    assert len(warnings) == 1 and text in warnings[0] and fc.path(2026).read_bytes() == saved
    assert "FEHLER" in capsys.readouterr().err
    # der nächste Lauf desselben Tages versucht es erneut (der Auszug ist noch von gestern)
    calc.rows, calc.status = liste(espn=lambda i: i), 200
    assert fc.update(calc, 2026, at(2, 7)) == [] and stand() == "2026-10-02T0745Z"


@pytest.mark.parametrize("content", ["{kaputt", "[]", '{"stand": 7}'])
def test_update_unlesbarer_auszug_wird_neu_geholt(raw, content):
    pool(range(1, 301))
    fc.path(2026).parent.mkdir(parents=True)
    fc.path(2026).write_text(content, encoding="utf-8")
    calc = FakeCalc()
    assert fc.update(calc, 2026, at(1, 6)) == [] and len(calc.calls) == 1 and stand() == "2026-10-01T0645Z"


def test_update_pool_in_unerwarteter_form(raw, capsys):
    path = ef.pool_dir(2026) / ef.POOL_FILE
    path.parent.mkdir(parents=True)
    path.write_text('{"players": null}', encoding="utf-8")
    warnings = fc.update(FakeCalc(), 2026, at(1, 6))
    assert len(warnings) == 1 and "FEHLER" in capsys.readouterr().err and not fc.path(2026).exists()


class FakeTageslauf(FakeDailySession):
    """Tageslauf-Fake: ESPN wie in test_fetch (erfundener Pool mit den IDs 1 … 300), dazu FantasyCalc."""

    def __init__(self):
        super().__init__(FakeEspn({0: tx("t0")}, topics=[topic("k1")], current=1))
        self.calc = FakeCalc()

    def get(self, url, params=None, headers=None, timeout=None):
        if url == fc.URL:
            return self.calc.get(url, params, timeout)
        return super().get(url, params, headers, timeout)


def test_cmd_daily_mit_marktwert(raw, monkeypatch, capsys):
    session = FakeTageslauf()
    monkeypatch.setattr(ef.requests, "Session", lambda: session)
    now = at(1, 6)
    assert ef.cmd_daily(2026, now, transactions=True, pool=True, marktwert=True) == 0
    assert len(session.calc.calls) == 1 and len(json.loads(fc.path(2026).read_bytes())["spieler"]) == 209
    # zweiter Lauf am selben UTC-Tag: kein Abruf; ohne --marktwert ebenfalls nicht
    assert ef.cmd_daily(2026, now + timedelta(hours=1), pool=True, marktwert=True) == 0 and len(session.calc.calls) == 1
    assert ef.cmd_daily(2026, at(2, 6), pool=True) == 0 and len(session.calc.calls) == 1
    # Ausfall am nächsten Tag: nur Warnung, der Lauf bleibt grün, der Auszug von gestern bleibt
    session.calc.status = 503
    saved = fc.path(2026).read_bytes()
    capsys.readouterr()
    assert ef.cmd_daily(2026, at(2, 6), pool=True, marktwert=True) == 0 and fc.path(2026).read_bytes() == saved
    assert "Warnung: Marktwert: FantasyCalc: HTTP 503" in capsys.readouterr().out
    session.calc.status = 200
    assert ef.cmd_daily(2026, at(2, 7), pool=True, marktwert=True) == 0 and stand() == "2026-10-02T0745Z"


def test_parse_args_marktwert():
    args = ef.parse_args(["--transactions", "--pool", "--wetter", "--marktwert"])
    assert (args.transactions, args.pool, args.wetter, args.marktwert, args.news) == (True, True, True, True, False)
    assert ef.parse_args(["--marktwert"]).marktwert and not ef.parse_args(["--pool"]).marktwert
    for argv in (["--marktwert", "--due"], ["--marktwert", "--weeks", "1"], ["--summary", "--marktwert"]):
        with pytest.raises(SystemExit):
            ef.parse_args(argv)
