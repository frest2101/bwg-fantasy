"""Tests Stand-Skript für den claude.ai-Projekt-Chat (scripts/claude_stand.py).

Offline: Alle Antworten sind kleine erfundene JSON-Bausteine in der Form der ESPN-Antworten – Spieler, Teamnamen,
Punkte, Zeiten und der Manager-Name („Zacharias Erfundenmann“) sind erfunden, echt sind nur die IDs und Kürzel der
NFL-Teams und die Team-IDs 1, 2, 3 und 10 der Liga (für die Kürzel der App). Die erfundene Woche 7 enthält die
Zeitumstellung vom 25.10.2026. Das Netz ersetzt eine Fake-Funktion für requests.get.
Aufruf: python -m pytest
"""

import ast
import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import requests

import app_export
import claude_stand as cs
import espn_fetch as ef
import lineup

UTC = timezone.utc
WOCHE = 7
JETZT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)          # Freitag vor der Zeitumstellung, 14:00 MESZ
KC, DEN, BUF, MIA, SF, SEA, DAL, PHI, NYG, NYJ, CHI = 12, 7, 2, 15, 25, 26, 6, 21, 19, 20, 3
OFFENSE = [20, 21]                                         # eligibleSlots: Bank und IR gehen immer
MANAGER = ("Zacharias", "Erfundenmann", "zerfunden99", "ERFUNDENE-GUID")  # erfunden, darf nie im Text stehen
SPALTEN = ["id", "name", "pos", "nfl", "inj", "avg", "form", "trend", "ros_g", "ros_rang", "gegner_n1", "mu_n1",
           "proj", "proj3"]


def ms(*teile) -> int:
    return int(datetime(*teile, tzinfo=UTC).timestamp() * 1000)


MOVE_APP, MOVE_NEU, TRADE = ms(2026, 10, 21, 8, 16), ms(2026, 10, 23, 11, 30), ms(2026, 10, 22, 18, 0)


# ---------------------------------------------------------------- erfundene Bausteine

def eintrag(pid, name, pos, pro, slot, ist=None, proj=None, inj="ACTIVE", wahl=(), gesperrt=False) -> dict:
    """Kadereintrag wie in mRoster; dazu Stat-Einträge, die nicht zählen dürfen (Vorwoche, Saison, Vorjahr)."""
    stats = [{"seasonId": 2026, "scoringPeriodId": WOCHE - 1, "statSourceId": 0, "statSplitTypeId": 1, "appliedTotal": 99.0},
             {"seasonId": 2026, "scoringPeriodId": 0, "statSourceId": 1, "statSplitTypeId": 0, "appliedTotal": 88.0},
             {"seasonId": 2025, "scoringPeriodId": WOCHE, "statSourceId": 0, "statSplitTypeId": 1, "appliedTotal": 77.0}]
    for quelle, wert in ((1, proj), (0, ist)):
        if wert is not None:
            stats.append({"seasonId": 2026, "scoringPeriodId": WOCHE, "statSourceId": quelle, "statSplitTypeId": 1,
                          "appliedTotal": wert})
    return {"playerId": pid, "lineupSlotId": slot,
            "playerPoolEntry": {"id": pid, "lineupLocked": gesperrt, "status": "ONTEAM",
                                "player": {"id": pid, "fullName": name, "defaultPositionId": pos, "proTeamId": pro,
                                           "injuryStatus": inj, "eligibleSlots": list(wahl) + OFFENSE, "stats": stats}}}


def team(tid, name, bilanz, eintraege) -> dict:
    w, l, t = bilanz
    return {"id": tid, "name": name, "abbrev": "XX", "owners": ["{ERFUNDENE-GUID}"], "primaryOwner": "{ERFUNDENE-GUID}",
            "record": {"overall": {"wins": w, "losses": l, "ties": t}}, "roster": {"entries": eintraege}}


def spiel(gast, heim, anstoss, state="pre", punkte=("0", "0"), detail="", zeit_gueltig=True) -> dict:
    seite = lambda pro, ort, score: {"homeAway": ort, "score": score, "team": {"id": str(pro), "abbreviation": cs.NFL[pro]}}
    return {"date": anstoss, "competitions": [{
        "timeValid": zeit_gueltig, "competitors": [seite(heim, "home", punkte[1]), seite(gast, "away", punkte[0])],
        "status": {"type": {"state": state, "completed": state == "post", "shortDetail": detail}}}]}


def scoreboard(woche=WOCHE) -> dict:
    return {"season": {"type": 2, "year": 2026}, "week": {"number": woche, "teamsOnBye": [{"abbreviation": "CHI"}]},
            "events": [spiel(KC, DEN, "2026-10-23T00:15Z", "post", ("20", "27"), "Final"),
                       spiel(BUF, MIA, "2026-10-23T11:00Z", "in", ("14", "10"), "5:23 - 3rd"),
                       spiel(SF, SEA, "2026-10-25T18:00Z"),             # nach der Umstellung: 19:00 MEZ
                       spiel(DAL, PHI, "2026-10-24T17:00:00Z"),          # vor der Umstellung: 19:00 MESZ
                       spiel(NYG, NYJ, "2026-10-26T00:20Z", zeit_gueltig=False)]}


