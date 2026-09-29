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


def is_starter(slot: int) -> bool:
    return slot not in (SLOT_BENCH, SLOT_IR)


def optimal_points(players: list[tuple[int, Decimal]]) -> Decimal:
    """Beste Aufstellung nach CLAUDE.md aus (Position, Punkte) aller startfähigen Spieler.

    Basis = QB1 + RB1–2 + WR1–3 + TE1 + D/ST1–2 + K1. Die übrigen RB/WR/TE („Reste“) füllen
    2 FLEX und OP: opt1 = drei beste Reste, opt2 = QB2 + zwei beste Reste; Optimal = Basis + max(opt1, opt2).
    Dieselbe Regel gilt für Projektionen (Kader-Projektion) wie für Ist-Punkte.
    """
    by_pos = {pos: sorted((p for q, p in players if q == pos), reverse=True) for pos in (QB, RB, WR, TE, K, DST)}
    base = sum((sum(by_pos[pos][:n], ZERO) for pos, n in {QB: 1, RB: 2, WR: 3, TE: 1, DST: 2, K: 1}.items()), ZERO)
    rest = sorted(by_pos[RB][2:] + by_pos[WR][3:] + by_pos[TE][1:], reverse=True)
    qb2 = by_pos[QB][1] if len(by_pos[QB]) > 1 else ZERO
    return base + max(sum(rest[:3], ZERO), qb2 + sum(rest[:2], ZERO))
