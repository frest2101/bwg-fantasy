"""Tests Rechenwerk (Baustein 2) gegen docs/referenz_w1-w2.md (Record Book 2.7).

Die Sollwerte werden aus der Referenzdatei gelesen, nicht abgeschrieben – jede Zahl steht nur dort.
Aufruf: python -m pytest
"""

import json
import shutil
from decimal import ROUND_HALF_UP, Decimal

import pytest

import compute
import espn_fetch as ef
import rawdata
from rawdata import RosterRow

REFERENZ = ef.REPO_DIR / "docs" / "referenz_w1-w2.md"
TOLERANZ = Decimal("0.01")
# Profil „Stärke“ im Stand der Referenz (Notion W2, Min–Max). Seit Session 4 gilt ein anderes Profil (Win 0, Kader 25)
# und z als Standard; die Referenz prüft deshalb mit diesen eingefrorenen Gewichten die Min–Max-Normwerte.
STAERKE_W2 = {"pf": 30, "allplay": 25, "win": 15, "coaching": 10, "kader": 10, "floor": 10, "form": 0}
# Teamnamen der Referenz → team_id, eingefroren auf den Stand von W2 (übersteht spätere Umbenennungen in ESPN)
REFERENZ_IDS = {t["name"]: t["id"] for t in ef.load_json(ef.week_dir(2026, 2) / "mTeam.json")["teams"]}


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
    """Team-Zeilen nach dem Namen aus der Referenz."""
    by_id = {t["team_id"]: t for t in season["teams"]}
    return {name: by_id[team_id] for name, team_id in REFERENZ_IDS.items()}


def team_week(season, name, week):
    return next(r for r in season["team_weeks"] if r["team_id"] == REFERENZ_IDS[name] and r["week"] == week)


@pytest.fixture(scope="module")
def score_w2(season):
    """Min–Max-Score mit den eingefrorenen W2-Gewichten und der Rang danach, je team_id."""
    scores = {t["team_id"]: compute.weighted_score(t["norm"]["minmax"], STAERKE_W2) for t in season["teams"]}
    ranks = {tid: i for i, tid in enumerate(sorted(scores, key=scores.get, reverse=True), start=1)}
    return {tid: (scores[tid], ranks[tid]) for tid in scores}


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
def test_score_probe(score_w2, row):
    rang, name, score = row
    value, rank = score_w2[REFERENZ_IDS[name]]
    assert value.quantize(Decimal(1), rounding=ROUND_HALF_UP) == Decimal(score)
    assert rank == int(rang)


def test_top_team_je_woche(season):
    for w in season["weeks"]:
        rows = [r for r in table("Matchups") if int(r[0]) == w["week"]]
        scores = [(r[1], num(r[2])) for r in rows] + [(r[3], num(r[4])) for r in rows]
        assert w["top_team_id"] == REFERENZ_IDS[max(scores, key=lambda s: s[1])[0]]


# ---------------------------------------------------------------- gegen Zweitreferenz (Notion-Werte Session G1, gerundet)

@pytest.mark.parametrize("row", table("Zweitreferenz G1 – Ränge"), ids=lambda r: r[0])
def test_g1_raenge_form_streak(teams, score_w2, row):
    """Rang Score mit den W2-Gewichten; die Spalte Restspielplan entfällt (Beschluss: erwartete Restsiege)."""
    name, rang, rang_division, rang_score, form, streak, _restspielplan = row
    t = teams[name]
    assert (t["rang"], t["rang_division"]) == (int(rang), int(rang_division))
    assert score_w2[t["team_id"]][1] == int(rang_score)
    assert t["streak"] == streak
    assert abs(t["form"] - num(form)) <= Decimal("0.011")  # G1 rundete 278,905 per Float auf 278,9


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


def test_normierung_randfaelle():
    """Alle Teams gleich: Min–Max 50, alle Rangpunkte = n, z = 0 (Std-Abw. 0)."""
    result = compute.normalize({1: Decimal(5), 2: Decimal(5), 3: Decimal(5)})
    assert set(result["minmax"].values()) == {50}
    assert set(result["rank"].values()) == {3}
    assert set(result["z"].values()) == {0}


