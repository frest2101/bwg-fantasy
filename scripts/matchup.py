"""Positions-Matchup (Baustein 4, Session 8): wie viele Punkte jede NFL-Defense den Spielern einer Position zulässt und
was das für den Spielplan eines Spielers heißt.

Regeln: Auftrag Session 8 (docs/auftraege/session8.md, Punkt 2) mit dem Beschluss in session6_vorbereitung.md §2 –
dieselbe Formel wie die D/ST-Faktoren (dst.py), nur je Defense und Position (QB, RB, WR, TE, K) statt je Offense:
- Z(D, P) = Ø je Spiel der Punkte (Liga-Scoring, appliedTotal), die Spieler der Position P (defaultPositionId) mit
  stats["210"] == 1 gegen die Defense D erzielt haben. Team eines Spielers = NFL-Team des Spiels (proTeamId im
  Ist-Eintrag, rawdata.PoolRow.game_team), Gegner aus dem NFL-Spielplan. Ein Spiel zählt für eine Position nur,
  wenn mindestens ein Spieler der Position gespielt hat.
- Ligaschnitt LS_P = Ø der Z über alle Defenses mit mindestens einem Spiel; r = Z/LS_P.
- F = (n·r26 + 5·r25 + 5·1,00)/(n + 10), n = Spiele der Defense in der laufenden Saison; Rang 1 = höchstes F.
- Vorjahr aus basis/positionen_<vorjahr>.json (Summen je Team, Position und Woche im Liga-Scoring aus den Rohstats,
  espn_fetch.positions_extract); fehlt der Auszug, gilt r25 = 1,00 (Ligamittel) für alle Defenses.
F > 1 heißt: Gegen diese Defense holen Spieler der Position mehr Punkte als im Schnitt (gutes Matchup für den
Spieler). Position gegen Defense, kein Einzelduell. ESPNs positionalRatings dienen nur als Test (Vorwochenstand).
D/ST bleibt im D/ST-Modul; player_mu nimmt für D/ST dessen Faktoren. Keine Zwischenstände: jeder Lauf rechnet neu.
"""

from decimal import Decimal

import dst
import espn_fetch as ef
import rawdata
from lineup import DST, K, POSITION_NAMES, QB, RB, TE, WR
from zahlen import ONE, ZERO, dec

POSITIONS = (QB, RB, WR, TE, K)
NAMES = POSITION_NAMES

FORMEL = ("F = (n·r26 + 5·r25 + 5·1,00)/(n + 10); r = Z/Ligaschnitt der Position; Z = Ø Punkte je Spiel, die Spieler "
          "der Position gegen die Defense erzielt haben")
# Auslöser wie D/ST ohne z: der z-Auslöser (dst.z_score mit DST_CV) kommt erst, wenn die Positions-CV gegen echte
# Wochenwerte je Position und Defense geprüft sind (Auftrag Session 8, Punkt 2)
AUSLOESER = {"delta": "|F − F Vorwoche| ≥ 0,10", "rang": "Rang nach F um mindestens 5 Plätze verschoben"}
# Stellen im JSON wie dst.PRECISION: F, r und die gemittelten Spielplan-Faktoren 3, sonst 2 (Punkte, Z, Ligaschnitt)
PRECISION = {k: 3 for k in ("f", "f_vorwoche", "delta", "r25", "r26", "naechste3", "rest", "sos_po", "f_verlauf")}


# ---------------------------------------------------------------- Spiele je Position und Defense

def prior_games(extract: dict, prior_nfl: dict[int, rawdata.NflTeam]) -> tuple[dict[int, dict[int, dict]], list[str]]:
    """Vorjahr: Position → Defense → {Woche: Punkte der Position gegen die Defense} aus dem Auszug
    basis/positionen_<vorjahr>.json; nur Wochen mit mindestens einem Spieler der Position (n > 0).

    Offense ohne Gegner im Vorjahres-Spielplan: Warnung, die Woche fällt heraus.
    """
    games: dict[int, dict[int, dict]] = {pos: {} for pos in POSITIONS}
    warnings = []
    for key, by_pos in extract["teams"].items():
        team = int(key)
        for pos in POSITIONS:
            entry = by_pos.get(NAMES[pos]) or {"pts": [], "n": []}
            for week, pts, n in zip(extract["wochen"], entry["pts"], entry["n"]):
                if not n:
                    continue
                defense = prior_nfl[team].opponents.get(week) if team in prior_nfl else None
                if defense is None:
                    name = prior_nfl[team].abbrev if team in prior_nfl else key
                    warnings.append(f"Vorjahr W{week}: {NAMES[pos]} von {name} ohne Gegner laut Spielplan – übersprungen")
                    continue
                games[pos].setdefault(defense, {})[week] = dec(pts if pts is not None else 0)
    return {pos: {d: dict(sorted(w.items())) for d, w in sorted(g.items())} for pos, g in games.items()}, warnings


