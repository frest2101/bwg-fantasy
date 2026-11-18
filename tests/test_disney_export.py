"""Tests Import der Disney-DSGVO-Auskunft (scripts/disney_export.py) an erfundenen Daten.

Die echte Auskunft liegt nicht im Repo (Datenschutz); alle Punktwerte und Teamnamen hier sind erfunden und nur so
gewählt, dass sie eine Regel des Imports auslösen (echt sind nur Liga- und Teamname des Filters und die Saisons, an
denen eine Regel hängt). Die abgeleiteten Dateien prüft tests/test_history_wochen.py.
Aufruf: python -m pytest
"""

import csv
import io
import zipfile
from decimal import Decimal

import pytest

import disney_export as dx

KOPF = ["Season", "League", "Team", "Week", "Points", "Adjusted points", "Bench points", "Result", "Opponent", "Rank",
        "Record W-L-T", "Season points for", "Season points against", "Streak", "Coach points"]


def csv_text(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=KOPF)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in KOPF})
    return out.getvalue()


def zeile(week, pts, result, record, pa_cum, opponent="not in export", league="BWG Fantasy", team="Hugh Jass",
          season=2099, bench="10.00"):
    return {"Season": str(season), "League": league, "Team": team, "Week": str(week), "Points": pts,
            "Adjusted points": "1.00", "Bench points": bench, "Result": result, "Opponent": opponent, "Rank": "1",
            "Record W-L-T": record, "Season points for": "999.00", "Season points against": pa_cum, "Streak": "W1",
            "Coach points": "5"}


def po(week, pts="", bench=""):
    return zeile(week, pts, "no regular-season game", "--", "", bench=bench)


# ---------------------------------------------------------------- Lesen

def test_liest_nur_weekly_scores_unter_nfl_aus_dem_zip(tmp_path):
    """Erfundenes ZIP mit Konto-Datei und einer gleichnamigen Datei unter espn/: gelesen wird nur nfl/weekly_scores.csv."""
    path = tmp_path / "auskunft.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("auskunft/nfl/weekly_scores.csv", "﻿Season\n2099\n")
        z.writestr("auskunft/espn/weekly_scores.csv", "falsch\n")
        z.writestr("auskunft/nfl/account.csv", "email\nx@example.invalid\n")
    assert dx.quelltext(path) == "Season\n2099\n"


def test_mehrere_oder_tiefe_treffer_brechen_ab(tmp_path):
    path = tmp_path / "auskunft.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a/nfl/weekly_scores.csv", "x\n")
        z.writestr("b/nfl/weekly_scores.csv", "y\n")
    with pytest.raises(dx.ImportFehler, match="2 Treffer"):
        dx.quelltext(path)
    deep = tmp_path / "tief.zip"
    with zipfile.ZipFile(deep, "w") as z:
        z.writestr("a/b/nfl/weekly_scores.csv", "x\n")
    with pytest.raises(dx.ImportFehler, match="0 Treffer"):
        dx.quelltext(deep)


def test_entpackter_ordner(tmp_path):
    (tmp_path / "auskunft" / "nfl").mkdir(parents=True)
    (tmp_path / "auskunft" / "nfl" / "weekly_scores.csv").write_bytes(b"Season\n")
    assert dx.quelltext(tmp_path) == "Season\n"
    with pytest.raises(dx.ImportFehler, match="weder ZIP noch Ordner"):
        dx.quelltext(tmp_path / "fehlt.zip")


def test_nur_bwg_hugh_jass_und_spalten_der_positivliste():
    """Erfundene Zeilen einer anderen Liga und eines anderen Teams fallen weg; Coach points, Rank, Streak, Adjusted
    points und Season points for werden nicht übernommen."""
    rows = [zeile(1, "100.00", "win", "1-0-0", "90.00"), zeile(1, "1.00", "win", "1-0-0", "1.00", league="Andere Liga"),
            zeile(1, "2.00", "win", "1-0-0", "1.00", team="Anderes Team")]
    got = dx.zeilen(csv_text(rows))
    assert len(got) == 1 and list(got[0]) == list(dx.SPALTEN) and got[0]["Points"] == "100.00"