def liga() -> dict:
    hjs = [eintrag(101, "Quentin Erfunden", 1, KC, 0, ist=21.345, proj=20.0, wahl=[0, 7], gesperrt=True),
           eintrag(102, "Rudi Beispiel", 2, SF, 2, proj=15.333333, wahl=[2, 23, 7]),
           eintrag(103, "Willi Muster", 3, CHI, 4, proj=0.0, wahl=[4, 23, 7]),
           eintrag(104, "Fritz Flex", 2, BUF, 23, ist=7.666666, proj=9.0, inj="QUESTIONABLE", wahl=[2, 23, 7], gesperrt=True),
           eintrag(-16026, "Testabwehr Eins D/ST", 16, SEA, 16, proj=6.0, wahl=[16]),
           eintrag(106, "Bodo Bank", 3, SF, 20, proj=12.5, wahl=[4, 23, 7]),
           eintrag(-16015, "Testabwehr Zwei D/ST", 16, MIA, 20, ist=4.0, proj=5.0, wahl=[16], gesperrt=True),
           eintrag(108, "Kurt Keinpunkt", 3, KC, 20, ist=0.0, proj=3.0, wahl=[4, 23, 7], gesperrt=True),
           eintrag(109, "Otto Offen", 2, SEA, 20, proj=3.0, wahl=[2, 23, 7]),
           eintrag(110, "Ingo Reserve", 3, DAL, 21, proj=0.0, inj="INJURY_RESERVE", wahl=[4, 23, 7])]
    sgk = [eintrag(201, "Gustav Gegner", 1, PHI, 0, proj=18.125, wahl=[0, 7]),
           eintrag(202, "Heinz Holzbein", 5, DEN, 17, ist=9.0, proj=8.0, wahl=[17], gesperrt=True),
           eintrag(203, "Neu Geholt", 2, NYG, 20, proj=4.0, wahl=[2, 23, 7])]
    seite = lambda tid, live, proj, chance: {"teamId": tid, "totalPoints": 0.0, "totalPointsLive": live,
                                             "totalProjectedPointsLive": proj, "winProbability": chance}
    item = lambda art, pid: {"type": art, "playerId": pid}
    return {
        "id": cs.LIGA_ID, "seasonId": 2026, "scoringPeriodId": WOCHE, "status": {"currentMatchupPeriod": WOCHE},
        "members": [{"id": "{ERFUNDENE-GUID}", "firstName": "Zacharias", "lastName": "Erfundenmann",
                     "displayName": "zerfunden99"}],
        "teams": [team(1, "Testteam Eins", (3, 2, 1), []), team(2, "Testteam Zwei", (5, 1, 0), hjs),
                  team(3, "Testteam Drei", (2, 4, 0), []), team(10, "Testteam Zehn", (2, 4, 0), sgk)],
        "schedule": [
            {"matchupPeriodId": WOCHE - 1, "home": seite(2, 150.0, 150.0, 1.0), "away": seite(1, 1.0, 1.0, 0.0),
             "winner": "HOME"},
            {"matchupPeriodId": WOCHE, "home": seite(10, 9.0, 27.125, 0.345), "away": seite(2, 29.011666, 61.5, 0.655),
             "winner": "UNDECIDED"},
            {"matchupPeriodId": WOCHE, "home": {"teamId": 1, "totalPoints": 100.5}, "away": {"teamId": 3, "totalPoints": 90.0},
             "winner": "HOME"}],
        "transactions": [
            {"id": "a", "type": "FREEAGENT", "status": "EXECUTED", "teamId": 2, "proposedDate": MOVE_APP,
             "memberId": "{ERFUNDENE-GUID}", "items": [item("ADD", 106), item("DROP", 9001)]},
            {"id": "b", "type": "WAIVER", "status": "EXECUTED", "teamId": 10, "proposedDate": MOVE_NEU - 86_400_000,
             "processDate": MOVE_NEU, "memberId": "{ERFUNDENE-GUID}", "items": [item("ADD", 203)]},
            {"id": "c", "type": "WAIVER", "status": "FAILED_INVALIDPLAYERSOURCE", "teamId": 3, "processDate": MOVE_NEU,
             "items": [item("ADD", 203), item("DROP", 9003)]},
            {"id": "d", "type": "ROSTER", "status": "EXECUTED", "teamId": 2, "proposedDate": MOVE_APP + 5,
             "items": [item("LINEUP", 102)]},
            {"id": "e", "type": "TRADE_ACCEPT", "teamId": 1, "proposedDate": TRADE},
            {"id": "f", "type": "TRADE_PROPOSAL", "status": "PENDING", "teamId": 3, "proposedDate": TRADE,
             "items": [item("TRADE", 101)]}]}


def kona() -> dict:
    """Antwort auf kona_player_info für den einen Spieler ohne Kader (Form wie playerPoolEntry)."""
    eintrag_ = eintrag(9001, "Karl Abgang", 3, DAL, None, proj=0.0, inj="OUT")["playerPoolEntry"]
    eintrag_.update(status="WAIVERS", onTeamId=0, waiverProcessDate=ms(2026, 10, 26, 8, 0))
    return {"players": [eintrag_]}


def app(matchup_woche=WOCHE) -> dict:
    """claude.json in Kurzform: Kader gleich dem Live-Kader bis auf SGK (203 fehlt, 9002 steht noch darin)."""
    zeile = lambda pid, name, pos, nfl, ros=None, mu=None, proj=None: [pid, name, pos, nfl, None, None, None, None, ros,
                                                                       None, None, mu, proj, None]
    return {"stand": {"saison": 2026, "nach_woche": WOCHE - 1, "matchup_woche": matchup_woche,
                      "pool_stand": "2026-10-23T1045Z", "pool_woche": WOCHE},
            "teams": {"ACB": "Testteam Eins", "HJS": "Testteam Zwei", "4DS": "Testteam Drei", "SGK": "Testteam Zehn"},
            "spieler_spalten": SPALTEN, "free_agents_spalten": SPALTEN + ["status"],
            "kader": {"ACB": [], "4DS": [],
                      "HJS": [zeile(101, "Quentin Erfunden", "QB", "KC", 20.5, 1.05),
                              zeile(102, "Rudi Beispiel", "RB", "SF", 14.0, 0.947),
                              zeile(103, "Willi Muster", "WR", "CHI"), zeile(104, "Fritz Flex", "RB", "BUF"),
                              zeile(-16026, "Testabwehr Eins D/ST", "D/ST", "SEA"), zeile(106, "Bodo Bank", "WR", "SF", 9.875),
                              zeile(-16015, "Testabwehr Zwei D/ST", "D/ST", "MIA"), zeile(108, "Kurt Keinpunkt", "WR", "KC"),
                              zeile(109, "Otto Offen", "RB", "SEA"), zeile(110, "Ingo Reserve", "WR", "DAL")],
                      "SGK": [zeile(201, "Gustav Gegner", "QB", "PHI"), zeile(202, "Heinz Holzbein", "K", "DEN"),
                              zeile(9002, "Alter Kicker", "K", "NYJ")]},
            "free_agents": {"WR": [zeile(9001, "Karl Abgang", "WR", "DAL", 4.21, None, 1.5) + ["WAIVERS"]]},
            "transaktionen_spalten": ["datum_ms", "team", "typ", "zugang", "abgang"],
            "transaktionen": [[MOVE_APP - 3 * 86_400_000, "SGK", "FREEAGENT", ["Alter Kicker"], []],
                              [MOVE_APP, "HJS", "FREEAGENT", ["Bodo Bank"], ["Karl Abgang"]]]}


