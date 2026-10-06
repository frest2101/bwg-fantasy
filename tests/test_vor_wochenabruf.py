"""Wächter für den Hinweis „Gespielt, noch nicht gewertet“ (Beschluss Stephan 06.10.2026): Dienstags zwischen dem ersten
Tageslauf nach 00:00 UTC und dem Wochenabruf führt der Tagesstand schon die neue Woche (waiver.json › woche = N+2), der
Wochenstand noch die alte (players.json › mu_woche = N+1). Die App erkennt das allein an woche > mu_woche
(U.zwischenstand in app/js/ui.js), zeigt unter Markt (Freie Spieler, Bedarf je Team), auf der Spielerseite (Woche) und auf
der Team-Seite (Markt) eine Hinweiszeile und blendet Gegner und Faktor nächste 3 bzw. die Gegner-Kacheln aus.

Ohne node und ohne Browser: Der Test liest den JS-Code per Regex (ohne Kommentare) und hält fest, dass Bedingung,
Aufrufe, ausgeblendete Spalten und Glossar nicht auseinanderlaufen. Geprüft wird die Wirkung, nicht der Wortlaut einer
Zeile: Gleichwertige Umformulierungen (andere Reihenfolge einer Bedingung, anderer Variablenname) bleiben grün, eine
Spalte oder Kachel ohne Bedingung wird rot. Wie Hinweis und Tabellen tatsächlich aussehen (der Text hängt von der Uhrzeit
ab: „geplant …“ oder „fällig seit …“), zeigt ein Browser-Testlauf mit den App-Daten eines Dienstagmorgens (ad4df3f:
Hinweis) und danach (288d190, Montag 5d376e2: kein Hinweis). Die Byes im Profil prüft test_app_export
(profile_bye_weeks, nachgestellter Dienstag auf den echten Daten).
Aufruf: python -m pytest
"""

import re

import espn_fetch as ef

APP = ef.REPO_DIR / "app"
JS = APP / "js"
UI_JS, INDEX = JS / "ui.js", APP / "index.html"
WAIVER, SPIELER, TEAM = JS / "v_waiver.js", JS / "v_spieler.js", JS / "v_team.js"
# Spalten- bzw. Kachelobjekt mu oder mu3 als Bezeichner (nicht x.mu, nicht 'mu', nicht muWhy oder mu_woche)
MU = re.compile(r"(?<![\w.'\"-])mu3?\b")


def read(path) -> str:
    """Quelltext als Text; Zeilenenden (CRLF/LF) und ein BOM am Dateianfang spielen keine Rolle."""
    return path.read_text(encoding="utf-8-sig")


def code(path) -> str:
    """JS-Quelltext ohne Kommentare (// nach Zeilenanfang oder Leerraum, /* … */); „https://…“ bleibt stehen."""
    text = re.sub(r"/\*.*?\*/", "", read(path), flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text, flags=re.M)


def funktion(text: str, name: str) -> tuple[str, str]:
    """(Parameter, Rumpf) einer Funktion auf oberster Ebene: function name(…) { … bis zur schließenden Klammer am
    Zeilenanfang (Funktionen auf oberster Ebene enden so, alles darin ist eingerückt)."""
    m = re.search(rf"^(?:export )?(?:async )?function {name}\(([^)]*)\)\s*\{{(.*?)^\}}", text, re.M | re.S)
    assert m, f"Funktion {name} nicht gefunden"
    return m.group(1), m.group(2)


def bedingt(text: str, z: str) -> bool:
    """Steht in text eine Bedingung auf den Zwischenstand z (z ? …, z && …, !z …)? Nicht z?.feld."""
    return bool(re.search(rf"(?<![\w.])(?:!\s*{z}\b|{z}\s*(?:\?(?!\.)|&&))", text))


def klammer(text: str, i: int) -> str:
    """Ausdruck von der öffnenden eckigen Klammer an Stelle i bis zur passenden schließenden (Kachel-Liste)."""
    tiefe = 0
    for j in range(i, len(text)):
        tiefe += {"[": 1, "]": -1}.get(text[j], 0)
        if tiefe == 0:
            return text[i:j + 1]
    raise AssertionError("Klammer ohne Ende")


