"""Tests Öffentlichkeits-Check (scripts/check_public.py): die App enthält nur Ligadaten.

Die Negativtests bauen ihre Testfälle zur Laufzeit aus den Rohdaten – im Test-Code steht kein Manager-Name.
Aufruf: python -m pytest
"""

import json
import re
import shutil

import pytest

import check_public
import espn_fetch as ef

APP = ef.REPO_DIR / "app"
MTEAM = ef.week_dir(2026, 1) / "mTeam.json"


def test_app_ist_oeffentlich_tauglich():
    """Der ganze Ordner app/ (Code und app/data) besteht den Check."""
    if not (APP / "index.html").exists():
        pytest.skip("App noch nicht angelegt")
    assert check_public.check(APP, ef.REPO_DIR) == []


def test_redaktion_ohne_manager_namen():
    """Die freigegebenen Kernsätze (data/redaktion/*.csv) sind öffentlich: keine vollen Namen, Nachnamen,
    Anzeigenamen oder Member-IDs. CSV steht nicht in den App-Dateitypen, deshalb hier direkt mit den Mustern."""
    patterns = check_public.manager_patterns(ef.REPO_DIR)
    for path in sorted((ef.REPO_DIR / "data" / "redaktion").glob("*.csv")):
        text = path.read_text(encoding="utf-8")
        found = [kind for kind, rx in patterns if rx.search(text)]
        assert not found, f"{path.name}: enthält Manager-{', '.join(sorted(set(found)))}"


def test_mteam_rohdaten_sind_auszuege():
    """Jede committete wNN/mTeam.json ist genau das, was espn_fetch.team_extract schreibt: je Team nur Ligafelder
    (kein tradeBlock, keine draftStrategy), je Manager nur Name, Anzeigename und ID (keine notificationSettings),
    nichts Unbekanntes. Schlägt an, wenn eine Rohantwort ungefiltert ins Repo kommt (Entscheidung 01.10.2026).
    Die Meldung nennt nur die Datei, nie den Inhalt (Action-Logs sind öffentlich)."""
    paths = sorted(ef.RAW_DIR.glob("*/w*/mTeam.json"))
    assert paths, "keine mTeam.json in data/raw"
    kein_auszug = []
    for path in paths:
        raw = path.read_bytes()
        if ef.team_extract(json.loads(raw)) != (raw, []):
            kein_auszug.append(ef.rel(path))
    assert not kein_auszug, "kein mTeam-Auszug (scripts/espn_fetch.py, team_extract)"


def values(obj):
    """Alle Blattwerte eines JSON-Objekts (ohne Schlüssel)."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from values(v)
    else:
        yield obj


def test_statkorrekturen_nur_ids_und_zahlen():
    """wNN/statkorrektur.json ist öffentlich: in Spielen und Spielern nur Zahlen, Ziffernfolgen (IDs) und ESPN-Kennungen
    des Siegers – keine Spieler- oder Manager-Namen, keine Texte. Ohne Korrektur im Repo gibt es nichts zu prüfen."""
    erlaubt = re.compile(r"^(\d+|HOME|AWAY|TIE|UNDECIDED)$")
    patterns = check_public.manager_patterns(ef.REPO_DIR)
    for path in sorted(ef.RAW_DIR.glob("*/w*/" + ef.STATKORREKTUR_FILE)):
        data = ef.load_json(path)
        # nur die Zahl melden: pytest zeigt sonst die gefundenen Texte, und die Action-Logs sind öffentlich
        texte = sum(1 for v in values([data["spiele"], data["spieler"]]) if isinstance(v, str) and not erlaubt.match(v))
        assert texte == 0, f"{ef.rel(path)}: Textwerte in Spielen oder Spielern"
        text = path.read_text(encoding="utf-8")
        assert not [kind for kind, rx in patterns if rx.search(text)], ef.rel(path)


def write(folder, name, content):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def members():
    return json.loads(MTEAM.read_text(encoding="utf-8"))["members"]


def test_kopierte_mteam_datei_faellt_auf(tmp_path):
    shutil.copy(MTEAM, tmp_path / "teams.json")
    findings = check_public.check(tmp_path, ef.REPO_DIR)
    assert any("verbotener Schlüssel 'members'" in f for f in findings)
    assert any("Manager-Nachname" in f for f in findings)


def test_voller_name_und_anzeigename_im_text(tmp_path):
    m = members()[0]
    write(tmp_path, "a.html", f"<p>{m['firstName']} {m['lastName']}</p>")
    write(tmp_path, "b.json", {"text": m["displayName"]})
    findings = check_public.check(tmp_path, ef.REPO_DIR)
    assert any(f.startswith("a.html") and "voller Name" in f for f in findings)
    assert any(f.startswith("b.json") and "Anzeigename" in f for f in findings)
    # Meldungen nennen nie den gefundenen Namen (Action-Logs sind öffentlich)
    assert all(m["lastName"].lower() not in f.lower() for f in findings)


@pytest.mark.parametrize("obj, key", [
    ({"players": [{"id": 1, "seasonOutlook": "x"}]}, "seasonOutlook"),
    ({"tx": [{"memberId": "x", "teamId": 2}]}, "memberId"),
    ({"topics": [{"author": "x"}]}, "author"),
    ({"teams": [{"id": 2, "tradeBlock": {}}]}, "tradeBlock"),
    ({"teams": [{"id": 2, "draftStrategy": {}}]}, "draftStrategy"),
])
def test_verbotene_schluessel(tmp_path, obj, key):
    write(tmp_path, "data/x.json", obj)
    assert any(f"'{key}'" in f for f in check_public.check(tmp_path, ef.REPO_DIR))


def test_langer_text_und_dateitypen(tmp_path):
    write(tmp_path, "x.json", {"text": "a" * (check_public.MAX_TEXT + 1)})
    write(tmp_path, ".env", "TOKEN=1")
    write(tmp_path, "notiz.md", "# privat")
    findings = check_public.check(tmp_path, ef.REPO_DIR)
    assert any("Zeichen" in f for f in findings)
    assert any(f.startswith(".env") for f in findings)
    assert any(f.startswith("notiz.md") and "nicht erlaubt" in f for f in findings)


def test_spielernamen_ohne_fehlalarm(tmp_path):
    """Alle ~1050 NFL-Spielernamen des Pools lösen keinen Fund aus (Vornamen werden bewusst nicht geprüft)."""
    pool = ef.load_json(ef.week_dir(2026, 2) / ef.KONA_FILE)["players"]
    names = sorted(p["player"]["fullName"] for p in pool)
    assert len(names) > 1000
    write(tmp_path, "players.json", {"names": names})
    assert check_public.check(tmp_path, ef.REPO_DIR) == []
