"""Tests Wochen 2018–2022 aus der DSGVO-Auskunft von nfl.com (data/history, scripts/nfl_export.py, history.compute_history → wochen).

Die Rohdateien liegen nicht im Repo; geprüft werden die abgeleiteten Dateien gegen team_seasons.csv, gegen
docs/referenz_historie.md und auf innere Stimmigkeit, dazu der Datenschutz aller Dateien in data/history.
Aufruf: python -m pytest
"""

import csv
import re
from collections import Counter, defaultdict
from decimal import Decimal

import pytest

import check_public
import espn_fetch as ef
import history
import rawdata

HISTORY = ef.REPO_DIR / "data" / "history"
REFERENZ = ef.REPO_DIR / "docs" / "referenz_historie.md"
SAISONS = range(2018, 2023)


def rows(name: str) -> list[dict]:
    with open(HISTORY / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def table(heading: str) -> list[list[str]]:
    for block in REFERENZ.read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        if title.startswith(heading):
            lines = [[c.strip() for c in line.strip().strip("|").split("|")] for line in body.splitlines()
                     if line.startswith("|")]
            return lines[2:]
    raise LookupError(f"Abschnitt „{heading}“ fehlt in {REFERENZ.name}")


def num(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


WEEKS = rows("team_weeks.csv")
GAMES = rows("games.csv")
HJ = rows("hugh_jass_2023_2025.csv")
TS = {(int(r["season"]), int(r["slot"])): r for r in rows("team_seasons.csv")}
RS_GAMES = {int(r["season"]): int(r["rs_games"]) for r in rows("seasons.csv")}
PTS = {(int(w["season"]), int(w["week"]), int(w["slot"])): Decimal(w["pts"]) for w in WEEKS}
ZAEHLER = dict(table("Wochen 2018–2022 Zähler"))


def games_of(season: int, round_: str | None = None) -> list[dict]:
    return [g for g in GAMES if int(g["season"]) == season and (round_ is None or g["round"] == round_)]


def played(season: int, week: int) -> set[int]:
    return {int(g[k]) for g in GAMES if (int(g["season"]), int(g["week"])) == (season, week) for k in ("slot_a", "slot_b")}


# ---------------------------------------------------------------- Team-Wochen

def test_team_wochen_vollstaendig():
    assert len(WEEKS) == int(ZAEHLER["Team-Wochen"])
    keys = Counter((int(w["season"]), int(w["week"]), int(w["slot"])) for w in WEEKS)
    assert set(keys.values()) == {1}
    for season in SAISONS:
        assert {(wk, s) for (ss, wk, s) in keys if ss == season} == \
            {(wk, s) for wk in range(1, RS_GAMES[season] + 4) for s in range(1, 11)}


def test_phase_ergebnis_und_allplay_nur_in_der_regular_season():
    for w in WEEKS:
        rs = int(w["week"]) <= RS_GAMES[int(w["season"])]
        assert w["phase"] == ("RS" if rs else "PO")
        if rs:
            assert w["result"] in ("W", "L", "T")
            assert int(w["allplay_w"]) + int(w["allplay_l"]) + int(w["allplay_t"]) == 9
        else:
            assert w["result"] == w["allplay_w"] == w["allplay_l"] == w["allplay_t"] == ""


@pytest.mark.parametrize("key", [(s, t) for s in SAISONS for t in range(1, 11)], ids=lambda k: f"{k[0]}-{k[1]}")
def test_team_saison_wie_team_seasons(key):
    """50 Team-Saisons: PF aus den Wochen, PA aus den Paarungen und W-L exakt wie in team_seasons.csv."""
    season, slot = key
    mine = [w for w in WEEKS if (int(w["season"]), int(w["slot"]), w["phase"]) == (season, slot, "RS")]
    pa = sum((Decimal(g["pts_b"] if int(g["slot_a"]) == slot else g["pts_a"]) for g in games_of(season, "Regular Season")
              if slot in (int(g["slot_a"]), int(g["slot_b"]))), Decimal(0))
    expected = TS[key]
    assert sum(Decimal(w["pts"]) for w in mine) == Decimal(expected["pf"])
    assert pa == Decimal(expected["pa"])
    assert sum(w["result"] == "W" for w in mine) == int(expected["w"])
    assert sum(w["result"] == "L" for w in mine) == int(expected["l"])


def test_allplay_je_woche_stimmig():
    """Je Woche Σ All-Play-Siege = Σ Niederlagen, und jeder Wert folgt aus den Punkten der Woche."""
    by_week = defaultdict(list)
    for w in WEEKS:
        if w["phase"] == "RS":
            by_week[(w["season"], w["week"])].append(w)
    for week, teams in by_week.items():
        assert sum(int(w["allplay_w"]) for w in teams) == sum(int(w["allplay_l"]) for w in teams), week
        for w in teams:
            others = [Decimal(o["pts"]) for o in teams if o is not w]
            mine = Decimal(w["pts"])
            assert (int(w["allplay_w"]), int(w["allplay_l"]), int(w["allplay_t"])) == \
                (sum(o < mine for o in others), sum(o > mine for o in others), sum(o == mine for o in others))


@pytest.mark.parametrize("row", table("All-Play Hugh Jass 2018–2022"), ids=lambda r: r[0])
def test_allplay_wie_saisonstand_nfl(row):
    season, slot, w, l = (int(x) for x in row)
    mine = [x for x in WEEKS if (int(x["season"]), int(x["slot"]), x["phase"]) == (season, slot, "RS")]
    assert (sum(int(x["allplay_w"]) for x in mine), sum(int(x["allplay_l"]) for x in mine)) == (w, l)


def test_hoechster_wochenwert():
    best = max(WEEKS, key=lambda w: Decimal(w["pts"]))
    assert Decimal(best["pts"]) == num(ZAEHLER["Höchster Wochenwert"])
    assert (best["season"], best["week"], best["slot"]) == (
        ZAEHLER["Höchster Wochenwert Saison"], ZAEHLER["Höchster Wochenwert Woche"], ZAEHLER["Höchster Wochenwert Slot"])


# ---------------------------------------------------------------- Spiele

def test_spiele_regular_season():
    """335 Spiele, je Woche jedes Team genau einmal, Punkte wie in den Team-Wochen, Sieger wie das Ergebnis."""
    rs = [g for g in GAMES if g["round"] == "Regular Season"]
    assert len(rs) == int(ZAEHLER["Spiele Regular Season"])
    for season in SAISONS:
        for week in range(1, RS_GAMES[season] + 1):
            slots = [int(g[k]) for g in rs if (int(g["season"]), int(g["week"])) == (season, week)
                     for k in ("slot_a", "slot_b")]
            assert sorted(slots) == list(range(1, 11)), (season, week)
    results = {(int(w["season"]), int(w["week"]), int(w["slot"])): w["result"] for w in WEEKS}
    for g in rs:
        key = int(g["season"]), int(g["week"])
        a, b = int(g["slot_a"]), int(g["slot_b"])
        assert (Decimal(g["pts_a"]), Decimal(g["pts_b"])) == (PTS[(*key, a)], PTS[(*key, b)])
        assert Decimal(g["pts_a"]) > Decimal(g["pts_b"]) and int(g["winner_slot"]) == a   # 2018–2022 ohne Unentschieden
        assert (results[(*key, a)], results[(*key, b)]) == ("W", "L")
        assert g["herleitung"] == "Punkte gegen"


@pytest.mark.parametrize("row", table("Endstände Screenshot-Spiele 2018–2022"), ids=lambda r: f"{r[0]}-W{r[1]}-{r[3]}")
def test_screenshot_spiele_mit_endstand(row):
    season, week, round_, a, b, pts_a, pts_b = row
    hits = [g for g in GAMES if (g["season"], g["week"], g["round"]) == (season, week, round_)
            and {g["slot_a"], g["slot_b"]} == {a, b}]
    assert len(hits) == 1
    g = hits[0]
    got = {g["slot_a"]: Decimal(g["pts_a"]), g["slot_b"]: Decimal(g["pts_b"])}
    assert (got[a], got[b]) == (num(pts_a), num(pts_b))


def test_alle_screenshot_paarungen_im_export():
    """Jedes Spiel aus matchups_hist.csv 2018–2022 (auch live/partial) steht mit demselben Sieger in games.csv."""
    shots = [m for m in rows("matchups_hist.csv") if int(m["season"]) in SAISONS]
    assert len(shots) == 7
    for m in shots:
        hit = [g for g in GAMES if (g["season"], g["week"]) == (m["season"], m["week"])
               and {g["slot_a"], g["slot_b"]} == {m["slot_a"], m["slot_b"]}]
        assert len(hit) == 1 and hit[0]["winner_slot"] == m["winner_slot"], m


@pytest.mark.parametrize("season", SAISONS)
def test_playoff_bracket(season):
    """Byes, Runde 1, Halbfinale und Finalwoche passen zu Endplätzen, Divisionssiegern und Punkten."""
    teams = {slot: TS[(season, slot)] for slot in range(1, 11)}
    place = {s: int(t["final_rank"]) for s, t in teams.items()}
    field = {s for s, t in teams.items() if t["playoffs"] == "1"}
    byes = {s for s in field if teams[s]["div_rank"] == "1"}
    w1, w2, w3 = RS_GAMES[season] + 1, RS_GAMES[season] + 2, RS_GAMES[season] + 3
    po = [g for g in games_of(season) if g["round"] != "Regular Season"]
    weiter = {"Quarterfinal": 4, "Semifinal": 2}          # Endplatz, bis zu dem der Sieger der Runde kommt
    for g in po:
        week, a, b = int(g["week"]), int(g["slot_a"]), int(g["slot_b"])
        assert (Decimal(g["pts_a"]), Decimal(g["pts_b"])) == (PTS[(season, week, a)], PTS[(season, week, b)])
        assert Decimal(g["pts_a"]) > Decimal(g["pts_b"]) and int(g["winner_slot"]) == a
        assert {a, b} <= field and place[a] < place[b]
        if g["round"] in weiter:                                # je Spiel ein Weiterkommender gegen einen Ausscheidenden
            assert place[a] <= weiter[g["round"]] < place[b], g
    assert played(season, w1).isdisjoint(byes)                     # Bye der Divisionssieger ist kein Spiel
    for week, round_, teilnehmer in ((w1, "Quarterfinal", field - byes),
                                     (w2, "Semifinal", byes | {s for s in field - byes if place[s] <= 4})):
        games = [g for g in po if int(g["week"]) == week]
        assert len(games) == 2 and {g["round"] for g in games} == {round_}
        assert played(season, week) == teilnehmer
        if round_ == "Semifinal":
            assert all(len({int(g["slot_a"]), int(g["slot_b"])} & byes) == 1 for g in games)
    final_week = {g["round"]: (int(g["slot_a"]), int(g["slot_b"])) for g in po if int(g["week"]) == w3}
    by_place = {p: s for s, p in place.items()}
    assert final_week == {"Final": (by_place[1], by_place[2]), "Spiel um Platz 3": (by_place[3], by_place[4]),
                          "Spiel um Platz 5": (by_place[5], by_place[6])}
    assert all(place[s] > 6 for s in range(1, 11) if s not in field)
    assert not any({int(g["slot_a"]), int(g["slot_b"])} - field for g in po)   # Trostrunde nicht abgeleitet


def test_playoff_zaehler():
    assert sum(g["round"] != "Regular Season" for g in GAMES) == int(ZAEHLER["Playoff-Spiele"])
    assert sum(g["herleitung"] == "Seed-Regel" for g in GAMES) == int(ZAEHLER["Playoff-Spiele nach Seed-Regel"])
    assert sorted({(g["season"], g["round"]) for g in GAMES if g["herleitung"] == "Seed-Regel"}) == [
        ("2018", "Quarterfinal"), ("2022", "Quarterfinal")]
    # Halbfinale 2018 von Stephan bestätigt (03.10.2026): Hugh Jass (2) gegen gloane saubande (8)
    assert sorted((g["slot_a"], g["slot_b"]) for g in GAMES if g["herleitung"] == "Bestätigt") == [("2", "8"), ("4", "6")]


def seed_regel(season: int) -> dict[str, set[frozenset]]:
    """Seed-Regel unabhängig von nfl_export nachgebaut: Divisionssieger Seed 1–2, die übrigen 3–6, je nach W, dann PF;
    Runde 1 3–6 und 4–5; Halbfinale ohne Neusetzen 1 gegen Sieger 4–5, 2 gegen Sieger 3–6."""
    teams = [t for (s, _), t in TS.items() if s == season and t["playoffs"] == "1"]
    def order(rows):
        return [int(t["slot"]) for t in sorted(rows, key=lambda t: (-int(t["w"]), -Decimal(t["pf"])))]
    s = order([t for t in teams if t["div_rank"] == "1"]) + order([t for t in teams if t["div_rank"] != "1"])
    place = {int(t["slot"]): int(t["final_rank"]) for t in teams}
    def sieger(a, b):
        return a if place[a] <= 4 else b
    return {"Quarterfinal": {frozenset((s[2], s[5])), frozenset((s[3], s[4]))},
            "Semifinal": {frozenset((s[0], sieger(s[3], s[4]))), frozenset((s[1], sieger(s[2], s[5])))}}


@pytest.mark.parametrize("season", SAISONS)
def test_seed_regel_trifft_alle_runden_ausser_halbfinale_von_hand(season):
    """Entscheidung Stephan 03.10.2026: Die Seed-Regel gilt 2018–2022. Sie trifft jede Runde 1 und jedes Halbfinale –
    außer den Halbfinalen 2020 und 2021, die nach Runde 1 von Hand neu gepaart wurden."""
    rule = seed_regel(season)
    for round_, expected in rule.items():
        got = {frozenset((int(g["slot_a"]), int(g["slot_b"]))) for g in games_of(season, round_)}
        if round_ == "Semifinal" and season in (2020, 2021):
            assert got != expected
        else:
            assert got == expected, round_


# ---------------------------------------------------------------- Hugh Jass 2023–2025

def test_hugh_jass_2023_2025_kopf_vermerkt_umfang_und_gegenprobe():
    head = [line for line in (HISTORY / "hugh_jass_2023_2025.csv").read_text(encoding="utf-8").splitlines()
            if line.startswith("#")]
    assert head[0].startswith("# Umfang: nur Hugh Jass")
    probe = next(line for line in head if "Gegenprobe" in line)
    assert f"{ZAEHLER['Gegenprobe Hugh Jass 2020–2022 exakt']} von {ZAEHLER['Gegenprobe Hugh Jass 2020–2022 Wochen']}" \
        in probe


@pytest.mark.parametrize("season", (2023, 2024, 2025))
def test_hugh_jass_wochen_wie_saisonwerte(season):
    mine = [r for r in HJ if int(r["season"]) == season]
    assert [int(r["week"]) for r in mine] == list(range(1, RS_GAMES[season] + 1))
    assert {r["slot"] for r in mine} == {"2"}
    t = TS[(season, 2)]
    assert sum(Decimal(r["pts"]) for r in mine) == Decimal(t["pf"])
    assert sum(Decimal(r["pts_against"]) for r in mine) == Decimal(t["pa"])
    assert (sum(r["result"] == "W" for r in mine), sum(r["result"] == "L" for r in mine)) == (int(t["w"]), int(t["l"]))
    for r in mine:
        pf, pa = Decimal(r["pts"]), Decimal(r["pts_against"])
        assert r["result"] == ("W" if pf > pa else "L")


# ---------------------------------------------------------------- Datenschutz (Repo öffentlich)

ERLAUBTE_SPALTEN = {
    "team_seasons.csv": {"season", "slot", "team_name", "division", "div_rank", "w", "l", "pf", "pa", "final_rank",
                         "playoffs", "scoring_title"},
    "seasons.csv": {"season", "platform", "teams", "rs_games", "scoring_era", "qb_format", "keeper_mode", "keeper_min",
                    "division_phase", "division_1", "division_2", "playoff_format", "draft_utc"},
    "franchises.csv": {"slot", "franchise", "name_chain"},
    "matchups_hist.csv": {"season", "week", "round", "slot_a", "slot_b", "pts_a", "pts_b", "winner_slot", "status",
                          "source"},
    "team_weeks.csv": {"season", "week", "phase", "slot", "pts", "bench_pts", "allplay_w", "allplay_l", "allplay_t",
                       "result"},
    "games.csv": {"season", "week", "round", "slot_a", "slot_b", "pts_a", "pts_b", "winner_slot", "herleitung"},
    "hugh_jass_2023_2025.csv": {"season", "week", "slot", "pts", "pts_against", "result"},
    "rekorde.csv": {"id", "kategorie", "rekord", "wert", "details", "quelle", "ableitbar", "verifiziert", "slots",
                    "saisons"},
}
LANGE_ZAHL = re.compile(r"(?<![\d.])\d{6,}(?![\d.])")    # Nutzer-, Team-, Liga- oder Spieler-IDs; Punkte haben ≤ 4 Stellen
HASH = re.compile(r"\b[0-9a-fA-F]{16,}\b")                # z. B. die 32-stelligen Nutzer-Hashes von nfl.com
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")   # ESPN-Member-IDs


def test_data_history_nur_bekannte_dateien_und_spalten():
    """Jede CSV in data/history hat nur Spalten der Positivliste – keine user_id, team_id, player_id, E-Mail …"""
    found = {p.name for p in HISTORY.glob("*.csv")}
    assert found == set(ERLAUBTE_SPALTEN)
    for name, allowed in ERLAUBTE_SPALTEN.items():
        with open(HISTORY / name, encoding="utf-8", newline="") as f:
            lines = list(csv.reader(line for line in f if not line.startswith("#")))
        assert set(lines[0]) <= allowed, name
        assert all(len(line) == len(lines[0]) for line in lines), name   # kein Zusatzfeld hinter der letzten Spalte


def test_data_history_ohne_mail_und_ids():
    """Keine E-Mail-Adresse, keine langen Ziffernfolgen (IDs) und keine Hashes in data/history. Die Meldung nennt
    nur die Datei, nie den Fund (Action-Logs sind öffentlich)."""
    for path in sorted(HISTORY.iterdir()):
        text = path.read_text(encoding="utf-8")
        assert "@" not in text, path.name
        assert not LANGE_ZAHL.search(text), path.name
        assert not HASH.search(text), path.name
        assert not UUID.search(text), path.name


@pytest.mark.parametrize("muster", ["1234567", "2023,1,2,187.57,156.70,1234567", "x,0000aaaa-bbbb-cccc-dddd-eeeeffff0000"])
def test_datenschutz_muster_greifen_in_csv(muster):
    """Erfundene IDs als unquotiertes CSV-Feld werden erkannt; echte Punktwerte und Daten nicht."""
    assert LANGE_ZAHL.search(muster) or UUID.search(muster)
    assert not LANGE_ZAHL.search("2018,1,RS,2,2770.60,115.23,0,9,0,L,24.09.2026")


def test_data_history_ohne_manager_namen():
    """Historie ohne Manager (Entscheidung 28.09.2026): keine vollen Namen, Nachnamen, Anzeigenamen oder Member-IDs
    in data/history – Muster wie in check_public; die Meldung nennt nur Datei und Fundart."""
    patterns = check_public.manager_patterns(ef.REPO_DIR)
    for path in sorted(HISTORY.iterdir()):
        text = path.read_text(encoding="utf-8")
        found = sorted({kind for kind, rx in patterns if rx.search(text)})
        assert not found, f"{path.name}: enthält Manager-{', '.join(found)}"


# ---------------------------------------------------------------- Kennzahlen (history.compute_history → wochen)

@pytest.fixture(scope="module")
def wochen():
    return history.compute_history(rawdata.Season(2026, 2))["wochen"]


def test_wochen_in_compute_history(wochen):
    """Ein Einstieg (Stephan 03.10.2026): die Wochen stehen in compute_history unter „wochen“."""
    assert set(wochen) == {"saisons", "spiele", "ohne_gegner", "h2h", "rekorde", "allplay", "hugh_jass_2023_2025"}


def test_spiele_fuer_die_wochenansicht(wochen):
    """App-Ansicht Wochen 2018–2022 (04.10.2026): jedes Spiel aus games.csv mit beiden Seiten und Bankpunkten."""
    spiele = wochen["spiele"]
    assert len(spiele) == len(GAMES)
    bench = {(int(w["season"]), int(w["week"]), int(w["slot"])): Decimal(w["bench_pts"]) for w in WEEKS}
    by_key = {(int(g["season"]), int(g["week"]), int(g["slot_a"])): g for g in GAMES}
    for s in spiele:
        g = by_key[(s["season"], s["week"], s["slot_a"])]
        assert (s["round"], s["herleitung"], s["slot_b"]) == (g["round"], g["herleitung"], int(g["slot_b"]))
        assert (s["pts_a"], s["pts_b"]) == (Decimal(g["pts_a"]), Decimal(g["pts_b"]))
        assert (s["bench_a"], s["bench_b"]) == (bench[(s["season"], s["week"], s["slot_a"])],
                                                bench[(s["season"], s["week"], s["slot_b"])])
        assert s["winner_slot"] == (int(g["winner_slot"]) if g["winner_slot"] else None)
    assert set(spiele[0]) == {"season", "week", "round", "herleitung", "slot_a", "pts_a", "bench_a", "slot_b", "pts_b",
                              "bench_b", "winner_slot"}


def test_ohne_gegner_nur_playoff_wochen(wochen):
    """Team-Wochen ohne Spiel: nur Playoffs (Bye, Trostrunde), zusammen mit den Spielen genau team_weeks.csv."""
    frei = wochen["ohne_gegner"]
    assert frei and all(f["phase"] == "PO" for f in frei)
    played = {(int(g["season"]), int(g["week"]), int(g[k])) for g in GAMES for k in ("slot_a", "slot_b")}
    keys = {(f["season"], f["week"], f["slot"]) for f in frei}
    assert not keys & played
    assert keys | played == {(int(w["season"]), int(w["week"]), int(w["slot"])) for w in WEEKS}
    assert all(f["pts"] == PTS[(f["season"], f["week"], f["slot"])] for f in frei)


def test_h2h_summen(wochen):
    for phase, n in (("RS", 335), ("PO", int(ZAEHLER["Playoff-Spiele"]))):
        pairs = wochen["h2h"][phase]
        assert len(pairs) == 45
        assert sum(p["spiele"] for p in pairs) == n
        assert all(p["w_a"] + p["l_a"] + p["t"] == p["spiele"] for p in pairs)
        games = Counter(frozenset((int(g["slot_a"]), int(g["slot_b"]))) for g in GAMES
                        if (g["round"] == "Regular Season") == (phase == "RS"))
        assert {frozenset((p["a"], p["b"])): p["spiele"] for p in pairs if p["spiele"]} == dict(games)


def test_h2h_pf_diff_und_siege(wochen):
    """Nachgerechnet für ein Paar aus games.csv: Hugh Jass (Slot 2) gegen Elephucks (Slot 3, heute 4th Down Syndrom), Regular Season."""
    pair = next(p for p in wochen["h2h"]["RS"] if (p["a"], p["b"]) == (2, 3))
    mine = [g for g in GAMES if g["round"] == "Regular Season" and {g["slot_a"], g["slot_b"]} == {"2", "3"}]
    assert pair["spiele"] == len(mine)
    assert pair["w_a"] == sum(g["winner_slot"] == "2" for g in mine)
    assert pair["pf_diff"] == sum((Decimal(g["pts_a"]) - Decimal(g["pts_b"])) * (1 if g["slot_a"] == "2" else -1)
                                  for g in mine)


def test_rekorde_regular_season(wochen):
    rs = wochen["rekorde"]["RS"]
    assert set(rs) == set(history.WOCHEN_REKORDE)
    best = rs["hoechster_score"][0]
    assert (best["season"], best["week"], best["team_id"], best["wert"]) == (2018, 2, 2, Decimal("338.43"))
    assert all(len(v) >= history.TOP_N for v in rs.values())
    sides = [(int(g["season"]), int(g["week"]), int(g[k])) for g in GAMES if g["round"] == "Regular Season"
             for k in ("slot_a", "slot_b")]
    assert rs["niedrigster_score"][0]["wert"] == min(PTS[s] for s in sides)
    assert rs["groesster_sieg"][0]["wert"] == max(Decimal(g["pts_a"]) - Decimal(g["pts_b"]) for g in GAMES
                                                  if g["round"] == "Regular Season")
    bench = {(int(w["season"]), int(w["week"]), int(w["slot"])): Decimal(w["bench_pts"]) for w in WEEKS}
    assert rs["hoechste_bank"][0]["wert"] == max(bench[s] for s in sides)


@pytest.mark.parametrize("phase", ["RS", "PO"])
def test_rekorde_unabhaengig_nachgerechnet(wochen, phase):
    """Der erste Eintrag jedes Rekords direkt aus games.csv und team_weeks.csv (ohne history.py)."""
    games = [g for g in GAMES if (g["round"] == "Regular Season") == (phase == "RS")]
    bench = {(int(w["season"]), int(w["week"]), int(w["slot"])): Decimal(w["bench_pts"]) for w in WEEKS}
    sides = [(int(g["season"]), int(g["week"]), int(g[k])) for g in games for k in ("slot_a", "slot_b")]
    margins = [Decimal(g["pts_a"]) - Decimal(g["pts_b"]) for g in games]
    expected = {"hoechster_score": max(PTS[s] for s in sides), "niedrigster_score": min(PTS[s] for s in sides),
                "groesster_sieg": max(margins), "knappstes_ergebnis": min(margins),
                "hoechste_bank": max(bench[s] for s in sides)}
    got = wochen["rekorde"][phase]
    assert {k: got[k][0]["wert"] for k in expected} == expected
    assert all(len(got[k]) >= history.TOP_N for k in expected)
    for k in ("hoechster_score", "groesster_sieg", "hoechste_bank"):
        assert [e["wert"] for e in got[k]] == sorted((e["wert"] for e in got[k]), reverse=True)
    for k in ("niedrigster_score", "knappstes_ergebnis"):
        assert [e["wert"] for e in got[k]] == sorted(e["wert"] for e in got[k])


def test_rekorde_nur_spiele_mit_gegner(wochen):
    """Byes und Trostrunde zählen nie: Der Bye-Wert 317,50 (cool runnings, 2018 W14) ist höher als
    jeder Playoff-Rekord, steht aber nicht drin; jeder Eintrag ist ein Spiel aus games.csv."""
    po = wochen["rekorde"]["PO"]
    assert PTS[(2018, 14, 4)] == Decimal("317.50") > po["hoechster_score"][0]["wert"]
    keys = {(int(g["season"]), int(g["week"]), int(g[k])) for g in GAMES for k in ("slot_a", "slot_b")}
    for entries in po.values():
        for e in entries:
            slots = e["team_ids"] if "team_ids" in e else [e["team_id"], e["opponent_id"]]
            assert all((e["season"], e["week"], s) in keys for s in slots)


def test_top_mit_gleichstand():
    """Erfundene Werte: wer mit dem n-ten gleichauf liegt, kommt mit."""
    values = [5, 9, 7, 7, 3, 7]
    assert history.top(values, lambda v: v, n=2) == [9, 7, 7, 7]
    assert history.top(values, lambda v: v, n=2, highest=False) == [3, 5]
    assert history.top([1], lambda v: v, n=5) == [1]


def test_allplay_saisons(wochen):
    ap = wochen["allplay"]
    assert len(ap) == 50
    for season in SAISONS:
        mine = [r for r in ap if r["season"] == season]
        assert sum(r["allplay_w"] for r in mine) == sum(r["allplay_l"] for r in mine)
        assert all(r["allplay_w"] + r["allplay_l"] + r["allplay_t"] == 9 * RS_GAMES[season] for r in mine)
        assert [r["allplay_pct"] for r in mine] == sorted((r["allplay_pct"] for r in mine), reverse=True)
    hj = next(r for r in ap if (r["season"], r["slot"]) == (2018, 2))
    assert hj["allplay_pct"] == Decimal(104) / Decimal(117) * 100


def test_hugh_jass_und_saisons_in_der_ausgabe(wochen):
    assert len(wochen["hugh_jass_2023_2025"]) == 42
    assert wochen["saisons"] == list(SAISONS)
