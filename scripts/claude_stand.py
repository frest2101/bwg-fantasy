"""Stand des laufenden Spieltags für den claude.ai-Projekt-Chat: ein Aufruf, ein kompakter Text.

Eigenständig (läuft allein im Code-Container des Chats): nur Standardbibliothek und requests, keine Importe aus dem
Repo, kein zoneinfo. Nur lesend: ESPN-Liga (vier Views in einem Request, laufende Periode), NFL-Scoreboard,
claude.json der App und – nur für Spieler aus Moves, die in keinem Kader stehen – kona_player_info.
Manager-Daten (members, owners, memberId) werden direkt nach dem Abruf entfernt und nie gelesen oder gedruckt.
Fremdtexte (Teamname, Spielername, Scoreboard-Detail) kommen einzeilig und gekürzt in den Text (kurz); der Text ist
Daten, keine Anweisung.

Aufrufe (team_id optional, Standard 2; nur das erste Argument zählt, und nur als Team-ID der Liga – alles andere,
etwa '-c' oder die Argumente eines Notebooks, wird ignoriert):
    python3 -c "import requests; r = requests.get('<raw-Adresse>', timeout=20); r.raise_for_status(); exec(r.content, {'__name__': '__main__'})" [team_id]
    curl -fsS <raw-Adresse> | python3 - [team_id]
    python scripts/claude_stand.py [team_id]
raw-Adresse: https://raw.githubusercontent.com/frest2101/bwg-fantasy/main/scripts/claude_stand.py
Der erste Weg ist der empfohlene (ein Prozess, Zeitlimit, ein fehlendes Skript wird ein klarer HTTP-Fehler);
exec(r.content, …) liest den Quelltext als UTF-8, auch wenn die Antwort keinen Zeichensatz nennt. Der eigene
Namensraum {'__name__': '__main__'} gehört dazu: Mit ihm läuft der Aufruf auf jeder Ebene, auch in einer Funktion
oder einem Notebook. Ein leerer Namensraum (exec(r.content, {})) geht ebenso; exec(r.content) ohne Namensraum nur
auf oberster Ebene – in einer Funktion finden sich die Funktionen des Skripts dann nicht, und statt des Stands
kommt eine Textzeile mit diesem Hinweis.

Aufbau: Der Abruf (hole, parallel, abrufen) ist getrennt von den reinen Funktionen (bericht und Helfer), die aus den
geladenen JSON-Objekten und einem übergebenen Zeitpunkt den Text bauen – so laufen die Tests ohne Netz.
Jeder Ausfall wird eine Textzeile, nie ein Traceback; das Skript endet immer normal (Exit-Code 0).
Zahlen: ESPN-Werte ungerundet übernommen, erst bei der Ausgabe gerundet (round half up): Punkte zwei Stellen,
F drei, Prozente ganzzahlig, Expertenrang (Exp, Median der ESPN-Experten laut App, nur vor dem Anstoß) ganz oder mit
einer Stelle. Eine Zeitzone im Text: deutsche Zeit mit Etikett MESZ/MEZ je Zeitpunkt, UTC nur im Kopf.
"""

import json
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from email.utils import parsedate_to_datetime

try:
    import requests
except ImportError:  # ohne requests gibt es eine Textzeile statt eines Tracebacks (siehe main)
    requests = None

# Saisonwechsel: LIGA_ID und SAISON müssen zu scripts/espn_fetch.py passen, KUERZEL zu scripts/app_export.py
# (tests/test_claude_stand.py vergleicht sie).
LIGA_ID = 1166555857
SAISON = 2026
MEIN_TEAM = 2
LIGA_URL = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SAISON}/segments/0/leagues/{LIGA_ID}"
LIGA_VIEWS = ("mMatchupScore", "mRoster", "mTeam", "mTransactions2")  # ohne scoringPeriodId: laufende Periode
KONA_VIEW = "kona_player_info"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
APP_URLS = ("https://raw.githubusercontent.com/frest2101/bwg-fantasy/main/app/data/claude.json",
            "https://frest2101.github.io/bwg-fantasy/data/claude.json")
VERBINDEN, LESEN = 5, 15      # Sekunden je Anfrage (Verbindungsaufbau, Pause zwischen zwei Datenpaketen)
FRIST, FRIST_NACH = 25, 15    # Sekunden je Runde (erste Runde: Liga, Scoreboard, App; zweite: Nachabrufe)

KUERZEL = {1: "ACB", 2: "HJS", 3: "4DS", 4: "CRN", 5: "TTY", 6: "SAM", 7: "RTZ", 8: "GLS", 9: "DYN", 10: "SGK"}
SLOT = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "FLEX", 7: "OP", 16: "D/ST", 17: "K", 20: "Bank", 21: "IR"}
STARTER_SLOTS = (0, 2, 4, 6, 23, 7, 16, 17)   # Reihenfolge der Ausgabe
STARTER_ZAHL = 13                              # QB, 2 RB, 3 WR, TE, 2 FLEX, OP, 2 D/ST, K
SLOT_BANK, SLOT_IR = 20, 21
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
NFL = {0: "FA", 1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN",
       11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
       21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX",
       33: "BAL", 34: "HOU"}
INJ = {None: "", "ACTIVE": "", "NORMAL": "", "QUESTIONABLE": "Q", "DOUBTFUL": "D", "OUT": "OUT",
       "INJURY_RESERVE": "IR", "SUSPENSION": "SUSP", "DAY_TO_DAY": "DTD"}
TAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
MOVE_ARTEN = {"WAIVER": "Waiver", "FREEAGENT": "Free Agent", "ROSTER": "Kader", "FUTURE_ROSTER": "Kader"}
SPIELER_ITEMS = {"ADD", "DROP"}
# Spielstatus eines Spielers: pre/in/post (Scoreboard), verschoben (laut ESPN beendet, aber ohne Ergebnis), bye und
# ohne (kein NFL-Team); ohne Scoreboard zu/auf (lineupLocked). OFFEN: Der Slot ist noch nicht gesperrt.
OFFEN = ("pre", "bye", "ohne", "auf", "verschoben")
SPIELFREI = ("bye", "ohne")            # zählt 0; ESPN projiziert D/ST auch in ihrer Bye-Woche
SAMMEL_AB = 3                          # zeigen mehr Bankspieler auf denselben Starter: eine Sammelzeile
TEXT_MAX = 40                          # Zeichen je Fremdtext (Teamname, Spielername, Scoreboard-Detail)
APP_FENSTER_TAGE = 14                  # claude.json führt die Moves der 14 Tage bis zum letzten Move
APP_FENSTER_MS = APP_FENSTER_TAGE * 86_400_000


# ---------------------------------------------------------------- Zahlen, Zeit, Fremdtext (rein)

def zahl(wert, stellen=2) -> str:
    """Zahl mit festen Nachkommastellen, round half up über Decimal; None → „–“."""
    if wert is None:
        return "–"
    d = (wert if isinstance(wert, Decimal) else Decimal(str(wert))).quantize(Decimal(1).scaleb(-stellen),
                                                                              rounding=ROUND_HALF_UP)
    return str(d if d else abs(d))  # kein „-0.00“


