"""Power Ranking (Stärke μ) und Playoff-Simulation (Baustein 4).

Beschluss Stephan 28.09.2026 (docs/auftraege/session4_vorbereitung.md §2) mit den Antworten zu Session 4 (Frage 3, 8):
- Stärke μᵢ = (n·PF̄ᵢ + k·Pᵢ)/(n + k), k = 6 (K). Pᵢ kommt aus der Kader-Projektion (compute/players, je Woche
  übergeben); fehlt sie, gilt der Vorjahres-Prior Pᵢ = L̄ + 0,6·(PF/Spiel Vorjahr − L̄ Vorjahr).
- Erwartete All-Play-Quote Eᵢ = 1/(T − 1)·Σⱼ Φ((μᵢ − μⱼ)/(σ√2)) mit dem gepoolten σ (compute.pooled_sigma).
- Rang nach μ; Trend nur zwischen zwei Wochen mit derselben P-Quelle, sonst „neu“ (None).
- Playoff-Simulation: je Lauf μ̃ᵢ ~ N(μᵢ, σ²/(n + k)), dann PF je offene Woche ~ N(μ̃ᵢ + devᵢ,w, σ²); Seeding
  „espn“ (W + 0,5·T, dann PF) oder „liga“ (Top 3 je Division, Divisionssieger auf 1–2).
- Endplatz (Stufe 4, Session 9): das Feld „liga“ spielt W15–17 aus (play_bracket, Annahme zur ESPN-Mechanik), gespielte
  Playoff-Spiele zählen wie ESPN sie meldet; daraus Endplatz-Verteilung und Draft-Position des Folgejahrs (umgekehrte
  Endplatzierung, linear, ohne Lotterie), nach W17 die feste Reihenfolge (final_places).

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

K = 6                                    # k = σ²/E[(P − μ)²] mit der Projektion P als Ausgangswert (Kalibrierung
                                         # 29.09.2026: fest für die ganze Saison, Prüfung nur zwischen zwei Saisons)
PRIOR_SHARE = Decimal("0.6")             # Anteil der Vorjahresabweichung vom Ligaschnitt, der im Prior bleibt
RUNS = 10_000                            # Läufe der Playoff-Simulation
SEEDINGS = ("liga", "espn")              # Standard „liga“: Top 3 je Division, Divisionssieger auf 1–2 (Regel 2026);
                                         # „espn“: Top 6 gesamt nach W, dann PF (so setzt ESPN ohne Korrektur)
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


# ---------------------------------------------------------------- Endplatz: Bracket W15–17 (Stufe 4)
# Annahme zur ESPN-Mechanik (vor dem 15.12.2026 nicht belegbar; nach W15, W16 und W17 gegen die echten Paarungen
# prüfen, Abweichungen meldet bracket_warnings): sechs Playoff-Teams, Seeds 1–2 mit Freilos in der ersten Runde, kein
# Reseeding (mSettings playoffReseed false); Spiel um Platz 5 der beiden Verlierer der ersten Runde in der zweiten,
# Finale und Spiel um Platz 3 in der dritten Runde; Trostrunde der vier übrigen als Leiter (nach jeder Runde: Sieger
# 7–8 auf Platz 7, Sieger 9–10 auf 8, Verlierer 7–8 auf 9, Verlierer 9–10 auf 10). Gleichstand gewinnt der höhere Seed.
BRACKET_FIELD, BRACKET_TEAMS, BRACKET_ROUNDS = 6, 10, 3
TIE = "T"


def playoff_weeks(settings: dict) -> list[int]:
    """NFL-Wochen der Playoff-Perioden laut mSettings (Perioden nach matchupPeriodCount), aufsteigend, z. B. [15, 16, 17]."""
    ss = settings["scheduleSettings"]
    return sorted(w for mp, wks in ss["matchupPeriods"].items() if int(mp) > ss["matchupPeriodCount"] for w in wks)


def playoff_games(schedule: list[dict], settings: dict) -> tuple[dict, dict]:
    """Playoff-Spiele aus mMatchupScore.schedule (Stand-Woche): (entschieden, Paarungen).

    entschieden: (Woche, frozenset{Heim, Gast}) → Sieger-team_id laut ESPN-Feld winner (nicht der Punktevergleich,
    Beschluss 8) oder TIE; Paarungen: Woche → Menge der Paarungen mit Gegner, auch offene. Freilose (ohne Gast) fehlen.
    """
    ss = settings["scheduleSettings"]
    week_of = {int(mp): min(wks) for mp, wks in ss["matchupPeriods"].items() if int(mp) > ss["matchupPeriodCount"]}
    decided, pairs = {}, {}
    for m in schedule:
        week = week_of.get(m.get("matchupPeriodId"))
        if week is None or not m.get("home") or not m.get("away"):
            continue
        home, away = m["home"]["teamId"], m["away"]["teamId"]
        key = frozenset((home, away))
        pairs.setdefault(week, set()).add(key)
        winner = {"HOME": home, "AWAY": away, "TIE": TIE}.get(m.get("winner"))
        if winner is not None:
            decided[(week, key)] = winner
    return decided, pairs


def _other(a, b, winner):
    return b if winner == a else a


def play_bracket(seeds: list, game) -> list:
    """Endplätze 1–10 nach der Annahme oben. seeds = Teams in Seed-Reihenfolge 1–10 (1–6 Playoffs, 7–10 Trostrunde nach
    Stand); game(runde, a, b) → Sieger, Runde 0–2 (W15–17); den Gleichstand entscheidet game nach dem Seed (der höhere
    gewinnt). Die Aufrufe kommen Runde für Runde (trace_bracket verlässt sich darauf)."""
    s = seeds

    def ladder(r: int, lad: list) -> list:
        top, bottom = game(r, lad[0], lad[1]), game(r, lad[2], lad[3])
        return [top, bottom, _other(lad[0], lad[1], top), _other(lad[2], lad[3], bottom)]

    # Runde 1: 3 gegen 6, 4 gegen 5 (Seeds 1–2 Freilos); Trostrunde 7–8 und 9–10
    w36, w45 = game(0, s[2], s[5]), game(0, s[3], s[4])
    lad = ladder(0, s[6:10])
    # Runde 2: 1 gegen Sieger 4–5, 2 gegen Sieger 3–6; Spiel um Platz 5 der Verlierer der Runde 1
    l36, l45 = _other(s[2], s[5], w36), _other(s[3], s[4], w45)
    semi1, semi2 = game(1, s[0], w45), game(1, s[1], w36)
    fifth = game(1, *sorted((l36, l45), key=s.index))
    lad = ladder(1, lad)
    # Runde 3: Finale, Spiel um Platz 3
    lost1, lost2 = _other(s[0], w45, semi1), _other(s[1], w36, semi2)
    champ = game(2, *sorted((semi1, semi2), key=s.index))
    third = game(2, *sorted((lost1, lost2), key=s.index))
    lad = ladder(2, lad)
    return [champ, _other(semi1, semi2, champ), third, _other(lost1, lost2, third),
            fifth, _other(l36, l45, fifth)] + lad


def trace_bracket(seeds: list, decided: dict, weeks: list[int]) -> tuple[dict, list | None, list]:
    """Bracket nur aus entschiedenen Spielen (decided wie playoff_games): Paarungen je Woche, soweit sie feststehen
    (bis einschließlich der ersten Runde mit offenem Spiel), Endplätze (None, solange ein Spiel offen ist oder ESPN
    ein Unentschieden meldet) und die Unentschieden [(Woche, a, b)]."""
    rank = {t: i for i, t in enumerate(seeds)}
    pairs: dict[int, set] = {w: set() for w in weeks}
    state = {"open": len(weeks)}
    ties = []

    def game(r, a, b):
        w = weeks[r]
        if r <= state["open"]:
            pairs[w].add(frozenset((a, b)))
        res = decided.get((w, frozenset((a, b))))
        if res is None:
            state["open"] = min(state["open"], r)
        elif res == TIE:
            ties.append((w, a, b))
        else:
            return res
        return a if rank[a] < rank[b] else b

    places = play_bracket(seeds, game)
    known = {w: pairs[w] for i, w in enumerate(weeks) if i <= state["open"] and i < len(weeks)}
    return known, places if state["open"] == len(weeks) and not ties else None, ties


def bracket_warnings(known: dict, espn_pairs: dict, ties: list) -> list[str]:
    """Abweichungen der ESPN-Paarungen von der Annahme (je Woche, die ESPN schon angelegt hat) und Unentschieden laut
    ESPN – beides heißt: Annahme prüfen, Stephan fragen (Auftrag Session 9, Schritte 7 und 8). Nur team_ids."""
    fmt = lambda ps: ", ".join("–".join(map(str, sorted(p))) for p in sorted(ps, key=sorted))  # noqa: E731
    out = [f"Playoffs W{w}: Paarungen laut ESPN ({fmt(espn_pairs[w])}) weichen von der Annahme ({fmt(rule)}) ab – "
           f"Annahme prüfen (CLAUDE.md, Playoff-Simulation), Stephan fragen"
           for w, rule in sorted(known.items()) if w in espn_pairs and espn_pairs[w] != rule]
    out += [f"Playoffs W{w}: ESPN meldet ein Unentschieden zwischen Team {a} und Team {b} – Endplatz offen, Stephan fragen"
            for w, a, b in ties]
    return out


def liga_order(order: list, division: list, playoff_teams: int) -> tuple[list, list]:
    """Seeding „liga“ aus der Rangfolge order (bester zuerst; Einträge sind Indizes in division): Divisionssieger
    zuerst, dann die übrigen der besten playoff_teams/Divisionen je Division nach Stand, aufgefüllt nach Stand – danach
    alle übrigen nach Stand (Trostrunde). Rückgabe (alle Teams in Seed-Reihenfolge, Divisionssieger)."""
    divisions = sorted(set(division))
    per_division = playoff_teams // len(divisions) if divisions else 0
    winners, seen = [], set()
    for i in order:
        if division[i] not in seen:
            seen.add(division[i])
            winners.append(i)
    qualified = {i for d in divisions for i in [j for j in order if division[j] == d][:per_division]}
    liga = winners + [i for i in order if i in qualified and i not in winners]
    liga += [i for i in order if i not in liga][:max(0, playoff_teams - len(liga))]  # falls Divisionen ungleich
    return liga + [i for i in order if i not in liga], winners


def simulate(teams: list[dict], games: list[dict], mu: dict[int, Decimal], sigma: Decimal,
             p_dev: dict[int, dict[int, Decimal]] | None = None, runs: int = RUNS, seed: int = 0,
             playoff_teams: int = 6, k: int = K, bracket: dict | None = None) -> dict:
    """Playoff-Simulation (Beschluss §2); beide Seedings werten dieselben Läufe aus.

    teams: Zeilen mit team_id, division, games, w, t, pf (Stand nach Woche N); games: open_games; mu: μ je Team.
    Je Lauf μ̃ᵢ ~ N(μᵢ, σ²/(nᵢ + k)), dann je offene Woche w PFᵢ,w ~ N(μ̃ᵢ + devᵢ,w, σ²), devᵢ,w aus p_dev (sonst 0).
    Mehr PF gewinnt, gleich = T. Stand = (W + 0,5·T, PF). „liga“ (Regel 2026, der Commissioner setzt nach W14
    nötigenfalls von Hand): je Division die besten playoff_teams/Divisionen (6/2 = 3), die Divisionssieger auf Seed 1–2,
    die übrigen nach Stand; „espn“: die besten playoff_teams nach Stand. Byes = Seeds 1…bye_count.
    Ausgabe je Seeding und Team: playoff, division, bye (Anteile 0–1), restsiege (Ø W + 0,5·T in den offenen
    Spielen), seeds (Anteil je Seed 1…playoff_teams) – als Decimal, exakt aus den Zählern.
    Endplatz (Stufe 4): bracket = {"weeks": Playoff-Wochen, "entschieden": playoff_games[0]}; passt die Liga zum Bracket
    (BRACKET_TEAMS Teams, BRACKET_FIELD Playoff-Teams, BRACKET_ROUNDS Wochen), spielt jeder Lauf das Feld „liga“ nach
    play_bracket aus: entschiedene Spiele zählen wie ESPN sie meldet (TIE: höherer Seed), offene mit
    PF ~ N(μ̃ + dev, σ²) aus einem eigenen Zufallsstrom (die Läufe der Regular Season bleiben gleich). „liga“ trägt dann
    zusätzlich endplatz (Anteil je Platz 1–10), pick (erwartete Draft-Position des Folgejahrs = Ø (11 − Endplatz)),
    pick1 (Anteil Endplatz 10) und pick_top3 (Anteil Endplatz 8–10); „espn“ bekommt keine Endplatz-Verteilung.
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
    # Endplatz (Stufe 4): nur wenn die Liga zum Bracket passt; eigener Zufallsstrom für die Playoff-Wochen
    with_bracket = (bracket is not None and size == BRACKET_TEAMS and playoff_teams == BRACKET_FIELD
                    and len(bracket["weeks"]) == BRACKET_ROUNDS)
    if with_bracket:
        b_weeks, decided = bracket["weeks"], bracket["entschieden"]
        b_gauss = random.Random(seed * 1000 + 17).gauss
        b_dev = [[float(dev.get(t, {}).get(w, 0)) for w in b_weeks] for t in ids]
        place_counts = [[0] * size for _ in ids]

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
        liga, winners = liga_order(order, division, playoff_teams)
        for i in winners:
            division_wins[i] += 1
        seeded = {"liga": liga[:playoff_teams], "espn": order[:playoff_teams]}
        for name in SEEDINGS:
            counts = seed_counts[name]
            for pos, i in enumerate(seeded[name]):
                counts[i][pos] += 1
        for i in range(size):
            half_wins_sum[i] += hw[i]
        if with_bracket:
            rank = {i: r for r, i in enumerate(liga)}

            def game(r, a, b, rank=rank, mt=mt):
                res = decided.get((b_weeks[r], frozenset((ids[a], ids[b]))))
                if res is not None and res != TIE:
                    return a if res == ids[a] else b
                if res is None:   # offen: simulieren
                    pa, pb = b_gauss(mt[a] + b_dev[a][r], s), b_gauss(mt[b] + b_dev[b][r], s)
                    if pa != pb:
                        return a if pa > pb else b
                return a if rank[a] < rank[b] else b   # Gleichstand (auch TIE laut ESPN): höherer Seed

            for place, i in enumerate(play_bracket(liga, game)):
                place_counts[i][place] += 1

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
            if with_bracket and name == "liga":
                places = place_counts[i]
                result[name][t].update(
                    endplatz=[share(c) for c in places],
                    pick=Decimal(sum(c * (size - p) for p, c in enumerate(places))) / runs,   # Pick = 11 − Endplatz
                    pick1=share(places[-1]), pick_top3=share(sum(places[-3:])))
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

