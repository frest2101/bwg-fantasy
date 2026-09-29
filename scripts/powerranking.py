"""Power Ranking (Stärke μ) und Playoff-Simulation (Baustein 4).

Beschluss Stephan 28.09.2026 (docs/auftraege/session4_vorbereitung.md §2) mit den Antworten zu Session 4 (Frage 3, 8):
- Stärke μᵢ = (n·PF̄ᵢ + k·Pᵢ)/(n + k), k = 4 Wochen. Pᵢ kommt aus der Kader-Projektion (compute/players, je Woche
  übergeben); fehlt sie, gilt der Vorjahres-Prior Pᵢ = L̄ + 0,6·(PF/Spiel Vorjahr − L̄ Vorjahr).
- Erwartete All-Play-Quote Eᵢ = 1/(T − 1)·Σⱼ Φ((μᵢ − μⱼ)/(σ√2)) mit dem gepoolten σ (compute.pooled_sigma).
- Rang nach μ; Trend nur zwischen zwei Wochen mit derselben P-Quelle, sonst „neu“ (None).
- Playoff-Simulation: je Lauf μ̃ᵢ ~ N(μᵢ, σ²/(n + k)), dann PF je offene Woche ~ N(μ̃ᵢ + devᵢ,w, σ²); Seeding
  „espn“ (W + 0,5·T, dann PF) oder „div“ (Divisionssieger auf 1–2).

Reine Funktionen. σ und die Team-Werte übergibt compute.py (kein Import von compute). Gerechnet wird mit Decimal,
nur Φ und die Simulation intern mit float; alle Ausgaben sind Decimal (gerundet wird erst beim Export).
"""

import csv
import math
import random
from decimal import Decimal
from pathlib import Path

import espn_fetch as ef
import rawdata
from zahlen import ZERO, dec

K = 4                                    # Stabilisierungskonstante k = σ²/τ² in Wochen (Beschluss: k = 4 behalten)
PRIOR_SHARE = Decimal("0.6")             # Anteil der Vorjahresabweichung vom Ligaschnitt, der im Prior bleibt
RUNS = 10_000                            # Läufe der Playoff-Simulation
SEEDINGS = ("espn", "div")               # Seeding-Schalter: ESPN (W, dann PF) oder Divisionssieger auf 1–2
QUELLE_VORJAHR, QUELLE_PROJEKTION = "vorjahr", "projektion"
REDAKTION_DIR = ef.REPO_DIR / "data" / "redaktion"   # freigegebene Kernsätze: power_ranking_<saison>.csv
KERNSATZ_FIELDS = ("woche", "slot", "kernsatz")
# Feldnamen der ESPN-Simulation in mStandings (teams[].currentSimulationResults) – noch an keiner Datei geprüft
ESPN_SIM_FIELDS = {"playoff": ("playoffPct", "playoffPercentage", "playoffPercent"),
                   "division": ("divisionWinPct", "divisionWinPercentage", "divisionPct")}
ESPN_SIM_TOLERANCE = Decimal("0.02")     # relative Abweichung der Summe vom Soll (6 Plätze, 2 Divisionen)
SQRT2 = math.sqrt(2)


def to_dec(value: float) -> Decimal:
    """float-Zwischenergebnis (Φ) als Decimal, auf 9 Stellen gekappt, damit Plattform-Ulps nicht durchschlagen."""
    return dec(round(value, 9))


# ---------------------------------------------------------------- Stärke μ

def league_mean(team_weeks: list[dict], week: int) -> Decimal:
    """L̄(w) = Ø PF aller Team-Wochen bis Woche w."""
    pfs = [r["pf"] for r in team_weeks if r["week"] <= week]
    if not pfs:
        raise ValueError(f"keine Team-Woche bis W{week}")
    return sum(pfs, ZERO) / len(pfs)


def prior_season(rows: list[dict], season: int) -> dict[int, Decimal]:
    """PF/Spiel je Franchise-Slot in der Regular Season `season` aus history/team_seasons: pf/(w + l)."""
    result = {}
    for r in rows:
        if int(r["season"]) != season:
            continue
        games = int(r["w"]) + int(r["l"])
        if games:
            result[int(r["slot"])] = dec(r["pf"]) / games
    return dict(sorted(result.items()))


def prior_p(l_bar: Decimal, pf_prev: dict[int, Decimal], l_bar_prev: Decimal | None, ids) -> dict[int, Decimal]:
    """Vorjahres-Prior Pᵢ = L̄ + 0,6·(PF/Spiel Vorjahr − L̄ Vorjahr); ohne Vorjahreszeile Pᵢ = L̄."""
    return {t: l_bar + PRIOR_SHARE * (pf_prev[t] - l_bar_prev) if t in pf_prev else l_bar for t in ids}


