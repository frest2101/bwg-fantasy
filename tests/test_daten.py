"""Datenprüfung: neue Rohdaten (Baustein 3/4) gegen Notion-Referenzen in docs/referenz_dst.md; committete
Stat-Korrekturen (wNN/statkorrektur.json) in sich stimmig.

Die Tests laufen, sobald der Wochenabruf die Dateien geholt hat; vorher werden sie übersprungen.
Aufruf: python -m pytest
"""

import statistics
from collections import defaultdict
from decimal import Decimal

import pytest

import espn_fetch as ef

REFERENZ = ef.REPO_DIR / "docs" / "referenz_dst.md"
FILES = ef.season_files(2026)


def table(heading: str) -> list[list[str]]:
    """Datenzeilen der Markdown-Tabelle unter „## <heading>“."""
    for block in REFERENZ.read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        if title.startswith(heading):
            rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                    for line in body.splitlines() if line.startswith("|")]
            return rows[2:]
    raise LookupError(f"Abschnitt „{heading}“ fehlt in {REFERENZ.name}")


def num(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


@pytest.fixture(scope="module")
def allowed_2025() -> dict[str, float]:
    """Off. zugelassen 2025 je Offense (Kürzel groß): Ø der Punkte, die gegnerische D/ST gegen sie erzielt haben."""
    if not (FILES["prior_dst"].exists() and FILES["prior_schedule"].exists()):
        pytest.skip("D/ST-Grundlage 2025 noch nicht abgerufen (holt der Wochenabruf)")
    teams = ef.load_json(FILES["prior_schedule"])["settings"]["proTeams"]
    abbrev = {t["id"]: t["abbrev"].upper() for t in teams}
    opponent = {(t["id"], int(week)): (g["awayProTeamId"] if g["homeProTeamId"] == t["id"] else g["homeProTeamId"])
                for t in teams for week, games in (t.get("proGamesByScoringPeriod") or {}).items() for g in games}
    points = defaultdict(list)
    for entry in ef.load_json(FILES["prior_dst"])["players"]:
        player = entry["player"]
        for s in player.get("stats", []):
            if ((s.get("seasonId"), s.get("statSourceId"), s.get("statSplitTypeId")) == (2025, 0, 1)
                    and (s.get("stats") or {}).get(ef.STAT_PLAYED) == 1):
                points[abbrev[opponent[(player["proTeamId"], s["scoringPeriodId"])]]].append(s["appliedTotal"])
    return {team: statistics.mean(values) for team, values in points.items()}


def test_dst_2025_alle_offenses(allowed_2025):
    assert len(allowed_2025) == ef.NFL_TEAMS


def test_dst_2025_ligaschnitt(allowed_2025):
    ligaschnitt = dict((r[0], r[1]) for r in table("Ligaschnitt"))["Ligaschnitt 2025"]
    assert abs(Decimal(str(statistics.mean(allowed_2025.values()))) - num(ligaschnitt)) <= Decimal("0.005")


@pytest.mark.parametrize("row", table("Stichprobe"), ids=lambda r: r[0])
def test_dst_2025_gegen_notion(allowed_2025, row):
    assert abs(Decimal(str(allowed_2025[row[0]])) - num(row[1])) <= Decimal("0.005")


@pytest.mark.parametrize("path", sorted(ef.RAW_DIR.glob("*/w[0-9][0-9]/" + ef.STATKORREKTUR_FILE)), ids=ef.rel)
def test_statkorrektur_stimmig(path):
    """Jede committete Stat-Korrektur: gehört zu ihrer Woche, „vorher“ ist der Stand der Wochendatei, Ist-Einträge nur
    mit Feldern aus IST_KEEP, Σ Starter (mRoster mit Korrektur) = korrigierte Team-Summe für alle Teams der Woche, und
    die Datei ist genau so geschrieben, wie update_statkorrekturen schreibt. Ohne Korrektur: kein Testfall."""
    korr = ef.load_json(path)
    season, week = korr["season"], korr["woche"]
    assert path.parent == ef.week_dir(season, week) and (korr["spiele"] or korr["spieler"])
    assert all(set(s["ist"]) <= ef.IST_KEEP and s["ist"]["scoringPeriodId"] == week for s in korr["spieler"])
    stored = {m["id"]: m for m in ef.load_json(path.parent / "mMatchupScore.json")["schedule"]}
    for g in korr["spiele"]:
        old = stored[g["id"]]
        assert [ef.to_points(old[side]["totalPoints"]) if old.get(side) else None for side in ("home", "away")] \
            == [ef.to_points(v) if v is not None else None for v in g["vorher"]["totalPoints"]], g["id"]
    games = [{"home": {"teamId": m["home_id"], "totalPoints": m["home_points"]},
              "away": {"teamId": m["away_id"], "totalPoints": m["away_points"]}}
             for m in ef.load_week_matchups(season, week) if m["away_id"] is not None]
    roster = ef.load_json(path.parent / "mRoster.json")
    assert ef.check_statkorrektur(roster, season, week, games, korr["spieler"]) == []
    assert path.read_bytes() == ef.statkorrektur_dumps(korr)