def espn_ranks(teams: list[dict]) -> dict[int, int] | None:
    """Endplatz laut ESPN aus mTeam: rankFinal (Handkorrektur des Commissioners), sonst rankCalculatedFinal – nur wenn
    alle Teams einen Wert über 0 haben (bis zum Saisonende stehen beide auf 0), sonst None."""
    ranks = {t["id"]: t.get("rankFinal") or t.get("rankCalculatedFinal") for t in teams}
    return ranks if ranks and all(isinstance(r, int) and r > 0 for r in ranks.values()) else None


def final_places(teams: list[dict], settings: dict, decided: dict, espn_pairs: dict,
                 espn_rank: dict[int, int] | None = None) -> dict:
    """Endplatz aus den Ergebnissen (Stufe 4, Schritt 8), nur bei abgeschlossener Regular Season: Seeding „liga“ aus der
    Schlusstabelle (W + 0,5·T, dann PF, Gleichstand nach team_id wie in simulate), Bracket nach play_bracket mit den
    entschiedenen Spielen.

    abweichung = Wochen, in denen ESPN anders paart als die Annahme oder ein Unentschieden meldet (bracket_warnings),
    dazu 17, wenn der Endplatz laut ESPN (espn_ranks) von dem nach der Annahme abweicht. fest = team_ids in Endplatz-
    Reihenfolge 1–10, sobald alle Spiele entschieden sind und es keine Abweichung gibt (Befund Gegenprüfung 01.10.2026:
    eine Reihenfolge, die das Rechenwerk selbst als ungeprüft meldet, ist keine Tatsache), sonst None; draft = Draft-
    Reihenfolge des Folgejahrs (Pick 1 = Endplatz 10, linear, ohne Lotterie, ohne getauschte Picks) oder None;
    espn_bestaetigt = True/False nach dem Abgleich mit espn_rank, None ohne ESPN-Endplatz; warnungen für den Lauf."""
    weeks = playoff_weeks(settings)
    playoff_teams = settings["scheduleSettings"]["playoffTeamCount"]
    if len(teams) != BRACKET_TEAMS or playoff_teams != BRACKET_FIELD or len(weeks) != BRACKET_ROUNDS:
        return {"fest": None, "draft": None, "abweichung": [], "espn_bestaetigt": None, "warnungen": []}
    ids = sorted(t["team_id"] for t in teams)
    by_id = {t["team_id"]: t for t in teams}
    order = sorted(range(len(ids)), key=lambda i: (2 * by_id[ids[i]]["w"] + by_id[ids[i]]["t"], by_id[ids[i]]["pf"]),
                   reverse=True)
    liga, _ = liga_order(order, [by_id[t]["division"] for t in ids], playoff_teams)
    known, places, ties = trace_bracket([ids[i] for i in liga], decided, weeks)
    warnungen = bracket_warnings(known, espn_pairs, ties)
    abweichung = {w for w, rule in known.items() if w in espn_pairs and espn_pairs[w] != rule} | {w for w, _, _ in ties}
    bestaetigt = None
    if places and espn_rank:
        bestaetigt = all(espn_rank.get(t) == place for place, t in enumerate(places, start=1))
        if not bestaetigt:
            abweichung.add(weeks[-1])
            warnungen.append("Endplatz laut ESPN (rankFinal/rankCalculatedFinal) weicht von der Annahme ab – keine feste "
                             "Draft-Reihenfolge, Annahme prüfen, Stephan fragen")
    ok = places is not None and not abweichung
    return {"fest": places if ok else None, "draft": places[::-1] if ok else None, "abweichung": sorted(abweichung),
            "espn_bestaetigt": bestaetigt, "warnungen": warnungen}