def prozent(anteil) -> str:
    """Anteil 0…1 als ganze Prozent (round half up); None → „–“."""
    return "–" if anteil is None else zahl(Decimal(str(anteil)) * 100, 0) + " %"


def kurz(text, n: int = TEXT_MAX) -> str:
    """Fremdtext für die Ausgabe: eine Zeile (Steuerzeichen, Zeilenumbrüche und Leerraum werden ein Leerzeichen),
    höchstens n Zeichen („…“ am Ende, wenn gekürzt). Den Teamnamen etwa kann jeder Manager bei ESPN ändern."""
    s = " ".join("".join(c if c.isprintable() else " " for c in str(text)).split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def umstellung(jahr: int, monat: int) -> datetime:
    """Letzter Sonntag im März bzw. Oktober, 01:00 UTC: Beginn bzw. Ende der Sommerzeit in der EU."""
    d = datetime(jahr, monat, 31, 1, tzinfo=timezone.utc)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def deutsche_zeit(dt: datetime) -> datetime:
    """UTC-Zeitpunkt in deutscher Zeit, ohne zoneinfo; tzname() ist das Etikett MESZ oder MEZ dieses Zeitpunkts."""
    sommer = umstellung(dt.year, 3) <= dt < umstellung(dt.year, 10)
    return dt.astimezone(timezone(timedelta(hours=2 if sommer else 1), "MESZ" if sommer else "MEZ"))


def zeit_text(dt, datum: bool = True, jahr: bool = False) -> str:
    """„So 04.10. 19:00 MESZ“ (datum=False: „So 19:00 MESZ“); das Etikett gehört zum Zeitpunkt, nicht zu „jetzt“."""
    if dt is None:
        return "(Zeit offen)"
    lokal = deutsche_zeit(dt)
    tag = lokal.strftime("%d.%m.%Y " if jahr else "%d.%m. ") if datum else ""
    return f"{TAG[lokal.weekday()]} {tag}{lokal:%H:%M} {lokal.tzname()}"


def aus_ms(wert):
    """ESPN-Zeitstempel (Epoch-ms) → UTC-Zeitpunkt; None bleibt None."""
    return None if not wert else datetime.fromtimestamp(wert / 1000, tz=timezone.utc)


def aus_iso(text):
    """Scoreboard-Zeit („2026-10-02T00:15Z“, auch mit Sekunden) → UTC-Zeitpunkt; Unlesbares → None."""
    for form in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, form).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return None


# ---------------------------------------------------------------- Rohdaten lesen (rein)

def ohne_personen(liga: dict) -> dict:
    """Entfernt Manager-Daten und Absichten aus der Liga-Antwort (an Ort und Stelle), bevor etwas sie liest."""
    liga.pop("members", None)
    for team in liga.get("teams") or []:
        for feld in ("owners", "primaryOwner", "tradeBlock", "draftStrategy"):
            team.pop(feld, None)
    for eintrag in liga.get("transactions") or []:
        eintrag.pop("memberId", None)
    return liga


def liga_mangel(daten):
    """None, wenn die Liga-Antwort brauchbar ist; sonst der Grund als Text."""
    fehlt = [k for k in ("scoringPeriodId", "teams", "schedule") if not (daten or {}).get(k)]
    return f"Antwort ohne {', '.join(fehlt)}" if fehlt else None


def scoreboard_passt(scoreboard, woche) -> bool:
    """Das Scoreboard zeigt die Regular-Season-Woche der Liga (sonst holt der Abruf sie gezielt nach)."""
    if not scoreboard:
        return False
    return (scoreboard.get("week") or {}).get("number") == woche and (scoreboard.get("season") or {}).get("type") == 2


def spiele_aus(scoreboard: dict):
    """Scoreboard → (Spiel je proTeamId, Liste der Spiele). state: pre (offen), in (läuft), post (beendet),
    verschoben (ESPN meldet state „post“, aber completed false).

    Für ein abgesagtes Spiel ist diese Form belegt (2022 W17 BUF@CIN: state post, completed false, shortDetail
    „Canceled“); für ein verschobenes ist sie angenommen. Defensiv: Solche Spiele bilden eine eigene Gruppe mit
    ESPNs Detailtext, ihre Starter gelten wie offene als tauschbar. Beim ersten echten Fall die Form prüfen.
    """
    je_team, liste = {}, []
    for ev in scoreboard.get("events") or []:
        c = (ev.get("competitions") or [{}])[0]
        typ = (c.get("status") or ev.get("status") or {}).get("type") or {}
        seiten = {x.get("homeAway"): x for x in c.get("competitors") or []}
        heim, gast = seiten.get("home"), seiten.get("away")
        if not heim or not gast:
            continue
        h, g = kurz(heim["team"].get("abbreviation", "?"), 5), kurz(gast["team"].get("abbreviation", "?"), 5)
        state = typ.get("state") if typ.get("state") in ("pre", "in", "post") else "pre"
        if state == "post" and not typ.get("completed"):
            state = "verschoben"
        spiel = {"state": state, "detail": kurz(typ.get("shortDetail") or typ.get("description") or ""),
                 "anstoss": aus_iso(ev.get("date") or c.get("date")) if c.get("timeValid", True) else None,
                 "paarung": f"{g}@{h}", "stand": f"{kurz(gast.get('score', '?'), 4)}:{kurz(heim.get('score', '?'), 4)}"}
        liste.append(spiel)
        je_team[int(heim["team"]["id"])] = dict(spiel, gegner=f"vs {g}")
        je_team[int(gast["team"]["id"])] = dict(spiel, gegner=f"@ {h}")
    return je_team, liste


def wochenwert(player: dict, woche, saison, quelle: int):
    """appliedTotal des Wochen-Eintrags (statSplitTypeId 1): quelle 0 = Ist, 1 = Projektion; None ohne Eintrag."""
    for s in player.get("stats") or []:
        if (s.get("scoringPeriodId"), s.get("statSplitTypeId"), s.get("statSourceId"), s.get("seasonId")) \
                == (woche, 1, quelle, saison):
            return s.get("appliedTotal")
    return None


def spielerzeile(ppe: dict, woche, saison, je_team: dict, hat_sb: bool) -> dict:
    """Ein Spieler aus playerPoolEntry (mRoster) bzw. einem kona-Eintrag – beide haben dieselbe Form."""
    p = ppe.get("player") or {}
    pro = p.get("proTeamId")
    if hat_sb:
        state = je_team[pro]["state"] if pro in je_team else "bye" if pro else "ohne"
    else:  # ohne Scoreboard: ESPN sperrt den Slot mit dem Anstoß (lineupLocked); Byes sind dann nicht erkennbar
        state = "zu" if ppe.get("lineupLocked") else "auf"
    pid = p.get("id", ppe.get("id"))
    inj = INJ.get(p.get("injuryStatus"), p.get("injuryStatus") or "")
    return {"id": pid, "name": kurz(p.get("fullName") or f"Spieler {pid}"), "pos": POS.get(p.get("defaultPositionId"), "?"),
            "pro": pro, "nfl": NFL.get(pro, "?"), "inj": kurz(inj, 20),
            "ist": wochenwert(p, woche, saison, 0), "proj": wochenwert(p, woche, saison, 1),
            "wahl": set(p.get("eligibleSlots") or []), "state": state, "slot": None, "team": None,
            "status": ppe.get("status"), "frist": ppe.get("waiverProcessDate")}