def test_wochenrang_und_median(season):
    for week in (1, 2):
        rows = [r for r in season["team_weeks"] if r["week"] == week]
        assert sorted(r["wochenrang"] for r in rows) == list(range(1, 11))
        assert sum(r["median_win"] for r in rows) == 5  # 10 Teams, keine Gleichstände am Median
        assert all(r["wochenrang"] == 1 + r["allplay_l"] for r in rows)


@pytest.mark.parametrize("profile", compute.PROFILES)
def test_profil_gewichte(profile):
    assert sum(compute.PROFILES[profile].values()) == 100


def test_nur_regular_season():
    assert compute.last_regular_week(2026) == 14
    assert compute.completed_weeks(2026, through=2) == [1, 2]
    with pytest.raises(ef.FetchError, match="Regular Season"):
        compute.completed_weeks(2026, through=15)


def test_laufende_woche_zaehlt_nicht(tmp_path, monkeypatch):
    """Konstruierte Datenlage (unabhängig vom wachsenden Repo-Stand): W1 abgeschlossen, W2 läuft noch."""
    for week in (1, 2):
        source, target = ef.week_dir(2026, week), tmp_path / "2026" / f"w{week:02d}"
        target.mkdir(parents=True)
        for view in ("mSettings", "mTeam", "mMatchupScore"):
            shutil.copy(source / f"{view}.json", target / f"{view}.json")
    matchups = target / "mMatchupScore.json"
    data = json.loads(matchups.read_bytes())
    for m in data["schedule"]:
        if m["matchupPeriodId"] == 2:
            m["winner"] = "UNDECIDED"
    matchups.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(ef, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ef, "REPO_DIR", tmp_path.parent)

    assert compute.completed_weeks(2026) == [1]
    with pytest.raises(ef.FetchError, match="nicht abgeschlossen"):
        compute.completed_weeks(2026, through=2)


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


def test_sigma_gepoolt_mit_startwert(season):
    """σ² = (Σ Quadratsummen + 20·35²)/(Σ(n−1) + 20); nach W2 ≈ 35,52 (ohne Startwert 36,54)."""
    assert abs(season["sigma"] - Decimal("35.52")) <= Decimal("0.01")
    assert compute.pooled_sigma([]) == 35


def test_matchup_glueck(season, teams):
    """Matchup-Glück je Woche: nur, wenn das Ergebnis der Punkteseite widerspricht, Gewicht = (|PF − Median| +
    |PA − Median|) / (2σ) ≤ 1. Nach W2: Hugh Jass 0 (beide Siege über dem Median); gloane W1 Niederlage 9,91 über dem
    Median gegen Hugh Jass 22,63 darüber → −(9,91 + 22,63)/(2σ); 4th Down W2 Sieg 36,40 unter dem Median gegen
    TeamTy 67,74 darunter → gekappt +1; cool runnings W1 Sieg 14,75 unter dem Median gegen SaureGurken 58,55
    darunter → (14,75 + 58,55)/(2σ) > 1 → +1."""
    sigma, eps = season["sigma"], Decimal("1e-12")
    medians = {w["week"]: w["median"] for w in season["weeks"]}
    for t in teams.values():
        rows = [r for r in season["team_weeks"] if r["team_id"] == t["team_id"]]
        running = Decimal(0)
        for r in rows:
            assert r["median_abstand"] == r["pf"] - medians[r["week"]]
            assert r["gegner_abstand"] == r["pa"] - medians[r["week"]]
            assert (r["median_abstand"] > 0) == r["median_win"]
            expect = min(Decimal(1), (abs(r["median_abstand"]) + abs(r["gegner_abstand"])) / (2 * sigma))
            if r["result"] == "W" and r["median_abstand"] < 0:
                assert r["matchup_glueck"] == expect
            elif r["result"] == "L" and r["median_abstand"] > 0:
                assert r["matchup_glueck"] == -expect
            else:
                assert r["matchup_glueck"] == 0
            running += r["matchup_glueck"]
            assert r["matchup_kum"] == running
            assert abs(r["allplay_pct"] - (r["allplay_w"] + Decimal("0.5") * r["allplay_t"]) / 9 * 100) < eps
        assert t["matchup_glueck"] == running
        assert t["median_w"] + t["median_l"] == t["games"]
        assert abs(t["spielplan_pkt"] - sum(r["gegner_pkt"] for r in rows)) < eps
    assert teams["Hugh Jass"]["matchup_glueck"] == 0 and teams["Hugh Jass"]["median_w"] == 2
    assert abs(team_week(season, "gloane saubande", 1)["matchup_glueck"] + Decimal("32.54") / (2 * sigma)) < Decimal("1e-9")
    assert team_week(season, "4th Down Syndrom", 2)["matchup_glueck"] == 1
    assert team_week(season, "cool runnings", 1)["matchup_glueck"] == 1


