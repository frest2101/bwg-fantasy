"""FantasyPros-Adressen: Sitemap-Auszug (Abruf mit Fake-Sitzung) und Zuordnung ESPN-Name → Adresse.

Die Sitemaps hier sind erfunden: echte Beispiel-Adressen (Stand 30.09.2026) zwischen Füllern „testspieler-…“,
damit die Mindestzahl je Position erreicht ist; dazu der erfundene „Theo Testmann III“ (Adressen mit und ohne Zusatz).
"""

import json

import pytest

import espn_fetch as ef
import fantasypros as fp

# echte Adressen aus den Sitemaps vom 30.09.2026 (Auswahl), je Position; theo-testmann(-iii) ist erfunden
EXAMPLES = {
    "QB": ["josh-allen-qb", "brock-purdy", "patrick-mahomes", "gardner-minshew"],
    "RB": ["kenneth-walker-rb", "james-cook", "jacory-croskeymerritt", "kenneth-gainwell", "theo-testmann-iii",
           "theo-testmann"],
    "WR": ["dj-moore-wr", "amonra-stbrown", "marvin-harrison-jr", "deebo-samuel", "jamarr-chase",
           "isaiah-williams", "isaiah-williams-wr", "nathaniel-dell", "jmichael-sturdivant", "antonio-williams-wr"],
    "TE": ["travis-kelce", "connor-heyward"], "K": ["kaimi-fairbairn"], "DST": ["san-francisco-defense"],
}


def sitemap_xml(position: str, count: int | None = None) -> str:
    """Erfundene Positions-Sitemap: Beispiele plus Füller, je Spieler Seite und Unterseiten wie bei FantasyPros."""
    fill = count if count is not None else fp.MIN_PLAYERS[position]
    slugs = EXAMPLES[position] + [f"testspieler-{position.lower()}-{i}" for i in range(fill)]
    urls = []
    for s in slugs:
        urls += [f"https://www.fantasypros.com/nfl/players/{s}.php",
                 f"https://www.fantasypros.com/nfl/players/{s}.php?week=draft",
                 f"https://www.fantasypros.com/nfl/stats/{s}.php"]
    return "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code, self.text = status_code, text


class FakeSitemaps:
    """Ersetzt die requests-Sitzung für FantasyPros; merkt sich die angefragten Positionen."""

    def __init__(self, status: int = 200, count: int | None = None):
        self.status, self.count, self.calls = status, count, []

    def get(self, url, params=None, timeout=None):
        assert url == fp.SITEMAP_URL and timeout
        self.calls.append(params["position"])
        return FakeResponse(self.status, sitemap_xml(params["position"], self.count) if self.status == 200 else "down")


@pytest.fixture(autouse=True)
def ohne_pause(monkeypatch):
    monkeypatch.setattr(fp, "PAUSE", 0)


@pytest.fixture
def known():
    data = json.loads(fp.fetch(FakeSitemaps()))
    return fp.index(data)


# ---------------------------------------------------------------- Schreibweisen

def test_slug_wie_fantasypros():
    assert fp.slug("Ja'Marr Chase") == "jamarr-chase"
    assert fp.slug("Ka’imi Fairbairn") == "kaimi-fairbairn"
    assert fp.slug("A.J. Brown") == "aj-brown"
    assert fp.slug("Juanyeh Thomás") == "juanyeh-thomas"                        # erfundener Name mit Akzent
    assert fp.variants("Amon-Ra St. Brown") == {"amon-ra-st-brown", "amonra-st-brown", "amonra-stbrown"}
    assert "jacory-croskeymerritt" in fp.variants("Jacory Croskey-Merritt")
    assert fp.variants("Stetson Bennett") == {"stetson-bennett"}                  # „St“ nur als eigenes Wort


# ---------------------------------------------------------------- Zuordnung