def bewegungen(liga: dict) -> dict:
    """Transaktionen der laufenden Periode, sortiert in Moves (wie die App: ausgeführt, mit Zugang oder Abgang),
    angenommene Trades (ESPN nennt dort keine Spieler), gescheiterte Claims, reine Aufstellungswechsel, Sonstiges."""
    aus = {"moves": [], "trades": [], "claims": Counter(), "lineup": Counter(), "sonst": Counter()}
    for t in liga.get("transactions") or []:
        typ, status = t.get("type"), t.get("status")
        arten = {i.get("type") for i in t.get("items") or []}
        if typ in MOVE_ARTEN and status == "EXECUTED" and arten & SPIELER_ITEMS:
            aus["moves"].append(t)
        elif typ == "TRADE_ACCEPT" and status in (None, "EXECUTED"):
            aus["trades"].append(t)
        elif typ in ("ROSTER", "FUTURE_ROSTER") and status == "EXECUTED" and "LINEUP" in arten:
            aus["lineup"][t.get("teamId")] += 1
        elif typ == "WAIVER" and str(status).startswith("FAILED"):
            aus["claims"][t.get("teamId")] += 1
        else:
            aus["sonst"][kurz(f"{typ} {status}", 60)] += 1
    for liste in (aus["moves"], aus["trades"]):
        liste.sort(key=lambda t: (tx_zeit(t) or 0, str(t.get("id"))))
    return aus


def tx_zeit(t: dict):
    """Zeit einer Transaktion wie in der App: processDate, sonst proposedDate (Epoch-ms)."""
    return t.get("processDate") or t.get("proposedDate")


def spieler_ohne_kader(liga: dict) -> list:
    """IDs der Spieler aus Moves, die heute in keinem Kader stehen – nur sie braucht der kona-Abruf."""
    im_kader = {e.get("playerId") for t in liga.get("teams") or [] for e in (t.get("roster") or {}).get("entries") or []}
    bewegt = {i.get("playerId") for t in bewegungen(liga)["moves"] for i in t.get("items") or []
              if i.get("type") in SPIELER_ITEMS}
    return sorted(bewegt - im_kader - {None})


def kona_filter(ids: list, woche) -> dict:
    """X-Fantasy-Filter für kona_player_info; ohne sortPercOwned antwortet ESPN mit HTTP 400."""
    return {"players": {"filterIds": {"value": list(ids)}, "limit": max(50, len(ids)),
                        "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
                        "filterStatsForCurrentSeasonScoringPeriodId": {"value": [woche]}}}


def app_index(app, woche, saison=None) -> dict:
    """claude.json als Nachschlagetabellen: Spieler je ID (Name, Position, ROS/Spiel, F, Projektion), Kader je
    Kürzel, Moves als Zähler (Zeit, Kürzel). f_ok/proj_ok: Die Datei meint dieselbe Woche wie ESPN.

    Vertrag mit scripts/app_export.py (build_claude; tests/test_claude_stand.py liest dazu die committete Datei):
    stand (saison, nach_woche, matchup_woche, pool_stand, pool_woche, experten_quellen, experten_tiefe), spieler_spalten
    mit id, name, pos, nfl, ros_g, mu_n1, proj, exp, exp_n, kader je Kürzel, free_agents, transaktionen_spalten mit
    datum_ms und team.
    fremd: Die Datei zeigt eine andere Saison als ESPN (nach dem Saisonwechsel, bis W1 final ist) – dann gilt nur
    die Kopfzeile, nichts aus der Datei wird verglichen. marken: Moves lassen sich als [App]/[NEU] markieren;
    führt die Datei Transaktionen ohne die Spalten datum_ms und team, wäre sonst jeder Move fälschlich [NEU].
    """
    stand = (app or {}).get("stand") or {}
    fremd = bool(app) and saison is not None and stand.get("saison") not in (None, saison)
    nutzbar = bool(app) and not fremd
    aus = {"da": bool(app), "fremd": fremd, "saison": saison, "stand": stand, "spieler": {}, "kader": None,
           "tx": Counter(), "bis": None, "marken": nutzbar,
           "f_ok": nutzbar and stand.get("matchup_woche") == woche,
           "proj_ok": nutzbar and stand.get("pool_woche") == woche}
    if not nutzbar:
        return aus
    spalten = app.get("spieler_spalten") or []
    if isinstance(app.get("kader"), dict) and "id" in spalten:
        aus["kader"] = {}
        for kz, zeilen in app["kader"].items():
            aus["kader"][kz] = set()
            for zeile in zeilen:
                s = dict(zip(spalten, zeile))
                aus["spieler"][s["id"]] = s
                aus["kader"][kz].add(s["id"])
    frei_spalten = app.get("free_agents_spalten") or spalten
    for zeilen in (app.get("free_agents") or {}).values() if "id" in frei_spalten else []:
        for zeile in zeilen:
            s = dict(zip(frei_spalten, zeile))
            aus["spieler"].setdefault(s["id"], s)
    tx_spalten, tx_zeilen = app.get("transaktionen_spalten") or [], app.get("transaktionen") or []
    if tx_zeilen and not {"datum_ms", "team"} <= set(tx_spalten):
        aus["marken"] = False
        return aus
    for zeile in tx_zeilen:
        t = dict(zip(tx_spalten, zeile))
        aus["tx"][(t["datum_ms"], t.get("team"))] += 1
    aus["bis"] = max((zeit for zeit, _ in aus["tx"] if zeit), default=None)
    return aus


def lage_aus(liga: dict, scoreboard, index: dict, kona) -> dict:
    """Alles, was die Abschnitte brauchen: Woche, Teams, Kürzel, Spiele, Kader je Team, Spieler je ID, App-Index."""
    woche, saison = liga.get("scoringPeriodId"), liga.get("seasonId", SAISON)
    hat_sb = scoreboard_passt(scoreboard, woche)
    je_team, spiele = spiele_aus(scoreboard) if hat_sb else ({}, [])
    teams = {t["id"]: t for t in liga.get("teams") or []}
    spieler, kader = {}, {}
    for tid, team in teams.items():
        kader[tid] = []
        for e in (team.get("roster") or {}).get("entries") or []:
            z = spielerzeile(e.get("playerPoolEntry") or {}, woche, saison, je_team, hat_sb)
            z.update(slot=e.get("lineupSlotId"), team=tid)
            kader[tid].append(z)
            spieler[z["id"]] = z
    for eintrag in (kona or {}).get("players") or []:
        z = spielerzeile(eintrag, woche, saison, je_team, hat_sb)
        z["team"] = eintrag.get("onTeamId") or None  # zwischen Liga- und kona-Abruf geholt: dann steht hier das Team
        spieler.setdefault(z["id"], z)
    bye = [kurz(t.get("abbreviation", "?"), 5) for t in (scoreboard.get("week") or {}).get("teamsOnBye") or []] \
        if hat_sb else []
    return {"woche": woche, "liga": liga, "teams": teams, "hat_sb": hat_sb, "spiele": spiele, "je_team": je_team,
            "bye": bye, "kader": kader, "spieler": spieler, "app": index, "kona_da": kona is not None,
            "kz": {tid: KUERZEL.get(tid) or kurz(t.get("abbrev") or f"T{tid}", 6) for tid, t in teams.items()}}