def text(jetzt=JETZT, **anders) -> str:
    """Bericht des vollständigen erfundenen Falls; anders ersetzt einzelne Antworten (None = Ausfall)."""
    teile = {"liga": liga(), "scoreboard": scoreboard(), "app": app(), "kona": kona(), "abweichung": 2.4}
    teile.update(anders)
    return cs.bericht(jetzt, **teile)


# ---------------------------------------------------------------- Konstanten, Eigenständigkeit

def test_konstanten_passen_zum_repo():
    assert (cs.LIGA_ID, cs.SAISON) == (ef.LEAGUE_ID, ef.DEFAULT_SEASON)   # Saisonwechsel: beide Stellen ändern
    assert cs.LIGA_URL == ef.BASE_URL.format(season=ef.DEFAULT_SEASON, league=ef.LEAGUE_ID)
    assert cs.KONA_VIEW == ef.KONA_VIEW and "mTransactions2" in cs.LIGA_VIEWS and ef.TX_VIEW in cs.LIGA_VIEWS
    assert cs.KUERZEL == app_export.KUERZEL and cs.MEIN_TEAM in cs.KUERZEL
    assert cs.SLOT == lineup.SLOT_NAMES and cs.POS == lineup.POSITION_NAMES
    assert (cs.SLOT_BANK, cs.SLOT_IR) == (lineup.SLOT_BENCH, lineup.SLOT_IR)
    assert set(cs.STARTER_SLOTS) == set(cs.SLOT) - {cs.SLOT_BANK, cs.SLOT_IR}
    assert cs.STARTER_ZAHL == sum(n for _, n in lineup.BASE_SLOTS) + 3    # dazu 2 FLEX und OP
    assert cs.APP_FENSTER_MS == 14 * 86_400_000 and all(url.endswith("/claude.json") for url in cs.APP_URLS)


def test_nfl_kuerzel_wie_im_spielplan():
    plan = ef.load_json(ef.season_files(ef.DEFAULT_SEASON)["schedule"])
    assert cs.NFL == {t["id"]: t["abbrev"].upper() for t in plan["settings"]["proTeams"]}


def test_skript_ist_eigenstaendig():
    """Nur Standardbibliothek und requests, kein zoneinfo, nichts aus dem Repo – es läuft allein im Chat-Container."""
    baum = ast.parse(Path(cs.__file__).read_text(encoding="utf-8"))
    module = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            module |= {a.name.split(".")[0] for a in knoten.names}
        elif isinstance(knoten, ast.ImportFrom):
            module.add((knoten.module or "").split(".")[0])
            assert knoten.level == 0
    assert "zoneinfo" not in module
    assert module - {"requests"} <= set(sys.stdlib_module_names)
    quelle = Path(cs.__file__).read_text(encoding="utf-8")
    assert "datetime.now(" not in quelle[:quelle.index("def hole(")]  # die reinen Funktionen kennen keine Uhr


# ---------------------------------------------------------------- Zahlen und Zeit

@pytest.mark.parametrize("wert, erwartet", [
    (12.345, "12.35"), (18.125, "18.13"), (2.675, "2.68"), (7.333333333, "7.33"), (6.666666667, "6.67"), (0.005, "0.01"),
    (-1.005, "-1.01"), (-0.001, "0.00"), (0, "0.00"), (236.35004197, "236.35"), (Decimal("0.125"), "0.13"), (None, "–")])
def test_zahl_rundet_half_up(wert, erwartet):
    assert cs.zahl(wert) == erwartet


def test_zahl_stellen_und_prozent():
    assert cs.zahl(1.0495, 3) == "1.050" and cs.zahl(0.9465, 3) == "0.947" and cs.zahl(2.5, 0) == "3"
    assert cs.zahl(1.25, 1) == "1.3"                                  # „%.1f“ gäbe 1.2
    assert [cs.prozent(a) for a in (0.345, 0.655, 0.5449, 1, 0, None)] == ["35 %", "66 %", "54 %", "100 %", "0 %", "–"]


@pytest.mark.parametrize("utc, erwartet", [
    ((2026, 10, 25, 0, 59), "So 25.10. 02:59 MESZ"),     # letzte Minute Sommerzeit
    ((2026, 10, 25, 1, 0), "So 25.10. 02:00 MEZ"),       # Umstellung 01:00 UTC
    ((2027, 3, 28, 0, 59), "So 28.03. 01:59 MEZ"),
    ((2027, 3, 28, 1, 0), "So 28.03. 03:00 MESZ"),
    ((2026, 12, 31, 23, 30), "Fr 01.01. 00:30 MEZ"),
    ((2026, 9, 8, 22, 15), "Mi 09.09. 00:15 MESZ")])
def test_deutsche_zeit_mit_etikett_des_zeitpunkts(utc, erwartet):
    assert cs.zeit_text(datetime(*utc, tzinfo=UTC)) == erwartet


def test_umstellung_und_zeitformen():
    assert cs.umstellung(2026, 10) == datetime(2026, 10, 25, 1, tzinfo=UTC)
    assert cs.umstellung(2026, 3) == datetime(2026, 3, 29, 1, tzinfo=UTC)
    assert cs.umstellung(2027, 10) == datetime(2027, 10, 31, 1, tzinfo=UTC)
    assert cs.zeit_text(JETZT, datum=False) == "Fr 14:00 MESZ" and cs.zeit_text(JETZT, jahr=True) == "Fr 23.10.2026 14:00 MESZ"
    assert cs.zeit_text(None) == "(Zeit offen)" and cs.aus_ms(None) is None
    assert cs.aus_iso("2026-10-02T00:15Z") == cs.aus_iso("2026-10-02T00:15:00Z") == datetime(2026, 10, 2, 0, 15, tzinfo=UTC)
    assert cs.aus_iso("kaputt") is None and cs.aus_iso(None) is None
    assert cs.aus_ms(MOVE_APP) == datetime(2026, 10, 21, 8, 16, tzinfo=UTC)


# ---------------------------------------------------------------- Bericht: Kopf, Spiele, Matchups

def test_kopf_vor_der_umstellung():
    zeilen = text().split("\n")
    assert zeilen[0] == ("STAND Fr 23.10.2026 14:00 MESZ (12:00 UTC, Uhr des Containers; ESPN-Serverzeit weicht +2 s ab)"
                         " – ESPN Woche 7")
    assert zeilen[1] == ("App: gerechnet bis Woche 6; Tagesstand Fr 23.10. 12:45 MESZ (vor 1.3 h); "
                         "letzter Move in der App Mi 21.10. 10:16 MESZ")
    assert zeilen[2].startswith("Alle Zeiten deutsche Zeit. Punkte, Projektion (Proj) und Siegchance: ESPN live.")
    assert zeilen[2].endswith("ROS/Sp = ROS-Projektion je Spiel, F = Positions-Matchup des Gegners (> 1 günstig).")
    assert "nicht auswertbar" not in "\n".join(zeilen)


