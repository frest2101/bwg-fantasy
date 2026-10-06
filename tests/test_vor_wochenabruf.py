"""Wächter für den Hinweis „Gespielt, noch nicht gewertet“ (Beschluss Stephan 06.10.2026): Dienstags zwischen dem ersten
Tageslauf nach 00:00 UTC und dem Wochenabruf führt der Tagesstand schon die neue Woche (waiver.json › woche = N+2), der
Wochenstand noch die alte (players.json › mu_woche = N+1). Die App erkennt das allein an woche > mu_woche
(U.zwischenstand in app/js/ui.js), zeigt unter Markt (Freie Spieler, Bedarf je Team), auf der Spielerseite (Woche) und auf
der Team-Seite (Markt) eine Hinweiszeile und blendet Gegner und Faktor nächste 3 bzw. die Gegner-Kacheln aus.

Ohne node und ohne Browser: Der Test liest den JS-Code per Regex (ohne Kommentare) und hält fest, dass Bedingung,
Aufrufe, ausgeblendete Spalten und Glossar nicht auseinanderlaufen. Wie Hinweis und Tabellen tatsächlich aussehen (der Text
hängt von der Uhrzeit ab: geplanter Termin oder „steht noch aus“), zeigt ein Browser-Testlauf mit den App-Daten eines
Dienstagmorgens (ad4df3f: Hinweis) und danach (288d190, Montag 5d376e2: kein Hinweis). Die Byes im Profil prüft
test_app_export (profile_bye_weeks, nachgestellter Dienstag auf den echten Daten).
Aufruf: python -m pytest
"""

import re

import espn_fetch as ef

APP = ef.REPO_DIR / "app"
JS = APP / "js"
UI_JS, INDEX = JS / "ui.js", APP / "index.html"
WAIVER, SPIELER, TEAM = JS / "v_waiver.js", JS / "v_spieler.js", JS / "v_team.js"


def read(path) -> str:
    """Quelltext als Text; Zeilenenden (CRLF/LF) und ein BOM am Dateianfang spielen keine Rolle."""
    return path.read_text(encoding="utf-8-sig")


def code(path) -> str:
    """JS-Quelltext ohne Kommentare (// nach Zeilenanfang oder Leerraum, /* … */); „https://…“ bleibt stehen."""
    text = re.sub(r"/\*.*?\*/", "", read(path), flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text, flags=re.M)


def test_bedingung_nur_aus_tages_und_wochenstand():
    """Zwischenstand = waiver.json › woche größer als players.json › mu_woche – nicht manifest › datenstand.pool_woche
    (das ist der Wochen-Pool, also die gewertete Woche, und erkennt den Zustand nie)."""
    m = re.search(r"^export const zwischenstand = \(W, P\) =>(.*?);$", code(UI_JS), re.M | re.S)
    assert m, "U.zwischenstand in app/js/ui.js nicht gefunden"
    assert "W.woche > P.mu_woche" in m.group(1) and "pool_woche" not in m.group(1)
    assert "export function zwischenHinweis(z, zusatz)" in code(UI_JS)
    assert "ib('vor-wochenabruf'" in code(UI_JS), "Hinweiszeile ohne i-Knopf zum Glossar"


def test_ansichten_mit_hinweis():
    """Markt, Spielerseite und Team-Seite prüfen den Zwischenstand mit Tagesstand W und Wochenstand P und zeigen die
    Hinweiszeile; unter Markt › Reihenfolge & Claims bewusst nicht (dort zählt nur die Spalte Schwächen)."""
    for path in (WAIVER, SPIELER, TEAM):
        text = code(path)
        assert "U.zwischenstand(W, P)" in text, f"{path.name}: Zwischenstand nicht geprüft"
        assert "U.zwischenHinweis(" in text, f"{path.name}: Hinweiszeile fehlt"
    assert "ansicht !== 'reihenfolge' && z ? U.zwischenHinweis(" in code(WAIVER)
    assert "if (z && (prof || B)) U.ap(box, U.zwischenHinweis(z));" in code(TEAM)


def test_gegner_und_faktor_ausgeblendet():
    """Im Zwischenstand gälten Gegner und Faktor nächste 3 noch für die gespielte Woche: unter Markt › Freie Spieler fehlen
    beide Spalten in allen Horizonten samt Legende, auf der Spielerseite die Kacheln Gegner, Faktor und Rang."""
    waiver = code(WAIVER)
    assert "z ? [] : [mu, X(mu3)]" in waiver and "z ? [] : [mu, mu3]" in waiver
    assert not re.search(r"\[mu, (?:X\()?mu3\)?", waiver.replace("z ? [] : [mu, X(mu3)]", "").replace("z ? [] : [mu, mu3]", "")), \
        "Spalte Gegner ohne Bedingung"
    assert "z ? [] : ['mu-n1', 'mu-naechste3']" in waiver
    assert "m && !z ? [U.tile(" in code(SPIELER)


def test_glossar():
    """Der Eintrag „Gespielt, noch nicht gewertet“ steht im Glossar, und jeder i-Knopf mit festem Schlüssel in ui.js hat
    einen Eintrag."""
    ids = set(re.findall(r'<dt id="g-([\w-]+)">', read(INDEX)))
    assert "vor-wochenabruf" in ids
    knoepfe = set(re.findall(r"\bib\('([\w-]+)'", code(UI_JS)))
    assert knoepfe and knoepfe <= ids, f"i-Knopf ohne Glossareintrag: {sorted(knoepfe - ids)}"
