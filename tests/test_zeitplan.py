"""Wächter für den Zeitplan des Tageslaufs: Plan (.github/workflows/tageslauf.yml), Anzeige „Nächster Tageslauf“
(app/js/app.js) und Texte (Glossar, README, Kurzformel „stündlich von etwa … bis Mitternacht“) nennen dieselben Zeiten.
Dazu der Wochenabruf (.github/workflows/wochenabruf.yml, UTC): WOCHENABRUF_H in app/js/ui.js (Hinweis „Gespielt, noch
nicht gewertet“ und „Nächster Wochenabruf“ im Datenstand-Fenster) und Glossar „Aktualisierung“ nennen dieselben Termine.

Ohne Netz und ohne YAML-Paket: Die cron-Zeilen samt timezone liest ein Regex aus dem Workflow. Geprüft wird nicht, ob
GitHub pünktlich startet (erfahrungsgemäß 10–16 min nach dem Slot), sondern nur, dass die Stellen nicht wieder
auseinanderlaufen – wer die cron-Zeilen ändert, zieht app.js (DAILY) bzw. ui.js (WOCHENABRUF_H), Glossar
„Aktualisierung“ und README nach.
Aufruf: python -m pytest
"""

import json
import re

import espn_fetch as ef

WORKFLOW = ef.REPO_DIR / ".github" / "workflows" / "tageslauf.yml"
WOCHENABRUF = ef.REPO_DIR / ".github" / "workflows" / "wochenabruf.yml"
APP_JS = ef.REPO_DIR / "app" / "js" / "app.js"
UI_JS = ef.REPO_DIR / "app" / "js" / "ui.js"
INDEX = ef.REPO_DIR / "app" / "index.html"
README = ef.REPO_DIR / "README.md"
# Dateien mit der Kurzformel (ohne CLAUDE.md und docs/auftraege: Projektanweisung und historische Aufträge)
KURZTEXTE = [WORKFLOW, INDEX, README, ef.REPO_DIR / "docs" / "app_daten.md", ef.REPO_DIR / "scripts" / "espn_fetch.py",
             *sorted((ef.REPO_DIR / "app" / "js").glob("*.js"))]

ZONE = "Europe/Berlin"       # Slots in deutscher Zeit (Beschluss 02.10.2026), GitHub rechnet Sommer- und Winterzeit
VERZUG_MIN = 15              # typischer Startverzug bei GitHub; Grundlage von „etwa 05:00 Uhr“ in den Texten
# ein Eintrag: - cron: "<Minute> <Stunde von>-<Stunde bis> * * *", in der Zeile darunter timezone: "<IANA-Name>"
CRON_ZEILE = re.compile(r"^\s*-\s*cron:", re.M)
# die timezone-Zeile steht genau zwei Leerzeichen tiefer als der Listenstrich (Schlüssel desselben Eintrags) – anders
# eingerückt wäre der Workflow ungültig und liefe still gar nicht mehr
CRON = re.compile(r'^([ ]*)-[ ]cron:[ ]*"(\d+) (\d+)-(\d+) \* \* \*"[^\n]*\n\1[ ]{2}timezone:[ ]*"([^"]+)"[ ]*$', re.M)
KURZFORMEL = re.compile(r"von etwa (\d\d:\d\d) Uhr bis Mitternacht")
# Wochenabruf: - cron: "<Minute> <Stunde> * * <Wochentag>" in UTC (ohne timezone), 2 = Dienstag
CRON_WOCHE = re.compile(r'^\s*-\s*cron:\s*"(\d+) (\d+) \* \* (\d)"', re.M)


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def plan() -> list[tuple[int, int, int, str]]:
    """cron-Einträge des Workflows in Dateireihenfolge: (Minute, erste Stunde, letzte Stunde, Zeitzone)."""
    return [(int(minute), int(von), int(bis), zone) for _, minute, von, bis, zone in CRON.findall(read(WORKFLOW))]


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
    """Die Kurzformel „von etwa 05:00 Uhr bis Mitternacht“ (App, Doku, Docstrings, Glossar) folgt aus dem Plan:
    „etwa“ = erster Slot plus der typische Startverzug, „bis Mitternacht“ = letzter Slot in der Stunde vor 24 Uhr."""
    hour, minute = slots()[0]
    start = hour * 60 + minute + VERZUG_MIN
    erwartet = f"{start // 60:02d}:{start % 60:02d}"
    assert slots()[-1][0] == 23, "letzter Slot nicht mehr in der Stunde vor Mitternacht – Kurzformel anpassen"
    gefunden = {path.name: KURZFORMEL.findall(read(path)) for path in KURZTEXTE}
    assert any(gefunden.values()), "Kurzformel kommt in keiner Datei mehr vor – Wächter anpassen"
    for name, zeiten in gefunden.items():
        assert set(zeiten) <= {erwartet}, f"{name}: Kurzformel nennt {sorted(set(zeiten))}, der Plan ergibt {erwartet}"