def test_kopf_nach_der_umstellung_und_abweichung():
    zeilen = text(jetzt=datetime(2026, 10, 26, 12, 0, tzinfo=UTC), abweichung=-200.0).split("\n")
    assert zeilen[0].startswith("STAND Mo 26.10.2026 13:00 MEZ (12:00 UTC, Uhr des Containers; ESPN-Serverzeit weicht -200 s")
    assert zeilen[1].startswith("! Die Uhr des Containers weicht stark von ESPN ab")
    assert "Tagesstand Fr 23.10. 12:45 MESZ (vor 73.3 h)" in zeilen[2]   # das Etikett gehört zum Zeitpunkt
    assert "weicht" not in text(abweichung=None).split("\n")[0]


def test_nfl_spiele_mit_etikett_je_anstoss():
    """Am Freitag (MESZ) steht der Sonntagsanstoß nach der Umstellung schon in MEZ."""
    zeilen = text().split("\n")
    start = zeilen.index("NFL W7: 1 final, 1 läuft, 3 offen; Bye: CHI")
    assert zeilen[start + 1:start + 6] == ["  final: KC@DEN 20:27",
                                           "  läuft: BUF@MIA 14:10 (5:23 - 3rd)",
                                           "  offen Sa 24.10. 19:00 MESZ: DAL@PHI",
                                           "  offen So 25.10. 19:00 MEZ: SF@SEA",
                                           "  offen (Zeit offen): NYG@NYJ"]


def test_nur_eine_zeitzone_im_text():
    zeilen = text().split("\n")
    assert "UTC" in zeilen[0] and not any("UTC" in z for z in zeilen[1:])
    assert all(("MESZ" in z or "MEZ" in z) for z in zeilen if z.startswith("  offen ") and "Zeit offen" not in z)


def test_matchup_zeilen():
    zeilen = text().split("\n")
    start = zeilen.index("MATCHUPS W7 (* = eigenes): Team (Bilanz) Punkte live | Live-Projektion | Siegchance | "
                         "Starter final/läuft/offen")
    assert zeilen[start + 1] == (" *SGK (2-4) 9.00 | 27.13 | 35 % | 1/0/1  –  "
                                 "HJS (5-1) 29.01 | 61.50 | 66 % | 1/1/2 +1 Bye")
    assert zeilen[start + 2] == "  ACB (3-2-1) 100.50 | – | – | 0/0/0  –  4DS (2-4) 90.00 | – | – | 0/0/0  [Sieger ACB]"
    assert zeilen[start + 3] == ""                                   # die Vorwoche (150.00) kommt nicht vor
    assert cs.gegner_von(liga(), 2) == 10 and cs.gegner_von(liga(), 3) == 1 and cs.gegner_von(liga(), 7) is None


def test_matchup_freilos_und_keine_paarung():
    daten = liga()
    daten["schedule"] = [{"matchupPeriodId": WOCHE, "home": {"teamId": 2, "totalPoints": 0.0}}]
    ausgabe = cs.bericht(JETZT, daten, scoreboard(), app(), kona())
    assert " *HJS (5-1) 0.00 | – | – | 1/1/2 +1 Bye  (Freilos)" in ausgabe and "SGK Testteam Zehn" not in ausgabe
    daten["schedule"] = [{"matchupPeriodId": WOCHE - 1, "home": {"teamId": 2}, "away": {"teamId": 10}}]
    assert "  keine Paarung in dieser Matchup-Periode" in cs.bericht(JETZT, daten, scoreboard(), app(), kona())


def test_matchup_unentschieden_und_playoff_runde():
    daten = liga()
    daten["schedule"][2].update(winner="TIE", playoffTierType="WINNERS_BRACKET")
    daten["schedule"][1]["playoffTierType"] = "NONE"
    zeilen = cs.bericht(JETZT, daten, scoreboard(), app(), kona()).split("\n")
    assert ("  ACB (3-2-1) 100.50 | – | – | 0/0/0  –  4DS (2-4) 90.00 | – | – | 0/0/0  [Unentschieden]  [WINNERS_BRACKET]"
            in zeilen)
    assert " *SGK (2-4) 9.00 | 27.13 | 35 % | 1/0/1  –  HJS (5-1) 29.01 | 61.50 | 66 % | 1/1/2 +1 Bye" in zeilen


# ---------------------------------------------------------------- Bericht: Aufstellung und Bank

def test_starter_zeilen():
    zeilen = text().split("\n")
    start = zeilen.index("HJS Testteam Zwei – Slot Spieler NFL Spiel | Punkte | Proj | F")
    assert zeilen[start + 1:start + 7] == [
        "  QB   Quentin Erfunden KC @ DEN final | 21.35 | 20.00 | F 1.050",
        "  RB   Rudi Beispiel SF @ SEA So 19:00 MEZ | – | 15.33 | F 0.947",
        "  WR   Willi Muster CHI Bye | – | 0.00",
        "  FLEX Fritz Flex RB BUF @ MIA läuft (5:23 - 3rd) | 7.67 | 9.00 | Q",
        "  D/ST Testabwehr Eins D/ST SEA vs SF So 19:00 MEZ | – | 6.00",
        "  ! nur 5 von 13 Starter-Slots besetzt"]
    gegner = zeilen.index("SGK Testteam Zehn – Slot Spieler NFL Spiel | Punkte | Proj | F")
    assert gegner > start
    assert zeilen[gegner + 1:gegner + 3] == ["  QB   Gustav Gegner PHI vs DAL Sa 19:00 MESZ | – | 18.13",
                                             "  K    Heinz Holzbein DEN vs KC final | 9.00 | 8.00"]
    assert "ACB Testteam Eins –" not in "\n".join(zeilen)            # nur eigenes Team und Gegner


