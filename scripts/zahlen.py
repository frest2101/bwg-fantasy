"""Zahlen und Rundung für Rechenwerk und App-Export (Baustein 4).

Gerechnet wird mit ungerundeten Decimal-Werten (über str(), ohne Binär-Artefakte). Gerundet wird erst bei der
Ausgabe, round half up. Punkte zwei Stellen (CLAUDE.md), einige Kennzahlen drei (Auftrag Session 4, Frage 11 a).
"""

from decimal import ROUND_HALF_UP, Decimal

ZERO, HALF, ONE, HUNDRED = Decimal(0), Decimal("0.5"), Decimal(1), Decimal(100)


def dec(value) -> Decimal:
    """ESPN-Float oder Zahl als Decimal, über str() ohne Binär-Artefakte (ungerundet)."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def round_to(value, places: int = 2) -> Decimal:
    """Auf places Stellen, round half up."""
    return dec(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def rounded(value, places: int = 2, precision: dict[str, int] | None = None):
    """Decimal → Zahl mit places Stellen (round half up), rekursiv für dict/list.

    precision legt für einzelne Schlüssel eine andere Stellenzahl fest; sie gilt für den ganzen Teilbaum darunter,
    z. B. {"z": 3} für die z-Normwerte.
    """
    if isinstance(value, Decimal):
        number = float(round_to(value, places))
        return int(number) if places == 0 else number
    if isinstance(value, dict):
        precision = precision or {}
        return {k: rounded(v, precision.get(k, places), precision) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v, places, precision) for v in value]
    return value