def pool_games(pools: dict[int, list], nfl: dict[int, rawdata.NflTeam]) -> tuple[dict[int, dict[int, dict]], list[str]]:
    """Saison: Position → Defense → {Woche: Σ Punkte der Spieler der Position gegen die Defense} aus den Spielerpools
    {Woche: [PoolRow]}; nur gespielt (210 == 1).

    Team = NFL-Team des Spiels (game_team, ohne Ist-Eintrag das heutige pro_team). Ohne Gegner in der Woche
    (Bye laut Spielplan oder unbekanntes Team): Warnung, der Spieler fällt heraus.
    """
    games: dict[int, dict[int, dict]] = {pos: {} for pos in POSITIONS}
    warnings = []
    for week, rows in sorted(pools.items()):
        for r in rows:
            if r.pos not in POSITIONS or not r.played:
                continue
            team = r.game_team or r.pro_team
            defense = nfl[team].opponents.get(week) if team in nfl else None
            if defense is None:
                name = nfl[team].abbrev if team in nfl else str(team)
                warnings.append(f"W{week}: {r.name} ({NAMES[r.pos]}) hat gespielt, Team {name} laut Spielplan ohne "
                                f"Spiel – übersprungen")
                continue
            weeks = games[r.pos].setdefault(defense, {})
            weeks[week] = weeks.get(week, ZERO) + (r.actual if r.actual is not None else ZERO)
    return {pos: {d: dict(sorted(w.items())) for d, w in sorted(g.items())} for pos, g in games.items()}, warnings


def scoring_points(settings: dict) -> dict[str, Decimal]:
    """statId (Text) → Punkte des Liga-Scorings ohne Overrides (espn_fetch.scoring_table), für den Abgleich mit dem
    Auszug des Vorjahrs."""
    return {str(stat): points for stat, (points, _) in ef.scoring_table(settings).items()}


# ---------------------------------------------------------------- Einstieg