def periode_von(liga: dict):
    """Laufende Matchup-Periode; in den Playoffs und nach W17 muss sie nicht die Woche (scoringPeriodId) sein."""
    return (liga.get("status") or {}).get("currentMatchupPeriod", liga.get("scoringPeriodId"))


def paarungen(liga: dict) -> list:
    """Matchups der laufenden Matchup-Periode."""
    periode = periode_von(liga)
    return [m for m in liga.get("schedule") or [] if m.get("matchupPeriodId") == periode]


def paarung_von(liga: dict, team_id: int):
    """Das Matchup eines Teams in der laufenden Matchup-Periode; None ohne Paarung."""
    for m in paarungen(liga):
        if team_id in [(m.get(seite) or {}).get("teamId") for seite in ("home", "away")]:
            return m
    return None


def gegner_von(liga: dict, team_id: int):
    """Team-ID des Gegners in der laufenden Matchup-Periode; None bei Freilos oder ohne Paarung."""
    m = paarung_von(liga, team_id) or {}
    ids = [(m.get(seite) or {}).get("teamId") for seite in ("home", "away")]
    return next((i for i in ids if i not in (team_id, None)), None)


# ---------------------------------------------------------------- Abschnitte des Textes (rein)

def kopf(jetzt: datetime, liga, index: dict, abweichung, ausfall: dict) -> list:
    """Uhrzeit (deutsche Zeit und UTC), Abweichung zur ESPN-Serverzeit, Woche, Datenstand der App und Lesehilfe."""
    zeile = f"STAND {zeit_text(jetzt, jahr=True)} ({jetzt:%H:%M} UTC, Uhr des Containers"
    if abweichung is not None:
        sek = zahl(abweichung, 0)  # Vorzeichen am gerundeten Wert: gerundet 0 steht ohne
        zeile += f"; ESPN-Serverzeit weicht {'' if sek == '0' or sek.startswith('-') else '+'}{sek} s ab"
    zeile += ")"
    woche = (liga or {}).get("scoringPeriodId")
    if liga:
        periode = periode_von(liga)
        zeile += f" – ESPN Woche {woche}" + (f" (Matchup-Periode {periode})" if periode != woche else "")
    aus = [zeile]
    if abweichung is not None and abs(abweichung) >= 120:
        aus.append("! Die Uhr des Containers weicht stark von ESPN ab – „jetzt“ und Altersangaben mit Vorsicht lesen")
    lesehilfe = "Alle Zeiten deutsche Zeit. Punkte, Projektion (Proj) und Siegchance: ESPN live."
    stand = index["stand"]
    if not index["da"]:
        aus.append(f"App: claude.json nicht erreichbar ({ausfall.get('app', 'kein Abruf')}) – Datenstand der App, F, "
                   "ROS/Sp, Marken [App]/[NEU] und Kadervergleich fehlen")
    elif index["fremd"]:
        aus.append(f"App zeigt Saison {kurz(stand.get('saison'), 10)}, ESPN Saison {index['saison']} – F, ROS/Sp, "
                   "Marken [App]/[NEU] und Kadervergleich fehlen")
    else:
        pool = None
        try:
            pool = datetime.strptime(stand.get("pool_stand") or "", "%Y-%m-%dT%H%MZ").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
        tagesstand = "ohne Tagesstand" if pool is None else \
            f"Tagesstand {zeit_text(pool)} (vor {zahl(Decimal(int((jetzt - pool).total_seconds())) / 3600, 1)} h)"
        letzter = "Moves der App nicht lesbar" if not index["marken"] else \
            f"letzter Move in der App {zeit_text(aus_ms(index['bis']))}" if index["bis"] else "kein Move in der App"
        aus.append(f"App: gerechnet bis Woche {stand.get('nach_woche', '?')}; {tagesstand}; {letzter}")
        lesehilfe += " Laut App (Wochenstand): ROS/Sp = ROS-Projektion je Spiel"
        if index["f_ok"]:
            lesehilfe += ", F = Faktor (Position) des Gegners laut Matchups (> 1 günstig)."
        else:
            lesehilfe += f"; F fehlt, die App rechnet die Matchups für Woche {stand.get('matchup_woche', '?')}."
    aus.append(lesehilfe)
    return aus


def nfl_zeilen(lage: dict, ausfall: dict) -> list:
    """NFL-Spiele der Woche nach Status; offene Spiele je Anstoß mit dem Zonen-Etikett dieses Anstoßes."""
    if not lage["hat_sb"]:
        return [f"NFL-Scoreboard nicht erreichbar ({ausfall.get('scoreboard', 'kein Abruf')}) – Spielstatus, Gegner "
                "und Anstoßzeiten fehlen; gesperrt/offen je Spieler stammt aus dem ESPN-Kader (lineupLocked). "
                "Byes nicht erkennbar – D/ST-Projektionen können spielfreie Teams betreffen"]
    final = [s for s in lage["spiele"] if s["state"] == "post"]
    laeuft = [s for s in lage["spiele"] if s["state"] == "in"]
    verschoben = [s for s in lage["spiele"] if s["state"] == "verschoben"]
    offen = {}
    for s in lage["spiele"]:
        if s["state"] == "pre":
            offen.setdefault(s["anstoss"], []).append(s["paarung"])
    aus = [f"NFL W{lage['woche']}: {len(final)} final, {len(laeuft)} läuft, {sum(map(len, offen.values()))} offen"
           + (f", {len(verschoben)} verschoben" if verschoben else "")
           + (f"; Bye: {', '.join(lage['bye'])}" if lage["bye"] else "")]
    if final:
        aus.append("  final: " + ", ".join(f"{s['paarung']} {s['stand']}" for s in final))
    if laeuft:
        aus.append("  läuft: " + ", ".join(f"{s['paarung']} {s['stand']} ({s['detail']})" for s in laeuft))
    for anstoss in sorted(offen, key=lambda a: (a is None, a)):
        aus.append(f"  offen {zeit_text(anstoss)}: " + ", ".join(offen[anstoss]))
    if verschoben:
        aus.append("  verschoben (laut ESPN beendet ohne Ergebnis): "
                   + ", ".join(f"{s['paarung']} ({s['detail'] or 'ohne Angabe'})" for s in verschoben))
    return aus


def starterzahl(lage: dict, team_id) -> str:
    """Starter eines Teams nach Spielstatus: final/läuft/offen, dazu getrennt Bye, ohne NFL-Team und verschoben;
    ohne Scoreboard gesperrt/offen."""
    c = Counter(z["state"] for z in lage["kader"].get(team_id, []) if z["slot"] in STARTER_SLOTS)
    if not lage["hat_sb"]:
        return f"{c['zu']}/{c['auf']}"
    zusatz = (("bye", "Bye"), ("ohne", "ohne Team"), ("verschoben", "verschoben"))
    return f"{c['post']}/{c['in']}/{c['pre']}" + "".join(f" +{c[k]} {wort}" for k, wort in zusatz if c[k])


