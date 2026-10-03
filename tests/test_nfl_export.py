"""Tests Import der nfl.com-DSGVO-Auskunft (scripts/nfl_export.py) an erfundenen Daten.

Der echte Export liegt nicht im Repo (Datenschutz); alle Werte hier sind erfunden und nur so gewählt, dass sie eine
Regel des Imports auslösen. Die abgeleiteten Dateien prüft tests/test_history_wochen.py.
Aufruf: python -m pytest
"""

import csv
from decimal import Decimal

import pytest

import nfl_export as nx


def write(folder, name, header, rows):
    with open(folder / name, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


# ---------------------------------------------------------------- Lesen

def test_nur_spalten_der_positivliste(tmp_path):
    """Erfundene Zeile mit Mail und Nutzer-ID: Zurück kommen nur die Spalten der Positivliste."""
    columns = nx.DATEIEN["teams"][1]
    header = ["email", "owner_user_id", *columns]
    row = ["x@example.invalid", "abc", *["1"] * len(columns)]
    write(tmp_path, "nfl_fantasy_league_team_20990101.csv", header, [row])
    got = nx.read_export(tmp_path, "teams")
    assert [list(r) for r in got] == [list(columns)]


def test_fehlende_spalte_bricht_ab(tmp_path):
    write(tmp_path, "nfl_fantasy_league_20990101.csv", ["game_id", "league_id"], [["102099", "1"]])
    with pytest.raises(nx.ImportFehler, match="Spalten fehlen"):
        nx.read_export(tmp_path, "liga")


def test_praefixe_trennen_die_dateien(tmp_path):
    for name in ("nfl_fantasy_league_20990101.csv", "nfl_fantasy_league_team_20990101.csv",
                 "nfl_fantasy_league_team_players_20990101.csv", "nfl_fantasy_league_team_week_stats_20990101.csv"):
        (tmp_path / name).write_text("a\n", encoding="utf-8")
    assert nx.export_file(tmp_path, "nfl_fantasy_league_").name == "nfl_fantasy_league_20990101.csv"
    assert nx.export_file(tmp_path, "nfl_fantasy_league_team_").name == "nfl_fantasy_league_team_20990101.csv"
    assert nx.export_file(tmp_path, "nfl_fantasy_league_team_week_stats_").name.endswith("week_stats_20990101.csv")


def test_nur_eine_liga():
    nx.one_league([{"league_id": "7"}], [{"league_id": "7"}])
    with pytest.raises(nx.ImportFehler, match="mehr als einer Liga"):
        nx.one_league([{"league_id": "7"}], [{"league_id": "8"}])


def test_punkte_mit_mehr_als_zwei_stellen_brechen_ab():
    assert nx.points("12.5") == Decimal("12.5")
    with pytest.raises(nx.ImportFehler):
        nx.points("12.345")


# ---------------------------------------------------------------- Versionen und Zeitzonen

def v(ts, pts):
    return {"updated_ts": ts, "pts": pts}


def test_letzte_version_gilt():
    """Erfundene Live-Stände und eine Stat-Korrektur einen Tag später: Es gilt die jüngste Version."""
    versions = [v("2099-12-27T00:00:00", "60.00"), v("2099-12-27T02:00:00", "90.00"),
                v("2099-12-28T00:00:00", "200.10"), v("2099-12-31T00:00:00", "200.00")]
    assert nx.latest(versions, lambda r: r["pts"])["pts"] == "200.00"


def test_zu_dichte_versionen_brechen_ab():
    """Zwei verschiedene Stände unter 9 h: wegen gemischter Zeitzonen (Versatz bis 8 h) wäre die Reihenfolge unsicher."""
    for later in ("2099-12-28T06:00:00", "2099-12-28T08:30:00"):
        with pytest.raises(nx.ImportFehler, match="zu dicht"):
            nx.latest([v("2099-12-28T00:00:00", "200.10"), v(later, "200.00")], lambda r: r["pts"])
    assert nx.latest([v("2099-12-28T00:00:00", "200.10"), v("2099-12-28T09:00:00", "200.00")],
                     lambda r: r["pts"])["pts"] == "200.00"
    # gleiche Werte dicht beieinander sind harmlos
    assert nx.latest([v("2099-12-28T00:00:00", "1.00"), v("2099-12-28T01:00:00", "1.00")], lambda r: r["pts"])


# ---------------------------------------------------------------- Regular Season

def test_paarung_aus_punkten_gegen():
    """Erfundene Woche mit vier Teams: Gegner = das Team mit genau den Punkten gegen."""
    weeks = [{"season": 2099, "week": 1, "phase": nx.RS, "slot": s, "pts": Decimal(p), "result": r}
             for s, p, r in ((1, "100.00", "W"), (2, "90.00", "L"), (3, "80.00", "L"), (4, "120.00", "W"))]
    latest_rows = {(2099, s, 1): {"total_pts_against": pa} for s, pa in ((1, "90.00"), (2, "100.00"),
                                                                         (3, "120.00"), (4, "80.00"))}
    games = nx.rs_games(latest_rows, weeks)
    assert [(g["slot_a"], g["slot_b"]) for g in games] == [(1, 2), (4, 3)]
    latest_rows[(2099, 3, 1)] = {"total_pts_against": "121.00"}
    with pytest.raises(nx.ImportFehler, match="nicht eindeutig"):
        nx.rs_games(latest_rows, weeks)


# ---------------------------------------------------------------- Playoffs

FMT = {"po_teams": 6, "po_start": 15, "po_end": 17}


def saison(places: dict[int, int], byes: set[int]) -> list[dict]:
    """Erfundene Team-Saisons: Endplatz je Slot, Divisionssieger = byes; Bilanz fällt mit dem Endplatz, damit die
    Seeds den Slots entsprechen (1–2 Bye, 3–6 nach W)."""
    return [{"season": "2099", "slot": str(s), "playoffs": "1" if p <= 6 else "0",
             "div_rank": "1" if s in byes else "2", "final_rank": str(p), "w": str(14 - p), "pf": str(3000 - p)}
            for s, p in places.items()]


def wochen(pts: dict[tuple[int, int], str]) -> list[dict]:
    return [{"season": 2099, "week": w, "slot": s, "pts": Decimal(p)} for (w, s), p in pts.items()]


PLACES = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10}
BYES = {1, 2}
# Runde 1: Sieger 3, 4 gegen Verlierer 5, 6; Halbfinale: 1, 2 gegen 3, 4; Finalwoche nach Endplatz
FINALWOCHE = {(17, 1): "150", (17, 2): "140", (17, 3): "130", (17, 4): "120", (17, 5): "110", (17, 6): "100"}


