"""Tests Liga-Historie (data/history, einmaliger Notion-Export) gegen docs/referenz_historie.md und auf innere Stimmigkeit.

Aufruf: python -m pytest
"""

import csv
from collections import defaultdict
from decimal import Decimal

import pytest

import espn_fetch as ef

HISTORY = ef.REPO_DIR / "data" / "history"
REFERENZ = ef.REPO_DIR / "docs" / "referenz_historie.md"


def rows(name: str) -> list[dict]:
    with open(HISTORY / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


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


TEAM_SEASONS = rows("team_seasons.csv")
SEASONS = {int(r["season"]): r for r in rows("seasons.csv")}
BY_SEASON = defaultdict(list)
for r in TEAM_SEASONS:
    BY_SEASON[int(r["season"])].append(r)


@pytest.mark.parametrize("row", table("Summen je Franchise"), ids=lambda r: f"Slot {r[0]}")
def test_summen_je_franchise(row):
    slot, n, w, l, pf, pa, division, div_rank, final_rank, playoffs, scoring = row
    mine = [r for r in TEAM_SEASONS if r["slot"] == slot]
    assert len(mine) == int(n)
    for field, expected in (("w", w), ("l", l), ("division", division), ("div_rank", div_rank),
                            ("final_rank", final_rank), ("playoffs", playoffs), ("scoring_title", scoring)):
        assert sum(int(r[field]) for r in mine) == int(expected), field
    assert sum(Decimal(r["pf"]) for r in mine) == num(pf)
    assert sum(Decimal(r["pa"]) for r in mine) == num(pa)


@pytest.mark.parametrize("season", sorted(BY_SEASON))
def test_saison_in_sich_stimmig(season):
    teams, meta = BY_SEASON[season], SEASONS[season]
    assert len(teams) == int(meta["teams"])
    assert all(int(r["w"]) + int(r["l"]) == int(meta["rs_games"]) for r in teams)
    assert sorted(int(r["final_rank"]) for r in teams) == list(range(1, len(teams) + 1))
    assert all((int(r["final_rank"]) <= 6) == (r["playoffs"] == "1") for r in teams)
    for division in {r["division"] for r in teams}:
        members = [r for r in teams if r["division"] == division]
        assert sorted(int(r["div_rank"]) for r in members) == list(range(1, len(members) + 1))
    top = max(teams, key=lambda r: Decimal(r["pf"]))
    assert [r["slot"] for r in teams if r["scoring_title"] == "1"] == [top["slot"]]


@pytest.mark.parametrize("row", table("Champions"), ids=lambda r: r[0])
def test_champions(row):
    season, slot, team = row
    champion = next(r for r in BY_SEASON[int(season)] if r["final_rank"] == "1")
    assert (champion["slot"], champion["team_name"]) == (slot, team)


def test_zaehler():
    counts = dict((r[0], int(r[1])) for r in table("Zähler"))
    assert sum(r["final_rank"] == "1" for r in TEAM_SEASONS) == counts["Titel"]
    assert sum(r["div_rank"] == "1" for r in TEAM_SEASONS) == counts["Divisionssiege"]
    assert sum(r["scoring_title"] == "1" for r in TEAM_SEASONS) == counts["Scoring-Titel"]
    last = sum(int(r["final_rank"]) == int(SEASONS[int(r["season"])]["teams"]) for r in TEAM_SEASONS)
    assert last == counts["Letzte"]


def test_franchises_und_einzelspiele():
    slots = {r["slot"] for r in rows("franchises.csv")}
    assert slots == {str(s) for s in range(1, 11)} == {r["slot"] for r in TEAM_SEASONS}
    for m in rows("matchups_hist.csv"):
        assert m["winner_slot"] in (m["slot_a"], m["slot_b"])
        assert m["status"] in ("final", "live", "partial")
        if m["status"] == "final":
            winner_pts = m["pts_a"] if m["winner_slot"] == m["slot_a"] else m["pts_b"]
            assert Decimal(winner_pts) == max(Decimal(m["pts_a"]), Decimal(m["pts_b"]))