def compute_matchup(ssn: rawdata.Season, weeks: list[int]) -> dict:
    """Positions-Matchup nach Woche N = weeks[-1]: je NFL-Defense und Position Z, r, F, Rang und Auslöser, dazu der
    NFL-Spielplan und F/Rang je Position für die Spielerwerte (player_mu). weeks = abgeschlossene Wochen 1…N.

    Vorwoche von W1 ist der Stand vor der Saison (n = 0 für alle). Zahlen als ungerundete Decimal; beim Export mit
    zahlen.rounded(…, precision=PRECISION) runden. Warnungen (Liste „warnungen“) gibt compute.py auf stderr aus.
    """
    through = weeks[-1]
    if list(weeks) != list(range(1, through + 1)):
        raise ValueError(f"Positions-Matchup braucht die Wochen 1…{through} ohne Lücke, nicht {weeks}")
    nfl = ssn.nfl()
    pools = {}
    for week in weeks:
        pools[week] = ssn.pool(week)
        if pools[week] is None:
            raise ef.FetchError(f"W{week}: {ef.KONA_FILE} fehlt – das Positions-Matchup braucht den Spielerpool jeder Woche")
    warnings: list[str] = []

    # Vorjahr: Z25, LS25, r25 je Position (fest für die ganze Saison); ohne Auszug r25 = 1,00 (Ligamittel)
    extract, prior_nfl = ssn.prior_positions(), ssn.prior_nfl()
    if extract is not None and prior_nfl is not None:
        source = "basis"
        games25, found = prior_games(extract, prior_nfl)
        warnings += found
        if {k: dec(v) for k, v in extract.get("scoring", {}).items()} != scoring_points(ssn.settings()):
            warnings.append(f"Liga-Scoring geändert – basis/positionen_{ssn.season - 1}.json löschen, "
                            f"der Wochenabruf holt sie neu")
    else:
        source, games25 = "ligamittel", {pos: {} for pos in POSITIONS}
    z25 = {pos: dst.means(games25[pos]) for pos in POSITIONS}
    ls25 = {pos: dst.league_average(z25[pos]) for pos in POSITIONS}
    r25 = {pos: {t: z25[pos][t] / ls25[pos] if t in z25[pos] else ONE for t in sorted(nfl)} for pos in POSITIONS}

    # Saison: Stand nach jeder Woche 0…N je Position, jeweils nur mit den Daten bis dahin
    games26, found = pool_games(pools, nfl)
    warnings += found
    states = {pos: {w: dst.season_state(games26[pos], w, r25[pos]) for w in range(0, through + 1)} for pos in POSITIONS}

    regular, playoffs = dst.season_weeks(ssn.settings())
    all_weeks = range(1, max(regular + playoffs) + 1)
    next_weeks = [w for w in range(through + 1, through + dst.NEXT_WEEKS + 1) if w in all_weeks]
    rest_weeks = [w for w in regular if w > through]

    # Rangsprung nur gegen eine Vorwoche mit Rangordnung: ohne Vorjahr teilen sich vor der Saison alle Defenses Rang 1
    # (F = 1,00), ein „Sprung“ davon aus wäre keiner
    ranked = {pos: len(set(states[pos][through - 1]["rang"].values())) > 1 for pos in POSITIONS}
    defenses = []
    for t in sorted(nfl):
        team = nfl[t]
        by_pos = {}
        for pos in POSITIONS:
            now, before = states[pos][through], states[pos][through - 1]
            delta = now["f"][t] - before["f"][t]
            rank_shift = before["rang"][t] - now["rang"][t] if ranked[pos] else None  # > 0: nach oben
            by_pos[NAMES[pos]] = {
                "z25": z25[pos].get(t), "n25": len(games25[pos].get(t, {})) if source == "basis" else None,
                "z26": now["z26"].get(t), "n": now["n"][t], "r25": r25[pos][t], "r26": now["r26"].get(t),
                "f": now["f"][t], "f_vorwoche": before["f"][t], "delta": delta,
                "rang": now["rang"][t], "rang_vorwoche": before["rang"][t],
                "ausloeser": dst.triggers(delta, None, rank_shift),
                "zugelassen": [games26[pos].get(t, {}).get(w) for w in weeks],
                "f_verlauf": [states[pos][w]["f"][t] for w in weeks],
            }
        defenses.append({"id": t, "abbrev": team.abbrev, "bye": next((w for w in all_weeks if w not in team.opponents), None),
                         "pos": by_pos})
    return {
        "saison": ssn.season, "vorjahr": ssn.season - 1, "through_week": through, "vorjahr_quelle": source,
        "positionen": [NAMES[pos] for pos in POSITIONS],
        "ligaschnitt": {NAMES[pos]: {str(ssn.season - 1): ls25[pos], str(ssn.season): states[pos][through]["ls26"]}
                        for pos in POSITIONS},
        "formel": FORMEL, "ausloeser_legende": AUSLOESER,
        "wochen": {"n1": through + 1 if through + 1 in all_weeks else None, "naechste3": next_weeks,
                   "rest": rest_weeks, "sos_po": playoffs},
        "defenses": defenses,
        "spielplan": {t: dict(nfl[t].opponents) for t in sorted(nfl)},
        "f": {NAMES[pos]: states[pos][through]["f"] for pos in POSITIONS},
        "rang": {NAMES[pos]: states[pos][through]["rang"] for pos in POSITIONS},
        "warnungen": warnings,
    }


# ---------------------------------------------------------------- Spielerwerte (Export)

def player_mu(m: dict | None, dst_result: dict | None, pos: int, pro_team: int) -> dict | None:
    """Spielplan-Faktoren eines Spielers: F und Rang des Gegners in Woche N+1, Ø F der nächsten 3 Kalenderwochen,
    Rest bis W14 und SoS W15–17 (dst.schedule_factor: eine Woche ohne Spiel fällt heraus).

    QB/RB/WR/TE/K aus dem Positions-Matchup m; D/ST aus den D/ST-Faktoren (F und Rang der gegnerischen Offense –
    gleiche Richtung, > 1 günstig für den Spieler). None ohne Daten, ohne NFL-Team oder für eine Position ohne
    Faktor. n1 = None, wenn es keine Woche N+1 gibt; Bye in N+1: opp, f und rang None.
    """
    if not m or pro_team not in m["spielplan"]:
        return None
    if pos == DST:
        if not dst_result:
            return None
        f = {t["id"]: t["f"] for t in dst_result["teams"]}
        rang = {t["id"]: t["rang"] for t in dst_result["teams"]}
    elif pos in NAMES and NAMES[pos] in m["f"]:
        f, rang = m["f"][NAMES[pos]], m["rang"][NAMES[pos]]
    else:
        return None
    opponents, wochen = m["spielplan"][pro_team], m["wochen"]
    abbrev = {d["id"]: d["abbrev"] for d in m["defenses"]}
    n1 = None
    if wochen["n1"] is not None:
        opp = opponents.get(wochen["n1"])
        n1 = {"week": wochen["n1"], "opp": abbrev.get(opp), "f": f.get(opp), "rang": rang.get(opp)}
    return {"n1": n1, "naechste3": dst.schedule_factor(f, opponents, wochen["naechste3"]),
            "rest": dst.schedule_factor(f, opponents, wochen["rest"]),
            "sos_po": dst.schedule_factor(f, opponents, wochen["sos_po"])}