def matchup_zeilen(lage: dict, mein_team: int) -> list:
    """Je Matchup beide Seiten: Punkte live, Live-Projektion, Siegwahrscheinlichkeit, Starter nach Spielstatus."""
    spalte = "Starter final/läuft/offen" if lage["hat_sb"] else "Starter gesperrt/offen"
    woche, periode = lage["woche"], periode_von(lage["liga"])
    titel = f"MATCHUPS W{woche}" if periode == woche else \
        f"MATCHUPS Matchup-Periode {periode} (Starterzahlen und Aufstellungen: ESPN Woche {woche})"
    aus = [f"{titel} (* = eigenes): Team (Bilanz) Punkte live | Live-Projektion | Siegchance | {spalte}"]

    def seite(s: dict) -> str:
        tid = s.get("teamId")
        rec = ((lage["teams"].get(tid) or {}).get("record") or {}).get("overall") or {}
        bilanz = f"{rec.get('wins', 0)}-{rec.get('losses', 0)}" + (f"-{rec['ties']}" if rec.get("ties") else "")
        return (f"{lage['kz'].get(tid, tid)} ({bilanz}) {zahl(s.get('totalPointsLive', s.get('totalPoints')))} | "
                f"{zahl(s.get('totalProjectedPointsLive'))} | {prozent(s.get('winProbability'))} | "
                f"{starterzahl(lage, tid)}")

    spiele = paarungen(lage["liga"])
    for m in spiele:
        seiten = [m[k] for k in ("home", "away") if m.get(k)]
        marke = "*" if mein_team in [s.get("teamId") for s in seiten] else " "
        sieger = {"HOME": "home", "AWAY": "away"}.get(m.get("winner"))
        ende = f"  [Sieger {lage['kz'].get((m.get(sieger) or {}).get('teamId'), '?')}]" if sieger else \
            "  [Unentschieden]" if m.get("winner") == "TIE" else ""
        if m.get("playoffTierType") not in (None, "NONE"):  # Playoffs: ESPNs Bezeichnung der Runde, unverändert
            ende += f"  [{kurz(m['playoffTierType'], 30)}]"
        aus.append(f" {marke}" + "  –  ".join(seite(s) for s in seiten) + ("  (Freilos)" if len(seiten) == 1 else "") + ende)
    return aus if spiele else aus + ["  keine Paarung in dieser Matchup-Periode"]


def frei_wort(z: dict) -> str:
    """Wort für einen Spieler ohne Spiel – dasselbe in seiner Zeile und im Bank-Hinweis."""
    return "Bye" if z["state"] == "bye" else "ohne NFL-Team"


def spiel_text(lage: dict, z: dict) -> str:
    """Gegner und Spielstatus eines Spielers: „vs DEN So 22:25 MESZ“, „@ CLE final“, „Bye“; ohne Scoreboard gesperrt/offen."""
    if not lage["hat_sb"]:
        return "gesperrt" if z["state"] == "zu" else "offen"
    if z["state"] in SPIELFREI:
        return frei_wort(z)
    spiel = lage["je_team"][z["pro"]]
    if spiel["state"] == "post":
        return f"{spiel['gegner']} final"
    if spiel["state"] == "verschoben":
        return f"{spiel['gegner']} verschoben ({spiel['detail'] or 'ohne Angabe'})"
    if spiel["state"] == "in":
        return f"{spiel['gegner']} läuft ({spiel['detail']})"
    return f"{spiel['gegner']} {zeit_text(spiel['anstoss'], datum=False)}"


def exp_ok(lage: dict) -> bool:
    """Expertenränge der App gelten für diese Woche: claude.json meint dieselbe Woche wie ESPN (pool_woche) und ESPN
    hatte zum Stand der App schon Listen veröffentlicht (stand.experten_quellen > 0)."""
    return bool(lage["app"]["proj_ok"] and lage["app"]["stand"].get("experten_quellen"))


def expertenrang(lage: dict, z: dict):
    """Expertenrang laut App (claude.json exp und exp_n, stand.experten_quellen und experten_tiefe) als „RB 12.5 (8/8)“
    (Median der ESPN-Experten, Experten mit Rang von allen) bzw. „RB >50 (3/8)“ (höchstens die Hälfte führt ihn in
    ihren Top 50); None, wenn die App eine andere Woche meint, das Spiel schon begonnen hat (nach dem Anpfiff nehmen die
    Experten Spieler aus ihren Listen), der Spieler spielfrei ist oder kein Experte ihn führt.
    Regel wie live_core.expertenrang (Live-Ansicht der App)."""
    if not exp_ok(lage) or z["state"] not in OFFEN or z["state"] in SPIELFREI:
        return None
    a, stand = lage["app"]["spieler"].get(z["id"]) or {}, lage["app"]["stand"]
    n = a.get("exp_n")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        return None
    wert, tiefe = a.get("exp"), (stand.get("experten_tiefe") or {}).get(z["pos"])
    rang = zahl(wert, 1 if wert % 1 else 0) if wert is not None else f">{tiefe if tiefe is not None else '?'}"
    return f"{z['pos']} {rang} ({n}/{stand['experten_quellen']})"


def spielerspalten(lage: dict, z: dict, kopf_text: str) -> str:
    """Eine Zeile: Slot Spieler NFL Spiel | Punkte | Proj | F | Exp | Verletzung (F nur, wenn die App dieselbe Woche
    meint; Exp = Expertenrang laut App, nur vor dem Anstoß, siehe expertenrang).

    Ohne Spiel (Bye, ohne NFL-Team) steht bei Proj „–“: ESPN projiziert D/ST auch in ihrer Bye-Woche, die Zahl wäre
    keine Erwartung (gezählt wird 0)."""
    f = (lage["app"]["spieler"].get(z["id"]) or {}).get("mu_n1") if lage["app"]["f_ok"] else None
    proj = None if z["state"] in SPIELFREI else z["proj"]
    exp = expertenrang(lage, z)
    return (f"  {kopf_text} {z['nfl']} {spiel_text(lage, z)} | {zahl(z['ist'])} | {zahl(proj)}"
            + (f" | F {zahl(f, 3)}" if f is not None else "") + (f" | Exp {exp}" if exp else "")
            + (f" | {z['inj']}" if z["inj"] else ""))