# Seeds der erfundenen Saison: 1–2 Bye, 3–6 nach W → Seed-Regel: Runde 1 3–6 und 4–5, Halbfinale 1–4 und 2–3
EINDEUTIG = {(15, 3): "200", (15, 6): "130", (15, 4): "120", (15, 5): "100",      # nur 3–6/4–5 passt (4 < 6)
             (16, 1): "150", (16, 4): "140", (16, 2): "135", (16, 3): "100", **FINALWOCHE}   # nur 1–4/2–3 (2 < 4)
MEHRDEUTIG = {(15, 3): "200", (15, 4): "190", (15, 5): "130", (15, 6): "100",
              (16, 1): "200", (16, 2): "190", (16, 3): "130", (16, 4): "100", **FINALWOCHE}


def rounds(games):
    return [(g["round"], g["slot_a"], g["slot_b"], g["herleitung"]) for g in games]


def test_bracket_eindeutig_aus_punkten():
    """Erfunden: Die Punkte lassen je Runde nur eine Paarung zu, und sie ist die der Seed-Regel."""
    assert rounds(nx.playoff_games(2099, FMT, wochen(EINDEUTIG), saison(PLACES, BYES), [])) == [
        ("Quarterfinal", 3, 6, "Bracket"), ("Quarterfinal", 4, 5, "Bracket"),
        ("Semifinal", 1, 4, "Bracket"), ("Semifinal", 2, 3, "Bracket"),
        ("Final", 1, 2, "Endplatz"), ("Spiel um Platz 3", 3, 4, "Endplatz"), ("Spiel um Platz 5", 5, 6, "Endplatz")]


def test_mehrdeutig_loest_die_seed_regel_oder_ein_screenshot():
    """Erfunden: Beide Paarungen passen zu den Punkten → die Seed-Regel entscheidet; ein Screenshot geht vor."""
    got = rounds(nx.playoff_games(2099, FMT, wochen(MEHRDEUTIG), saison(PLACES, BYES), []))
    assert got[:4] == [("Quarterfinal", 3, 6, "Seed-Regel"), ("Quarterfinal", 4, 5, "Seed-Regel"),
                       ("Semifinal", 1, 4, "Seed-Regel"), ("Semifinal", 2, 3, "Seed-Regel")]
    shot = [{"season": "2099", "week": "16", "slot_a": "4", "slot_b": "1"}]
    got = rounds(nx.playoff_games(2099, FMT, wochen(MEHRDEUTIG), saison(PLACES, BYES), shot))
    assert got[2:4] == [("Semifinal", 1, 4, "Screenshot"), ("Semifinal", 2, 3, "Screenshot")]