def test_gegner_punkte(season):
    """Spielplan: Ligaschnitt der Woche − Gegnerpunkte; über alle Teams einer Woche Σ = 0 (jeder ist Gegner von einem)."""
    for w in season["weeks"]:
        rows = [r for r in season["team_weeks"] if r["week"] == w["week"]]
        assert all(r["gegner_pkt"] == w["ligaschnitt"] - r["pa"] for r in rows)
        assert abs(sum(r["gegner_pkt"] for r in rows)) < Decimal("1e-9")


def test_wochenwerte_effizienz_und_projektion(season):
    """Effizienz und Projektions-Delta je Woche folgen aus PF, Optimal und Starter-Projektion der Zeile;
    die Liga-Effizienz der Woche ist Σ PF / Σ Optimal (nicht der Ø der Teamwerte)."""
    for r in season["team_weeks"]:
        assert r["efficiency"] == r["pf"] / r["optimal"] * 100
        assert r["projektions_delta"] == r["pf"] - r["starter_projection"]
    for w in season["weeks"]:
        rows = [r for r in season["team_weeks"] if r["week"] == w["week"]]
        assert w["effizienz_liga"] == sum(r["pf"] for r in rows) / sum(r["optimal"] for r in rows) * 100
        assert 0 < w["effizienz_liga"] <= 100


def test_form_band():
    assert compute.form_band(Decimal(35), 3) is None  # erst ab 4 Spielen
    assert abs(compute.form_band(Decimal(35), 10) - Decimal(35) * Decimal("0.2333333333").sqrt()) < Decimal("1e-6")


def test_profil_staerke_und_z_standard(season):
    assert compute.PROFILES["Stärke"] == {"pf": 30, "allplay": 25, "win": 0, "coaching": 10, "kader": 25,
                                          "floor": 10, "form": 0}
    order = sorted(season["teams"], key=lambda t: t["score"]["Stärke"]["z"], reverse=True)
    assert [t["rang_score"] for t in order] == list(range(1, 11))
    assert all(t["kader_quelle"] == "potenzial" for t in season["teams"])  # ros.json gibt es für W2 nicht


class FakeSeason:
    """Konstruierte Rohdaten für Unentschieden: 4 Teams, eine Woche, 1–2 enden 100:100, 3 schlägt 4."""

    def __init__(self, points: dict[int, tuple[int, int]]):
        self.points = points  # team_id → (pf, gegner)

    def matchups(self, week):
        done, rows = set(), []
        for tid, (pf, opp) in self.points.items():
            if tid in done:
                continue
            done |= {tid, opp}
            rows.append({"home_id": tid, "away_id": opp, "home_points": Decimal(pf),
                         "away_points": Decimal(self.points[opp][0]), "final": True})
        return rows

    def roster(self, week):
        return [RosterRow(tid, 0, tid, 1, "", 0, Decimal(pf), Decimal(0), True, None) for tid, (pf, _) in self.points.items()]

    def teams(self):
        return [{"id": tid, "name": f"T{tid}", "divisionId": 0, "waiverRank": tid, "transactionCounter": {}}
                for tid in self.points]


