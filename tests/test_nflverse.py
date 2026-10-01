"""nflverse-Stammdaten: Auszug aus players.csv (Abruf mit Fake-Sitzung), Korrekturen, Alter und NFL-Jahr.

Alle Spieler hier sind erfunden (IDs 1–12 und 9001), bis auf die zwei echten ESPN-IDs der Korrekturtabelle.
"""

import gzip
import json
from datetime import date
from decimal import Decimal

import pytest

import espn_fetch as ef
import nflverse as nv

HEAD = "gsis_id,display_name,espn_id,birth_date,rookie_season,last_season,draft_year,draft_round,draft_pick"


def csv_text(rows: list[str], head: str = HEAD) -> str:
    return "\n".join([head] + rows) + "\n"


ROWS = [
    "00-1,Testspieler Eins,1,1999-12-27,2022,2026,2022,7,262",
    "00-2,Testspieler Zwei,2,2005-01-19,2026,2026,2026,1,4",
    "00-3,Testspieler Drei,3,1995-06-30,2017,2026,,,",              # ungedraftet
    "00-4,Testspieler Vier,4,,2024,2026,2024.0,3.0,70.0",           # ohne Geburtsdatum, Zahlen als Kommazahl
    "00-5,Testspieler Fünf alt,5,1990-01-01,2012,2019,2012,1,1",    # doppelte ESPN-ID: die jüngere letzte Saison gilt
    "00-6,Testspieler Fünf,5,2001-02-03,2023,2026,2023,2,40",
    "00-7,Testspieler ohne ESPN-ID,,2000-01-01,2022,2026,2022,1,1",
    "00-8,Testspieler nicht gesucht,99,2000-01-01,2022,2026,2022,1,1",
]


def test_auszug():
    ext = nv.extract(csv_text(ROWS), {1, 2, 3, 4, 5})
    assert ext["quelle"] == nv.QUELLE and "CC BY 4.0" in ext["lizenz"]
    assert list(ext["spieler"]) == ["1", "2", "3", "4", "5"]
    assert ext["spieler"]["1"] == {"geb": "1999-12-27", "rookie": 2022, "draft": [2022, 7, 262]}
    assert ext["spieler"]["3"] == {"geb": "1995-06-30", "rookie": 2017, "draft": None}
    assert ext["spieler"]["4"] == {"geb": None, "rookie": 2024, "draft": [2024, 3, 70]}
    assert ext["spieler"]["5"]["geb"] == "2001-02-03"
    assert "Testspieler" not in nv.dumps(ext).decode("utf-8")      # keine Namen im Auszug
    raw = nv.dumps(ext)
    assert json.loads(raw) == ext and raw.count(b"\n") == 6 + 5     # Kopf und Klammern, dazu eine Zeile je Spieler


def test_auszug_kurze_zeile_und_unsinnige_zahl():
    """Eine Zeile mit zu wenigen Feldern oder „inf“ als Zahl ist kein Fehler: Die fehlenden Angaben bleiben leer."""
    ext = nv.extract(csv_text(["00-9,Testspieler kurz,7", "00-8,Testspieler inf,8,2000-01-01,inf,2026,inf,1,1"]), {7, 8})
    assert ext["spieler"] == {"7": {"geb": None, "rookie": None, "draft": None},
                              "8": {"geb": "2000-01-01", "rookie": None, "draft": None}}


def test_auszug_unbrauchbare_liste():
    with pytest.raises(ef.FetchError, match="Spalten fehlen .*rookie_season"):
        nv.extract(csv_text(ROWS, HEAD.replace("rookie_season", "rookie")), {1})
    with pytest.raises(ef.FetchError, match="nur 5 von 10"):
        nv.extract(csv_text(ROWS), set(range(1, 11)))               # unter 80 % der gesuchten Spieler
    assert len(nv.extract(csv_text(ROWS), {1, 2, 3, 4, 5, 6})["spieler"]) == 5   # 5 von 6 reicht


