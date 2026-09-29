"""Tests Record Book und Transaktionsliste (scripts/records.py, Baustein 4).

Echte Werte W1–W2 gegen docs/referenz_w1-w2.md (Sollwerte aus der Referenzdatei gelesen, nicht abgeschrieben),
Serien, Gleichstände, Byes und Transaktionsfilter an konstruierten Daten.
Aufruf: python -m pytest -q tests/test_records.py
"""

import json
from decimal import Decimal

import pytest

import check_public
import compute
import espn_fetch as ef
import rawdata
import records
from rawdata import RosterRow
from zahlen import HUNDRED, ZERO, rounded

REFERENZ = ef.REPO_DIR / "docs" / "referenz_w1-w2.md"
REFERENZ_IDS = {t["name"]: t["id"] for t in ef.load_json(ef.week_dir(2026, 2) / "mTeam.json")["teams"]}
FORBIDDEN = {"members", "owners", "primaryOwner", "memberId", "isLeagueManager", "firstName", "lastName",
             "outlooks", "seasonOutlook"} | set(check_public.FORBIDDEN_KEYS)


def table(heading: str) -> list[list[str]]:
    """Datenzeilen der Markdown-Tabelle unter „## <heading>…“ (ohne Kopf und Trennlinie)."""
    for block in REFERENZ.read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        if title.startswith(heading):
            rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                    for line in body.splitlines() if line.startswith("|")]
            return rows[2:]
    raise LookupError(f"Abschnitt „{heading}“ fehlt in {REFERENZ.name}")