def test_fehlende_spalte_bricht_ab():
    with pytest.raises(dx.ImportFehler, match="Spalten fehlen: Bench points"):
        dx.zeilen("Season,League,Team,Week,Points\n")


def test_punkte_und_bilanz():
    assert dx.points("12.5") == Decimal("12.5")
    for text in ("12.345", "", "abc"):
        with pytest.raises(dx.ImportFehler):
            dx.points(text)
    assert dx.bilanz("3-1-0") == (3, 1, 0)
    with pytest.raises(dx.ImportFehler):
        dx.bilanz("--")


# ---------------------------------------------------------------- Wochen

NAMES = {(2099, 1): "Team Eins", (2099, 2): "Eigenes Team", (2099, 3): "Team Drei"}


def wochen(rows):
    return {int(r["Week"]): {c: r[c] for c in dx.SPALTEN} for r in rows}


def saison(n_rs=2):
    """Erfundene Saison mit 2 Spielen der Regular Season, drei Playoff-Wochen und einer leeren Woche dahinter."""
    return [zeile(1, "100.00", "win (from record)", "1-0-0", "90.00", opponent="Team Drei"),
            zeile(2, "80.00", "loss", "1-1-0", "200.00"),
            po(3, "70.00", "5.00"), po(4, "60.00", "6.00"), po(5, "50.00", "7.00"), po(6)]


def test_regular_season_und_playoff_wochen():
    got = dx.saison_wochen(2099, wochen(saison()), 2, NAMES)
    assert [(w["week"], w["phase"], w["pts"], w["pts_against"], w["opponent_slot"], w["result"]) for w in got] == [
        (1, "RS", Decimal("100.00"), Decimal("90.00"), 3, "W"), (2, "RS", Decimal("80.00"), Decimal("110.00"), None, "L"),
        (3, "PO", Decimal("70.00"), None, None, None), (4, "PO", Decimal("60.00"), None, None, None),
        (5, "PO", Decimal("50.00"), None, None, None)]
    assert [w["bench_pts"] for w in got] == [Decimal("10.00")] * 2 + [Decimal("5.00"), Decimal("6.00"), Decimal("7.00")]


def test_punkte_nach_der_letzten_playoff_woche_brechen_ab():
    rows = saison()
    rows[-1] = po(6, "1.00", "0.00")
    with pytest.raises(dx.ImportFehler, match="nach der letzten Playoff-Woche"):
        dx.saison_wochen(2099, wochen(rows), 2, NAMES)


def test_fehlende_woche_bricht_ab():
    rows = [r for r in saison() if r["Week"] != "4"]
    with pytest.raises(dx.ImportFehler, match="Wochen fehlen"):
        dx.saison_wochen(2099, wochen(rows), 2, NAMES)


@pytest.mark.parametrize("change, match", [
    ({"Result": "loss (from record)"}, "Result passt nicht"),         # Result widerspricht der Bilanz
    ({"Record W-L-T": "2-0-0"}, "genau ein Spiel"),                   # Bilanz springt um zwei Spiele
    ({"Season points against": "120.00"}, "nicht zu den Punkten"),    # Sieg mit weniger Punkten als der Gegner
    ({"Opponent": "Unbekannt"}, "Gegner"),
    ({"Opponent": "Eigenes Team"}, "Gegner"),                         # gegen sich selbst
])
def test_widersprueche_brechen_ab(change, match):
    rows = saison()
    rows[0] = dict(rows[0], **change)
    with pytest.raises(dx.ImportFehler, match=match):
        dx.saison_wochen(2099, wochen(rows), 2, NAMES)


@pytest.mark.parametrize("change", [{"Record W-L-T": "1-1-0"}, {"Season points against": "300.00"},
                                    {"Result": "win"}, {"Opponent": "Team Eins"}])
def test_playoff_woche_mit_bilanz_oder_gegner_bricht_ab(change):
    rows = saison()
    rows[2] = dict(rows[2], **change)
    with pytest.raises(dx.ImportFehler, match="Playoff-Woche"):
        dx.saison_wochen(2099, wochen(rows), 2, NAMES)


