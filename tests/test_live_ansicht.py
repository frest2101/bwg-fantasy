"""Wächter für die Live-Ansicht der App (#spieltag: app/js/live_core.js und app/js/v_spieltag.js).

Die Ansicht holt den laufenden Spieltag im Browser direkt bei ESPN. Dieser Test liest nur den Quelltext (ohne Netz,
ohne node, ohne Daten und ohne Uhr – ein fehlendes Werkzeug auf dem Runner oder ein neuer Datenstand hielte sonst die
abgeleiteten Daten zurück) und hält fest, was für ein öffentliches Repo gelten muss: nur lesende ESPN-Endpunkte und
nur GET, keine Zugangsdaten, kein Token, kein Dauerabruf, nichts im Browser-Speicher, keine Manager-Daten, keine
ESPN-Redaktionstexte, keine gescheiterten Claims, kein HTML und keine Adresse aus fremden Texten. Dazu die
Verdrahtung: Route, Liga-ID, Tageslauf-Knopf, Glossar und die Konstanten, die live_core.js mit scripts/claude_stand.py
teilt.

Grenzen: Der Test sucht Muster im Quelltext, er führt nichts aus. Er fängt die naheliegenden Wege ab, keinen
absichtlich versteckten (etwa einen aus Teilstrings zusammengesetzten Funktionsnamen in einem anderen Modul). Die
Rechnung selbst prüft er nicht: Die Gegenprobe mit node gegen das Stand-Skript liegt nicht im Repo und wird von Hand
wiederholt, wenn live_core.js oder claude_stand.py sich ändern (docs/app_daten.md, Abschnitt Live-Ansicht).
Kommentare zählen nicht: Geprüft wird der Quelltext ohne Kommentare, damit ein harmloses Wort in einer Erklärung den
Test nicht rot macht.
Aufruf: python -m pytest
"""

import re

import check_public
import claude_stand as cs
import espn_fetch as ef

APP = ef.REPO_DIR / "app"
JS = APP / "js"
CORE, VIEW = JS / "live_core.js", JS / "v_spieltag.js"
APP_JS, UI_JS = JS / "app.js", JS / "ui.js"
INDEX = APP / "index.html"
WORKFLOWS = ef.REPO_DIR / ".github" / "workflows"

ERLAUBTE_VIEWS = {"mMatchupScore", "mRoster", "mTeam", "mTransactions2", "kona_player_info"}
ERLAUBTE_HOSTS = {"lm-api-reads.fantasy.espn.com", "site.api.espn.com"}     # ESPN, nur lesend
GLOSSAR = ("live", "live-punkte", "live-siegchance", "live-starter", "neu-tagesstand", "tageslauf-starten")
KNOPF = "Tageslauf starten (GitHub)"
# Manager-Daten, Absichten und ESPN-Redaktionstexte: dieselbe Liste wie im Öffentlichkeits-Check, dazu „owners“ & Co.
VERBOTEN = sorted(check_public.FORBIDDEN_KEYS | {"owners", "primaryOwner", "members", "outlooks", "seasonOutlook"})
# HTML aus Text: Fremdtexte kommen nur als Textknoten über h() in die Seite
HTML_WEGE = ("innerHTML", "outerHTML", "insertAdjacentHTML", "setHTMLUnsafe", "setHTML(", "srcdoc", "document.write",
             "DOMParser", "parseFromString", "createContextualFragment", "eval(", "Function(")