def num(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def keys_deep(value) -> set:
    """Alle Schlüssel eines verschachtelten dict/list."""
    if isinstance(value, dict):
        return set(value) | set().union(*(keys_deep(v) for v in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(keys_deep(v) for v in value))
    return set()


# ---------------------------------------------------------------- Referenz als Spiele

@pytest.fixture(scope="module")
def ref_games() -> list[tuple[int, int, Decimal, int, Decimal]]:
    """Paarungen der Referenz: (Woche, team_id A, Punkte A, team_id B, Punkte B)."""
    return [(int(w), REFERENZ_IDS[a], num(pa), REFERENZ_IDS[b], num(pb)) for w, a, pa, b, pb in table("Matchups")]


@pytest.fixture(scope="module")
def ref_team_weeks(ref_games) -> list[tuple[int, int, Decimal, Decimal]]:
    """(Woche, team_id, PF, PA) je Team-Woche der Referenz."""
    return [row for w, a, pa, b, pb in ref_games for row in ((w, a, pa, pb), (w, b, pb, pa))]


# ---------------------------------------------------------------- echte Daten W1–W2

@pytest.fixture(scope="module")
def ssn():
    return rawdata.Season(2026, 2)


@pytest.fixture(scope="module")
def weeks():
    return compute.completed_weeks(2026, 2)


@pytest.fixture(scope="module")
def team_weeks(ssn, weeks):
    return compute.compute_team_weeks(ssn, weeks)


@pytest.fixture(scope="module")
def rec(ssn, weeks, team_weeks):
    return records.compute_records(ssn, weeks, team_weeks)


@pytest.fixture(scope="module")
def tx(ssn):
    return records.compute_transactions(ssn)


def team_week_set(entries) -> set:
    return {(e["week"], e["team_id"], e["wert"]) for e in entries}


def test_h2h_gegen_referenz(rec, ref_games):
    """Alle 45 Paare; gespielte Paare mit W-L-T und PF-Differenz aus der Matchup-Tabelle, die übrigen leer."""
    expected = {}
    for _, a, pa, b, pb in ref_games:
        (x, px), (y, py) = sorted(((a, pa), (b, pb)))
        e = expected.setdefault((x, y), {"spiele": 0, "w_a": 0, "l_a": 0, "t": 0, "pf_diff": ZERO})
        e["spiele"] += 1
        e["w_a"] += px > py
        e["l_a"] += px < py
        e["t"] += px == py
        e["pf_diff"] += px - py
    assert len(rec["h2h"]) == 45
    assert [(p["a"], p["b"]) for p in rec["h2h"]] == sorted((p["a"], p["b"]) for p in rec["h2h"])
    for p in rec["h2h"]:
        assert p["a"] < p["b"]
        want = expected.get((p["a"], p["b"]), {"spiele": 0, "w_a": 0, "l_a": 0, "t": 0, "pf_diff": ZERO})
        assert {k: p[k] for k in want} == want, (p["a"], p["b"])


def test_rekorde_score_gegen_referenz(rec, ref_team_weeks):
    """Höchster/niedrigster Score, höchster Verlierer, niedrigster Sieger aus der Matchup-Tabelle."""
    rs = rec["records_rs"]
    pf = [(w, t, p) for w, t, p, _ in ref_team_weeks]
    losers = [(w, t, p) for w, t, p, q in ref_team_weeks if p < q]
    winners = [(w, t, p) for w, t, p, q in ref_team_weeks if p > q]
    best = lambda rows, f: {r for r in rows if r[2] == f(x[2] for x in rows)}  # noqa: E731
    assert team_week_set(rs["hoechster_score"]) == best(pf, max)
    assert team_week_set(rs["niedrigster_score"]) == best(pf, min)
    assert team_week_set(rs["hoechster_verlierer"]) == best(losers, max)
    assert team_week_set(rs["niedrigster_sieger"]) == best(winners, min)
    # Stichprobe aus dem Auftrag: 307,51 und 118,83
    assert [e["wert"] for e in rs["hoechster_score"]] == [max(p for _, _, p in pf)] == [Decimal("307.51")]
    assert [e["wert"] for e in rs["niedrigster_score"]] == [min(p for _, _, p in pf)] == [Decimal("118.83")]


def test_rekorde_spiele_gegen_referenz(rec, ref_games):
    """Größter Sieg und knappstes Ergebnis: Sieger, Verlierer, Ergebnis und Differenz."""
    games = [(w, *sorted(((a, pa), (b, pb)), key=lambda s: -s[1])) for w, a, pa, b, pb in ref_games]
    diffs = {(w, x[0], y[0], x[1], y[1]): x[1] - y[1] for w, x, y in games}
    as_set = lambda entries: {(e["week"], *e["team_ids"], *e["punkte"]) for e in entries}  # noqa: E731
    assert as_set(rec["records_rs"]["groesster_sieg"]) == {g for g, d in diffs.items() if d == max(diffs.values())}
    assert as_set(rec["records_rs"]["knappstes_ergebnis"]) == {g for g, d in diffs.items() if d == min(diffs.values())}
    for e in rec["records_rs"]["groesster_sieg"] + rec["records_rs"]["knappstes_ergebnis"]:
        assert e["wert"] == e["punkte"][0] - e["punkte"][1] and not e["unentschieden"]


def test_serien_gegen_referenz(rec, ref_team_weeks):
    """Längste Sieges- und Niederlagenserie nach W2: alle Teams mit 2-0 bzw. 0-2 (Gleichstand = alle)."""
    results = {}
    for w, t, p, q in sorted(ref_team_weeks):
        results.setdefault(t, []).append("W" if p > q else "L" if p < q else "T")
    for key, res in (("laengste_siegesserie", "W"), ("laengste_niederlagenserie", "L")):
        entries = rec["records_rs"][key]
        assert {e["team_id"] for e in entries} == {t for t, r in results.items() if r == [res, res]}
        assert all(e["weeks"] == [1, 2] and e["wert"] == 2 and e["laufend"] for e in entries)


def test_verschenkt_gegen_referenz(rec):
    """Meiste Verschenkt (Team-Woche) aus Saisontabelle: „davon einzeln“ und Differenz zum Gesamtwert."""
    candidates = []
    for team, *_, total, single in table("Saisontabelle"):
        week, value = single.split()
        week, value = int(week.lstrip("W")), num(value)
        candidates += [(week, REFERENZ_IDS[team], value), (3 - week, REFERENZ_IDS[team], num(total) - value)]
    top = max(v for *_, v in candidates)
    got = rec["records_rs"]["meiste_verschenkt"]
    assert {(w, t) for w, t, v in candidates if v == top} == {(e["week"], e["team_id"]) for e in got}
    assert all(abs(e["wert"] - top) <= Decimal("0.01") for e in got)


def test_bank_und_bester_spieler_aus_kader(rec, ssn, weeks, team_weeks):
    """Höchste Bank = max Bank-Punkte der Team-Wochen; bester Spieler = max über alle Kaderspieler außer IR."""
    bench = max(r["bench"] for r in team_weeks)
    assert team_week_set(rec["records_rs"]["hoechste_bank"]) == \
        {(r["week"], r["team_id"], r["bench"]) for r in team_weeks if r["bench"] == bench}
    rows = [(w, p) for w in weeks for p in ssn.roster(w) if p.slot != records.SLOT_IR]
    best = max(p.actual for _, p in rows)
    got = rec["records_rs"]["bester_spieler"]
    assert {(e["week"], e["player_id"], e["team_id"], e["wert"]) for e in got} == \
        {(w, p.player_id, p.team_id, p.actual) for w, p in rows if p.actual == best}
    for e in got:
        row = next(p for p in ssn.roster(e["week"]) if p.player_id == e["player_id"])
        assert (e["name"], e["slot"], e["pos"]) == (row.name, records.SLOT_NAMES[row.slot],
                                                    records.POSITION_NAMES[row.pos])


def test_records_po_leer_mit_gleicher_struktur(rec):
    assert list(rec["records_po"]) == list(rec["records_rs"]) == list(records.RECORD_KEYS)
    assert all(v == [] for v in rec["records_po"].values())


def test_positionen_summe_gleich_pf(rec, team_weeks):
    """Invariante: Σ nach Position = Σ nach Slot = summe = PF je Team; Σ Anteil = 100; D/ST und K in beiden gleich."""
    pf = {}
    for r in team_weeks:
        pf[r["team_id"]] = pf.get(r["team_id"], ZERO) + r["pf"]
    assert sorted(rec["positions"]) == sorted(pf)
    for team_id, p in rec["positions"].items():
        assert p["summe"] == pf[team_id]
        for kind, keys in (("nach_position", ("QB", "RB", "WR", "TE", "K", "D/ST")),
                           ("nach_slot", ("QB", "RB", "WR", "TE", "FLEX", "OP", "D/ST", "K"))):
            assert tuple(p[kind]) == keys
            assert sum((v["pts"] for v in p[kind].values()), ZERO) == pf[team_id]
            assert abs(sum((v["anteil"] for v in p[kind].values()), ZERO) - HUNDRED) < Decimal("1e-20")
        for key in ("D/ST", "K"):
            assert p["nach_position"][key]["pts"] == p["nach_slot"][key]["pts"]


def test_positionen_ligarang(rec):
    """Ligarang je Schlüssel: 1 + Anzahl Teams mit mehr Punkten."""
    teams = rec["positions"]
    for kind in ("nach_position", "nach_slot"):
        for key in next(iter(teams.values()))[kind]:
            values = {t: p[kind][key]["pts"] for t, p in teams.items()}
            for t, p in teams.items():
                assert p[kind][key]["rang"] == 1 + sum(1 for v in values.values() if v > values[t])


def test_top_scorer(rec, ssn, weeks):
    """Je Woche die 10 besten Kaderspieler inklusive Bank, absteigend; kein Nicht-Gewählter hat mehr Punkte."""
    assert list(rec["top_scorer"]) == weeks
    abbrev = {t.id: t.abbrev for t in ssn.nfl().values()}
    for week, chosen in rec["top_scorer"].items():
        assert len(chosen) >= 10
        points = [p["pts"] for p in chosen]
        assert points == sorted(points, reverse=True)
        rest = [p.actual for p in ssn.roster(week)
                if p.slot != records.SLOT_IR and p.player_id not in {c["player_id"] for c in chosen}]
        assert max(rest) <= points[-1]
        if len(chosen) > 10:
            assert points[9] == points[-1]  # nur Gleichstand auf Platz 10 verlängert die Liste
        assert set(chosen[0]) == {"rang", "player_id", "name", "pos", "pro_team", "nfl", "team_id", "slot", "pts",
                                  "proj"}
        assert all(p["nfl"] == abbrev[p["pro_team"]] for p in chosen)
    # die Liste enthält die Bank: W1 hat mindestens einen Bank-Spieler unter den Top 10
    assert any(p["slot"] == "Bank" for p in rec["top_scorer"][1])


def test_records_json_und_deterministisch(rec, ssn, weeks, team_weeks):
    """Ausgabe ist nach rounded() JSON-fähig, ohne verbotene Schlüssel, und ein zweiter Lauf ist byte-gleich."""
    text = json.dumps(rounded(rec), ensure_ascii=False, sort_keys=False)
    again = json.dumps(rounded(records.compute_records(ssn, weeks, team_weeks)), ensure_ascii=False)
    assert text == again
    assert not keys_deep(rec) & FORBIDDEN


# ---------------------------------------------------------------- konstruierte Team-Wochen

def tw(team: int, week: int, opp: int | None, pf, pa, bench="0", verschenkt="0") -> dict:
    pf, pa = Decimal(str(pf)), Decimal(str(pa))
    return {"team_id": team, "week": week, "opponent_id": opp, "pf": pf, "pa": pa,
            "result": "W" if pf > pa else "L" if pf < pa else "T",
            "bench": Decimal(bench), "verschenkt": Decimal(verschenkt)}


def game(week: int, a: int, pa, b: int, pb, **extra) -> list[dict]:
    return [tw(a, week, b, pa, pb, **extra), tw(b, week, a, pb, pa, **extra)]


def test_serien_konstruiert_gleichstand_und_unentschieden():
    """Team 1: W W L W W (zwei Serien der Länge 2), Team 2: W W T W (T unterbricht), Team 3: L L L L L."""
    rows = []
    for week, (r1, r2) in enumerate([("W", "W"), ("W", "W"), ("L", "T"), ("W", "W"), ("W", None)], start=1):
        rows.append(tw(1, week, 3, 100 if r1 == "W" else 90, 95))
        if r2:
            rows.append(tw(2, week, 4, {"W": 100, "T": 95}[r2], 95))
        rows.append(tw(3, week, 1, 80, 100))
    wins = records.longest_streaks(rows, "W")
    assert [(e["team_id"], e["weeks"], e["wert"], e["laufend"]) for e in wins] == [
        (1, [1, 2], 2, False), (2, [1, 2], 2, False), (1, [4, 5], 2, True)]
    losses = records.longest_streaks(rows, "L")
    assert [(e["team_id"], e["weeks"], e["wert"], e["laufend"]) for e in losses] == [(3, [1, 5], 5, True)]
    assert records.result_runs([r for r in rows if r["team_id"] == 2]) == [
        ("W", 1, 2, 2), ("T", 3, 3, 1), ("W", 4, 4, 1)]


def test_rekorde_konstruiert_gleichstand():
    """Gleichstand liefert alle Einträge; ein Unentschieden ist das knappste Ergebnis, aber kein Sieg/Verlierer."""
    rows = (game(1, 1, 150, 2, 100, bench="30", verschenkt="12") + game(1, 3, 120, 4, 120)
            + game(2, 1, 100, 3, 150, bench="30") + game(2, 2, 90, 4, 140))
    rs = records.season_records(rows, {})
    assert team_week_set(rs["hoechster_score"]) == {(1, 1, Decimal(150)), (2, 3, Decimal(150))}
    assert team_week_set(rs["niedrigster_score"]) == {(2, 2, Decimal(90))}
    assert [(e["week"], e["team_ids"], e["wert"]) for e in rs["groesster_sieg"]] == [
        (1, [1, 2], Decimal(50)), (2, [3, 1], Decimal(50)), (2, [4, 2], Decimal(50))]
    assert [(e["week"], e["team_ids"], e["punkte"], e["wert"], e["unentschieden"]) for e in rs["knappstes_ergebnis"]] \
        == [(1, [3, 4], [Decimal(120), Decimal(120)], ZERO, True)]
    # Verlierer/Sieger ohne Unentschieden
    assert team_week_set(rs["hoechster_verlierer"]) == {(1, 2, Decimal(100)), (2, 1, Decimal(100))}
    assert team_week_set(rs["niedrigster_sieger"]) == {(2, 4, Decimal(140))}
    assert team_week_set(rs["hoechste_bank"]) == {(1, 1, Decimal(30)), (1, 2, Decimal(30)),
                                                  (2, 1, Decimal(30)), (2, 3, Decimal(30))}
    assert team_week_set(rs["meiste_verschenkt"]) == {(1, 1, Decimal(12)), (1, 2, Decimal(12))}
    assert rs["bester_spieler"] == []  # ohne Kaderzeilen


def roster_row(team, slot, pid, pos, actual, projection=0) -> RosterRow:
    return RosterRow(team, slot, pid, pos, f"Spieler {pid}", 1, Decimal(str(actual)), Decimal(str(projection)),
                     True, None)


def test_playoffs_bye_wird_uebersprungen():
    """Playoff-Team-Wochen: Bye (ohne Gegner) zählt nirgends, auch nicht für Serien, Spieler oder Positionen."""
    rows = game(15, 1, 200, 2, 150) + [tw(3, 15, None, 999, 0, bench="500")] + game(16, 1, 180, 3, 170) \
        + game(17, 1, 190, 2, 185)
    rosters = {15: [roster_row(1, 0, 11, 1, 40), roster_row(3, 0, 31, 1, 90)], 16: [], 17: []}
    rs = records.season_records(rows, rosters)
    assert team_week_set(rs["hoechster_score"]) == {(15, 1, Decimal(200))}
    assert team_week_set(rs["hoechste_bank"]) == {(w, t, ZERO) for w, t in
                                                  [(15, 1), (15, 2), (16, 1), (16, 3), (17, 1), (17, 2)]}
    assert [(e["team_id"], e["weeks"], e["wert"]) for e in rs["laengste_siegesserie"]] == [(1, [15, 17], 3)]
    assert [(e["player_id"], e["wert"]) for e in rs["bester_spieler"]] == [(11, Decimal(40))]
    assert 3 not in {t for t, p in records.positions(rows[:2] + rows[2:3], rosters).items()}


def test_bester_spieler_konstruiert():
    """Bester Spieler: IR zählt nicht, Bank schon; Gleichstand liefert alle; nur Team-Wochen mit Spiel."""
    rows = game(1, 1, 100, 2, 90) + game(2, 1, 100, 2, 90)
    rosters = {1: [roster_row(1, 21, 1, 2, 80), roster_row(1, 20, 2, 3, 45), roster_row(2, 0, 3, 1, 30)],
               2: [roster_row(2, 4, 4, 3, 45), roster_row(3, 0, 5, 1, 99)]}  # Team 3 ohne Spiel in W2
    best = records.season_records(rows, rosters)["bester_spieler"]
    assert [(e["week"], e["team_id"], e["player_id"], e["slot"], e["pos"], e["wert"]) for e in best] == [
        (1, 1, 2, "Bank", "WR", Decimal(45)), (2, 2, 4, "WR", "WR", Decimal(45))]


def test_nur_unentschieden_kein_groesster_sieg():
    """Ein Unentschieden ist kein Sieg: ohne Sieg bleibt „größter Sieg“ leer, Sieger- und Verlierer-Rekorde auch."""
    rs = records.season_records(game(1, 1, 120, 2, 120), {})
    assert rs["groesster_sieg"] == [] and rs["hoechster_verlierer"] == [] and rs["niedrigster_sieger"] == []
    assert [(e["team_ids"], e["wert"], e["unentschieden"]) for e in rs["knappstes_ergebnis"]] == [([1, 2], ZERO, True)]
    assert rs["laengste_siegesserie"] == [] and rs["laengste_niederlagenserie"] == []


def test_compute_records_ohne_wochen(ssn):
    """n = 0: alle 45 Paare mit Nullen, keine Rekorde, keine Positionen, keine Top-Scorer."""
    rec0 = records.compute_records(ssn, [], [])
    assert len(rec0["h2h"]) == 45 and all(p["spiele"] == 0 and p["pf_diff"] == ZERO for p in rec0["h2h"])
    assert all(v == [] for v in rec0["records_rs"].values())
    assert rec0["positions"] == {} and rec0["top_scorer"] == {}


def test_h2h_konstruiert():
    """Paare a < b mit W-L-T aus Sicht von a und Σ PF-Differenz; ohne team_ids nur Teams aus team_weeks."""
    rows = game(1, 2, 110, 1, 100) + game(2, 1, 120, 2, 120) + game(3, 1, 130, 2, 100) + game(3, 3, 90, 4, 80)
    pairs = {(p["a"], p["b"]): p for p in records.h2h(rows)}
    assert len(pairs) == 6
    assert pairs[(1, 2)] == {"a": 1, "b": 2, "spiele": 3, "w_a": 1, "l_a": 1, "t": 1, "pf_diff": Decimal(20)}
    assert pairs[(3, 4)]["w_a"] == 1 and pairs[(1, 3)]["spiele"] == 0
    assert len(records.h2h(rows, [1, 2, 3, 4, 5])) == 10


def test_positionen_konstruiert():
    """Anteil = Punkte / Summe × 100, Ligarang mit geteiltem besseren Rang, Bank und IR zählen nicht."""
    rosters = {1: [roster_row(1, 0, 1, 1, 30), roster_row(1, 7, 2, 1, 10), roster_row(1, 23, 3, 2, 10),
                   roster_row(1, 20, 4, 3, 50), roster_row(1, 21, 5, 3, 60),
                   roster_row(2, 0, 6, 1, 30), roster_row(2, 16, 7, 16, 20)]}
    pos = records.positions(game(1, 1, 50, 2, 50), rosters)
    assert pos[1]["summe"] == Decimal(50) and pos[2]["summe"] == Decimal(50)
    assert pos[1]["nach_position"]["QB"] == {"pts": Decimal(40), "anteil": Decimal(80), "rang": 1}
    assert pos[1]["nach_slot"]["QB"] == {"pts": Decimal(30), "anteil": Decimal(60), "rang": 1}
    assert pos[2]["nach_slot"]["QB"]["rang"] == 1  # Gleichstand 30 = 30 teilt Rang 1
    assert pos[1]["nach_slot"]["OP"]["pts"] == Decimal(10) and pos[1]["nach_slot"]["FLEX"]["pts"] == Decimal(10)
    assert pos[1]["nach_position"]["D/ST"]["rang"] == 2
    with pytest.raises(ValueError):
        records.positions(game(1, 1, 50, 2, 50), {1: [roster_row(1, 1, 9, 1, 5)]})  # Slot 1 gibt es in der Liga nicht


def test_top_scorer_gleichstand_und_ir():
    """Gleichstand auf Platz n verlängert die Liste; IR zählt nicht, Bank schon."""
    rows = [roster_row(1, 20, pid, 3, pts) for pid, pts in [(1, 30), (2, 20), (3, 20), (4, 10)]] \
        + [roster_row(2, 21, 5, 3, 99)]
    top = records.top_scorer({4: rows}, n=2, abbrev={1: "ATL"})
    assert list(top) == [4]
    assert [(p["player_id"], p["rang"], p["slot"], p["nfl"]) for p in top[4]] == [
        (1, 1, "Bank", "ATL"), (2, 2, "Bank", "ATL"), (3, 2, "Bank", "ATL")]
    assert records.top_scorer({4: rows[:1]}, n=2)[4][0]["nfl"] is None  # weniger als n Spieler, Kürzel unbekannt


# ---------------------------------------------------------------- Transaktionen konstruiert

def entry(tid, kind, team, status="EXECUTED", items=(), proposed=1000, processed=None, period=1) -> dict:
    t = {"id": tid, "type": kind, "teamId": team, "proposedDate": proposed, "scoringPeriodId": period,
         "items": list(items), "memberId": "{GEHEIM}", "isLeagueManager": False, "bidAmount": 0}
    if status is not None:
        t["status"] = status
    if processed is not None:
        t["processDate"] = processed
    return t


def item(kind, pid, frm, to) -> dict:
    return {"type": kind, "playerId": pid, "fromTeamId": frm, "toTeamId": to, "fromLineupSlotId": -1,
            "toLineupSlotId": 20, "isKeeper": False, "overallPickNumber": 0}


CONSTRUCTED = [
    entry("w-ok", "WAIVER", 1, items=[item("ADD", 11, 0, 1), item("DROP", 12, 1, 0)], proposed=500, processed=2000),
    entry("w-fail", "WAIVER", 2, status="FAILED_INVALIDPLAYERSOURCE", items=[item("ADD", 11, 0, 2)], processed=2000),
    entry("w-cancel", "WAIVER", 3, status="CANCELED", items=[item("ADD", 13, 0, 3)]),
    entry("fa", "FREEAGENT", 2, items=[item("ADD", 14, 0, 2)], proposed=1500),
    entry("trade", "TRADE_ACCEPT", 4, status=None, proposed=1200),
    entry("trade-x", "TRADE_ACCEPT", 5, status="CANCELED", proposed=1300),
    entry("proposal", "TRADE_PROPOSAL", 5, status="PENDING", items=[item("TRADE", 15, 5, 6)], proposed=1100),
    entry("draft", "DRAFT", 1, items=[item("DRAFT", 16, 0, 1)], proposed=100),
    entry("lineup", "ROSTER", 1, items=[item("LINEUP", 11, 0, 0), item("LINEUP", 17, 0, 0)], proposed=3000),
    entry("future", "FUTURE_ROSTER", 1, items=[item("LINEUP", 11, 0, 0)], proposed=3100),
    entry("drop", "ROSTER", 3, items=[item("DROP", 18, 3, 0)], proposed=3200, period=0),
]
NAMES = {11: "Spieler Elf", 12: "Spieler Zwölf", 14: "Spieler Vierzehn", 18: "Spieler Achtzehn"}


def test_transaktionsfilter_konstruiert():
    """Nur ausgeführte Moves und angenommene Trades; Datum processDate sonst proposedDate; sortiert nach Datum."""
    moves = records.transaction_list(CONSTRUCTED, NAMES)
    assert [(m["id"], m["type"], m["team_id"], m["datum"], m["periode"]) for m in moves] == [
        ("trade", "TRADE_ACCEPT", 4, 1200, 1), ("fa", "FREEAGENT", 2, 1500, 1), ("w-ok", "WAIVER", 1, 2000, 1),
        ("drop", "ROSTER", 3, 3200, 0)]
    by_id = {m["id"]: m for m in moves}
    assert by_id["trade"]["items"] == []
    assert by_id["w-ok"]["items"] == [
        {"type": "ADD", "player_id": 11, "name": "Spieler Elf", "from_team_id": 0, "to_team_id": 1},
        {"type": "DROP", "player_id": 12, "name": "Spieler Zwölf", "from_team_id": 1, "to_team_id": 0}]
    assert by_id["drop"]["items"][0]["type"] == "DROP"
    assert not keys_deep(moves) & FORBIDDEN and "bidAmount" not in keys_deep(moves)


def test_aufstellungswechsel_konstruiert():
    """ROSTER/FUTURE_ROSTER mit LINEUP-Item je Team; reine Drops und andere Typen zählen nicht; alle Teams mit 0."""
    assert records.lineup_changes(CONSTRUCTED, [1, 2, 3, 4]) == {1: 2, 2: 0, 3: 0, 4: 0}


def test_draft_konstruiert():
    picks = [{"overallPickNumber": 2, "roundId": 1, "roundPickNumber": 2, "teamId": 7, "playerId": 12, "keeper": True},
             {"overallPickNumber": 1, "roundId": 1, "roundPickNumber": 1, "teamId": 3, "playerId": 99, "keeper": False}]
    assert records.draft_list(picks, NAMES) == [
        {"pick": 1, "runde": 1, "runden_pick": 1, "team_id": 3, "player_id": 99, "name": None, "keeper": False},
        {"pick": 2, "runde": 1, "runden_pick": 2, "team_id": 7, "player_id": 12, "name": "Spieler Zwölf",
         "keeper": True}]


class FakeSeason:
    """Minimaler Ersatz für rawdata.Season: Kader und Pool je Woche."""

    def __init__(self, through: int, rosters: dict, pools: dict):
        self.through, self._rosters, self._pools = through, rosters, pools

    def roster(self, week):
        return self._rosters.get(week, [])

    def pool(self, week):
        return self._pools.get(week)


def test_spielernamen_juengste_woche_gewinnt():
    """Namen aus Kader und Pool der Wochen 1…through; die jüngere Woche gewinnt, leere Namen und Woche > through nicht."""
    pool_row = lambda pid, name: rawdata.PoolRow(pid, name, 3, 1, 0, None, None, None, None, None, False)  # noqa: E731
    fake = FakeSeason(2, {1: [roster_row(1, 20, 7, 3, 0)._replace(name="Alt")],
                          2: [roster_row(1, 20, 7, 3, 0)._replace(name="Neu")],
                          3: [roster_row(1, 20, 8, 3, 0)._replace(name="Zu spät")]},
                      {1: [pool_row(9, "Pool"), pool_row(10, "")], 2: None})
    assert records.player_names(fake) == {7: "Neu", 9: "Pool"}


def test_letzte_14_tage_ab_archivdatum():
    """„letzte“ zählt ab dem jüngsten Datum der Liste (nicht ab heute); die Grenze selbst liegt außerhalb."""
    day = records.DAY_MS
    moves = [{"id": str(d), "datum": d * day} for d in (1, 16, 17, 30)]
    assert [m["id"] for m in records.recent(moves, 30 * day)] == ["17", "30"]
    assert records.recent([], None) == []


# ---------------------------------------------------------------- Transaktionen am echten Archiv

def test_transaktionen_echtes_archiv(tx, ssn):
    """Alle ausgeführten WAIVER/FREEAGENT und TRADE_ACCEPT sind drin, keine gescheiterten oder zurückgezogenen."""
    archive = ssn.transactions()
    ids = {m["id"] for m in tx["items"]}
    executed = {t["id"] for t in archive if t["type"] in records.MOVE_TYPES and t.get("status") == "EXECUTED"}
    rejected = {t["id"] for t in archive if t.get("status") not in ("EXECUTED", None)}
    trades = {t["id"] for t in archive if t["type"] == "TRADE_ACCEPT"}
    assert executed <= ids and trades <= ids and not rejected & ids
    assert not {t["id"] for t in archive if t["type"] == "DRAFT"} & ids
    assert {m["type"] for m in tx["items"]} <= {"WAIVER", "FREEAGENT", "ROSTER", "FUTURE_ROSTER", "TRADE_ACCEPT"}
    # Namen kommen aus Kader und Pool bis through (hier 2). Das Archiv wächst täglich weiter; ein Spieler, der erst
    # nach through in ESPNs Pool kam, hat dann noch keinen Namen (None) – das darf die tägliche Action nicht rot machen.
    known = [m for m in tx["items"] if (m["periode"] or 0) <= ssn.through]
    for m in tx["items"]:
        if m["type"] == "TRADE_ACCEPT":
            assert m["items"] == [] and m["datum"]
        else:
            assert m["items"] and all(i["type"] in ("ADD", "DROP") for i in m["items"])
        assert all(i["name"] is None or isinstance(i["name"], str) for i in m["items"])
    assert all(i["name"] for m in known for i in m["items"])  # Messung: 0 IDs ohne Namen
    assert [(m["datum"], m["id"]) for m in tx["items"]] == sorted((m["datum"], m["id"]) for m in tx["items"])
    assert tx["bis"] == max(m["datum"] for m in tx["items"])
    assert tx["letzte"] == [m for m in tx["items"] if m["datum"] > tx["bis"] - 14 * records.DAY_MS]
    # spieler: jede genannte ID, passend zu den Namen in items und draft; bis through und im Draft mit Namen
    named = {(i["player_id"], i["name"]) for m in tx["items"] for i in m["items"]} \
        | {(d["player_id"], d["name"]) for d in tx["draft"]}
    assert set(tx["spieler"].items()) == named
    assert all(tx["spieler"][i["player_id"]] for m in known for i in m["items"])
    assert all(tx["spieler"][d["player_id"]] for d in tx["draft"])


def test_aufstellungswechsel_echtes_archiv(tx, ssn):
    archive = ssn.transactions()
    lineup = [t for t in archive if t["type"] in records.LINEUP_TYPES and t.get("status") == "EXECUTED"
              and any(i["type"] == "LINEUP" for i in t["items"])]
    assert sorted(tx["aufstellungswechsel"]) == [t["id"] for t in ssn.teams()]
    assert sum(tx["aufstellungswechsel"].values()) == len(lineup)
    # reine Drops in ROSTER-Einträgen stehen als Move in items, nicht bei den Aufstellungswechseln
    drops = {t["id"] for t in archive if t["type"] in records.LINEUP_TYPES and t.get("status") == "EXECUTED"
             and any(i["type"] == "DROP" for i in t["items"])}
    assert drops <= {m["id"] for m in tx["items"]}


def test_draft_echt(tx, ssn):
    raw = ef.load_json(ef.season_files(2026)["draft"])["draftDetail"]["picks"]
    assert [d["pick"] for d in tx["draft"]] == sorted(p["overallPickNumber"] for p in raw)
    assert sum(d["keeper"] for d in tx["draft"]) == sum(1 for p in raw if p["keeper"])
    assert all(d["name"] for d in tx["draft"])
    assert {d["team_id"] for d in tx["draft"]} == {t["id"] for t in ssn.teams()}


def test_transaktionen_ohne_verbotene_schluessel(tx):
    assert not keys_deep(tx) & FORBIDDEN
    json.dumps(rounded(tx), ensure_ascii=False)