def test_widerspruch_zur_seed_regel_bricht_ab():
    """Erfunden: Ein Screenshot (oder die Punkte) legt eine Paarung fest, die der Seed-Regel widerspricht."""
    shot = [{"season": "2099", "week": "16", "slot_a": "1", "slot_b": "3"}]
    with pytest.raises(nx.ImportFehler, match="widerspricht"):
        nx.playoff_games(2099, FMT, wochen(MEHRDEUTIG), saison(PLACES, BYES), shot)


def test_halbfinale_von_hand(monkeypatch):
    """Erfunden: Ist das Halbfinale der Saison als „von Hand neu gepaart“ geführt, muss es von der Regel abweichen."""
    monkeypatch.setattr(nx, "HALBFINALE_VON_HAND", {2099})
    shot = [{"season": "2099", "week": "16", "slot_a": "1", "slot_b": "3"}]
    got = rounds(nx.playoff_games(2099, FMT, wochen(MEHRDEUTIG), saison(PLACES, BYES), shot))
    assert got[2:4] == [("Semifinal", 1, 3, "Screenshot"), ("Semifinal", 2, 4, "Screenshot")]
    with pytest.raises(nx.ImportFehler, match="trifft"):
        nx.playoff_games(2099, FMT, wochen(EINDEUTIG), saison(PLACES, BYES), [])


def test_seed_regel_ohne_neusetzen_mit_ueberraschungen():
    """Erfunden: Seed 5 und 6 gewinnen Runde 1, die W-Reihenfolge weicht von Slot und Endplatz ab, und Slot 3 und 4
    (beide 8 W) trennt erst PF: Slot 4 wird Seed 3, Slot 3 Seed 4 – dadurch heißt Runde 1 4–6 und 3–5 (nach Slot
    sortiert wäre es 3–6 und 4–5). Ohne Neusetzen spielt Seed 1 gegen den Sieger aus 4–5 (Slot 5), Seed 2 gegen den aus
    3–6 (Slot 6); neu gesetzt hieße es 1 gegen Slot 6 – das schließen die Endplätze aus (Slot 1 und 6 im Finale)."""
    plaetze = {1: 1, 6: 2, 2: 3, 5: 4, 3: 5, 4: 6, 7: 7, 8: 8, 9: 9, 10: 10}
    bilanz = {1: ("10", "3000"), 2: ("9", "2900"), 3: ("8", "2700"), 4: ("8", "2800"), 5: ("7", "2650"),
              6: ("5", "2500"), 7: ("4", "2400"), 8: ("3", "2300"), 9: ("2", "2200"), 10: ("1", "2100")}
    rows = [{"season": "2099", "slot": str(s), "playoffs": "1" if p <= 6 else "0", "div_rank": "1" if s in (1, 2) else "2",
             "final_rank": str(p), "w": bilanz[s][0], "pf": bilanz[s][1]} for s, p in plaetze.items()]
    pts = {(15, 6): "200", (15, 5): "190", (15, 3): "150", (15, 4): "140",          # beide Paarungen passen
           (16, 1): "180", (16, 5): "170", (16, 6): "175", (16, 2): "160",
           (17, 1): "150", (17, 6): "140", (17, 2): "130", (17, 5): "120", (17, 3): "110", (17, 4): "100"}
    assert nx.seeds([1, 2, 3, 4, 5, 6], {int(r["slot"]): r for r in rows}) == [1, 2, 4, 3, 5, 6]
    assert rounds(nx.playoff_games(2099, FMT, wochen(pts), rows, []))[:4] == [
        ("Quarterfinal", 5, 3, "Seed-Regel"), ("Quarterfinal", 6, 4, "Seed-Regel"),
        ("Semifinal", 1, 5, "Bracket"), ("Semifinal", 6, 2, "Bracket")]


def test_bestaetigte_paarung_entscheidet(monkeypatch):
    """Erfunden: Eine bestätigte Paarung wirkt wie ein Screenshot; eine, die nicht zur Runde passt, bricht ab."""
    monkeypatch.setattr(nx, "BESTAETIGT", {(2099, 16): {frozenset((1, 4))}})
    got = rounds(nx.playoff_games(2099, FMT, wochen(MEHRDEUTIG), saison(PLACES, BYES), []))
    assert got[2:4] == [("Semifinal", 1, 4, "Bestätigt"), ("Semifinal", 2, 3, "Bestätigt")]
    monkeypatch.setattr(nx, "BESTAETIGT", {(2099, 16): {frozenset((1, 9))}})
    with pytest.raises(nx.ImportFehler, match="bestätigte Paarung"):
        nx.playoff_games(2099, FMT, wochen(MEHRDEUTIG), saison(PLACES, BYES), [])