# Schreibende oder dauerhafte Verbindungen (ganze Wörter, Groß-/Kleinschreibung zählt: „post“ ist ein Spielstatus)
SCHREIBWEGE = ("POST", "PUT", "DELETE", "PATCH", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource")
# Ablage im Browser: Die Rohantwort (samt Manager-Daten) wird verworfen; gelesen wird nur „Mein Team“ (U.meinTeam())
SPEICHER = (r"\blocalStorage\b", r"\bsessionStorage\b", r"\bindexedDB\b", r"\bcaches\s*\.", r"\.cookie\b",
            r"\bstore\s*\.\s*set\b", r"\bsetMeinTeam\b", r"\bBroadcastChannel\b", r"\bserviceWorker\b")
# Umwege zu fetch oder zum Speicher über das globale Objekt bzw. nachgeladenen Code
UMWEGE = (r"\bglobalThis\b", r"\bwindow\b", r"\bself\b", r"\bimport\s*\(", r"\bnavigator\b")
# Dauerabruf: Zeitgeber dürfen nur abbrechen, Ereignisse nur aus Knöpfen und Auswahl kommen
ABRUF_NAMEN = ("laden", "holen", "hole", "abrufen", "teilen", "render", "route", "refresh", "zeichne", "fetch")
# Gescheiterte und zurückgezogene Claims, Trade-Vorschläge: zeigt die öffentliche App nicht (Glossar „Transaktionen“)
NICHT_OEFFENTLICH = re.compile(r"FAILED|CANCELED|PENDING|PROPOS|DECLINE|VETO|UPHOLD")
TOKEN = re.compile(r"github_pat_|\bgh[opsur]_\w")


def read(path) -> str:
    """Quelltext als Text; Zeilenenden (CRLF/LF) und ein BOM am Dateianfang spielen keine Rolle."""
    return path.read_text(encoding="utf-8-sig")


def code(path) -> str:
    """JS-Quelltext ohne Kommentare (// bis zum Zeilenende nach Zeilenanfang oder Leerraum, /* … */). Bewusst
    einfach: „https://…“ bleibt stehen, weil vor // ein Doppelpunkt steht."""
    text = re.sub(r"/\*.*?\*/", "", read(path), flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text, flags=re.M)


def live() -> dict[str, str]:
    """Quelltext ohne Kommentare der beiden Live-Module je Dateiname."""
    return {p.name: code(p) for p in (CORE, VIEW)}


def js_tabelle(text: str, name: str) -> dict[int, str]:
    """Ein Objekt-Literal {0: 'QB', …} aus dem JS-Quelltext als dict."""
    block = re.search(rf"const {name} = \{{(.*?)\}};", text, re.S)
    assert block, f"{name} in live_core.js nicht gefunden"
    return {int(k): v for k, v in re.findall(r"(\d+): '([^']+)'", block.group(1))}


def test_route_und_chip():
    """#spieltag steht im Router und lädt v_spieltag.js; „#live“ bleibt die aria-live-Region. Kein eigener Tab: Der
    Zugang ist die erste Ansicht im Bereich Woche (Chip „Spieltag live“, während der Saison auch der Tab Woche; fünf Tabs,
    App-Konzept 04.10.2026). Den Chip „Live“ im Kopf gibt es seit Paket P2 nicht mehr (dort steht Mein Team); seinen
    Nachlade-Tipp übernimmt der Tab Woche."""
    views = re.search(r"const VIEWS = \{(.*?)\};", read(APP_JS), re.S)
    assert views, "VIEWS in app/js/app.js nicht gefunden"
    routen = dict(re.findall(r"(\w+): '(\w+)'", views.group(1)))
    assert routen.get("spieltag") == "v_spieltag"
    assert "live" not in routen, "#live ist die aria-live-Region (id=\"live\"), keine Route"
    for modul in routen.values():
        assert (JS / f"{modul}.js").exists(), f"Route ohne Datei: {modul}.js"
    html = read(INDEX)
    assert re.search(r'<div id="live"[^>]*aria-live="polite"', html)
    app = read(APP_JS)
    assert "['live', 'Spieltag live', 'v_spieltag']" in app, "Spieltag live ist die erste Ansicht im Bereich Woche"
    assert "p === 'live' ? '#spieltag'" in app, "Chip „Spieltag live“ führt auf #spieltag"
    assert "U.saisonLaeuft() ? 'spieltag'" in app, "#woche öffnet während der Saison den Spieltag live"
    assert """querySelector('.tabs a[data-s="woche"]')""" in code(VIEW), "Tab Woche lädt in der offenen Live-Ansicht neu"
    leiste = html.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[0]
    assert "#spieltag" not in leiste and leiste.count("<a ") == 5


def test_liga_und_endpunkte():
    """Liga-ID und Adresse wie in scripts/espn_fetch.py; angefragt werden nur die erlaubten Views und nur die beiden
    ESPN-Lese-Hosts. Die Ansicht selbst nennt keine Adresse – alle kommen aus live_core.js."""
    core, view = code(CORE), code(VIEW)
    liga_id = re.search(r"^export const LIGA_ID = (\d+);", core, re.M)
    assert liga_id and int(liga_id.group(1)) == ef.LEAGUE_ID == cs.LIGA_ID
    url = re.search(r"export const ligaUrl = saison => `([^`]+)`;", core)
    assert url and url.group(1).replace("${saison}", "{season}").replace("${LIGA_ID}", "{league}") == ef.BASE_URL
    assert re.search(r"export const SCOREBOARD_URL = '([^']+)';", core).group(1) == cs.SCOREBOARD_URL
    views = re.search(r"export const LIGA_VIEWS = \[([^\]]+)\];", core)
    assert views and tuple(re.findall(r"'(\w+)'", views.group(1))) == cs.LIGA_VIEWS
    assert re.search(r"export const KONA_VIEW = '(\w+)';", core).group(1) == ef.KONA_VIEW == cs.KONA_VIEW
    for name, text in live().items():
        genannt = set(re.findall(r"['\"`](m[A-Z]\w+|kona_\w+)['\"`]", text))
        assert genannt <= ERLAUBTE_VIEWS, f"{name}: nicht erlaubter View {sorted(genannt - ERLAUBTE_VIEWS)}"
        hosts = set(re.findall(r"https?://([^/'\"`\s]+)", text))
        assert hosts <= ERLAUBTE_HOSTS, f"{name}: fremder Host {sorted(hosts - ERLAUBTE_HOSTS)}"
    assert not re.search(r"https?:|['\"`]//", view), "v_spieltag.js nennt keine Adressen selbst"
    assert not re.search(r"\bview\s*=", view), "Views nur über LIGA_VIEWS und KONA_VIEW aus live_core.js"
    assert set(re.findall(r"\bview: C\.(\w+)", view)) == {"KONA_VIEW"} and "C.LIGA_VIEWS.map(v => ['view', v])" in view


def test_nur_lesen_ohne_zugangsdaten():
    """Ein einziger fetch-Aufruf in der Ansicht, GET, ohne Cookies; kein Schreibweg, kein Umweg über das globale
    Objekt. live_core.js rechnet nur (kein Netz, kein DOM, kein Zeitgeber). Nirgends in der App Cookies an einem
    Abruf, ein Token oder ein Aufruf der GitHub-API (Beschluss 02.10.2026: der Tageslauf wird nur verlinkt, nicht
    aus der App gestartet)."""
    core, view = code(CORE), code(VIEW)
    assert len(re.findall(r"\bfetch\b", view)) == 1, "genau eine Nennung von fetch in v_spieltag.js (kein Alias, kein zweiter Abruf)"
    aufrufe = re.findall(r"\bfetch\(([^;]*);", view, re.S)
    assert len(aufrufe) == 1, "genau ein fetch-Aufruf in v_spieltag.js"
    assert "method: 'GET'" in aufrufe[0] and "credentials: 'omit'" in aufrufe[0]
    assert "AbortController" in view, "Zeitlimit je Abruf fehlt"
    for muster in (r"\bfetch\b", r"\bdocument\s*[.\[]", r"\bsetTimeout\b", r"\bconsole\s*\.", r"\bimport\b", r"\bDate\s*\.\s*now\b"):
        assert not re.search(muster, core), f"live_core.js soll rein bleiben: {muster}"
    for name, text in live().items():
        for wort in SCHREIBWEGE:
            assert not re.search(rf"(?<![\w$]){wort}(?![\w$])", text), f"{name}: {wort}"
        for muster in UMWEGE:
            assert not re.search(muster, text), f"{name}: {muster}"
    for path in sorted(JS.glob("*.js")):
        text = code(path)
        methoden = set(re.findall(r"\bmethod\s*:\s*([^,}\s]+)", text))
        assert methoden <= {"'GET'"}, f"{path.name}: Abruf mit {sorted(methoden)} – die App liest nur"
        cookies = set(re.findall(r"\bcredentials\s*:\s*([^,}\s]+)", text))
        assert cookies <= {"'omit'"}, f"{path.name}: credentials {sorted(cookies)} – kein Abruf mit Cookies"
        for wort in ("withCredentials", "api.github.com", "Authorization", "/dispatches", "Bearer "):
            assert wort not in text, f"{path.name}: {wort} – kein Token und kein GitHub-API-Aufruf in der App"


def test_kein_token_in_der_app():
    """Kein GitHub-Token im Code der App (JS, HTML, CSS) – auch nicht als Platzhalter. app/data bleibt außen vor:
    Der Test hängt an keinem Datenstand."""
    for path in sorted(p for p in APP.rglob("*") if p.suffix in (".js", ".html", ".css") and "data" not in p.relative_to(APP).parts):
        assert not TOKEN.search(read(path)), f"{path.relative_to(APP)}: sieht nach einem GitHub-Token aus"


def test_kein_dauerabruf():
    """Geladen wird nur beim Öffnen und auf Knopfdruck. Die Ansicht hat keinen wiederkehrenden Zeitgeber; jeder
    setTimeout bricht nur ab (Zeitlimit, Nachlauf) und ruft nichts auf, das lädt; Ereignisse kommen nur aus Knöpfen
    und der Team-Auswahl, nicht aus Sichtbarkeit, Fokus oder Netzstatus."""
    view = code(VIEW)
    for wort in ("setInterval", "requestAnimationFrame", "requestIdleCallback", "MutationObserver", "IntersectionObserver"):
        assert wort not in view, f"v_spieltag.js: {wort}"
    timer = re.findall(r"\bsetTimeout\b([^\n]*)", view)      # je Zeitgeber der Rest seiner Zeile
    assert timer, "Zeitlimit je Abruf fehlt (setTimeout mit abort)"
    for rest in timer:
        assert ".abort()" in rest, f"setTimeout ohne abort: {rest.strip()[:80]}"
        # auch ctx.route( / ctx.refresh( zählen – deshalb kein Punkt im Lookbehind
        funde = [n for n in ABRUF_NAMEN if re.search(rf"(?<![\w$]){n}\s*\(", rest)]
        assert not funde, f"setTimeout ruft {funde} auf – das wäre ein Dauerabruf: {rest.strip()[:80]}"
    assert set(re.findall(r"addEventListener\(\s*'(\w+)'", view)) <= {"abort"}, "Ereignisse nur für den Abbruch eines Abrufs"
    # on…-Schlüssel für h() und zugewiesene Handler; „once“ ist eine Option von addEventListener, kein Ereignis
    assert set(re.findall(r"(?<![\w$.])on(?!ce\b)([a-z]+)\s*:", view)) <= {"click", "change"}, "Auslöser nur Knopf und Auswahl"
    assert set(re.findall(r"\.on([a-z]+)\s*=(?!=)", view)) <= {"click"}, "Auslöser nur Knopf und Auswahl"


def test_nichts_im_browser_speicher():
    """Die Live-Module legen nichts ab: kein localStorage, sessionStorage, IndexedDB, Cache, Cookie und kein
    U.store.set und kein U.setMeinTeam – die Rohantwort von ESPN enthält Manager-Daten und wird nach dem Rechnen verworfen;
    Mein Team wird nur über U.meinTeam() gelesen."""
    for name, text in live().items():
        for muster in SPEICHER:
            assert not re.search(muster, text), f"{name}: {muster}"
    view = code(VIEW)
    assert "U.meinTeam()" in view, "Mein Team wird über U.meinTeam() gelesen"
    assert set(re.findall(r"\bstore\s*\.\s*(\w+)", view)) <= {"get"}, "aus dem Browser-Speicher wird nur gelesen (Mein Team)"


def test_keine_manager_und_keine_redaktionstexte():
    """Die Live-Module nennen kein Feld mit Manager-Daten, Absichten oder ESPN-Texten – auch nicht, um es zu löschen:
    Sie lesen nach Positivliste und geben nur Abgeleitetes weiter. Gescheiterte und zurückgezogene Claims und
    Trade-Vorschläge liest und zeigt die Ansicht nicht (wie der Moves-Tab, Glossar „Transaktionen“)."""
    for name, text in live().items():
        funde = [wort for wort in VERBOTEN if re.search(rf"(?<![\w$]){re.escape(wort)}(?![\w$])", text)]
        assert not funde, f"{name}: nennt {funde}"
        assert not NICHT_OEFFENTLICH.search(text), f"{name}: {NICHT_OEFFENTLICH.search(text).group(0)} – nur ausgeführte Moves und angenommene Trades"
    html = read(INDEX)
    transaktionen = re.search(r'<dt id="g-transaktionen">.*?</dt><dd>(.*?)</dd>', html, re.S).group(1)
    assert "keine gescheiterten Claims" in transaktionen
    neu = re.search(r'<dt id="g-neu-tagesstand">.*?</dt><dd>(.*?)</dd>', html, re.S).group(1)
    assert not re.search(r"Claims[^.]*gezählt", neu), "Glossar widerspricht sich: gescheiterte Claims werden nicht gezählt"


def test_kein_html_und_keine_adresse_aus_fremden_texten():
    """Fremdtexte (Spieler- und Teamnamen, Scoreboard-Detail) kommen nur als Textknoten über h() in die Seite. Links
    der Ansicht zeigen nur in die App (#…, höchstens mit angehängter ID); die einzige Adresse nach außen ist der feste
    Tageslauf-Knopf aus ui.js."""
    for name, text in live().items():
        for wort in HTML_WEGE:
            assert wort not in text, f"{name}: {wort}"
    view = code(VIEW)
    ziel = re.compile(r"^(?:\w+\([\w.]+\) \? )?'#[\w/]*'(?: \+ [\w.]+)?(?: : null)?$")
    hrefs = [x.strip() for x in re.findall(r"\bhref\s*:\s*([^,}]+)", view)]
    assert hrefs and all(ziel.match(x) for x in hrefs), f"href nur als '#…' (+ ID): {[x for x in hrefs if not ziel.match(x)]}"
    for muster in (r"\.href\b", r"\bsetAttribute\(\s*['\"](?:href|src|action|style|on\w+)", r"\blocation\b", r"\bopen\s*\(",
                   r"\b(?:src|action|formaction|style)\s*:"):
        assert not re.search(muster, view), f"v_spieltag.js: {muster}"


def test_tageslauf_knopf_zeigt_auf_den_workflow():
    """Der Knopf im Datenstand-Fenster und in der Live-Ansicht öffnet die Workflow-Seite des Tageslaufs (neuer Tab,
    noopener, Aussehen der übrigen Knöpfe); die Datei gibt es, und sie lässt sich von Hand starten
    (workflow_dispatch). In der Live-Ansicht steht der Knopf immer, nicht nur bei neuen Bewegungen."""
    ui = code(UI_JS)
    url = re.search(r"export const TAGESLAUF_URL = '([^']+)';", ui)
    assert url, "TAGESLAUF_URL in app/js/ui.js nicht gefunden"
    kopf, datei = url.group(1).rsplit("/", 1)
    assert kopf == "https://github.com/frest2101/bwg-fantasy/actions/workflows"
    assert datei == "tageslauf.yml" and (WORKFLOWS / datei).exists()
    assert re.search(r"^\s*workflow_dispatch:", read(WORKFLOWS / datei), re.M)
    knopf = re.search(r"export const tageslaufKnopf = [^\n]+", ui)
    assert knopf, "tageslaufKnopf in app/js/ui.js nicht gefunden"
    for teil in ("href: TAGESLAUF_URL", "target: '_blank'", "rel: 'noopener'", "class: 'btn'", f"'{KNOPF}'"):
        assert teil in knopf.group(0), f"tageslaufKnopf ohne {teil}"
    assert "U.tageslaufKnopf()" in code(APP_JS), "Knopf fehlt im Datenstand-Fenster"
    view = code(VIEW)
    # Kopf der Ansicht: Überschrift mit Bereichs-Zeile (U.kopf), direkt danach Hinweis, Aktualisieren und Tageslauf-Knopf
    kopfzeile = re.search(r"U\.kopf\(box, r, 'Spieltag live'\);\s*U\.ap\(box, kopf,[^\n]*", view)
    assert kopfzeile and "U.tageslaufKnopf()" in kopfzeile.group(0), "Knopf steht in der Live-Ansicht immer neben „Aktualisieren“"
    for path in sorted(JS.glob("*.js")):
        if path != UI_JS:
            assert "/actions" not in code(path), f"{path.name}: Adresse der Actions nur über TAGESLAUF_URL in ui.js"


def test_glossar_eintraege():
    """Die Einträge der Live-Ansicht stehen im Glossar; jeder i-Knopf der Ansicht und der Verweis im
    Datenstand-Fenster haben ein Ziel. Die Texte nennen die übertragene Größe und den Weg nach dem Tageslauf."""
    html = read(INDEX)
    ids = set(re.findall(r'<dt id="g-([\w-]+)">', html))
    assert set(GLOSSAR) <= ids, f"Glossar ohne {sorted(set(GLOSSAR) - ids)}"
    view = code(VIEW)
    knoepfe = set(re.findall(r"U\.ib\('([\w-]+)'", view))
    legende = re.search(r"U\.legend\(\[([^\]]+)\]\)", view)
    assert legende, "Legende der Live-Ansicht nicht gefunden"
    knoepfe |= set(re.findall(r"'([\w-]+)'", legende.group(1)))
    assert knoepfe and knoepfe <= ids, f"i-Knopf ohne Glossareintrag: {sorted(knoepfe - ids)}"
    assert set(GLOSSAR) <= knoepfe
    assert "#erklaerungen/tageslauf-starten" in code(APP_JS)

    def eintrag(gid: str) -> str:
        return re.search(rf'<dt id="g-{gid}">.*?</dt><dd>(.*?)</dd>', html, re.S).group(1)

    assert "ESPN" in eintrag("live-siegchance") and "keine eigene Rechnung" in eintrag("live-siegchance")
    assert "Zwischenstände" in eintrag("live-punkte")
    assert "1,1 MB übertragen (4,5 MB entpackt)" in eintrag("live")
    starten = eintrag("tageslauf-starten")
    assert KNOPF in starten and "Aktualisieren" in starten and "Daten neu laden" in starten


def test_konstanten_wie_im_stand_skript():
    """live_core.js ist die Abschrift der Regeln aus scripts/claude_stand.py: Slots, Positionen, NFL-Kürzel,
    Starterzahl, Status-Gruppen und die Schwelle der Sammelzeile stimmen überein."""
    core = code(CORE)
    assert js_tabelle(core, "SLOT") == cs.SLOT
    assert js_tabelle(core, "POS") == cs.POS
    assert js_tabelle(core, "NFL") == cs.NFL

    def liste(name: str) -> list[str]:
        block = re.search(rf"const {name} = \[([^\]]*)\];", core)
        assert block, f"{name} in live_core.js nicht gefunden"
        return [x.strip().strip("'") for x in block.group(1).split(",")]

    assert [int(x) for x in liste("STARTER_SLOTS")] == list(cs.STARTER_SLOTS)
    assert liste("OFFEN") == list(cs.OFFEN) and liste("SPIELFREI") == list(cs.SPIELFREI)
    assert liste("MOVE_TYPEN") == list(cs.MOVE_ARTEN) and set(liste("SPIELER_ITEMS")) == cs.SPIELER_ITEMS
    zahl = {name: int(wert) for name, wert in re.findall(r"const (STARTER_ZAHL|SAMMEL_AB|TEXT_MAX) = (\d+);", core)}
    assert zahl == {"STARTER_ZAHL": cs.STARTER_ZAHL, "SAMMEL_AB": cs.SAMMEL_AB, "TEXT_MAX": cs.TEXT_MAX}
    assert re.search(r"const SLOT_BANK = (\d+), SLOT_IR = (\d+);", core).groups() == (str(cs.SLOT_BANK), str(cs.SLOT_IR))