def strength(n: int, pf_mean: Decimal | None, p: Decimal, k: int = K) -> Decimal:
    """μ = (n·PF̄ + k·P)/(n + k); ohne gespieltes Spiel μ = P."""
    return (n * pf_mean + k * p) / (n + k) if n else p


def rank_teams(mu: dict[int, Decimal], pf_per_game: dict[int, Decimal]) -> dict[int, int]:
    """Rang 1…T nach μ; Gleichstand nach PF/Spiel, dann team_id."""
    order = sorted(mu, key=lambda t: (-mu[t], -pf_per_game[t], t))
    return {t: rang for rang, t in enumerate(order, start=1)}


def trend(rang_vorwoche: int | None, rang: int, quelle_vorwoche: str | None, quelle: str) -> int | None:
    """Rang Vorwoche − Rang jetzt (positiv = aufgestiegen); None ohne Vorwoche oder bei Wechsel der P-Quelle („neu“)."""
    if rang_vorwoche is None or quelle_vorwoche != quelle:
        return None
    return rang_vorwoche - rang


def strength_week(team_weeks: list[dict], week: int, ids: list[int], pf_prev: dict[int, Decimal],
                  l_bar_prev: Decimal | None, p_week: dict[int, Decimal] | None = None) -> dict:
    """Stärke aller Teams nach Woche `week`, nur aus den Team-Wochen bis dahin (kein gespeicherter Zwischenstand).

    p_week: P je Team aus der Kader-Projektion dieser Woche; None → Vorjahres-Prior. Ergebnis:
    {"week", "l_bar", "p_quelle", "teams": {team_id: {"n", "pf_mean", "p", "mu", "rang"}}}.
    """
    l_bar = league_mean(team_weeks, week)
    if p_week is None:
        p, quelle = prior_p(l_bar, pf_prev, l_bar_prev, ids), QUELLE_VORJAHR
    else:
        missing = [t for t in ids if t not in p_week]
        if missing:
            raise ValueError(f"Kader-Projektion W{week} ohne P für Team {', '.join(map(str, missing))}")
        p, quelle = {t: dec(p_week[t]) for t in ids}, QUELLE_PROJEKTION
    teams = {}
    for t in ids:
        pfs = [r["pf"] for r in team_weeks if r["team_id"] == t and r["week"] <= week]
        pf_mean = sum(pfs, ZERO) / len(pfs) if pfs else None
        teams[t] = {"n": len(pfs), "pf_mean": pf_mean, "p": p[t], "mu": strength(len(pfs), pf_mean, p[t])}
    ranks = rank_teams({t: v["mu"] for t, v in teams.items()},
                       {t: v["pf_mean"] if v["pf_mean"] is not None else ZERO for t, v in teams.items()})
    for t in ids:
        teams[t]["rang"] = ranks[t]
    return {"week": week, "l_bar": l_bar, "p_quelle": quelle, "teams": teams}


# ---------------------------------------------------------------- Erwartete All-Play-Quote

def phi(x: float) -> float:
    """Standardnormalverteilung Φ(x) = ½·(1 + erf(x/√2))."""
    return 0.5 * (1 + math.erf(x / SQRT2))


def win_probability(mu_a: Decimal, mu_b: Decimal, sigma: Decimal) -> Decimal:
    """Siegchance von a gegen b in einer Woche: Φ((μa − μb)/(σ√2))."""
    return to_dec(phi(float(mu_a - mu_b) / (float(sigma) * SQRT2)))


def expected_allplay(mu: dict[int, Decimal], sigma: Decimal) -> dict[int, Decimal]:
    """Eᵢ = 1/(T − 1)·Σ_{j≠i} Φ((μᵢ − μⱼ)/(σ√2)); Σ Eᵢ = T/2 (bei 10 Teams 5)."""
    ids = sorted(mu)
    s = float(sigma) * SQRT2
    return {i: to_dec(sum(phi(float(mu[i] - mu[j]) / s) for j in ids if j != i) / (len(ids) - 1)) for i in ids}


# ---------------------------------------------------------------- Kernsätze (Redaktion)

def kernsatz_path(season: int) -> Path:
    return REDAKTION_DIR / f"power_ranking_{season}.csv"


