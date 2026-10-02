"""Wächter für den Zeitplan des Tageslaufs: Plan (.github/workflows/tageslauf.yml), Anzeige „Nächster Tageslauf“
(app/js/app.js) und Texte (Glossar, README, Kurzformel „stündlich von etwa … bis Mitternacht“) nennen dieselben Zeiten.

Ohne Netz und ohne YAML-Paket: Die cron-Zeilen samt timezone liest ein Regex aus dem Workflow. Geprüft wird nicht, ob
GitHub pünktlich startet (erfahrungsgemäß 10–16 min nach dem Slot), sondern nur, dass die Stellen nicht wieder
auseinanderlaufen – wer die cron-Zeilen ändert, zieht app.js (DAILY), Glossar „Aktualisierung“ und README nach.
Aufruf: python -m pytest
"""

import json
import re

import espn_fetch as ef

WORKFLOW = ef.REPO_DIR / ".github" / "workflows" / "tageslauf.yml"
APP_JS = ef.REPO_DIR / "app" / "js" / "app.js"
INDEX = ef.REPO_DIR / "app" / "index.html"
README = ef.REPO_DIR / "README.md"
# Dateien mit der Kurzformel (ohne CLAUDE.md und docs/auftraege: Projektanweisung und historische Aufträge)
KURZTEXTE = [WORKFLOW, INDEX, README, ef.REPO_DIR / "docs" / "app_daten.md", ef.REPO_DIR / "scripts" / "espn_fetch.py",
             *sorted((ef.REPO_DIR / "app" / "js").glob("*.js"))]

ZONE = "Europe/Berlin"       # Slots in deutscher Zeit (Beschluss 02.10.2026), GitHub rechnet Sommer- und Winterzeit
VERZUG_MIN = 15              # typischer Startverzug bei GitHub; Grundlage von „etwa 05:00 Uhr“ in den Texten
# ein Eintrag: - cron: "<Minute> <Stunde von>-<Stunde bis> * * *", in der Zeile darunter timezone: "<IANA-Name>"
CRON_ZEILE = re.compile(r"^\s*-\s*cron:", re.M)
CRON = re.compile(r'^\s*-\s*cron:\s*"(\d+) (\d+)-(\d+) \* \* \*"[^\n]*\n\s*timezone:\s*"([^"]+)"\s*$', re.M)
KURZFORMEL = re.compile(r"stündlich von etwa (\d\d:\d\d) Uhr bis Mitternacht")


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def plan() -> list[tuple[int, int, int, str]]:
    """cron-Einträge des Workflows in Dateireihenfolge: (Minute, erste Stunde, letzte Stunde, Zeitzone)."""
    return [(int(minute), int(von), int(bis), zone) for minute, von, bis, zone in CRON.findall(read(WORKFLOW))]


def slots() -> list[tuple[int, int]]:
    """Alle Slots eines Tages als (Stunde, Minute), aufsteigend."""
    return sorted((hour, minute) for minute, von, bis, _ in plan() for hour in range(von, bis + 1))


def spannen() -> list[str]:
    """Die Blöcke so, wie Glossar und README sie nennen: „04:45–16:45“."""
    return [f"{von:02d}:{minute:02d}–{bis:02d}:{minute:02d}" for minute, von, bis, _ in plan()]


def test_plan_ist_lesbar_und_in_deutscher_zeit():
    """Jeder cron-Eintrag hat die einfache Form „Minute Stunde-Stunde * * *“ und direkt darunter die Zeitzone
    Europe/Berlin – sonst läse dieser Wächter am Plan vorbei, oder ein Block liefe in UTC."""
    entries = plan()
    assert entries, "kein cron-Eintrag mit timezone in tageslauf.yml gefunden"
    assert len(entries) == len(CRON_ZEILE.findall(read(WORKFLOW))), "cron-Eintrag in anderer Form oder ohne timezone"
    for minute, von, bis, zone in entries:
        assert zone == ZONE
        assert 0 <= minute <= 59 and 0 <= von <= bis <= 23
    assert len(set(slots())) == len(slots()), "zwei cron-Einträge treffen denselben Slot"


def test_kein_slot_in_der_umstellungsstunde():
    """Die Stunde 02:00–03:00 Uhr gibt es in Europe/Berlin am letzten Sonntag im März nicht und am letzten Sonntag
    im Oktober doppelt; GitHub schiebt Läufe der übersprungenen Stunde auf 03:00 Uhr. nextDaily() in app.js verlässt
    sich darauf, dass kein Slot dort liegt (genau ein UTC-Zeitpunkt je Slot und Tag)."""
    assert all(hour != 2 for hour, _ in slots())


def test_app_rechnet_mit_denselben_slots():
    """DAILY und DAILY_TZ in app/js/app.js (Anzeige „Nächster Tageslauf“) entsprechen den cron-Zeilen."""
    text = read(APP_JS)
    zone = re.search(r"^const DAILY_TZ = '([^']+)';$", text, re.M)
    daily = re.search(r"^const DAILY = (\[\[[\d, \[\]]+\]\]);$", text, re.M)
    assert zone and daily, "DAILY_TZ oder DAILY in app/js/app.js nicht gefunden"
    assert {z for *_, z in plan()} == {zone.group(1)}
    assert json.loads(daily.group(1)) == [[minute, von, bis] for minute, von, bis, _ in plan()]


def test_glossar_und_readme_nennen_die_slots():
    """Glossar „Aktualisierung“, README und der Kopfkommentar des Workflows nennen jeden Block des Plans, die Zahl der
    Läufe je Tag und die deutsche Zeit."""
    glossar = re.search(r'<dt id="g-aktualisierung">.*?</dt><dd>(.*?)</dd>', read(INDEX), re.S)
    assert glossar, "Glossareintrag g-aktualisierung fehlt in app/index.html"
    kopf = read(WORKFLOW).split("\nname:")[0]
    laeufe = f"{len(slots())} Läufe"
    for name, text in (("Glossar Aktualisierung", glossar.group(1)), ("README.md", read(README)), ("tageslauf.yml (Kopf)", kopf)):
        for spanne in spannen():
            assert spanne in text, f"{name}: Block {spanne} fehlt"
        assert laeufe in text, f"{name}: „{laeufe}“ fehlt"
        assert "deutscher Zeit" in text, f"{name}: Hinweis auf die deutsche Zeit fehlt"
    assert f'timezone: "{ZONE}"' in read(README)


def test_kurzformel_passt_zum_plan():
    """Die Kurzformel „stündlich von etwa 05:00 Uhr bis Mitternacht“ (App, Doku, Docstrings) folgt aus dem Plan:
    „etwa“ = erster Slot plus der typische Startverzug, „bis Mitternacht“ = letzter Slot in der Stunde vor 24 Uhr."""
    hour, minute = slots()[0]
    start = hour * 60 + minute + VERZUG_MIN
    erwartet = f"{start // 60:02d}:{start % 60:02d}"
    assert slots()[-1][0] == 23, "letzter Slot nicht mehr in der Stunde vor Mitternacht – Kurzformel anpassen"
    gefunden = {path.name: KURZFORMEL.findall(read(path)) for path in KURZTEXTE}
    assert any(gefunden.values()), "Kurzformel kommt in keiner Datei mehr vor – Wächter anpassen"
    for name, zeiten in gefunden.items():
        assert set(zeiten) <= {erwartet}, f"{name}: Kurzformel nennt {sorted(set(zeiten))}, der Plan ergibt {erwartet}"
