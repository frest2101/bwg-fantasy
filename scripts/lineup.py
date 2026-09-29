"""Aufstellungsregeln der Liga: Slot- und Positionskennungen und die beste mögliche Aufstellung.

Starter-Slots laut CLAUDE.md: QB, 2 RB, 3 WR, TE, 2 FLEX (RB/WR/TE), OP (QB/RB/WR/TE), 2 D/ST, K = 13 Starter.
"""

from decimal import Decimal

from zahlen import ZERO

# Lineup-Slot-IDs (lineupSlotId)
SLOT_QB, SLOT_RB, SLOT_WR, SLOT_TE, SLOT_OP, SLOT_DST, SLOT_K, SLOT_BENCH, SLOT_IR, SLOT_FLEX = 0, 2, 4, 6, 7, 16, 17, 20, 21, 23
SLOT_NAMES = {SLOT_QB: "QB", SLOT_RB: "RB", SLOT_WR: "WR", SLOT_TE: "TE", SLOT_OP: "OP", SLOT_DST: "D/ST",
              SLOT_K: "K", SLOT_BENCH: "Bank", SLOT_IR: "IR", SLOT_FLEX: "FLEX"}
# Positionen (defaultPositionId)
QB, RB, WR, TE, K, DST = 1, 2, 3, 4, 5, 16
POSITION_NAMES = {QB: "QB", RB: "RB", WR: "WR", TE: "TE", K: "K", DST: "D/ST"}
# Basis-Slots der Aufstellung in Anzeigereihenfolge: (Position, Zahl der Slots); danach 2 FLEX und OP
BASE_SLOTS = ((QB, 1), (RB, 2), (WR, 3), (TE, 1), (DST, 2), (K, 1))


def is_starter(slot: int) -> bool:
    return slot not in (SLOT_BENCH, SLOT_IR)


def optimal_lineup(players: list[tuple]) -> list[tuple[str, tuple | None]]:
    """Beste Aufstellung nach CLAUDE.md als Liste (Slot-Name, Eintrag) über alle 13 Starter-Slots.

    Einträge sind Tupel (Position, Wert, …): weitere Elemente (z. B. die Spieler-ID) machen die Reihenfolge bei
    gleichem Wert eindeutig und kennzeichnen den Spieler. Basis = QB1 + RB1–2 + WR1–3 + TE1 + D/ST1–2 + K1. Die
    übrigen RB/WR/TE („Reste“) füllen 2 FLEX und OP: opt1 = drei beste Reste, opt2 = QB2 + zwei beste Reste; bei
    Gleichstand opt1. Ein Slot ohne passenden Spieler bleibt None (Wert 0). Dieselbe Regel gilt für Projektionen
    (Kader-Projektion, Bedarf) wie für Ist-Punkte.
    """
    order = sorted(range(len(players)), key=lambda i: (-players[i][1], players[i][2:]))
    by_pos = {pos: [i for i in order if players[i][0] == pos] for pos in (QB, RB, WR, TE, K, DST)}
    lineup = []
    for pos, n in BASE_SLOTS:
        picks = by_pos[pos][:n]
        lineup += [(POSITION_NAMES[pos], players[i]) for i in picks] + [(POSITION_NAMES[pos], None)] * (n - len(picks))
    leftover = set(by_pos[RB][2:] + by_pos[WR][3:] + by_pos[TE][1:])
    rest = [i for i in order if i in leftover]
    value = lambda i: players[i][1] if i is not None else ZERO  # noqa: E731
    qb2 = by_pos[QB][1] if len(by_pos[QB]) > 1 else None
    opt1 = sum((value(i) for i in rest[:3]), ZERO)
    opt2 = value(qb2) + sum((value(i) for i in rest[:2]), ZERO)
    flex = rest[:2] + [None] * (2 - len(rest[:2]))
    op = qb2 if opt2 > opt1 else (rest[2] if len(rest) > 2 else None)
    lineup += [("FLEX", players[i] if i is not None else None) for i in flex]
    lineup.append(("OP", players[op] if op is not None else None))
    return lineup


def optimal_points(players: list[tuple[int, Decimal]]) -> Decimal:
    """Punkte der besten Aufstellung (optimal_lineup) aus (Position, Punkte) aller startfähigen Spieler."""
    return sum((entry[1] for _, entry in optimal_lineup(players) if entry is not None), ZERO)