def read_kernsaetze(path: Path) -> dict[tuple[int, int], str]:
    """Freigegebene Kernsätze (Spalten woche, slot, kernsatz) als {(woche, slot): Text}; fehlt die Datei → leer.

    Nur Text, keine Wertung durch den Code. Leere Kernsätze zählen nicht; doppelte (woche, slot) sind ein Fehler.
    Fehlermeldungen nennen nur Datei und Zeile, nie den Text (Action-Logs sind öffentlich).
    """
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in KERNSATZ_FIELDS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: Spalte(n) {', '.join(missing)} fehlen")
        result = {}
        for row in reader:
            text = (row["kernsatz"] or "").strip()
            if not text:
                continue
            try:
                key = (int(row["woche"]), int(row["slot"]))
            except (TypeError, ValueError):
                raise ValueError(f"{path.name}, Zeile {reader.line_num}: woche und slot müssen ganze Zahlen sein") from None
            if key in result:
                raise ValueError(f"{path.name}, Zeile {reader.line_num}: Kernsatz für Woche {key[0]}, Slot {key[1]} doppelt")
            result[key] = text
    return result


# ---------------------------------------------------------------- Playoff-Simulation

def open_games(schedule: list[dict], settings: dict, through: int) -> list[dict]:
    """Offene Paarungen der Regular Season nach Woche `through` aus mMatchupScore.schedule.

    Offen = matchupPeriodId > Periode der Woche through und ≤ matchupPeriodCount (Periode ↔ Woche über
    matchupPeriods). Je Spiel {"id", "period", "weeks", "home", "away"}, sortiert nach Periode und id.
    """
    ss = settings["scheduleSettings"]
    periods = {int(mp): sorted(wks) for mp, wks in ss["matchupPeriods"].items()}
    current = next((mp for mp, wks in periods.items() if through in wks), None)
    if current is None:
        raise ValueError(f"Woche {through} gehört laut mSettings zu keiner Matchup-Periode")
    games = [{"id": m["id"], "period": m["matchupPeriodId"], "weeks": periods[m["matchupPeriodId"]],
              "home": m["home"]["teamId"], "away": m["away"]["teamId"]}
             for m in schedule
             if current < m["matchupPeriodId"] <= ss["matchupPeriodCount"] and m.get("home") and m.get("away")]
    return sorted(games, key=lambda g: (g["period"], g["id"]))


def bye_count(playoff_teams: int) -> int:
    """Freilose der ersten Playoff-Runde: nächste Zweierpotenz ≥ Playoff-Teams minus Playoff-Teams (6 → 2)."""
    return (1 << (playoff_teams - 1).bit_length()) - playoff_teams if playoff_teams > 0 else 0


