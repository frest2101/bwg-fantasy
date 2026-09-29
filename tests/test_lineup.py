"""Tests Aufstellungsregel (scripts/lineup.py): optimal_lineup liefert die Slots, optimal_points ihre Summe.

Erfundene Kader aus (Position, Punkte, Kennung). Aufruf: python -m pytest tests/test_lineup.py
"""

from decimal import Decimal as D

from lineup import DST, K, QB, RB, TE, WR, optimal_lineup, optimal_points

SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "D/ST", "D/ST", "K", "FLEX", "FLEX", "OP"]


def roster(*entries):
    return [(pos, D(pts), key) for pos, pts, key in entries]


def test_slots_und_summe_voller_kader():
    """Reste RB 13, WR 9, TE 7 → opt1 = 29 < opt2 = QB2 20 + 13 + 9 = 42: QB2 im OP, RB 13 und WR 9 im FLEX."""
    players = roster((QB, 30, "q1"), (QB, 20, "q2"), (RB, 15, "r1"), (RB, 14, "r2"), (RB, 13, "r3"), (WR, 12, "w1"),
                     (WR, 11, "w2"), (WR, 10, "w3"), (WR, 9, "w4"), (TE, 8, "t1"), (TE, 7, "t2"), (K, 5, "k"),
                     (DST, 6, "d1"), (DST, 4, "d2"))
    lineup = optimal_lineup(players)
    assert [slot for slot, _ in lineup] == SLOTS
    assert [e[2] for _, e in lineup] == ["q1", "r1", "r2", "w1", "w2", "w3", "t1", "d1", "d2", "k", "r3", "w4", "q2"]
    assert optimal_points(players) == 30 + 15 + 14 + 12 + 11 + 10 + 8 + 6 + 4 + 5 + 13 + 9 + 20


def test_drei_reste_schlagen_qb2_und_gleichstand():
    """Reste RB 13, WR 6, TE 4 = 23 gegen QB2 3 + 19 = 22: drei Reste; bei Gleichstand (QB2 4) ebenfalls die Reste;
    QB2 5 (24 > 23) rückt in den OP."""
    base = [(RB, 15, "r1"), (RB, 14, "r2"), (WR, 9, "w1"), (WR, 8, "w2"), (WR, 7, "w3"), (TE, 5, "t1"), (K, 3, "k"),
            (DST, 2, "d1"), (DST, 1, "d2"), (RB, 13, "r3"), (WR, 6, "w4"), (TE, 4, "t2")]
    lineup = optimal_lineup(roster((QB, 20, "q1"), (QB, 3, "q2"), *base))
    assert [e[2] for _, e in lineup[10:]] == ["r3", "w4", "t2"]
    lineup = optimal_lineup(roster((QB, 20, "q1"), (QB, 4, "q2"), *base))
    assert [e[2] for _, e in lineup[10:]] == ["r3", "w4", "t2"]          # Gleichstand → opt1 wie bisher (max)
    lineup = optimal_lineup(roster((QB, 20, "q1"), (QB, 5, "q2"), *base))
    assert [e[2] for _, e in lineup[10:]] == ["r3", "w4", "q2"]          # 5 + 19 > 23
    assert optimal_points(roster((QB, 20, "q1"), (QB, 5, "q2"), *base)) == 20 + 15 + 14 + 9 + 8 + 7 + 5 + 3 + 2 + 1 + 24


def test_leere_slots_und_kleiner_kader():
    """Ein Kader mit QB und RB: alle übrigen Slots leer, Summe 15 (wie optimal_points bisher)."""
    lineup = optimal_lineup(roster((QB, 10, "q"), (RB, 5, "r")))
    assert [slot for slot, _ in lineup] == SLOTS
    assert [e[2] if e else None for _, e in lineup] == ["q", "r"] + [None] * 11
    assert optimal_points([(QB, D(10)), (RB, D(5))]) == 15
    assert optimal_lineup([]) == [(slot, None) for slot in SLOTS] and optimal_points([]) == 0


def test_gleichstand_deterministisch_nach_kennung():
    """Gleiche Punkte: die Kennung entscheidet, wer RB1 ist und wer in den FLEX rutscht – reproduzierbar."""
    players = roster((RB, 10, 3), (RB, 10, 1), (RB, 10, 2))
    assert [e[2] for slot, e in optimal_lineup(players) if slot in ("RB", "FLEX") and e] == [1, 2, 3]
    assert optimal_points([(RB, D(10))] * 3) == 30