def team_zeilen(lage: dict, team_id: int, ganz: bool = False) -> list:
    """Starter eines Teams und seine Bank. ganz (eigenes Team): alle Bank- und IR-Spieler, damit Alternativen für
    fragliche Starter im Text stehen; sonst nur die auffälligen (Punkte nach dem Anpfiff, oder mehr Projektion als
    ein noch tauschbarer Starter im passenden Slot)."""
    team = lage["teams"].get(team_id)
    if team is None:
        return [f"Team-ID {team_id} gibt es in der Liga nicht – keine Aufstellung"]
    kader = lage["kader"][team_id]
    aus = [f"{lage['kz'][team_id]} {kurz(team.get('name', ''))} – Slot Spieler NFL Spiel | Punkte | Proj"
           + (" | F" if lage["app"]["f_ok"] else "") + (" | Exp" if exp_ok(lage) else "")]
    starter = sorted((z for z in kader if z["slot"] in STARTER_SLOTS),
                     key=lambda z: (STARTER_SLOTS.index(z["slot"]), -(z["proj"] or 0), z["name"]))
    for z in starter:
        pos = f" {z['pos']}" if SLOT[z["slot"]] in ("FLEX", "OP") else ""  # dort sagt der Slot die Position nicht
        aus.append(spielerspalten(lage, z, f"{SLOT[z['slot']]:<4} {z['name']}{pos}"))
    if len(starter) < STARTER_ZAHL:
        aus.append(f"  ! nur {len(starter)} von {STARTER_ZAHL} Starter-Slots besetzt")

    def wert(z: dict):  # Projektion eines Starters, der noch getauscht werden kann; Bye und ohne Team zählen 0
        return 0 if z["state"] in ("bye", "ohne") else z["proj"] or 0

    def starter_text(s: dict) -> str:  # dieselbe Zahl bzw. dasselbe Wort wie in der Zeile des Starters
        stand = frei_wort(s) if s["state"] in SPIELFREI else \
            zahl(wert(s)) + (" verschoben" if s["state"] == "verschoben" else "")
        return f"{s['name']} ({SLOT[s['slot']]} {stand})"

    tauschbar = [z for z in starter if z["state"] in OFFEN]
    reserve = sorted((z for z in kader if z["slot"] not in STARTER_SLOTS),
                     key=lambda z: (z["slot"] == SLOT_IR, -(z["proj"] or 0), z["name"]))
    ziel = {}  # Bankspieler-ID → schwächster tauschbarer Starter im passenden Slot mit weniger Projektion
    for z in reserve:
        if z["slot"] == SLOT_BANK and z["state"] in ("pre", "auf") and z["proj"]:
            if z["pos"] == "D/ST" and not lage["hat_sb"]:
                continue  # ohne Scoreboard ist ein Bye nicht erkennbar, ESPN projiziert D/ST aber auch dann
            schwaecher = [s for s in tauschbar if s["slot"] in z["wahl"] and wert(s) < z["proj"]]
            if schwaecher:
                ziel[z["id"]] = min(schwaecher, key=wert)
    je_starter = Counter(s["id"] for s in ziel.values())
    bank = []
    for z in reserve:
        s = ziel.get(z["id"])
        hinweis = f" → mehr Proj als Starter {starter_text(s)}" if s and je_starter[s["id"]] <= SAMMEL_AB else ""
        if ganz or hinweis or (z["ist"] and z["state"] not in OFFEN):
            pos = "" if z["pos"] == "D/ST" else f" {z['pos']}"
            aus_slot = SLOT.get(z["slot"], "Bank")
            bank.append(spielerspalten(lage, z, f"{aus_slot:<4} {z['name']}{pos}") + hinweis)
    for s in starter:  # viele Bankspieler über demselben schwachen Starter: eine Zeile statt vieler fast gleicher
        if je_starter[s["id"]] > SAMMEL_AB:
            namen = [f"{z['name']} {zahl(z['proj'])}" for z in reserve if ziel.get(z["id"]) is s]
            bank.append(f"  → {len(namen)} Bankspieler mit mehr Proj als Starter {starter_text(s)}: " + ", ".join(namen))
    if ganz:
        titel = "  Bank und IR vollständig (→ = mehr Proj als ein noch offener Starter im passenden Slot):" if bank \
            else "  Bank und IR: leer"
    else:
        titel = "  Bank, nur Auffällige (Punkte, oder mehr Proj als ein noch offener Starter im passenden Slot):" if bank \
            else "  Bank: nichts Auffälliges (keine Punkte, keine höhere Projektion als ein offener Starter)"
    return aus + [titel] + bank


def nenn(lage: dict, pid, team_id, abgang: bool) -> str:
    """Bewegter Spieler: Name (Position NFL; wo er heute ist; Ist oder Proj der Woche live; ROS/Sp laut App)."""
    z, a = lage["spieler"].get(pid), lage["app"]["spieler"].get(pid) or {}
    if z is None:  # steht in keinem Kader und der kona-Abruf fehlt: Name laut App, sonst nur die ID
        teile = [f"{kurz(a.get('pos') or '?', 5)} {kurz(a.get('nfl') or '?', 5)}"]
        name = kurz(a.get("name") or f"Spieler {pid}")
        if lage["app"]["proj_ok"] and a.get("proj") is not None:
            teile.append(f"Proj laut App {zahl(a['proj'])}")
    else:
        name, teile = z["name"], [f"{z['pos']} {z['nfl']}"]
        if z["team"] is None:
            frist = f" bis {zeit_text(aus_ms(z['frist']))}" if z.get("frist") else ""
            teile.append({"WAIVERS": "auf Waivers" + frist, "FREEAGENT": "frei"}.get(
                z.get("status"), kurz(z.get("status") or "frei", 20)))
        elif abgang or z["team"] != team_id:
            teile.append(f"jetzt {lage['kz'].get(z['team'], z['team'])}")
        if z["inj"]:
            teile.append(z["inj"])
        if z["state"] == "bye":
            teile.append("Bye")
        elif z["ist"] is not None and z["state"] not in OFFEN:
            teile.append(f"Ist {zahl(z['ist'])}")
        elif z["proj"] is not None:
            teile.append(f"Proj {zahl(z['proj'])}")
    if a.get("ros_g") is not None:
        teile.append(f"ROS/Sp {zahl(a['ros_g'])}")
    return f"{name} ({'; '.join(teile)})"


def bewegung_zeilen(lage: dict, ausfall: dict) -> list:
    """Bewegungen der laufenden Periode mit Marke [App] oder [NEU, noch nicht in der App]; Claims und reine
    Aufstellungswechsel nur gezählt."""
    b, index, kz = bewegungen(lage["liga"]), lage["app"], lage["kz"]
    woche = lage["woche"]
    aus = [f"BEWEGUNGEN Periode {woche} (seit Wochenwechsel): {len(b['moves'])} Moves – +Zugang −Abgang "
           f"(Position NFL; Ist bzw. Proj W{woche} live)"]
    if spieler_ohne_kader(lage["liga"]) and not lage["kona_da"]:
        aus.append(f"  Spieler-Abruf (kona) nicht erreichbar ({ausfall.get('kona', 'kein Abruf')}) – Spieler ohne Kader "
                   "nur mit Namen laut App bzw. ID, ohne Waiver-Status")
    if index["da"] and not index["fremd"] and not index["marken"]:
        aus.append("  Marken nicht möglich – claude.json hat ein anderes Format (Transaktionen ohne datum_ms oder team)")
    rest, neu, alt = Counter(index["tx"]), 0, 0

    def marke(t: dict) -> str:
        nonlocal neu, alt
        if not index["marken"]:
            return ""
        schluessel = (tx_zeit(t), kz.get(t.get("teamId")))
        if rest[schluessel] > 0:
            rest[schluessel] -= 1
            return " [App]"
        if index["bis"] and (tx_zeit(t) or 0) <= index["bis"] - APP_FENSTER_MS:
            alt += 1
            return f" [älter als das {APP_FENSTER_TAGE}-Tage-Fenster der App]"
        neu += 1
        return " [NEU, noch nicht in der App]"

    zeilen = []
    for t in b["moves"]:
        tid = t.get("teamId")
        teile = ["+" + nenn(lage, i.get("playerId"), tid, False) for i in t["items"] if i.get("type") == "ADD"]
        teile += ["−" + nenn(lage, i.get("playerId"), tid, True) for i in t["items"] if i.get("type") == "DROP"]
        zeilen.append((tx_zeit(t) or 0, f"  {zeit_text(aus_ms(tx_zeit(t)))} {kz.get(tid, tid)} "
                                        f"{MOVE_ARTEN[t['type']]}: {' '.join(teile)}{marke(t)}"))
    for t in b["trades"]:
        zeilen.append((tx_zeit(t) or 0, f"  {zeit_text(aus_ms(tx_zeit(t)))} {kz.get(t.get('teamId'), t.get('teamId'))} "
                                        f"Trade angenommen (ESPN nennt die Spieler nicht){marke(t)}"))
    aus += [text for _, text in sorted(zeilen, key=lambda paar: paar[0])]
    if index["marken"] and zeilen:
        aus.append(f"  → {neu} Bewegung(en) neuer als die App" if neu else
                   f"  → keine Bewegung neuer als die App; {alt} älter als ihr {APP_FENSTER_TAGE}-Tage-Fenster" if alt else
                   "  → alle Bewegungen stehen schon in der App")

    def gezaehlt(c: Counter) -> str:
        return ", ".join(f"{kz.get(tid, tid)} {n}" for tid, n in sorted(c.items(), key=lambda p: (-p[1], str(p[0]))))

    if b["claims"]:
        aus.append("  Gescheiterte Claims (nur gezählt): " + gezaehlt(b["claims"]))
    if b["lineup"]:
        aus.append(f"  Reine Aufstellungswechsel (nur gezählt, {sum(b['lineup'].values())}): " + gezaehlt(b["lineup"]))
    if b["sonst"]:
        aus.append("  Sonstige Einträge (nur gezählt): " + ", ".join(f"{k} {n}" for k, n in sorted(b["sonst"].items())))
    return aus