def test_unentschieden_zaehlen_halb():
    fake = FakeSeason({1: (100, 2), 2: (100, 1), 3: (120, 4), 4: (80, 3)})
    rows = compute.compute_team_weeks(fake, [1])
    by_id = {r["team_id"]: r for r in rows}
    assert by_id[1]["result"] == by_id[2]["result"] == "T"
    assert (by_id[1]["allplay_w"], by_id[1]["allplay_l"], by_id[1]["allplay_t"]) == (1, 1, 1)
    assert by_id[1]["wochenrang"] == by_id[2]["wochenrang"] == 2
    compute.add_matchup(rows, Decimal(35))
    # Matchup-Glück: Unentschieden 0; Sieg über dem Median (Median 100) 0; Niederlage unter dem Median 0
    assert by_id[1]["allplay_pct"] == 50
    assert by_id[1]["matchup_glueck"] == by_id[3]["matchup_glueck"] == by_id[4]["matchup_glueck"] == 0
    assert by_id[1]["efficiency"] == 100  # der ganze Kader ist Starter: PF = Optimal
    teams = {t["team_id"]: t for t in compute.compute_teams(fake, [1], rows, Decimal(35))}
    # Win % = (W + 0,5·T)/G; All-Play = (1 + 0,5)/3; PF = Median zählt nicht als Median-Sieg
    assert teams[1]["win_pct"] == 50 and teams[1]["t"] == 1
    assert teams[1]["allplay_pct"] == 50 and teams[1]["matchup_glueck"] == 0 and teams[1]["median_l"] == 1
    assert teams[1]["streak"] == "T1"
    assert (teams[3]["rang"], teams[4]["rang"]) == (1, 4)
    assert {teams[1]["rang"], teams[2]["rang"]} == {2, 3}  # 0,5 Siege und gleiche PF


def test_paarungen_gleich_tabelle(season):
    """Spielplan und Tabelle nutzen dieselbe Quelle (Wochendatei): PF und Sieger stimmen je Team-Woche überein."""
    games = {(g["week"], g["home"]): g for g in compute.league_games(rawdata.Season(2026, 2), [1, 2])}
    for r in season["team_weeks"]:
        g = games.get((r["week"], r["team_id"])) or games[(r["week"], r["opponent_id"])]
        mine = g["home_pf"] if g["home"] == r["team_id"] else g["away_pf"]
        assert mine == r["pf"]
        assert (g["winner"] == r["team_id"]) == (r["result"] == "W")


def test_wochenstatus_ohne_byes(monkeypatch):
    """Eine Playoff-Woche mit Bye ohne Sieger gilt nicht als „läuft“, wenn alle echten Spiele final sind."""
    monkeypatch.setattr(ef, "local_weeks", lambda s: [14, 15])
    monkeypatch.setattr(ef, "load_week_matchups",
                        lambda s, w: [{"away_id": None, "final": False}, {"away_id": 3, "final": w == 15}])
    assert compute.week_status(2026, 13) == {14: "laeuft"}
    assert compute.week_status(2026, 14) == {}


def test_vorsaison_ohne_fehler():
    """Nach dem Saisonwechsel bis W1 final: nichts rechnen, Exit 0 (sonst wären die Actions wochenlang rot)."""
    assert compute.season_started(2026) and not compute.season_started(2099)
    assert compute.main(["--season", "2099"]) == 0


def test_roster_week_ir_bank_und_projektion():
    entries = [entry(0, 1, 20, projection=18), entry(20, 1, 30), entry(21, 2, 50), entry(2, 2, 10, projection=12)]
    result = compute.roster_week(entries, 2026, 1)
    assert result["starter_sum"] == 30 and result["starter_projection"] == 30
    assert result["bench"] == 30
    assert result["optimal"] == 30 + 10 + 20  # QB1 von der Bank, RB, QB2 im OP; IR-Spieler (50) zählt nicht