def test_bank_zeilen():
    """Bank nur mit Punkten oder mit mehr Projektion als ein noch tauschbarer Starter im passenden Slot."""
    zeilen = text().split("\n")
    start = zeilen.index("  Bank mit Punkten oder mit mehr Projektion als ein noch offener Starter im passenden Slot:")
    assert zeilen[start + 1:start + 4] == [
        "  Bank Bodo Bank WR SF @ SEA So 19:00 MEZ | – | 12.50 → mehr Proj als Starter Willi Muster (WR Bye)",
        "  Bank Testabwehr Zwei D/ST MIA vs BUF läuft (5:23 - 3rd) | 4.00 | 5.00",
        ""]
    ausgabe = "\n".join(zeilen)
    for name in ("Kurt Keinpunkt", "Otto Offen", "Ingo Reserve"):    # 0 Punkte, weniger Projektion, IR ohne Punkte
        assert name not in ausgabe
    assert "  Bank: nichts Auffälliges (keine Punkte, keine höhere Projektion als ein offener Starter)" in zeilen  # SGK


def test_bank_gegen_gesperrten_starter_zaehlt_nicht():
    daten = liga()
    hjs = daten["teams"][1]["roster"]["entries"]
    hjs[2]["playerPoolEntry"]["player"]["proTeamId"] = KC            # Willi Muster hat schon gespielt: nicht tauschbar
    assert "mehr Proj als Starter" not in cs.bericht(JETZT, daten, scoreboard(), app(), kona())
    hjs[2]["playerPoolEntry"]["player"]["proTeamId"] = SF            # offen, Projektion 0.00 < 12.50
    assert "→ mehr Proj als Starter Willi Muster (WR 0.00)" in cs.bericht(JETZT, daten, scoreboard(), app(), kona())


def test_anderes_team_und_unbekannte_team_id():
    ausgabe = text(mein_team=10)
    assert ausgabe.index("SGK Testteam Zehn –") < ausgabe.index("HJS Testteam Zwei –")
    assert "Team-ID 7 gibt es in der Liga nicht – keine Aufstellung" in text(mein_team=7)


# ---------------------------------------------------------------- Bericht: Bewegungen

def test_bewegungen_mit_marken():
    zeilen = text().split("\n")
    start = zeilen.index("BEWEGUNGEN Periode 7 (seit Wochenwechsel): 2 Moves – +Zugang −Abgang "
                         "(Position NFL; Ist bzw. Proj W7 live)")
    assert zeilen[start + 1:] == [
        "  Mi 21.10. 10:16 MESZ HJS Free Agent: +Bodo Bank (WR SF; Proj 12.50; ROS/Sp 9.88) "
        "−Karl Abgang (WR DAL; auf Waivers bis Mo 26.10. 09:00 MEZ; OUT; Proj 0.00; ROS/Sp 4.21) [App]",
        "  Do 22.10. 20:00 MESZ ACB Trade angenommen (ESPN nennt die Spieler nicht) [NEU, noch nicht in der App]",
        "  Fr 23.10. 13:30 MESZ SGK Waiver: +Neu Geholt (RB NYG; Proj 4.00) [NEU, noch nicht in der App]",
        "  → 2 Bewegung(en) neuer als die App",
        "  Gescheiterte Claims (nur gezählt): 4DS 1",
        "  Reine Aufstellungswechsel (nur gezählt, 1): HJS 1",
        "  Sonstige Einträge (nur gezählt): TRADE_PROPOSAL PENDING 1",
        "  Kader live ≠ App: SGK +Neu Geholt −Alter Kicker"]


def test_bewegungen_alle_in_der_app_und_kader_gleich():
    stand = app()
    stand["kader"]["SGK"][2] = [203, "Neu Geholt", "RB", "NYG"] + [None] * 10
    stand["transaktionen"] += [[MOVE_NEU, "SGK", "WAIVER", ["Neu Geholt"], []], [TRADE, "ACB", "TRADE_ACCEPT", [], []]]
    ausgabe = text(app=stand)
    assert "[NEU" not in ausgabe and ausgabe.count("[App]") == 3
    assert "  → alle Bewegungen stehen schon in der App" in ausgabe
    assert ausgabe.endswith("  Kader live = App (alle 4 Teams)")


def test_marke_zaehlt_gleiche_zeit_und_team_einzeln():
    """Zwei Moves desselben Teams mit derselben Zeit, die App kennt nur einen: einer [App], einer [NEU]."""
    daten = liga()
    daten["transactions"].append({"id": "a2", "type": "FREEAGENT", "status": "EXECUTED", "teamId": 2,
                                  "proposedDate": MOVE_APP, "items": [{"type": "ADD", "playerId": 109}]})
    zeilen = [z for z in cs.bericht(JETZT, daten, scoreboard(), app(), kona()).split("\n") if " HJS Free Agent: " in z]
    assert [z.rsplit("[", 1)[1] for z in zeilen] == ["App]", "NEU, noch nicht in der App]"]


def test_move_vor_dem_fenster_der_app_ist_nicht_neu():
    daten = liga()
    daten["transactions"][1]["processDate"] = MOVE_APP - cs.APP_FENSTER_MS
    ausgabe = cs.bericht(JETZT, daten, scoreboard(), app(), kona())
    assert "+Neu Geholt (RB NYG; Proj 4.00) [älter als das 14-Tage-Fenster der App]" in ausgabe
    assert "  → 1 Bewegung(en) neuer als die App" in ausgabe          # nur der Trade


def test_abgang_der_wieder_im_kader_steht_und_zugang_der_weg_ist():
    daten = liga()
    daten["transactions"][0]["items"] = [{"type": "ADD", "playerId": 9001}, {"type": "DROP", "playerId": 203}]
    ausgabe = cs.bericht(JETZT, daten, scoreboard(), app(), kona())
    assert "+Karl Abgang (WR DAL; auf Waivers bis Mo 26.10. 09:00 MEZ; OUT; Proj 0.00; ROS/Sp 4.21)" in ausgabe
    assert "−Neu Geholt (RB NYG; jetzt SGK; Proj 4.00)" in ausgabe
    assert cs.spieler_ohne_kader(daten) == [9001] and cs.spieler_ohne_kader(liga()) == [9001]  # 9003: nur gescheitert
    geholt = kona()                                                  # zwischen Liga- und kona-Abruf von SGK geholt
    geholt["players"][0].update(status="ONTEAM", onTeamId=10, waiverProcessDate=None)
    assert "−Karl Abgang (WR DAL; jetzt SGK; OUT; Proj 0.00; ROS/Sp 4.21) [App]" in text(kona=geholt)


def test_bewegter_spieler_mit_ist_statt_projektion():
    daten = liga()
    daten["transactions"][0]["items"] = [{"type": "ADD", "playerId": -16015}]
    assert "+Testabwehr Zwei D/ST (D/ST MIA; Ist 4.00)" in cs.bericht(JETZT, daten, scoreboard(), app(), kona())