def kadervergleich_zeilen(lage: dict) -> list:
    """Kader live gegen die Kader der App je Team – zeigt auch Trades, zu denen ESPN keine Spieler nennt."""
    index, kz = lage["app"], lage["kz"]
    if not index["da"] or index["fremd"]:  # steht schon im Kopf
        return []
    if index["kader"] is None:
        return ["  Kadervergleich fehlt (claude.json ohne Kader)"]

    def name(pid) -> str:
        return kurz((lage["spieler"].get(pid) or index["spieler"].get(pid) or {}).get("name") or f"Spieler {pid}")

    abweichung = []
    for tid in sorted(lage["kader"]):
        live, alt = {z["id"] for z in lage["kader"][tid]}, index["kader"].get(kz[tid], set())
        if live != alt:
            abweichung.append(f"{kz[tid]} " + " ".join(["+" + name(p) for p in sorted(live - alt)]
                                                       + ["−" + name(p) for p in sorted(alt - live)]))
    return ["  Kader live ≠ App: " + "; ".join(abweichung) if abweichung
            else f"  Kader live = App (alle {len(lage['kader'])} Teams)"]


def sicher(titel: str, funktion, *args) -> list:
    """Ein Abschnitt, der an einer unerwarteten Antwort scheitert, wird eine Textzeile – der Rest bleibt stehen."""
    try:
        return funktion(*args)
    except Exception as exc:  # z. B. ESPN benennt ein Feld um
        return [f"{titel}: nicht auswertbar ({type(exc).__name__}: {kurz(exc, 80)}) – bitte in Claude Code melden"]


def bericht(jetzt: datetime, liga, scoreboard=None, app=None, kona=None, mein_team: int = MEIN_TEAM,
            abweichung=None, ausfall=None) -> str:
    """Der ganze Text aus den geladenen Antworten (None = Ausfall) und dem Zeitpunkt jetzt (UTC); kein Netz, keine Uhr.

    ausfall nennt je Quelle (liga, scoreboard, app, kona) den Grund; abweichung = ESPN-Serverzeit − Uhr in Sekunden.
    """
    ausfall = ausfall or {}
    ist_liga = isinstance(liga, dict)
    woche = liga.get("scoringPeriodId") if ist_liga else None
    saison = liga.get("seasonId", SAISON) if ist_liga else None
    try:
        index = app_index(app, woche, saison)
    except Exception as exc:  # claude.json in unerwarteter Form: weiter wie ohne die Datei
        index = app_index(None, woche, saison)
        ausfall = dict(ausfall, app=f"nicht lesbar, {type(exc).__name__}: {kurz(exc, 80)}")
    aus = sicher("Kopf", kopf, jetzt, liga, index, abweichung, ausfall)
    if liga is None or liga_mangel(liga):
        grund = ausfall.get("liga") or ("kein Abruf" if liga is None else liga_mangel(liga))
        return "\n".join(aus + [f"ESPN-Liga nicht erreichbar ({grund}) – Matchups, Aufstellungen und Bewegungen fehlen. "
                                "Kein Live-Stand; in ein paar Minuten noch einmal aufrufen."])
    try:
        lage = lage_aus(liga, scoreboard, index, kona)
    except Exception as exc:  # z. B. ESPN ändert die Form von teams oder roster
        return "\n".join(aus + [f"ESPN-Liga: Antwort nicht auswertbar ({type(exc).__name__}: {kurz(exc, 80)}) – kein "
                                "Live-Stand; bitte in Claude Code melden"])
    if scoreboard and not lage["hat_sb"] and "scoreboard" not in ausfall:
        ausfall = dict(ausfall, scoreboard=f"zeigt Woche {kurz((scoreboard.get('week') or {}).get('number', '?'), 5)} "
                                           f"statt {lage['woche']}")
    aus += sicher("NFL-Spiele", nfl_zeilen, lage, ausfall)
    aus += [""] + sicher("Matchups", matchup_zeilen, lage, mein_team)
    aus += [""] + sicher(f"Aufstellung Team {mein_team}", team_zeilen, lage, mein_team, True)
    try:
        gegner = gegner_von(liga, mein_team)
        grund = "Freilos" if paarung_von(liga, mein_team) else "keine Paarung für das Team"
    except Exception:  # der Abschnitt Matchups meldet den Formatbruch schon
        gegner, grund = None, None
    if gegner is not None:
        aus += [""] + sicher(f"Aufstellung Team {gegner}", team_zeilen, lage, gegner)
    elif grund and mein_team in lage["teams"]:
        aus += ["", f"{lage['kz'][mein_team]}: kein Gegner in dieser Periode ({grund})"]
    aus += [""] + sicher("Bewegungen", bewegung_zeilen, lage, ausfall) + sicher("Kadervergleich", kadervergleich_zeilen, lage)
    return "\n".join(aus)


def messzeile(messung: list, gesamt: float, zeichen: int) -> str:
    """Letzte Zeile: Größe und Dauer je Abruf, Gesamtdauer, Zeichenzahl des Textes."""
    teile = [f"{m['name']} {zahl(m['kb'], 0)} KB {zahl(m['s'])} s" + (f" [{m['fehler']}]" if m["fehler"] else "")
             for m in messung]
    return "Messung: " + " · ".join(teile + [f"gesamt {zahl(gesamt)} s", f"{zeichen} Zeichen"])