@pytest.mark.parametrize("name, pos, expected", [
    ("Josh Allen", "QB", "josh-allen-qb"),              # Namensvetter: josh-allen ist ein anderer Spieler
    ("DJ Moore", "WR", "dj-moore-wr"),
    ("Brock Purdy", "QB", "brock-purdy"),
    ("Amon-Ra St. Brown", "WR", "amonra-stbrown"),
    ("Jacory Croskey-Merritt", "RB", "jacory-croskeymerritt"),
    ("Ja'Marr Chase", "WR", "jamarr-chase"),
    ("Marvin Harrison Jr.", "WR", "marvin-harrison-jr"),  # mit Zusatz, der Vater ist nicht gemeint
    ("Deebo Samuel Sr.", "WR", "deebo-samuel"),           # FantasyPros ohne Zusatz
    ("Gardner Minshew II", "QB", "gardner-minshew"),
    ("James Cook III", "RB", "james-cook"),
    ("Kenneth Walker III", "RB", "kenneth-walker-rb"),    # ohne Zusatz, mit Position
    ("Theo Testmann III", "RB", "theo-testmann-iii"),     # erfunden: voller Name vor dem Namen ohne Zusatz
    ("Isaiah Williams", "WR", None),                      # isaiah-williams und isaiah-williams-wr: mehrdeutig
    ("Tank Dell", "WR", None),                            # Spitzname, FantasyPros führt nathaniel-dell: keine Raterei
    ("Kenny Gainwell", "RB", None),
    ("J. Michael Sturdivant", "WR", "jmichael-sturdivant"),  # Initiale angezogen
    ("Connor Heyward", "RB", "connor-heyward"),           # ESPN RB, FantasyPros TE: eindeutig in einer anderen Position
    ("Josh Allen", "RB", None),                           # andere Position nur mit Anhang (josh-allen-qb): Namensvetter
    ("Antonio Williams", "RB", None),                     # ebenso (antonio-williams-wr)
    ("49ers D/ST", "D/ST", None),                         # D/ST verlinkt die App über ihre eigene Tabelle
    (None, "QB", None),
])
def test_slug_for(known, name, pos, expected):
    assert fp.slug_for(name, pos, known) == expected


def test_handtabelle(known):
    """Spitznamen aus der Handtabelle (echte ESPN-IDs); ohne ID bleibt es bei der Suche, fehlt die Adresse in der Sitemap der
    Position (veralteter Eintrag), gilt wieder die Regel."""
    assert fp.slug_for("Tank Dell", "WR", known, 4366031) == "nathaniel-dell"
    assert fp.slug_for("Kenny Gainwell", "RB", known, 4371733) == "kenneth-gainwell"
    assert fp.slug_for("Tank Dell", "WR", known) is None
    assert fp.slug_for("Nicholas Singleton", "RB", known, 4685555) is None       # nick-singleton fehlt im erfundenen Auszug
    assert fp.slug_for("Tank Dell", "RB", known, 4366031) is None                # falsche Position: Tabelle greift nicht
    assert fp.slug_for("Josh Allen", "QB", known, 3918298) == "josh-allen-qb"   # ohne Tabelleneintrag: Regel
    assert all(isinstance(pid, int) and slug == fp.slug(slug) for pid, slug in fp.HAND.items())


def test_ohne_auszug_keine_zuordnung():
    assert fp.index(None) == {}
    assert fp.slug_for("Brock Purdy", "QB", fp.index(None)) is None


# ---------------------------------------------------------------- Abruf

def test_fetch_auszug():
    session = FakeSitemaps()
    content = fp.fetch(session)
    data = json.loads(content)
    assert session.calls == list(fp.POSITIONS)
    assert set(data["positionen"]) == set(fp.POSITIONS)
    qb = data["positionen"]["QB"]
    assert qb == sorted(qb) and "josh-allen-qb" in qb and len(qb) == len(set(qb))   # nur Spielerseiten, ohne Unterseiten
    assert len(qb) == len(EXAMPLES["QB"]) + fp.MIN_PLAYERS["QB"]
    assert content == fp.fetch(FakeSitemaps())            # gleiche Antwort → gleiche Bytes („unverändert“)


def test_fetch_pausiert_zwischen_abrufen(monkeypatch):
    pauses = []
    monkeypatch.setattr(fp.time, "sleep", pauses.append)
    monkeypatch.setattr(fp, "PAUSE", 5)
    fp.fetch(FakeSitemaps())
    assert pauses == [5] * (len(fp.POSITIONS) - 1)        # robots.txt: Crawl-delay 5


def test_update_schreibt_nur_bei_aenderung_und_faengt_fehler(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path)
    assert fp.update(FakeSitemaps(status=503), 2026) == 1 and not fp.path(2026).exists()   # Fehler: zählen, nicht werfen
    assert "HTTP 503" in capsys.readouterr().err
    assert fp.update(FakeSitemaps(), 2026) == 0 and fp.path(2026).exists()
    before = fp.path(2026).stat().st_mtime_ns
    assert fp.update(FakeSitemaps(), 2026) == 0 and fp.path(2026).stat().st_mtime_ns == before
    assert "unverändert" in capsys.readouterr().out
    assert fp.update(FakeSitemaps(count=3), 2026) == 1 and fp.path(2026).stat().st_mtime_ns == before  # alte Datei bleibt


@pytest.mark.parametrize("session, message", [
    (FakeSitemaps(status=503), "HTTP 503"),
    (FakeSitemaps(count=3), "nur"),                        # zu wenige Spieler: kaputte oder umgebaute Sitemap
])
def test_fetch_fehler(session, message):
    with pytest.raises(ef.FetchError, match=message):
        fp.fetch(session)