def compute_power_ranking(ssn: rawdata.Season, weeks: list[int], team_weeks: list[dict], teams: list[dict],
                          sigma: Decimal, p_by_week: dict[int, dict[int, Decimal]] | None = None,
                          p_dev: dict[int, dict[int, Decimal]] | None = None, runs: int = RUNS,
                          stand: rawdata.Season | None = None) -> dict:
    """Power Ranking nach Woche N = weeks[-1] mit Wochenreihe 1…N, Playoff-Simulation und ESPN-Vergleich.

    teams: compute_teams-Ausgabe (team_id, division, w, l, t, pf, games, pf_per_game); sigma: gepooltes σ nach N.
    p_by_week: P je Woche und Team aus der Kader-Projektion (Woche fehlt → Vorjahres-Prior); p_dev: devᵢ,w =
    Pᵢ,w − P̄ᵢ je Team und offene Woche für die Simulation (fehlt → 0).
    stand: Season der Stand-Woche (Stufe 4: letzte finale Playoff-Woche, sonst ssn) – aus ihrem Spielplan kommen die
    gespielten Playoff-Spiele; Seed der Simulation = Saison·100 + Stand-Woche. Endplatz und Draft-Reihenfolge des
    Folgejahrs: sim.liga (Verteilung) und endplatz (final_places, erst nach der Regular Season).
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
    stand = stand or ssn
    seed = ssn.season * 100 + stand.through
    decided, espn_pairs = playoff_games(stand.schedule(), settings)
    endplatz = final_places(teams, settings, decided, espn_pairs, espn_ranks(ssn.teams())) if not games else None
    # Weicht ESPN von der Annahme ab, zählten echte Spiele in falschen Rollen: Endplatz-Verteilung aussetzen, bis die
    # Annahme angepasst ist (Befund Gegenprüfung 01.10.2026)
    bracket = None if endplatz and endplatz["abweichung"] else {"weeks": playoff_weeks(settings), "entschieden": decided}
    dev = p_dev or {}
    spiele = [{"id": g["id"], "week": g["weeks"][0], "home": g["home"], "away": g["away"],
               "p_home": win_probability(mu[g["home"]] + dec(dev.get(g["home"], {}).get(g["weeks"][0], 0)),
                                         mu[g["away"]] + dec(dev.get(g["away"], {}).get(g["weeks"][0], 0)), sigma)}
              for g in games]
    return {
        "l_bar": now["l_bar"], "l_bar_2025": l_bar_prev, "vorjahr": vorjahr, "sigma": sigma,
        "teams": result_teams,
        "sim": simulate(teams, games, mu, sigma, p_dev, runs, seed, playoff_teams, bracket=bracket),
        "sim_info": {"runs": runs, "seed": seed, "offene_spiele": len(games), "playoff_teams": playoff_teams,
                     "byes": bye_count(playoff_teams), "stand_woche": stand.through,
                     "playoff_entschieden": len(decided)},
        "endplatz": endplatz,
        "spiele": spiele,
        "espn_sim": espn_simulation(ssn),
    }