def test_stammdaten_korrektur_alter_und_nfl_jahr():
    assert nv.stammdaten(None) == {}
    falsch = {"spieler": {"4569603": {"geb": "2000-10-20", "rookie": 2024, "draft": [2024, 6, 184]},
                          "1": {"geb": "1999-12-27", "rookie": 2022, "draft": None},
                          "4": {"geb": None, "rookie": None, "draft": None}}}
    s = nv.stammdaten(falsch)
    assert s[4569603]["geb"] == date(2001, 1, 4)                    # Korrekturtabelle schlägt den Auszug
    assert s[1] == {"geb": date(1999, 12, 27), "rookie": 2022, "draft": None} and s[4]["geb"] is None
    assert all(date.fromisoformat(d) for d in nv.KORREKTUR.values())
    # Alter: Tage / 365,25; am 27.12.2026 genau 27 Jahre minus Schalttagsrest
    assert nv.age(date(1999, 12, 27), date(2026, 9, 29)).quantize(Decimal("0.01")) == Decimal("26.76")
    assert nv.age(None, date(2026, 9, 29)) is None
    assert [nv.nfl_year(r, 2026) for r in (2026, 2025, 2005, None, 2027)] == [1, 2, 22, None, None]


class FakeSession:
    """Beantwortet die eine nflverse-Anfrage mit einer gepackten, erfundenen players.csv."""

    def __init__(self, rows=ROWS, status=200, broken=False):
        self.rows, self.status, self.broken, self.calls = rows, status, broken, []

    def get(self, url, timeout=None):
        self.calls.append(url)

        class Response:
            status_code = self.status
            content = b"kein gzip" if self.broken else gzip.compress(csv_text(self.rows).encode("utf-8"))
        return Response()


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path)
    return tmp_path / "raw"


def pool(ids) -> None:
    """Erfundener Tagesstand mit den Spieler-IDs ids (dazu eine D/ST mit negativer ID)."""
    path = ef.pool_dir(2026) / ef.POOL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"players": [{"id": i} for i in list(ids) + [-16001]]}), encoding="utf-8")


def test_update_schreibt_nur_bei_aenderung(raw, capsys):
    session = FakeSession()
    assert nv.update(session, 2026) == 0 and session.calls == []    # ohne Spielerpool: kein Abruf, kein Fehler
    assert "noch kein Spielerpool" in capsys.readouterr().out and not nv.path(2026).exists()
    pool([1, 2, 3, 4, 5])
    assert nv.pool_ids(2026) == {1, 2, 3, 4, 5}                     # D/ST (negative ID) fällt weg
    assert nv.update(session, 2026) == 0 and session.calls == [nv.URL]
    saved = nv.path(2026).read_bytes()
    assert list(json.loads(saved)["spieler"]) == ["1", "2", "3", "4", "5"]
    before = nv.path(2026).stat().st_mtime_ns
    assert nv.update(session, 2026) == 0 and nv.path(2026).stat().st_mtime_ns == before
    assert "unverändert" in capsys.readouterr().out
    session.rows = ROWS[:1] + ["00-2,Testspieler Zwei,2,2005-01-20,2026,2026,2026,1,4"] + ROWS[2:]
    assert nv.update(session, 2026) == 0 and json.loads(nv.path(2026).read_bytes())["spieler"]["2"]["geb"] == "2005-01-20"


class KaputtesGzip(FakeSession):
    """Gültiger gzip-Kopf, beschädigter Datenstrom: gzip.decompress wirft zlib.error (keine OSError-Unterklasse)."""

    def get(self, url, timeout=None):
        good = gzip.compress(csv_text(self.rows * 50).encode("utf-8"))

        class Response:
            status_code = 200
            content = good[:10] + bytes(b ^ 0xFF for b in good[10:40]) + good[40:]
        return Response()


@pytest.mark.parametrize("session, text", [(FakeSession(status=503), "HTTP 503"), (FakeSession(broken=True), "nicht lesbar"),
                                           (KaputtesGzip(), "nicht lesbar"),
                                           (FakeSession(rows=ROWS[:2]), "nur 2 von 5")])
def test_update_fehler_lassen_den_alten_auszug_stehen(raw, capsys, session, text):
    pool([1, 2, 3, 4, 5])
    assert nv.update(FakeSession(), 2026) == 0
    saved = nv.path(2026).read_bytes()
    assert nv.update(session, 2026) == 1 and nv.path(2026).read_bytes() == saved
    assert text in capsys.readouterr().err


@pytest.mark.parametrize("content", ["[]", '{"players": null}', "{kaputt"])
def test_update_pool_auszug_in_unerwarteter_form(raw, capsys, content):
    """Ein Tagesstand in unerwarteter Form ist ein Fehler des Nebenteils (Rückgabe 1), keine Ausnahme."""
    path = ef.pool_dir(2026) / ef.POOL_FILE
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    assert nv.update(FakeSession(), 2026) == 1 and "FEHLER" in capsys.readouterr().err
