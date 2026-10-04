"""Wächter für Menü und Routen der App (App-Konzept 04.10.2026, Paket P1): fünf Bereiche als Tabs, jede Ansicht mit
vorhandenem Modul, jeder alte Hash leitet auf eine gültige Route um, und die App selbst verlinkt nur noch neue Routen.

Ohne node und ohne Browser: Der Test liest BEREICHE, VIEWS und ALT aus app/js/app.js per Regex und sucht Hash-Links
('#…' in Anführungszeichen, href="#…") im Code von app/js und in app/index.html. Ob die Umleitung im Browser greift,
prüft er nicht (das zeigt ein Browsertest mit allen alten Hashes); er hält fest, dass Routentabelle, Umleitungen und
Links nicht auseinanderlaufen – etwa wenn eine Ansicht umbenannt wird und ein Link irgendwo noch den alten Pfad trägt.
Aufruf: python -m pytest
"""

import re

import espn_fetch as ef

APP = ef.REPO_DIR / "app"
JS = APP / "js"
APP_JS = JS / "app.js"
INDEX = APP / "index.html"
# die fünf Bereiche in der Reihenfolge der Tabs
TABS = ["liga", "staerke", "woche", "markt", "keeper"]
# Routen der App bis 04.10.2026 (sieben Tabs, Ansichten ohne Tab, Lesart): Jede lebt als Umleitung weiter, damit Lesezeichen,
# README, Aufträge und die Anweisung des Claude-Projekts nicht ins Leere führen
ALTE_ROUTEN = {"tabelle", "tabelle/allplay", "tabelle/punkte", "tabelle/coaching", "tabelle/ausblick", "ranking",
               "spielplan", "rekorde", "rekorde/h2h", "matchup", "dst", "dst/offense", "wetter", "waiver", "moves",
               "moves/draft", "keeper/kader", "keeper/wert",
               "lesart"}                          # seit Paket P4 (04.10.2026) „Erklärungen“, #erklaerungen
# Elemente, die per „#…“ angesprochen werden, aber keine Routen sind (Sprungmarke, Knöpfe im Kopf)
KEINE_ROUTE = {"main", "stand", "such", "mt"}


def _app() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _block(name: str) -> str:
    m = re.search(rf"const {name} = \{{(.*?)\n?\}};", _app(), re.S)
    assert m, f"{name} in app/js/app.js nicht gefunden"
    return m.group(1)


def bereiche() -> dict[str, list[tuple[str, str]]]:
    """Bereich → [(Pfad der Ansicht, Modul)] in der Reihenfolge der Chips."""
    block = _block("BEREICHE")
    starts = list(re.finditer(r"^  (\w+): \{l: '", block, re.M))
    out = {}
    for i, m in enumerate(starts):
        teil = block[m.end():starts[i + 1].start() if i + 1 < len(starts) else len(block)]
        out[m.group(1)] = re.findall(r"\['([\w/-]*)', [^\]]*?'(v_\w+)'\]", teil)
    return out


def views() -> dict[str, str]:
    return dict(re.findall(r"(\w+): '(v_\w+)'", _block("VIEWS")))


def alt() -> dict[str, str]:
    paare = re.findall(r"(?:'([\w/-]+)'|(\w+)): '([\w/-]+)'", _block("ALT"))
    return {a or b: ziel for a, b, ziel in paare}


def gueltig(pfad: str) -> bool:
    """Neue Route (ohne „#“ und Parameter): Seite ohne Bereich oder Bereich mit einer seiner Ansichten am Anfang."""
    sec, _, rest = pfad.partition("/")
    if sec in views():
        return True
    pfade = [p for p, _ in bereiche().get(sec, [])]
    if sec not in TABS:
        return False
    if not rest:
        return "" in pfade or sec == "woche"          # #woche leitet auf die erste Ansicht um (app.js umleitung)
    return any(p and (rest == p or rest.startswith(p + "/")) for p in pfade)


def code(datei) -> str:
    """Quelltext ohne Zeilenkommentare (// nach Leerraum oder am Zeilenanfang; „https://“ bleibt)."""
    return "\n".join(re.sub(r"(^|\s)//.*$", "", z) for z in datei.read_text(encoding="utf-8").splitlines())


def test_tabs_sind_die_fuenf_bereiche():
    assert list(bereiche()) == TABS, "BEREICHE in app.js: fünf Bereiche in der Reihenfolge der Tabs"
    html = INDEX.read_text(encoding="utf-8")
    leiste = html.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r'<a href="#(\w+)" data-s="(\w+)">', leiste) == [(k, k) for k in TABS]
    kopf = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert re.search(r'<a class="brand" href="#start"', kopf), "Marke führt zur Startseite (Paket P2)"
    assert re.search(r'<button id="such"[^>]*aria-controls="pop"[^>]*aria-label="[^"]+"', kopf), "Lupe im Kopf fehlt"
    assert re.search(r'<button id="mt"[^>]*aria-controls="pop"[^>]*aria-label="[^"]+"', kopf), "Mein Team im Kopf fehlt"