def simulate(teams: list[dict], games: list[dict], mu: dict[int, Decimal], sigma: Decimal,
             p_dev: dict[int, dict[int, Decimal]] | None = None, runs: int = RUNS, seed: int = 0,
             playoff_teams: int = 6, k: int = K) -> dict:
    """Playoff-Simulation (Beschluss §2); beide Seedings werten dieselben Läufe aus.

    teams: Zeilen mit team_id, division, games, w, t, pf (Stand nach Woche N); games: open_games; mu: μ je Team.
    Je Lauf μ̃ᵢ ~ N(μᵢ, σ²/(nᵢ + k)), dann je offene Woche w PFᵢ,w ~ N(μ̃ᵢ + devᵢ,w, σ²), devᵢ,w aus p_dev (sonst 0).
    Mehr PF gewinnt, gleich = T. Stand = (W + 0,5·T, PF). „espn“: die besten playoff_teams nach Stand; „div“: die
    Divisionssieger (Bester je Division) vorn, dann die übrigen nach Stand. Byes = Seeds 1…bye_count.
    Ausgabe je Seeding und Team: playoff, division, bye (Anteile 0–1), restsiege (Ø W + 0,5·T in den offenen
    Spielen), seeds (Anteil je Seed 1…playoff_teams) – als Decimal, exakt aus den Zählern.
    """
    if runs < 1:
        raise ValueError("runs muss mindestens 1 sein")
    ids = sorted(t["team_id"] for t in teams)
    idx = {t: i for i, t in enumerate(ids)}
    by_id = {t["team_id"]: t for t in teams}
    size = len(ids)
    s = float(sigma)
    mu0 = [float(mu[t]) for t in ids]
    sd_mu = [s / math.sqrt(by_id[t]["games"] + k) for t in ids]
    half_wins0 = [2 * by_id[t]["w"] + by_id[t]["t"] for t in ids]      # halbe Siege: W zählt 2, T zählt 1
    pf0 = [float(by_id[t]["pf"]) for t in ids]
    division = [by_id[t]["division"] for t in ids]
    dev = p_dev or {}
    plan = [(idx[g["home"]], idx[g["away"]],
             [(float(dev.get(g["home"], {}).get(w, 0)), float(dev.get(g["away"], {}).get(w, 0))) for w in g["weeks"]])
            for g in games]
    byes = bye_count(playoff_teams)

    rng = random.Random(seed)
    gauss = rng.gauss
    half_wins_sum = [0] * size
    division_wins = [0] * size
    seed_counts = {name: [[0] * playoff_teams for _ in ids] for name in SEEDINGS}
    for _ in range(runs):
        mt = [gauss(m, sd) for m, sd in zip(mu0, sd_mu)]
        hw, pf = half_wins0[:], pf0[:]
        for h, a, devs in plan:
            ph = pa = 0.0
            for dh, da in devs:
                ph += gauss(mt[h] + dh, s)
                pa += gauss(mt[a] + da, s)
            pf[h] += ph
            pf[a] += pa
            if ph > pa:
                hw[h] += 2
            elif pa > ph:
                hw[a] += 2
            else:
                hw[h] += 1
                hw[a] += 1
        order = sorted(range(size), key=lambda i: (hw[i], pf[i]), reverse=True)  # stabil: Gleichstand nach team_id
        winners, seen = [], set()
        for i in order:
            if division[i] not in seen:
                seen.add(division[i])
                winners.append(i)
        for i in winners:
            division_wins[i] += 1
        seeded = {"espn": order[:playoff_teams],
                  "div": (winners + [i for i in order if i not in winners])[:playoff_teams]}
        for name in SEEDINGS:
            counts = seed_counts[name]
            for pos, i in enumerate(seeded[name]):
                counts[i][pos] += 1
        for i in range(size):
            half_wins_sum[i] += hw[i]

    def share(count: int) -> Decimal:
        return Decimal(count) / runs

    result = {}
    for name in SEEDINGS:
        result[name] = {}
        for i, t in enumerate(ids):
            counts = seed_counts[name][i]
            result[name][t] = {
                "playoff": share(sum(counts)), "division": share(division_wins[i]), "bye": share(sum(counts[:byes])),
                "restsiege": Decimal(half_wins_sum[i] - runs * half_wins0[i]) / (2 * runs),
                "seeds": [share(c) for c in counts],
            }
    return result


# ---------------------------------------------------------------- ESPN-Vergleich

def espn_simulation(ssn: rawdata.Season) -> dict[int, dict] | None:
    """ESPN-Playoff-Simulation aus mStandings (teams[].currentSimulationResults), nur zum Vergleich.

    Die Feldnamen sind noch an keiner echten Datei geprüft (mStandings gibt es erst ab dem Wochenabruf W3). Gelesen
    werden playoffPct und divisionWinPct (samt Varianten in ESPN_SIM_FIELDS). Ob ESPN Anteile oder Prozent liefert,
    entscheidet die Summe: Σ Playoff = Playoff-Plätze (Anteil) bzw. 100 × Plätze (Prozent), ebenso Σ Division =
    Zahl der Divisionen. Passt die Struktur nicht, ist das Ergebnis None; eine unstimmige Division-Summe gibt
    division None. Ausgabe je Team: {"playoff", "division"} als Anteil 0–1 (Decimal), sortiert nach team_id.
    """
    try:
        data = ssn.standings()
        ss = ssn.settings()["scheduleSettings"]
        expected = {"playoff": Decimal(ss["playoffTeamCount"]), "division": Decimal(len(ss["divisions"]))}
    except (ef.FetchError, KeyError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("teams"), list) or not data["teams"]:
        return None
    values: dict[str, dict[int, Decimal]] = {"playoff": {}, "division": {}}
    for team in data["teams"]:
        sim = team.get("currentSimulationResults") if isinstance(team, dict) else None
        tid = team.get("id") if isinstance(team, dict) else None
        if not isinstance(sim, dict) or not isinstance(tid, int) or isinstance(tid, bool):
            return None
        for field, names in ESPN_SIM_FIELDS.items():
            raw = next((sim[n] for n in names if n in sim), None)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                values[field][tid] = dec(raw)
    scaled = {}
    for field, per_team in values.items():
        scaled[field] = None
        if len(per_team) != len(data["teams"]):
            continue
        total = sum(per_team.values(), ZERO)
        for factor in (Decimal(1), Decimal(100)):
            target = expected[field] * factor
            if target and abs(total - target) <= ESPN_SIM_TOLERANCE * target:
                scaled[field] = {t: v / factor for t, v in per_team.items()}
                break
    if scaled["playoff"] is None:
        return None
    return {t: {"playoff": scaled["playoff"][t],
                "division": scaled["division"][t] if scaled["division"] is not None else None}
            for t in sorted(scaled["playoff"])}