# ---------------------------------------------------------------- Ausfälle

def test_ausfall_scoreboard():
    ausgabe = text(scoreboard=None, ausfall={"scoreboard": "HTTP 503"})
    assert ("NFL-Scoreboard nicht erreichbar (HTTP 503) – Spielstatus, Gegner und Anstoßzeiten fehlen; gesperrt/offen "
            "je Spieler stammt aus dem ESPN-Kader (lineupLocked)") in ausgabe
    assert "| Starter gesperrt/offen" in ausgabe and "| 1/1  –  HJS (5-1) 29.01 | 61.50 | 66 % | 2/3" in ausgabe
    assert "  QB   Quentin Erfunden KC gesperrt | 21.35 | 20.00 | F 1.050" in ausgabe
    assert "  RB   Rudi Beispiel SF offen | – | 15.33 | F 0.947" in ausgabe
    assert "→ mehr Proj als Starter Willi Muster (WR 0.00)" in ausgabe and "nicht auswertbar" not in ausgabe
    assert "  Bank Testabwehr Zwei D/ST MIA gesperrt | 4.00 | 5.00" in ausgabe and "MESZ: DAL@PHI" not in ausgabe


def test_scoreboard_einer_anderen_woche_gilt_als_ausfall():
    ausgabe = text(scoreboard=scoreboard(WOCHE - 1))
    assert "NFL-Scoreboard nicht erreichbar (zeigt Woche 6 statt 7)" in ausgabe and "final: KC@DEN" not in ausgabe
    vorsaison = scoreboard()
    vorsaison["season"]["type"] = 1
    assert not cs.scoreboard_passt(vorsaison, WOCHE) and cs.scoreboard_passt(scoreboard(), WOCHE)
    assert not cs.scoreboard_passt(None, WOCHE) and not cs.scoreboard_passt({}, WOCHE)


def test_ausfall_claude_json():
    ausgabe = text(app=None, ausfall={"app": "HTTP 404, ConnectionError"})
    zeilen = ausgabe.split("\n")
    assert zeilen[1] == ("App: claude.json nicht erreichbar (HTTP 404, ConnectionError) – Datenstand der App, F, ROS/Sp, "
                         "Marken [App]/[NEU] und Kadervergleich fehlen")
    assert zeilen[2] == "Alle Zeiten deutsche Zeit. Punkte, Projektion (Proj) und Siegchance: ESPN live."
    for fehlt in ("[App]", "[NEU", "Kader live", "| F", "ROS/Sp 9.88", "neuer als die App"):
        assert fehlt not in "\n".join(zeilen[3:])
    assert " *SGK (2-4) 9.00" in ausgabe                               # Kürzel kommen nicht aus claude.json
    assert "  Mi 21.10. 10:16 MESZ HJS Free Agent: +Bodo Bank (WR SF; Proj 12.50) −Karl Abgang (WR DAL; " in ausgabe
    assert "  QB   Quentin Erfunden KC @ DEN final | 21.35 | 20.00" in zeilen


def test_app_meint_eine_andere_woche():
    ausgabe = text(app=app(matchup_woche=WOCHE + 1))
    assert "; F fehlt, die App rechnet das Positions-Matchup für Woche 8." in ausgabe
    assert "| F" not in ausgabe and "ROS/Sp 9.88" in ausgabe
    spaet = app()
    spaet["stand"].update(pool_stand=None, pool_woche=None)
    assert "App: gerechnet bis Woche 6; ohne Tagesstand; letzter Move" in text(app=spaet)


def test_claude_json_in_unerwarteter_form_zaehlt_als_ausfall():
    kaputt = app()
    kaputt["kader"]["HJS"] = [None]                                   # erfundener Formatbruch
    zeilen = text(app=kaputt).split("\n")
    assert zeilen[1].startswith("App: claude.json nicht erreichbar (nicht lesbar, TypeError: ")
    assert "[App]" not in "\n".join(zeilen[2:]) and "nicht auswertbar" not in "\n".join(zeilen)
    assert "  QB   Quentin Erfunden KC @ DEN final | 21.35 | 20.00" in zeilen


def test_ausfall_kona():
    ausgabe = text(kona=None, ausfall={"kona": "ReadTimeout"})
    assert ("  Spieler-Abruf (kona) nicht erreichbar (ReadTimeout) – Spieler ohne Kader nur mit Namen laut App bzw. ID, "
            "ohne Waiver-Status") in ausgabe
    assert "−Karl Abgang (WR DAL; Proj laut App 1.50; ROS/Sp 4.21) [App]" in ausgabe
    assert "−Spieler 9001 (? ?)" in text(kona=None, app=None)
    daten = liga()
    daten["transactions"] = daten["transactions"][1:]                 # kein Spieler ohne Kader: kein Abruf, keine Zeile
    assert "kona" not in cs.bericht(JETZT, daten, scoreboard(), app(), None)


def test_ausfall_liga():
    ausgabe = text(liga=None, ausfall={"liga": "HTTP 503, HTTP 503"})
    zeilen = ausgabe.split("\n")
    assert zeilen[0] == "STAND Fr 23.10.2026 14:00 MESZ (12:00 UTC, Uhr des Containers; ESPN-Serverzeit weicht +2 s ab)"
    assert zeilen[1].startswith("App: gerechnet bis Woche 6;")
    assert zeilen[-1] == ("ESPN-Liga nicht erreichbar (HTTP 503, HTTP 503) – Matchups, Aufstellungen und Bewegungen "
                          "fehlen. Kein Live-Stand; in ein paar Minuten noch einmal aufrufen.")
    assert "ESPN-Liga nicht erreichbar (Antwort ohne teams, schedule)" in text(liga={"scoringPeriodId": 7})
    assert "ESPN-Liga nicht erreichbar (kein Abruf)" in cs.bericht(JETZT, None)


def test_kaputter_abschnitt_wird_eine_zeile():
    daten = liga()
    daten["schedule"][1]["home"] = "kaputt"                           # erfundener Formatbruch in einem Matchup
    ausgabe = cs.bericht(JETZT, daten, scoreboard(), app(), kona())
    assert "Matchups: nicht auswertbar (" in ausgabe and "bitte in Claude Code melden" in ausgabe
    assert "NFL W7: 1 final" in ausgabe and "BEWEGUNGEN Periode 7" in ausgabe and "Traceback" not in ausgabe