def test_startseite():
    """Die App öffnet mit der Startseite (Paket P2): #start ist eine Seite ohne Tab, leere und unbekannte Hashes führen dorthin,
    und ihre Karten nehmen Frage und Namen der Bereiche aus BEREICHE (eine Quelle für Kopf und Startseite)."""
    assert views().get("start") == "v_start"
    app = code(APP_JS)
    assert "history.replaceState(null, '', '#' + (res ? res.k : 'start'))" in app, "Rückfall ohne Route: Startseite"
    assert "bereiche: () => Object.entries(BEREICHE)" in app
    start = code(JS / "v_start.js")
    assert "ctx.bereiche()" in start
    # nur teams.json, schedule.json (S.teams, S.sched) und waiver.json – die Startseite lädt keine weiteren Dateien
    assert set(re.findall(r"ctx\.(?:load|lazy)\('([\w.]+)'", start)) == {"waiver.json"}


def test_jede_ansicht_hat_ein_modul():
    module = {m for liste in bereiche().values() for _, m in liste} | set(views().values())
    for m in sorted(module):
        assert (JS / f"{m}.js").exists(), f"Route ohne Datei: {m}.js"
    for k, liste in bereiche().items():
        pfade = [p for p, _ in liste]
        assert len(pfade) == len(set(pfade)), f"{k}: doppelte Ansicht"
        assert all(gueltig(f"{k}/{p}" if p else k) for p in pfade)


def test_alte_routen_leiten_um():
    umleitung = alt()
    assert ALTE_ROUTEN <= set(umleitung), f"alte Route ohne Umleitung: {sorted(ALTE_ROUTEN - set(umleitung))}"
    for quelle, ziel in umleitung.items():
        assert gueltig(ziel), f"Umleitung {quelle} → {ziel}: keine Route"
        # keine Ketten: das Ziel wird nicht noch einmal umgeleitet
        assert not any(ziel == a or ziel.startswith(a + "/") for a in umleitung), f"Umleitung {quelle} → {ziel} führt weiter"
    # alte erste Pfadteile sind keine neuen Routen mehr (sonst griffe die Umleitung nicht für Unterpfade)
    for quelle in ALTE_ROUTEN:
        sec = quelle.split("/")[0]
        assert sec in TABS or not gueltig(sec), f"{sec} ist zugleich alte und neue Route"


def test_app_verlinkt_nur_neue_routen():
    falsch = []
    for datei in sorted(JS.glob("*.js")):
        for pfad in re.findall(r"""['"`]#([a-z][\w/-]*)""", code(datei)):
            if re.fullmatch(r"[0-9a-f]{3,8}", pfad) or pfad in KEINE_ROUTE:   # Farben (#ffffff), Element-IDs
                continue
            if not gueltig(pfad.rstrip("/")):
                falsch.append(f"{datei.name}: #{pfad}")
        # Pfade ohne „#“: setQ schreibt die Adresse der offenen Ansicht, weekChips baut Wochen-Links (sonst r.base)
        for pfad in re.findall(r"""\b(?:setQ|weekChips)\(\s*['"`]([\w/-]*)""", code(datei)):
            if not gueltig(pfad.rstrip("/")):
                falsch.append(f"{datei.name}: setQ/weekChips {pfad}")
    for pfad in re.findall(r'href="#([^"?]*)', INDEX.read_text(encoding="utf-8")):
        if pfad not in KEINE_ROUTE and not gueltig(pfad):
            falsch.append(f"index.html: #{pfad}")
    assert not falsch, f"Links auf alte oder unbekannte Routen: {falsch}"


def test_einfach_ausfuehrlich():
    """Ein Schalter für alle Tabellen (Paket P5): U.table blendet Spalten mit x aus und trägt dann den Schalter, die Ansichten
    nach Abschnitt 8 kennzeichnen ihre Spalten, die Erklärung steht im Glossar, und die alten Spalten-Sichten unter Markt
    („Alle · Projektionen · Besitz“) und in der Spielerliste („Saison · Rest Saison · Besitz“) gibt es nicht mehr."""
    ui = code(JS / "ui.js")
    assert "export const spaltenVoll" in ui and "export function setSpaltenVoll" in ui
    assert "alle.filter(c => !c.x || spaltenVoll())" in ui, "U.table blendet Spalten nur für „Ausführlich“ aus"
    for modul in ("v_tabelle", "v_ranking", "v_spielplan", "v_matchup", "v_waiver", "v_spieler", "v_keeper", "v_rekorde"):
        assert re.search(r"\bx: (?:1|!!\w+)|\bX\(", code(JS / f"{modul}.js")), f"{modul}.js ohne Spalten nur für „Ausführlich“"
    assert 'id="g-spalten"' in INDEX.read_text(encoding="utf-8")
    for modul in ("v_waiver", "v_spieler"):
        assert not re.search(r"U\.seg\('Spalten'", code(JS / f"{modul}.js")), f"{modul}.js: alte Spalten-Sicht"


def test_team_seite_nach_bereichen():
    """Die Team-Seite gliedert sich in die fünf Bereiche des Menüs, in derselben Reihenfolge (Paket P6), mit Name und Frage
    aus BEREICHE; die Spielerseite hat die Abschnitte Woche, Saison, Rest der Saison, Markt, Keeper."""
    team = code(JS / "v_team.js")
    assert "ctx.bereiche()" in team
    stellen = [team.find(f"sec('{k}'") for k in TABS]
    assert all(i >= 0 for i in stellen) and stellen == sorted(stellen), "Abschnitte der Team-Seite in der Reihenfolge der Tabs"
    spieler = code(JS / "v_spieler.js")
    reihe = [spieler.find(x) for x in ("woche(box", "`Saison ${", "'Rest der Saison'", "'Markt'", "'Keeper'", "newsBox(p, W))")]
    assert all(i >= 0 for i in reihe) and reihe == sorted(reihe), "Abschnitte der Spielerseite"