def test_doppelte_woche_und_falsche_saisons_brechen_ab():
    rows = [{c: r[c] for c in dx.SPALTEN} for r in saison()]
    with pytest.raises(dx.ImportFehler, match="doppelt"):
        dx.alle_wochen(rows + rows[:1], {2099: 2}, NAMES)
    with pytest.raises(dx.ImportFehler, match="Saisons"):
        dx.alle_wochen(rows, {2099: 2}, NAMES)                      # nur 2099 statt 2015–2025


# ---------------------------------------------------------------- Prüfungen

def rs(season, week, pts, pa, result, phase="RS"):
    return {"season": season, "week": week, "phase": phase, "pts": Decimal(pts), "bench_pts": Decimal("1.00"),
            "pts_against": Decimal(pa) if pa else None, "result": result}


def test_saison_wie_team_seasons():
    weeks = {2099: [rs(2099, 1, "100.00", "90.00", "W"), rs(2099, 2, "80.00", "110.00", "L"),
                    rs(2099, 3, "500.00", None, None, phase="PO")]}
    ts = [{"season": "2099", "slot": "2", "w": "1", "l": "1", "pf": "180.00", "pa": "200.00"}]
    dx.check_saisons(weeks, ts)                                      # Playoff-Punkte zählen nicht zu PF
    with pytest.raises(dx.ImportFehler, match="team_seasons"):
        dx.check_saisons(weeks, [dict(ts[0], pf="180.01")])
    with pytest.raises(dx.ImportFehler, match="team_seasons"):
        dx.check_saisons(weeks, [dict(ts[0], w="2", l="0")])


def test_saison_mit_abweichender_pa_oder_unentschieden_bricht_ab():
    """Erfundene Werte: nur die PA weicht ab; ein Unentschieden passt nie, weil team_seasons.csv keine Spalte T hat."""
    weeks = {2099: [rs(2099, 1, "100.00", "90.00", "W"), rs(2099, 2, "80.00", "110.00", "L")]}
    ts = [{"season": "2099", "slot": "2", "w": "1", "l": "1", "pf": "180.00", "pa": "200.00"}]
    with pytest.raises(dx.ImportFehler, match="team_seasons"):
        dx.check_saisons(weeks, [dict(ts[0], pa="200.01")])
    tie = {2099: [rs(2099, 1, "100.00", "90.00", "W"), rs(2099, 2, "80.00", "80.00", "T")]}
    with pytest.raises(dx.ImportFehler, match="team_seasons"):
        dx.check_saisons(tie, [dict(ts[0], l="0", pa="170.00")])


def test_gegner_nur_2015_bis_2017():
    """Erfundene Werte: Ein Gegner 2023–2025 hätte in der Datei keine Spalte, 2018–2022 gilt games.csv → Abbruch."""
    weeks = {2016: [dict(rs(2016, 1, "100.00", "90.00", "W"), opponent_slot=3)],
             2024: [dict(rs(2024, 1, "100.00", "90.00", "W"), opponent_slot=None)]}
    dx.check_gegner(weeks)
    with pytest.raises(dx.ImportFehler, match="2024"):
        dx.check_gegner({**weeks, 2024: [dict(weeks[2024][0], opponent_slot=3)]})


def test_fallende_pa_und_leere_playoff_woche_brechen_ab():
    rows = saison()
    rows[1] = dict(rows[1], **{"Season points against": "80.00", "Points": "70.00"})   # Woche 2 mit PA −10
    with pytest.raises(dx.ImportFehler, match="PA fällt"):
        dx.saison_wochen(2099, wochen(rows), 2, NAMES)
    rows = saison()
    rows[3] = po(4)                                                   # leere Woche innerhalb der drei Playoff-Wochen
    with pytest.raises(dx.ImportFehler, match="kein Punktwert"):
        dx.saison_wochen(2099, wochen(rows), 2, NAMES)