def test_wochenabruf_zeiten_in_der_app():
    """WOCHENABRUF_H in app/js/ui.js (Stunden nach Dienstag 00:00 UTC) entspricht den cron-Zeilen von wochenabruf.yml;
    app.js nimmt „Nächster Wochenabruf“ aus ui.js (U.wochenabrufe für „alt“, U.wochenabrufTxt für den Text wie im Hinweis
    „Gespielt, noch nicht gewertet“) statt aus einer eigenen Uhrzeit, Glossar „Aktualisierung“ und README nennen dieselben
    Termine. Der Workflow läuft in UTC (ohne timezone) – mit einer Zeitzone stimmten die Stunden nicht."""
    workflow = read(WOCHENABRUF)
    termine = [(int(tag), int(stunde), int(minute)) for minute, stunde, tag in CRON_WOCHE.findall(workflow)]
    assert termine and len(termine) == len(CRON_ZEILE.findall(workflow)), "cron-Eintrag in anderer Form in wochenabruf.yml"
    assert "timezone:" not in workflow, "Wochenabruf mit Zeitzone: WOCHENABRUF_H rechnet in UTC"
    assert termine[0][0] == 2 and all(tag in (2, 3) for tag, _, _ in termine), "Wochenabruf dienstags, Nachläufe Di/Mi"
    ui = re.search(r"^export const WOCHENABRUF_H = (\[[\d., ]+\]);$", read(UI_JS), re.M)
    assert ui, "WOCHENABRUF_H in app/js/ui.js nicht gefunden"
    assert json.loads(ui.group(1)) == [(tag - 2) * 24 + stunde + minute / 60 for tag, stunde, minute in termine]
    (_, stunde, minute), *nach = termine
    app_js = read(APP_JS)
    for name, inhalt in (("app/js/app.js", app_js), ("app/js/ui.js", read(UI_JS))):
        assert f"T{stunde:02d}:{minute:02d}" not in inhalt, f"{name}: eigene Uhrzeit des Wochenabrufs statt WOCHENABRUF_H"
    assert "U.wochenabrufe(" in app_js and "U.wochenabrufTxt(" in app_js, "app.js: Wochenabruf nicht aus ui.js"
    kurz = {2: "Di", 3: "Mi"}
    text = (f"dienstags {stunde:02d}:{minute:02d} UTC, Nachläufe "
            + " und ".join(f"{kurz[t]} {h:02d}:{m:02d}" for t, h, m in nach) + " UTC")
    glossar = re.search(r'<dt id="g-aktualisierung">.*?</dt><dd>(.*?)</dd>', read(INDEX), re.S).group(1)
    for name, inhalt in (("Glossar Aktualisierung", glossar), ("README.md", read(README))):
        assert text in inhalt, f"{name}: „{text}“ fehlt"