def zwischen_name(rumpf: str) -> str:
    """Name der Variable mit U.zwischenstand(W, P) im Rumpf."""
    m = re.search(r"\b(\w+) = U\.zwischenstand\(W, P\)", rumpf)
    assert m, "U.zwischenstand(W, P) nicht als Variable gefunden"
    return m.group(1)


def test_bedingung_nur_aus_tages_und_wochenstand():
    """Zwischenstand = waiver.json › woche größer als players.json › mu_woche – nicht manifest › datenstand.pool_woche
    (das ist der Wochen-Pool, also die gewertete Woche, und erkennt den Zustand nie). Der Hinweis nennt den Wochenabruf
    wie das Datenstand-Fenster (wochenabrufTxt: „geplant …“, danach „fällig seit …“, nie „verpasst“) und behauptet nicht,
    die alte Woche sei schon gespielt: Beim ersten Tageslauf am Dienstag läuft das Montagsspiel oft noch."""
    ui = code(UI_JS)
    m = re.search(r"^export const zwischenstand\b(.*?);[ \t]*$", ui, re.M | re.S)
    assert m, "U.zwischenstand in app/js/ui.js nicht gefunden"
    assert re.search(r"W\.woche\s*>\s*P\.mu_woche|P\.mu_woche\s*<\s*W\.woche", m.group(1)), "Bedingung nicht woche > mu_woche"
    assert "pool_woche" not in m.group(1)
    _, txt = funktion(ui, "wochenabrufTxt")
    assert "wochenabrufe(" in txt and "fällig seit" in txt and "geplant" in txt
    _, hinweis = funktion(ui, "zwischenHinweis")
    assert "wochenabrufTxt(" in hinweis, "Hinweis ohne den Termin aus wochenabrufTxt"
    assert "ist gespielt" not in hinweis, "Hinweis behauptet „ist gespielt“ (Montagsspiel läuft beim ersten Tageslauf oft noch)"
    assert "ib('vor-wochenabruf'" in hinweis, "Hinweiszeile ohne i-Knopf zum Glossar"


def test_ansichten_mit_hinweis():
    """Markt, Spielerseite und Team-Seite prüfen den Zwischenstand mit Tagesstand W und Wochenstand P und zeigen die
    Hinweiszeile nur unter dieser Bedingung; unter Markt › Reihenfolge & Claims bewusst nicht (dort zählt nur die Spalte
    Schwächen), auf der Team-Seite nur über Profil oder Bedarf, auf der Spielerseite verspricht der Zusatz „folgen mit dem
    Wochenabruf“ nur Spielern mit Matchup-Wert."""
    aufrufe = {}
    for path in (WAIVER, SPIELER, TEAM):
        text = code(path)
        assert "U.zwischenstand(W, P)" in text, f"{path.name}: Zwischenstand nicht geprüft"
        zeilen = [z for z in text.splitlines() if "U.zwischenHinweis(" in z]
        assert zeilen, f"{path.name}: Hinweiszeile fehlt"
        for zeile in zeilen:
            i = zeile.index("U.zwischenHinweis(")
            z = re.match(r"U\.zwischenHinweis\((\w+)", zeile[i:]).group(1)
            assert bedingt(zeile[:i], z), f"{path.name}: Hinweiszeile ohne Bedingung auf {z}"
        aufrufe[path] = zeilen
    assert all("'reihenfolge'" in z.split("U.zwischenHinweis(")[0] for z in aufrufe[WAIVER]), \
        "Markt: Hinweis auch unter Reihenfolge & Claims"
    assert all(re.search(r"\bprof\b", v) and re.search(r"\bB\b", v) for v in (z.split("U.zwischenHinweis(")[0] for z in aufrufe[TEAM])), \
        "Team-Seite: Hinweis nicht an Profil oder Bedarf gebunden"
    assert all(re.search(r"\bm\s*(?:\?(?!\.)|&&)", z.split("U.zwischenHinweis(", 1)[1]) for z in aufrufe[SPIELER]), \
        "Spielerseite: Zusatz „folgen mit dem Wochenabruf“ auch ohne Matchup-Wert"