# ---------------------------------------------------------------- keine Manager-Daten

def test_kein_manager_name_im_text():
    """Der erfundene Manager steht in members, owners und memberId der Liga-Antwort – nie im Text."""
    roh = json.dumps(liga())
    assert all(teil in roh for teil in MANAGER)
    for ausgabe in (text(), text(app=None), text(scoreboard=None), text(kona=None), text(mein_team=10)):
        assert not any(teil in ausgabe for teil in MANAGER)
    sauber = cs.ohne_personen(liga())
    assert not any(teil in json.dumps(sauber) for teil in MANAGER)
    assert "members" not in sauber and all("owners" not in t and "primaryOwner" not in t for t in sauber["teams"])
    assert cs.bericht(JETZT, sauber, scoreboard(), app(), kona(), abweichung=2.4) == text()


# ---------------------------------------------------------------- Aufruf und Argumente

@pytest.mark.parametrize("argv, erwartet", [
    (["claude_stand.py"], 2), (["claude_stand.py", "10"], 10), (["-", "3"], 3), (["-c"], 2), (["-c", "7"], 7),
    (["ipykernel_launcher.py", "-f", "/erfunden/kernel-123.json"], 2), (["x", "--port", "8"], 2), (["x", "11"], 2),
    (["x", "0"], 2), (["x", "-3"], 2), (["x", "2.0"], 2), (["x", "abc"], 2), (["x", ""], 2), ([], 2), (None, 2),
    (["x", 5], 2)])
def test_team_aus_args_ignoriert_fremdes(argv, erwartet):
    assert cs.team_aus_args(argv) == erwartet


def test_messzeile():
    messung = [{"name": "ESPN-Liga", "kb": 4514.934, "s": 2.5949, "fehler": None},
               {"name": "Scoreboard", "kb": 0, "s": 15.0, "fehler": "ReadTimeout"}]
    assert cs.messzeile(messung, 15.125, 4728) == ("Messung: ESPN-Liga 4515 KB 2.59 s · Scoreboard 0 KB 15.00 s "
                                                   "[ReadTimeout] · gesamt 15.13 s · 4728 Zeichen")


# ---------------------------------------------------------------- Abruf mit Fake-Netz

class FakeAntwort:
    def __init__(self, daten=None, status: int = 200, datum="Fri, 23 Oct 2026 12:00:00 GMT"):
        self.status_code = status
        self.content = json.dumps(daten).encode("utf-8") if daten is not None else b"<html>kaputt</html>"
        self.headers = {"Date": datum} if datum else {}

    def json(self):
        return json.loads(self.content)


class FakeNetz:
    """Ersetzt requests.get: antwortet je Quelle (liga, kona, scoreboard, app_raw, app_pages) mit einer FakeAntwort,
    wirft eine hinterlegte Ausnahme oder ruft eine hinterlegte Funktion; merkt sich jede Anfrage."""

    def __init__(self, **antworten):
        self.antworten = {"liga": FakeAntwort(liga()), "kona": FakeAntwort(kona()), "scoreboard": FakeAntwort(scoreboard()),
                          "app_raw": FakeAntwort(app()), "app_pages": FakeAntwort(app())}
        self.antworten.update(antworten)
        self.anfragen = []

    def get(self, url, params=None, headers=None, timeout=None):
        if url == cs.SCOREBOARD_URL:
            quelle = "scoreboard"
        elif url == cs.LIGA_URL:
            quelle = "kona" if params == {"view": cs.KONA_VIEW} else "liga"
        else:
            quelle = {cs.APP_URLS[0]: "app_raw", cs.APP_URLS[1]: "app_pages"}[url]
        self.anfragen.append({"quelle": quelle, "params": params, "headers": headers, "timeout": timeout})
        antwort = self.antworten[quelle]
        if isinstance(antwort, Exception):
            raise antwort
        return antwort(params) if callable(antwort) else antwort

    def zahl(self, quelle) -> int:
        return sum(a["quelle"] == quelle for a in self.anfragen)


@pytest.fixture
def netz(monkeypatch):
    def bauen(**antworten) -> FakeNetz:
        fake = FakeNetz(**antworten)
        monkeypatch.setattr(cs, "requests", fake)
        return fake
    return bauen


def test_abrufen_alles_da(netz):
    fake = netz()
    roh = cs.abrufen()
    assert roh["ausfall"] == {} and [m["name"] for m in roh["messung"]] == [
        "ESPN-Liga", "Scoreboard", "claude.json", "Kona (1 Spieler ohne Kader)"]
    assert roh["liga"]["scoringPeriodId"] == WOCHE and not any(teil in json.dumps(roh["liga"]) for teil in MANAGER)
    assert roh["kona"] == kona() and roh["app"] == app() and roh["scoreboard"] == scoreboard()
    assert -5 < roh["abweichung"] - (datetime(2026, 10, 23, 12, tzinfo=UTC) - datetime.now(UTC)).total_seconds() < 5
    assert {q: fake.zahl(q) for q in fake.antworten} == {"liga": 1, "kona": 1, "scoreboard": 1, "app_raw": 1, "app_pages": 0}
    liga_anfrage = next(a for a in fake.anfragen if a["quelle"] == "liga")
    assert liga_anfrage["params"] == [("view", v) for v in ("mMatchupScore", "mRoster", "mTeam", "mTransactions2")]
    assert all(a["timeout"] == (cs.VERBINDEN, cs.LESEN) for a in fake.anfragen)
    filt = json.loads(next(a for a in fake.anfragen if a["quelle"] == "kona")["headers"]["X-Fantasy-Filter"])["players"]
    assert filt["filterIds"] == {"value": [9001]} and filt["sortPercOwned"] == {"sortPriority": 1, "sortAsc": False}
    assert filt["filterStatsForCurrentSeasonScoringPeriodId"] == {"value": [WOCHE]}   # ohne sortPercOwned: HTTP 400
    assert cs.bericht(JETZT, roh["liga"], roh["scoreboard"], roh["app"], roh["kona"], abweichung=2.4) == text()


def test_abrufen_claude_json_ausweichadresse(netz):
    fake = netz(app_raw=FakeAntwort(status=404))
    roh = cs.abrufen()
    assert roh["app"] == app() and "app" not in roh["ausfall"] and (fake.zahl("app_raw"), fake.zahl("app_pages")) == (1, 1)
    fake = netz(app_raw=requests.ConnectionError("erfunden"), app_pages=FakeAntwort())  # zweite Adresse: kein JSON
    roh = cs.abrufen()
    assert roh["app"] is None and roh["ausfall"] == {"app": "ConnectionError, JSONDecodeError"}
    assert "App: claude.json nicht erreichbar (ConnectionError, JSONDecodeError)" in cs.bericht(
        JETZT, roh["liga"], roh["scoreboard"], roh["app"], roh["kona"], ausfall=roh["ausfall"])