def team_aus_args(argv) -> int:
    """Team-ID aus dem ersten Argument, wenn dort eine Team-ID der Liga steht; alles andere zählt nicht.

    Unter „python3 -c“ ist argv ['-c'], im Notebook steht dort Fremdes (z. B. '-f', eine Kernel-Datei): Standard.
    """
    erstes = argv[1] if isinstance(argv, (list, tuple)) and len(argv) > 1 else None
    if isinstance(erstes, str) and erstes.isdecimal() and int(erstes) in KUERZEL:
        return int(erstes)
    return MEIN_TEAM


# ---------------------------------------------------------------- Abruf (Netz)

def hole(name: str, urls, params=None, headers=None, versuche: int = 1) -> dict:
    """GET auf die erste Adresse, die ein JSON-Objekt liefert; wirft nie.

    Ergebnis: name, daten (None bei Ausfall), kb, s, fehler (Grund als Text), abweichung (Date-Header − Uhr, s).
    """
    start = time.perf_counter()
    satz = {"name": name, "daten": None, "kb": 0, "s": 0.0, "fehler": None, "abweichung": None}
    gruende = []
    for url in [u for u in urls for _ in range(versuche)]:
        try:
            antwort = requests.get(url, params=params, headers=headers, timeout=(VERBINDEN, LESEN))
            uhr = datetime.now(timezone.utc)
            if antwort.status_code != 200:
                gruende.append(f"HTTP {antwort.status_code}")
                continue
            daten = antwort.json()
            if not isinstance(daten, dict):
                gruende.append("kein JSON-Objekt")
                continue
            satz.update(daten=daten, kb=len(antwort.content) / 1000)
            try:
                satz["abweichung"] = (parsedate_to_datetime(antwort.headers.get("Date")) - uhr).total_seconds()
            except (TypeError, ValueError):  # kein oder ein unlesbarer Date-Header: ohne Abweichung
                pass
            break
        except Exception as exc:  # Netz, Zeitlimit, kaputtes JSON: wird eine Textzeile im Bericht
            gruende.append(type(exc).__name__)
    satz["s"] = time.perf_counter() - start
    if satz["daten"] is None:
        satz["fehler"] = ", ".join(gruende) or "keine Adresse"
    return satz


def parallel(auftraege: dict, frist: float) -> dict:
    """Führt {schlüssel: Argumente für hole} gleichzeitig aus; wer bis zur Frist nicht fertig ist, gilt als Ausfall.

    Daemon-Fäden: Ein hängender Abruf hält weder den Text noch das Ende des Skripts auf.
    """
    fach, faeden = {}, []

    def lauf(schluessel, args):
        fach[schluessel] = hole(*args)

    for schluessel, args in auftraege.items():
        faden = threading.Thread(target=lauf, args=(schluessel, args), daemon=True)
        faden.start()
        faeden.append(faden)
    ende = time.perf_counter() + frist
    for faden in faeden:
        faden.join(max(0.0, ende - time.perf_counter()))
    fertig = dict(fach)
    return {schluessel: fertig.get(schluessel) or {"name": args[0], "daten": None, "kb": 0, "s": float(frist),
                                                    "fehler": f"keine Antwort nach {frist} s", "abweichung": None}
            for schluessel, args in auftraege.items()}


def abrufen() -> dict:
    """Alle Abrufe: erst Liga, Scoreboard und claude.json gleichzeitig, dann nur bei Bedarf das Scoreboard der
    Liga-Woche und kona für Spieler ohne Kader. → liga, scoreboard, app, kona, ausfall, messung, abweichung."""
    runde = parallel({"liga": ("ESPN-Liga", [LIGA_URL], [("view", v) for v in LIGA_VIEWS], None, 2),
                      "scoreboard": ("Scoreboard", [SCOREBOARD_URL]),
                      "app": ("claude.json", list(APP_URLS))}, FRIST)
    messung = [runde[k] for k in ("liga", "scoreboard", "app")]
    liga = runde["liga"]["daten"]
    if liga is not None:
        ohne_personen(liga)
        if liga_mangel(liga):
            runde["liga"]["fehler"], liga = liga_mangel(liga), None
    nach = {}
    if liga is not None:
        woche = liga["scoringPeriodId"]
        if not scoreboard_passt(runde["scoreboard"]["daten"], woche):  # anderer Wochenstand oder Ausfall: gezielt holen
            nach["scoreboard"] = (f"Scoreboard W{woche}", [SCOREBOARD_URL],
                                  {"seasontype": 2, "week": woche, "dates": liga.get("seasonId", SAISON)})
        ids = spieler_ohne_kader(liga)
        if ids:
            nach["kona"] = (f"Kona ({len(ids)} Spieler ohne Kader)", [LIGA_URL], {"view": KONA_VIEW},
                            {"X-Fantasy-Filter": json.dumps(kona_filter(ids, woche))})
        if nach:
            runde.update(parallel(nach, FRIST_NACH))
            messung += [runde[k] for k in nach]
    return {"liga": liga, "scoreboard": runde["scoreboard"]["daten"], "app": runde["app"]["daten"],
            "kona": (runde.get("kona") or {}).get("daten"),
            "ausfall": {k: m["fehler"] for k, m in runde.items() if m["fehler"]},
            "messung": messung, "abweichung": runde["liga"]["abweichung"]}


def main(argv=None) -> None:
    """Abrufen, Text bauen, drucken. Endet immer normal: Jeder Fehler wird eine Textzeile, kein Traceback.

    Das gilt auch, wenn der Quelltext per exec(r.content) ohne eigenen Namensraum in einer Funktion läuft: Dann
    findet main() die Namen des Skripts nicht (time, abrufen, messzeile …) – deshalb steht alles im try.
    """
    text, messung, start = "", [], None
    try:
        start = time.perf_counter()
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # Notebook-Ausgaben kennen reconfigure nicht
            pass
        if requests is None:
            text = "Stand-Skript: Das Paket requests fehlt (pip install requests) – kein Stand."
        else:
            roh = abrufen()
            messung = roh["messung"]
            text = bericht(datetime.now(timezone.utc), roh["liga"], roh["scoreboard"], roh["app"], roh["kona"],
                           team_aus_args(sys.argv if argv is None else argv), roh["abweichung"], roh["ausfall"])
    except Exception as exc:
        text = f"Stand-Skript: unerwarteter Fehler ({type(exc).__name__}: {exc}) – kein Stand; bitte in Claude Code melden."
        if isinstance(exc, NameError):  # nur ASCII: ohne Namensraum fehlt auch sys, die Ausgabe ist nicht auf UTF-8 gestellt
            text = (f"Stand-Skript: unerwarteter Fehler (NameError: {exc}) - kein Stand. Der Quelltext lief vermutlich per "
                    "exec ohne eigenen Namensraum in einer Funktion: Aufruf mit exec(r.content, {'__name__': '__main__'}) "
                    "wiederholen, sonst bitte in Claude Code melden.")
    try:
        print(text)
    except Exception:  # eine Ausgabe, die die Zeichen nicht darstellen kann und reconfigure nicht kennt
        try:
            print(ascii(text))
        except Exception:
            pass
    try:
        print("\n" + messzeile(messung, time.perf_counter() - start, len(text)))
    except Exception:  # ohne Namensraum fehlen auch messzeile und time; der Text darüber sagt es schon
        pass


# „builtins“: exec(r.content, {}) mit leerem Namensraum – __name__ kommt dann aus den Builtins; auch das soll laufen
if __name__ in ("__main__", "builtins"):
    main()
