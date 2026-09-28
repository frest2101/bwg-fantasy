"""Tests Rechenwerk (Baustein 2) gegen docs/referenz_w1-w2.md (Record Book 2.7).

Die Sollwerte werden aus der Referenzdatei gelesen, nicht abgeschrieben – jede Zahl steht nur dort.
Aufruf: python -m pytest
"""

from decimal import ROUND_HALF_UP, Decimal

import pytest

import compute
import espn_fetch as ef

REFERENZ = ef.REPO_DIR / "docs" / "referenz_w1-w2.md"
TOLERANZ = Decimal("0.01")


def table(heading: str) -> list[list[str]]:
    """Datenzeilen der Markdown-Tabelle unter der Überschrift „## <heading>…“ (ohne Kopf und Trennlinie)."""
    for block in REFERENZ.read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        if title.startswith(heading):
            rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                    for line in body.splitlines() if line.startswith("|")]
            return rows[2:]
    raise LookupError(f"Abschnitt „{heading}“ fehlt in {REFERENZ.name}")


def num(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def close(value: Decimal, text: str) -> bool:
    return abs(value - num(text)) <= TOLERANZ


@pytest.fixture(scope="module")
def season():
    return compute.compute_season(2026, through=2)


@pytest.fixture(scope="module")
def teams(season):
    return {t["name"]: t for t in season["teams"]}


def team_week(season, name, week):
    team_id = next(t["team_id"] for t in season["teams"] if t["name"] == name)
    return next(r for r in season["team_weeks"] if r["team_id"] == team_id and r["week"] == week)


# ---------------------------------------------------------------- gegen Referenz

@pytest.mark.parametrize("row", table("Matchups"), ids=lambda r: f"W{r[0]} {r[1]}–{r[3]}")
def test_matchup_punkte(season, row):
    """Paarung und Punkte; die Seite (Heim/Gast) zählt nicht."""
    week, a, points_a, b, points_b = row
    row_a, row_b = team_week(season, a, int(week)), team_week(season, b, int(week))
    assert row_a["opponent_id"] == row_b["team_id"]
    assert close(row_a["pf"], points_a) and close(row_b["pf"], points_b)


@pytest.mark.parametrize("row", table("Saisontabelle"), ids=lambda r: r[0])
def test_saisontabelle(season, teams, row):
    name, wl, pf, pa, allplay, verschenkt, einzeln = row
    t = teams[name]
    assert f"{t['w']}-{t['l']}" == wl
    assert close(t["pf"], pf) and close(t["pa"], pa)
    assert f"{t['allplay_w']}-{t['allplay_l']}" == allplay
    assert close(t["verschenkt"], verschenkt)
    week, value = einzeln.split()  # z. B. „W1 49,37“
    assert close(team_week(season, name, int(week[1:]))["verschenkt"], value)


@pytest.mark.parametrize("row", table("Score-Probe"), ids=lambda r: r[1])
def test_score_probe(teams, row):
    rang, name, score = row
    t = teams[name]
    assert t["score"]["Stärke"]["minmax"].quantize(Decimal(1), rounding=ROUND_HALF_UP) == Decimal(score)
    assert t["rang_score"] == int(rang)


def test_top_team_je_woche(season):
    by_id = {t["team_id"]: t["name"] for t in season["teams"]}
    for w in season["weeks"]:
        rows = [r for r in table("Matchups") if int(r[0]) == w["week"]]
        scores = [(r[1], num(r[2])) for r in rows] + [(r[3], num(r[4])) for r in rows]
        assert by_id[w["top_team_id"]] == max(scores, key=lambda s: s[1])[0]


# ---------------------------------------------------------------- gegen Zweitreferenz (Notion-Werte Session G1, gerundet)

@pytest.mark.parametrize("row", table("Zweitreferenz G1 – Ränge"), ids=lambda r: r[0])
def test_g1_raenge_form_streak_restspielplan(teams, row):
    name, rang, rang_division, rang_score, form, streak, restspielplan = row
    t = teams[name]
    assert (t["rang"], t["rang_division"], t["rang_score"]) == (int(rang), int(rang_division), int(rang_score))
    assert t["streak"] == streak
    assert abs(t["form"] - num(form)) <= Decimal("0.011")  # G1 rundete 278,905 per Float auf 278,9
    assert abs(t["restspielplan"] - num(restspielplan)) <= Decimal("0.051")


@pytest.mark.parametrize("kind, heading, toleranz", [
    ("minmax", "Zweitreferenz G1 – Min–Max", "0.051"),
    ("rank", "Zweitreferenz G1 – Rangpunkte", "0"),
    ("z", "Zweitreferenz G1 – z-Score", "0.0051"),
])
def test_g1_normierung(teams, kind, heading, toleranz):
    for name, *values in table(heading):
        for metric, value in zip(compute.METRICS, values, strict=True):
            assert abs(teams[name]["norm"][kind][metric] - num(value)) <= Decimal(toleranz), f"{name} {metric}"


# ---------------------------------------------------------------- Prüfpunkte und Regeln ohne Referenzwert

def test_starter_summe_gleich_pf(season):
    """Prüfpunkt 1 (Umbau-Plan): Summe der Starter-Punkte = PF, 20/20 Team-Wochen."""
    assert len(season["team_weeks"]) == 20
    for r in season["team_weeks"]:
        assert ef.to_points(r["abweichung"]) == 0, f"W{r['week']} Team {r['team_id']}"


@pytest.mark.parametrize("metric", compute.METRICS)
def test_normierung(season, metric):
    minmax = [t["norm"]["minmax"][metric] for t in season["teams"]]
    ranks = [t["norm"]["rank"][metric] for t in season["teams"]]
    z = [t["norm"]["z"][metric] for t in season["teams"]]
    assert (min(minmax), max(minmax)) in ((0, 100), (50, 50))
    assert max(ranks) == len(ranks) and min(ranks) >= 1
    assert abs(sum(z)) < Decimal("1e-9")


@pytest.mark.parametrize("profile", compute.PROFILES)
def test_profil_gewichte(profile):
    assert sum(compute.PROFILES[profile].values()) == 100


def test_nur_abgeschlossene_wochen_der_regular_season():
    assert compute.last_regular_week(2026) == 14
    assert compute.completed_weeks(2026, through=2) == [1, 2]
    with pytest.raises(ef.FetchError, match="Regular Season"):
        compute.completed_weeks(2026, through=15)
    with pytest.raises(ef.FetchError, match="nicht abgeschlossen"):
        compute.completed_weeks(2026, through=14)


def test_streak():
    assert compute.streak(["W"]) == "W1"
    assert compute.streak(["W", "L", "L"]) == "L2"
    assert compute.streak(["L", "W", "W", "W"]) == "W3"


# ---------------------------------------------------------------- Optimal-Regel an konstruierten Kadern

def roster(*players):
    return [(pos, Decimal(str(points))) for pos, points in players]


def test_optimal_opt1_drei_reste():
    # Basis 20 + 15 + 14 + 12 + 11 + 10 + 7 + 5 + 4 + 3 = 101; Reste 13, 9, 8, 6; QB2 5
    players = roster((1, 20), (1, 5), (2, 15), (2, 14), (2, 13), (3, 12), (3, 11), (3, 10), (3, 9), (3, 8),
                     (4, 7), (4, 6), (16, 5), (16, 4), (5, 3))
    assert compute.optimal_points(players) == 101 + 13 + 9 + 8


def test_optimal_opt2_qb2_im_op():
    # wie oben, aber QB2 = 25 (QB1 = 30): opt2 = 25 + 13 + 9 schlägt opt1 = 13 + 9 + 8
    players = roster((1, 30), (1, 25), (2, 15), (2, 14), (2, 13), (3, 12), (3, 11), (3, 10), (3, 9), (3, 8),
                     (4, 7), (4, 6), (16, 5), (16, 4), (5, 3))
    assert compute.optimal_points(players) == 111 + 25 + 13 + 9


def test_optimal_zu_wenige_spieler():
    assert compute.optimal_points(roster((1, 10), (2, 5))) == 15


def entry(slot, pos, points, projection=0, week=1):
    stats = [{"seasonId": 2026, "scoringPeriodId": week, "statSourceId": 0, "statSplitTypeId": 1, "appliedTotal": points},
             {"seasonId": 2026, "scoringPeriodId": week, "statSourceId": 1, "statSplitTypeId": 1, "appliedTotal": projection}]
    return {"lineupSlotId": slot, "playerPoolEntry": {"player": {"defaultPositionId": pos, "stats": stats}}}


def test_roster_week_ir_bank_und_projektion():
    entries = [entry(0, 1, 20, projection=18), entry(20, 1, 30), entry(21, 2, 50), entry(2, 2, 10, projection=12)]
    result = compute.roster_week(entries, 2026, 1)
    assert result["starter_sum"] == 30 and result["starter_projection"] == 30
    assert result["bench"] == 30
    assert result["optimal"] == 30 + 10 + 20  # QB1 von der Bank, RB, QB2 im OP; IR-Spieler (50) zählt nicht