def test_abrufen_scoreboard_der_liga_woche_wird_nachgeholt(netz):
    """Das Scoreboard steht ohne Angabe auf einer anderen Woche: zweiter Abruf mit Woche und Saison der Liga."""
    fake = netz(scoreboard=lambda params: FakeAntwort(scoreboard(WOCHE if params else WOCHE - 1)))
    roh = cs.abrufen()
    assert cs.scoreboard_passt(roh["scoreboard"], WOCHE) and roh["ausfall"] == {}
    assert [a["params"] for a in fake.anfragen if a["quelle"] == "scoreboard"] == [
        None, {"seasontype": 2, "week": WOCHE, "dates": 2026}]
    assert [m["name"] for m in roh["messung"]][-2:] == ["Scoreboard W7", "Kona (1 Spieler ohne Kader)"]


def test_abrufen_scoreboard_und_kona_fallen_aus(netz):
    fake = netz(scoreboard=requests.Timeout("erfunden"), kona=FakeAntwort(status=400))
    roh = cs.abrufen()
    assert roh["scoreboard"] is None and roh["kona"] is None and fake.zahl("scoreboard") == 2
    assert roh["ausfall"] == {"scoreboard": "Timeout", "kona": "HTTP 400"}
    ausgabe = cs.bericht(JETZT, roh["liga"], roh["scoreboard"], roh["app"], roh["kona"], ausfall=roh["ausfall"])
    assert "NFL-Scoreboard nicht erreichbar (Timeout)" in ausgabe and "(kona) nicht erreichbar (HTTP 400)" in ausgabe


@pytest.mark.parametrize("antwort, grund", [
    (FakeAntwort(status=503), "HTTP 503, HTTP 503"), (requests.ConnectionError("erfunden"), "ConnectionError, ConnectionError"),
    (FakeAntwort({"messages": ["erfunden"]}), "Antwort ohne scoringPeriodId, teams, schedule"),
    (FakeAntwort([1, 2]), "kein JSON-Objekt, kein JSON-Objekt")])
def test_main_ohne_liga_endet_mit_meldung(netz, capsys, antwort, grund):
    fake = netz(liga=antwort)
    assert cs.main(["claude_stand.py"]) is None                       # kein sys.exit, keine Ausnahme: Exit-Code 0
    aus = capsys.readouterr()
    assert f"ESPN-Liga nicht erreichbar ({grund}) – " in aus.out and "Traceback" not in aus.out + aus.err
    assert aus.out.rstrip().split("\n")[-1].startswith("Messung: ESPN-Liga ")
    assert fake.zahl("kona") == 0 and fake.zahl("scoreboard") == 1    # ohne Liga keine Nachabrufe


def test_main_druckt_bericht_und_messung(netz, capsys):
    netz()
    cs.main(["-", "10"])
    zeilen = capsys.readouterr().out.rstrip("\n").split("\n")
    assert zeilen[0].startswith("STAND ") and " – ESPN Woche 7" in zeilen[0]
    assert zeilen.index("SGK Testteam Zehn – Slot Spieler NFL Spiel | Punkte | Proj | F") \
        < zeilen.index("HJS Testteam Zwei – Slot Spieler NFL Spiel | Punkte | Proj | F")
    assert zeilen[-2] == "" and zeilen[-1].startswith("Messung: ESPN-Liga ") and " · gesamt " in zeilen[-1]
    assert zeilen[-1].endswith(f" · {len(chr(10).join(zeilen[:-2]))} Zeichen")
    assert not any(teil in "\n".join(zeilen) for teil in MANAGER)


def test_main_faengt_unerwartete_fehler(netz, capsys, monkeypatch):
    netz()
    monkeypatch.setattr(cs, "abrufen", lambda: 1 / 0)
    cs.main(["-c"])
    aus = capsys.readouterr().out
    assert aus.startswith("Stand-Skript: unerwarteter Fehler (ZeroDivisionError: division by zero) – kein Stand")
    monkeypatch.setattr(cs, "requests", None)                          # requests nicht installiert
    cs.main(["-c"])
    assert "Das Paket requests fehlt" in capsys.readouterr().out


def test_hole_wirft_nie_und_parallel_haelt_die_frist(netz):
    netz(scoreboard=lambda params: time.sleep(1.0) or FakeAntwort(scoreboard()))
    start = time.perf_counter()
    runde = cs.parallel({"sb": ("Scoreboard", [cs.SCOREBOARD_URL]), "app": ("claude.json", list(cs.APP_URLS))}, 0.2)
    assert time.perf_counter() - start < 0.9
    assert runde["sb"]["daten"] is None and runde["sb"]["fehler"] == "keine Antwort nach 0.2 s"
    assert runde["app"]["daten"] == app() and runde["app"]["fehler"] is None and runde["app"]["kb"] > 0
    ohne_datum = cs.hole("claude.json", [cs.APP_URLS[1]])              # Fake ohne Scoreboard-Verzögerung
    assert ohne_datum["daten"] is not None and ohne_datum["abweichung"] is not None
    assert cs.hole("leer", [])["fehler"] == "keine Adresse"


def test_lauf_ueber_exec_wie_im_chat(monkeypatch, capsys):
    """Aufruf „python3 -c "import requests; exec(requests.get(…).text)"“: Quelltext per exec im Namensraum __main__,
    sys.argv ist ['-c']; das Skript importiert requests dann selbst, deshalb steht der Fake an requests.get."""
    fake = FakeNetz()
    monkeypatch.setattr(requests, "get", fake.get)
    monkeypatch.setattr(sys, "argv", ["-c"])
    quelle = Path(cs.__file__).read_text(encoding="utf-8")
    exec(compile(quelle, "<string>", "exec"), {"__name__": "__main__"})
    zeilen = capsys.readouterr().out.rstrip("\n").split("\n")
    assert zeilen[0].startswith("STAND ") and "HJS Testteam Zwei – Slot Spieler NFL Spiel | Punkte | Proj | F" in zeilen
    assert zeilen[-1].startswith("Messung: ") and fake.zahl("liga") == 1