# ---------------------------------------------------------------- Einstieg

def compute_power_ranking(ssn: rawdata.Season, weeks: list[int], team_weeks: list[dict], teams: list[dict],
                          sigma: Decimal, p_by_week: dict[int, dict[int, Decimal]] | None = None,
                          p_dev: dict[int, dict[int, Decimal]] | None = None, runs: int = RUNS) -> dict:
    """Power Ranking nach Woche N = weeks[-1] mit Wochenreihe 1…N, Playoff-Simulation und ESPN-Vergleich.

    teams: compute_teams-Ausgabe (team_id, division, w, l, t, pf, games, pf_per_game); sigma: gepooltes σ nach N.
    p_by_week: P je Woche und Team aus der Kader-Projektion (Woche fehlt → Vorjahres-Prior); p_dev: devᵢ,w =
    Pᵢ,w − P̄ᵢ je Team und offene Woche für die Simulation (fehlt → 0). Seed der Simulation = Saison·100 + N.
    """
    through = weeks[-1]
    if ssn.through != through:
        raise ValueError(f"Season-Stand W{ssn.through} passt nicht zur letzten gerechneten Woche W{through}")
    by_id = {t["team_id"]: t for t in teams}
    ids = sorted(by_id)
    p_by_week = p_by_week or {}

    vorjahr = ssn.season - 1
    pf_prev = prior_season(ssn.history("team_seasons"), vorjahr)
    l_bar_prev = sum(pf_prev.values(), ZERO) / len(pf_prev) if pf_prev else None
    series = [strength_week(team_weeks, w, ids, pf_prev, l_bar_prev, p_by_week.get(w)) for w in weeks]
    now = series[-1]
    before = series[-2] if len(series) > 1 else None
    mu = {t: now["teams"][t]["mu"] for t in ids}
    e = expected_allplay(mu, sigma)

    kernsaetze = read_kernsaetze(kernsatz_path(ssn.season))
    unknown = sorted({slot for _, slot in kernsaetze} - set(ids))
    if unknown:
        raise ValueError(f"{kernsatz_path(ssn.season).name}: unbekannte Slots {', '.join(map(str, unknown))}")

    result_teams = {}
    for t in ids:
        cur = now["teams"][t]
        rang_vorwoche = before["teams"][t]["rang"] if before else None
        result_teams[t] = {
            "mu": cur["mu"], "se": sigma / Decimal(cur["n"] + K).sqrt(), "p": cur["p"], "p_quelle": now["p_quelle"],
            "e": e[t], "rang": cur["rang"], "rang_vorwoche": rang_vorwoche,
            "trend": trend(rang_vorwoche, cur["rang"], before["p_quelle"] if before else None, now["p_quelle"]),
            "kernsatz": kernsaetze.get((through, t)),
            "verlauf": [{"week": s["week"], "mu": s["teams"][t]["mu"], "rang": s["teams"][t]["rang"],
                         "p_quelle": s["p_quelle"], "kernsatz": kernsaetze.get((s["week"], t))} for s in series],
        }

    settings = ssn.settings()
    games = open_games(ssn.schedule(), settings, through)
    playoff_teams = settings["scheduleSettings"]["playoffTeamCount"]
    seed = ssn.season * 100 + through
    dev = p_dev or {}
    spiele = [{"id": g["id"], "week": g["weeks"][0], "home": g["home"], "away": g["away"],
               "p_home": win_probability(mu[g["home"]] + dec(dev.get(g["home"], {}).get(g["weeks"][0], 0)),
                                         mu[g["away"]] + dec(dev.get(g["away"], {}).get(g["weeks"][0], 0)), sigma)}
              for g in games]
    return {
        "l_bar": now["l_bar"], "l_bar_2025": l_bar_prev, "vorjahr": vorjahr, "sigma": sigma,
        "teams": result_teams,
        "sim": simulate(teams, games, mu, sigma, p_dev, runs, seed, playoff_teams),
        "sim_info": {"runs": runs, "seed": seed, "offene_spiele": len(games), "playoff_teams": playoff_teams,
                     "byes": bye_count(playoff_teams)},
        "spiele": spiele,
        "espn_sim": espn_simulation(ssn),
    }