def test_bestaetigung_ausserhalb_der_runden_bricht_ab(monkeypatch):
    """Erfunden: Eine Bestätigung für die Finalwoche oder eine Saison ohne Export würde nie gelesen → Abbruch."""
    fmts = {2099: {"po_start": 15}}
    for key in ((2099, 17), (2098, 16)):
        monkeypatch.setattr(nx, "BESTAETIGT", {key: {frozenset((1, 4))}})
        with pytest.raises(nx.ImportFehler, match="nicht in Runde 1 oder Halbfinale"):
            nx.check_confirmed(fmts)
    monkeypatch.setattr(nx, "BESTAETIGT", {(2099, 16): {frozenset((1, 4))}})
    nx.check_confirmed(fmts)


def test_seeds_gleichstand_bricht_ab():
    rows = saison(PLACES, BYES)
    for r in rows:
        if r["slot"] in ("5", "6"):
            r.update(w="5", pf="2000")
    with pytest.raises(nx.ImportFehler, match="Gleichstand"):
        nx.seeds([1, 2, 3, 4, 5, 6], {int(r["slot"]): r for r in rows})


def test_widerspruch_zum_screenshot_bricht_ab():
    shot = [{"season": "2099", "week": "15", "slot_a": "3", "slot_b": "5"}]   # passt nicht zu den Punkten
    with pytest.raises(nx.ImportFehler, match="keine Paarung"):
        nx.playoff_games(2099, FMT, wochen(EINDEUTIG), saison(PLACES, BYES), shot)


def test_finalwoche_muss_zum_endplatz_passen():
    with pytest.raises(nx.ImportFehler, match="Final"):
        nx.playoff_games(2099, FMT, wochen({**EINDEUTIG, (17, 2): "160"}), saison(PLACES, BYES), [])


def spiel(season, week, a, b, winner):
    return {"season": season, "week": week, "slot_a": a, "slot_b": b, "winner_slot": winner}


def test_screenshot_muss_unter_den_spielen_stehen():
    """Erfunden: Ein Screenshot-Spiel, das fehlt oder einen anderen Sieger hat, bricht den Import ab."""
    games = [spiel(2019, 15, 2, 3, 2)]
    shot = {"season": "2019", "week": "15", "slot_a": "3", "slot_b": "2", "winner_slot": "2"}
    nx.check_screenshots(games, [shot])
    with pytest.raises(nx.ImportFehler, match="Screenshot-Spiel"):
        nx.check_screenshots(games, [dict(shot, winner_slot="3")])
    with pytest.raises(nx.ImportFehler, match="Screenshot-Spiel"):
        nx.check_screenshots(games, [dict(shot, slot_b="4")])
    nx.check_screenshots([], [dict(shot, season="2024")])        # außerhalb 2018–2022 nicht geprüft


def test_unbekannter_schalter_schreibt_nicht(tmp_path):
    """Ein vertippter Schalter bricht ab, statt die Dateien zu schreiben."""
    with pytest.raises(SystemExit) as stop:
        nx.main([str(tmp_path), "--chek"])
    assert stop.value.code == 2


# ---------------------------------------------------------------- Hugh Jass

def snap(ts, w, l, pts, pa):
    return {"game_id": "102099", "team_id": "1", "wins": str(w), "losses": str(l), "ties": "0",
            "pts": pts, "pts_against": pa, "updated_ts": ts}


def test_hugh_jass_differenzen_mit_korrektur():
    """Erfundene Snapshots einer Saison mit 2 Spielen; die Korrektur am Tag nach Spiel 2 zählt in Woche 2."""
    snaps = [snap("2099-09-10T00:00:00", 1, 0, "100.00", "90.00"), snap("2099-09-12T00:00:00", 1, 0, "100.00", "90.00"),
             snap("2099-09-17T00:00:00", 1, 1, "180.00", "200.00"), snap("2099-09-18T00:00:00", 1, 1, "179.00", "200.00")]
    ts = [{"season": "2099", "slot": "2", "w": "1", "l": "1", "pf": "179.00", "pa": "200.00"}]
    got = nx.hugh_jass(snaps, ts, {2099: 2}, seasons=(2099,))
    assert [(r["week"], r["pts"], r["pts_against"], r["result"]) for r in got] == [
        (1, Decimal("100.00"), Decimal("90.00"), "W"), (2, Decimal("79.00"), Decimal("110.00"), "L")]