def test_gegner_und_faktor_ausgeblendet():
    """Im Zwischenstand gälten Gegner und Faktor nächste 3 noch für die gespielte Woche: unter Markt › Freie Spieler fehlen
    beide Spalten in allen Horizonten samt Legende, auf der Spielerseite die Kacheln Gegner, Faktor und Rang und die
    Matchup-Notiz. Die Notiz „Kein Matchup-Wert“ (Spieler ohne Wert) bleibt auch im Zwischenstand."""
    params, rumpf = funktion(code(WAIVER), "available")
    zw = params.split(",")[-1].strip()                     # letzter Parameter = Zwischenstand
    leer = re.compile(rf"(?<![\w.]){zw}\s*\?\s*\[\]\s*:\s*\[([^\[\]]*)\]")    # zw ? [] : [...]
    inhalte = leer.findall(rumpf)
    assert sum(1 for i in inhalte if re.search(r"(?<![\w.'\"-])mu\b", i) and re.search(r"(?<![\w.'\"-])mu3\b", i)) >= 2, \
        "Gegner und Faktor nächste 3 nicht in beiden Spalten-Zweigen (Langfristig und die übrigen Horizonte) bedingt"
    assert any("'mu-n1'" in i and "'mu-naechste3'" in i for i in inhalte), "Legende Gegner/Faktor nächste 3 nicht bedingt"
    rest = re.sub(r"\bconst mu3? =", "", leer.sub("", rumpf))
    assert not MU.search(rest), "Spalte Gegner oder Faktor nächste 3 ohne Bedingung"
    assert "'mu-n1'" not in rest and "'mu-naechste3'" not in rest, "Legende Gegner/Faktor nächste 3 ohne Bedingung"

    _, woche = funktion(code(SPIELER), "woche")
    z = zwischen_name(woche)
    i = woche.index("'mu-n1'")                             # Kachel Gegner
    k = woche.rfind("[", 0, woche.rfind("U.tile(", 0, i))   # Liste der Matchup-Kacheln
    zeile = woche[woche.rfind("\n", 0, k) + 1:k]
    assert bedingt(zeile, z), "Kacheln Gegner, Faktor und Rang ohne Bedingung"
    kacheln = klammer(woche, k)
    assert all(key in kacheln for key in ("'mu-n1'", "'mu-f'", "'mu-rang'")), "Kachel Faktor oder Rang außerhalb der Bedingung"
    kein = woche.index("Kein Matchup-Wert")
    notiz = min(woche.index("Faktor der gegnerischen Offense"), woche.index("Position gegen Defense"))
    assert bedingt(woche[kein:notiz], z), "Matchup-Notiz ohne Bedingung"
    assert not bedingt(woche[woche.rfind("\n", 0, kein):kein], z), "Notiz „Kein Matchup-Wert“ im Zwischenstand ausgeblendet"


def test_glossar():
    """Der Eintrag „Gespielt, noch nicht gewertet“ steht im Glossar, nennt keine eigene Uhrzeit (die Zeiten stehen unter
    Aktualisierung, test_zeitplan hält sie zusammen), und jeder i-Knopf mit festem Schlüssel in ui.js hat einen Eintrag."""
    index = read(INDEX)
    ids = set(re.findall(r'<dt id="g-([\w-]+)">', index))
    assert "vor-wochenabruf" in ids
    eintrag = re.search(r'<dt id="g-vor-wochenabruf">.*?</dt><dd>(.*?)</dd>', index, re.S).group(1)
    assert not re.search(r"\d\d:\d\d", eintrag), "Glossar „Gespielt, noch nicht gewertet“ nennt eine Uhrzeit ohne Wächter"
    knoepfe = set(re.findall(r"\bib\('([\w-]+)'", code(UI_JS)))
    assert knoepfe and knoepfe <= ids, f"i-Knopf ohne Glossareintrag: {sorted(knoepfe - ids)}"