def test_team_weeks_und_games(monkeypatch):
    monkeypatch.setattr(dx, "NFL_EXPORT", (2099,))
    weeks = {2099: [rs(2099, 1, "100.00", "90.00", "W"), rs(2099, 2, "70.00", None, None, phase="PO")]}
    tw = [{"season": "2099", "week": "1", "slot": "2", "phase": "RS", "pts": "100.00", "bench_pts": "1.00", "result": "W"},
          {"season": "2099", "week": "2", "slot": "2", "phase": "PO", "pts": "70.00", "bench_pts": "1.00", "result": ""},
          {"season": "2099", "week": "1", "slot": "5", "phase": "RS", "pts": "90.00", "bench_pts": "0.00", "result": "L"}]
    games = [{"season": "2099", "week": "1", "round": "Regular Season", "slot_a": "2", "slot_b": "5",
              "pts_a": "100.00", "pts_b": "90.00"}]
    dx.check_team_weeks(weeks, tw, games)
    with pytest.raises(dx.ImportFehler, match="team_weeks"):
        dx.check_team_weeks(weeks, [dict(tw[0], bench_pts="2.00"), *tw[1:]], games)
    with pytest.raises(dx.ImportFehler, match="games"):
        dx.check_team_weeks(weeks, tw, [dict(games[0], pts_b="91.00")])
    with pytest.raises(dx.ImportFehler, match="andere Wochen"):
        dx.check_team_weeks(weeks, tw[:1], games)


def test_screenshot_muss_zur_auskunft_passen():
    """Erfundenes Finale: Der Screenshot zeigt einen Hundertstel mehr als der Endstand der Auskunft → Abbruch."""
    weeks = {2099: [rs(2099, 1, "100.00", "90.00", "W"), rs(2099, 3, "150.00", None, None, phase="PO")]}
    shot = {"season": "2099", "week": "3", "slot_a": "2", "slot_b": "9", "pts_a": "150.00", "pts_b": "120.00"}
    dx.check_screenshots(weeks, [shot, dict(shot, slot_a="7")])     # Spiel ohne Hugh Jass wird nicht geprüft
    with pytest.raises(dx.ImportFehler, match="Screenshot-Spiel 2099 W3"):
        dx.check_screenshots(weeks, [dict(shot, pts_a="150.01")])
    regular = {"season": "2099", "week": "1", "slot_a": "4", "slot_b": "2", "pts_a": "90.00", "pts_b": "100.00"}
    dx.check_screenshots(weeks, [regular])
    with pytest.raises(dx.ImportFehler, match="W1"):                  # in der Regular Season zählt auch die PA
        dx.check_screenshots(weeks, [dict(regular, pts_a="91.00")])


def test_main_schreibt_und_prueft(tmp_path, monkeypatch, capsys):
    """Ablauf von main() mit erfundenem Inhalt (build umgangen): schreiben, --check grün, nach einer Änderung rot."""
    (tmp_path / "data" / "history").mkdir(parents=True)
    monkeypatch.setattr(dx.ef, "REPO_DIR", tmp_path)
    monkeypatch.setattr(dx, "build", lambda source: {"x.csv": "# Kopf\na,b\n1,2\n"})
    assert dx.main([str(tmp_path)]) == 0
    assert (tmp_path / "data" / "history" / "x.csv").read_bytes() == b"# Kopf\na,b\n1,2\n"
    assert dx.main([str(tmp_path), "--check"]) == 0 and "aktuell" in capsys.readouterr().out
    (tmp_path / "data" / "history" / "x.csv").write_bytes(b"a,b\n1,3\n")
    assert dx.main([str(tmp_path), "--check"]) == 1 and "weicht ab: x.csv" in capsys.readouterr().out


def test_abbruch_schreibt_nichts(tmp_path, monkeypatch):
    (tmp_path / "data" / "history").mkdir(parents=True)
    monkeypatch.setattr(dx.ef, "REPO_DIR", tmp_path)
    def fehler(source):
        raise dx.ImportFehler("erfunden")
    monkeypatch.setattr(dx, "build", fehler)
    assert dx.main([str(tmp_path)]) == 1
    assert not list((tmp_path / "data" / "history").iterdir())


def test_unbekannter_schalter_schreibt_nicht(tmp_path):
    """Ein vertippter Schalter bricht ab, statt die Dateien zu schreiben."""
    with pytest.raises(SystemExit) as stop:
        dx.main([str(tmp_path), "--chek"])
    assert stop.value.code == 2
