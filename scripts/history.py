"""Liga-Historie 2015–2025 für die App (Baustein 4): All-Time, Saisons, PF+, Champions, abgeleitete Rekorde und die
Wochen 2018–2022 (H2H, Wochenrekorde, All-Play).

Quelle ist der einmalige Notion-Export unter data/history/*.csv (ohne Manager, siehe dortige README), für die Wochen
2018–2022 die DSGVO-Auskunft von nfl.com (scripts/nfl_export.py).
Schlüssel ist der Franchise-Slot 1–10 (= mTeam-ID). Punkte als ungerundete Decimal, gerundet wird erst beim Export.

Ära: Alt-Scoring 2015–2017 ergibt deutlich weniger Punkte als das BWG-Scoring ab 2018; die Regular Season hatte
2016–2020 13 Spiele, sonst 14. Saisonübergreifende Punkt-Rekorde werden deshalb je Ära und je Spiel verglichen,
PF+ (relativ zum Ligaschnitt der Saison) ist ohnehin vergleichbar.
"""

import csv
import statistics
from decimal import Decimal

import espn_fetch as ef
import rawdata
import records
from zahlen import HALF, HUNDRED, ZERO, dec

# scoring_era aus seasons.csv → kurzes Ära-Kennzeichen; ein neuer Wert muss hier bewusst eingetragen werden
ERAS = {"alt (2015–2017)": "alt", "BWG-Scoring ab 2018": "bwg"}
ERA_TEXT = {key: text for text, key in ERAS.items()}
LOWEST_PF_ERAS = ("bwg",)       # „wenigste PF“ nur seit 2018 (Auftrag Session 4)
FINAL, VERIFIED = "final", "verifiziert"
EXPORT_QUELLE = "nfl.com-Export"
# 338,43 (Hugh Jass, 2018 W2) ist seit dem nfl.com-Export belegt (team_weeks.csv), aber nicht das Allzeit-Hoch: Ein
# höherer Wert eines anderen Teams, vermutlich 2023–2025, ist bekannt und unverifiziert (Stephan 03.10.2026)
HINWEIS_HOECHSTES_SPIEL = "ein höherer, unverifizierter Wert ist bekannt"


# ---------------------------------------------------------------- Grundlagen

def era_key(scoring_era: str) -> str:
    """Ära-Kennzeichen ("alt" oder "bwg") aus seasons.scoring_era; unbekannte Ära → ValueError."""
    if scoring_era not in ERAS:
        raise ValueError(f"unbekannte Scoring-Ära „{scoring_era}“ in data/history/seasons.csv")
    return ERAS[scoring_era]


def w_pct(w: int, l: int) -> Decimal:
    """W % = W / (W + L) · 100 (die Historie kennt keine Unentschieden)."""
    return Decimal(w) / Decimal(w + l) * HUNDRED if w + l else ZERO


def season_averages(rows: list[dict]) -> dict[int, tuple[Decimal, int]]:
    """Je Saison aus team_seasons.csv: (Ligaschnitt-PF = Ø PF aller Teams, Teamzahl)."""
    by_season: dict[int, list[Decimal]] = {}
    for r in rows:
        by_season.setdefault(int(r["season"]), []).append(dec(r["pf"]))
    return {season: (sum(pfs, ZERO) / len(pfs), len(pfs)) for season, pfs in sorted(by_season.items())}


# ---------------------------------------------------------------- Tabellen

def team_seasons(rows: list[dict], formats: dict[int, dict]) -> list[dict]:
    """Alle Team-Saisons mit W %, PF/Spiel, PF+ = 100 · PF / Ø PF aller Teams der Saison, „letzter“
    (Endplatz = Teamzahl) und Ära-Kennzeichen (aera, rs_games: 13 oder 14 Spiele).

    formats: Zeilen aus seasons.csv je Saison. Sortiert nach Saison und Slot.
    """
    averages = season_averages(rows)
    result = []
    for r in rows:
        season = int(r["season"])
        w, l, pf = int(r["w"]), int(r["l"]), dec(r["pf"])
        avg_pf, n_teams = averages[season]
        fmt = formats[season]
        result.append({
            "season": season, "slot": int(r["slot"]), "team_name": r["team_name"],
            "division": int(r["division"]), "div_rank": int(r["div_rank"]),
            "w": w, "l": l, "w_pct": w_pct(w, l),
            "pf": pf, "pa": dec(r["pa"]), "pf_spiel": pf / (w + l),
            "pf_plus": HUNDRED * pf / avg_pf,
            "final_rank": int(r["final_rank"]), "playoffs": r["playoffs"] == "1",
            "scoring_titel": r["scoring_title"] == "1",
            "letzter": int(r["final_rank"]) == n_teams,
            "aera": era_key(fmt["scoring_era"]), "rs_games": int(fmt["rs_games"]),
        })
    return sorted(result, key=lambda t: (t["season"], t["slot"]))


def seasons(format_rows: list[dict], ts: list[dict]) -> list[dict]:
    """Format je gespielter Saison (ohne Regeländerungen und Draft) mit Ligaschnitt PF und PF/Spiel.

    Divisionen als Slots aus den Team-Saisons. Saisons ohne Team-Zeilen (die laufende) fehlen.
    """
    result = []
    for f in sorted(format_rows, key=lambda f: int(f["season"])):
        season = int(f["season"])
        teams = [t for t in ts if t["season"] == season]
        if not teams:
            continue
        pfs = [t["pf"] for t in teams]
        result.append({
            "season": season, "platform": f["platform"], "teams": int(f["teams"]), "rs_games": int(f["rs_games"]),
            "scoring_era": f["scoring_era"], "aera": era_key(f["scoring_era"]),
            "qb_format": f["qb_format"] or None, "keeper_mode": f["keeper_mode"] or None,
            "divisions": [{"division": d, "slots": [t["slot"] for t in teams if t["division"] == d]}
                          for d in sorted({t["division"] for t in teams})],
            "playoff_format": f["playoff_format"] or None,
            "ligaschnitt_pf": sum(pfs, ZERO) / len(pfs),
            "ligaschnitt_pf_spiel": sum(pfs, ZERO) / sum(t["w"] + t["l"] for t in teams),
        })
    return result


def namenskette(chain: str, name_2026: str | None) -> str:
    """Namenskette aus franchises.csv; weicht der aktuelle ESPN-Name vom letzten Glied ab, wird er angehängt."""
    if name_2026 and chain.split(" → ")[-1] != name_2026:
        return f"{chain} → {name_2026}"
    return chain


def alltime(ts: list[dict], franchises: list[dict], names_2026: dict[int, str]) -> list[dict]:
    """All-Time je Franchise-Slot: Bilanz, W % = W/(W+L), PF, PA, Ø PF+, Titel, Finals, Playoffs, Divisionssiege,
    Scoring-Titel, Letzte (Endplatz = Teamzahl der Saison), Ø Endplatz.

    Sortiert nach Titeln, dann W % (absteigend), dann Slot.
    """
    result = []
    for f in franchises:
        slot = int(f["slot"])
        mine = [t for t in ts if t["slot"] == slot]
        if not mine:
            continue
        w, l = sum(t["w"] for t in mine), sum(t["l"] for t in mine)
        name = names_2026.get(slot) or f["name_chain"].split(" → ")[-1]
        result.append({
            "slot": slot, "name_2026": name, "namenskette": namenskette(f["name_chain"], name),
            "saisons": len(mine), "w": w, "l": l, "w_pct": w_pct(w, l),
            "pf": sum((t["pf"] for t in mine), ZERO), "pa": sum((t["pa"] for t in mine), ZERO),
            "pf_plus_avg": statistics.mean(t["pf_plus"] for t in mine),
            "titel": sum(t["final_rank"] == 1 for t in mine),
            "titel_saisons": [t["season"] for t in mine if t["final_rank"] == 1],
            "finals": sum(t["final_rank"] <= 2 for t in mine),
            "playoffs": sum(t["playoffs"] for t in mine),
            "divisionssiege": sum(t["div_rank"] == 1 for t in mine),
            "scoring_titel": sum(t["scoring_titel"] for t in mine),
            "letzte": sum(t["letzter"] for t in mine),
            "platz_avg": Decimal(sum(t["final_rank"] for t in mine)) / len(mine),
        })
    return sorted(result, key=lambda a: (-a["titel"], -a["w_pct"], a["slot"]))


def champions(ts: list[dict]) -> list[dict]:
    """Champion je Saison (Endplatz 1) mit Name der Saison, Bilanz, PF, PF+, Scoring-Titel und Ära."""
    keep = ("season", "slot", "team_name", "w", "l", "pf", "pf_plus", "scoring_titel", "aera", "rs_games")
    return [dict({k: t[k] for k in keep}, scoring_era=ERA_TEXT[t["aera"]]) for t in ts if t["final_rank"] == 1]


# ---------------------------------------------------------------- Rekorde

def _holders(ts: list[dict], key: str, best) -> tuple[Decimal, list[dict]]:
    """Bestwert (best = max oder min) des Schlüssels und alle Team-Saisons mit genau diesem Wert (Gleichstand)."""
    value = best(t[key] for t in ts)
    keep = ("season", "slot", "team_name", "w", "l", "w_pct", "pf", "pf_spiel", "pf_plus", "rs_games")
    return value, [{k: t[k] for k in keep} for t in ts if t[key] == value]


def derived_records(ts: list[dict]) -> list[dict]:
    """Abgeleitete All-Time-Rekorde je Ära aus den Team-Saisons (Regular Season).

    beste Bilanz (höchstes W %), meiste PF (höchstes PF/Spiel, weil 13 und 14 Spiele in einer Ära vorkommen),
    beste PF+, wenigste PF (niedrigstes PF/Spiel, nur seit 2018). Bei Gleichstand stehen alle Halter drin.
    """
    records = []
    eras = sorted({t["aera"] for t in ts}, key=lambda e: min(t["season"] for t in ts if t["aera"] == e))
    for era in eras:
        mine = [t for t in ts if t["aera"] == era]
        specs = [("beste_bilanz", "w_pct", max), ("meiste_pf", "pf_spiel", max), ("beste_pf_plus", "pf_plus", max)]
        if era in LOWEST_PF_ERAS:
            specs.append(("wenigste_pf", "pf_spiel", min))
        for record_id, key, best in specs:
            value, holders = _holders(mine, key, best)
            records.append({"id": record_id, "aera": era, "scoring_era": ERA_TEXT[era],
                            "saisons": sorted({t["season"] for t in mine}), "kriterium": key, "wert": value,
                            "halter": holders})
    return records


def games(matchups: list[dict], ts: list[dict]) -> list[dict]:
    """Die belegten Einzelspiele vor 2026 mit Teamnamen der Saison; rekordfähig nur mit Status final."""
    names = {(t["season"], t["slot"]): t["team_name"] for t in ts}
    result = []
    for m in matchups:
        season = int(m["season"])
        slot_a, slot_b = int(m["slot_a"]), int(m["slot_b"])
        result.append({
            "season": season, "week": int(m["week"]), "round": m["round"],
            "slot_a": slot_a, "name_a": names.get((season, slot_a)), "pts_a": dec(m["pts_a"]),
            "slot_b": slot_b, "name_b": names.get((season, slot_b)), "pts_b": dec(m["pts_b"]),
            "winner_slot": int(m["winner_slot"]), "status": m["status"], "source": m["source"] or None,
            "rekordfaehig": m["status"] == FINAL,
        })
    return sorted(result, key=lambda g: (g["season"], g["week"], g["slot_a"]))


def kuratierte_rekorde(rows: list[dict]) -> list[dict]:
    """rekorde.csv typisiert: die kuratierten Rekorde aus dem Notion-Ligaarchiv nach redaktioneller Durchsicht
    (ohne Manager, ohne Chat-Quellen und Dateinamen). slots und saisons sind mit „|“ getrennt, ableitbar/verifiziert 0/1."""
    def liste(text: str) -> list[int]:
        return [int(x) for x in text.split("|") if x]
    return [{"id": r["id"], "kategorie": r["kategorie"], "rekord": r["rekord"], "wert": r["wert"],
             "details": r["details"], "quelle": r["quelle"], "ableitbar": r["ableitbar"] == "1",
             "verifiziert": r["verifiziert"] == "1", "slots": liste(r["slots"]), "saisons": liste(r["saisons"])}
            for r in rows]


def record_games(export: list[dict], matchups: list[dict], ts: list[dict]) -> list[dict]:
    """Spiele für das höchste Einzelspiel: für die Saisons des nfl.com-Exports dessen Endstände (games.csv, final),
    für alle übrigen Saisons die Screenshot-Spiele aus matchups_hist.csv – nie beide für dieselbe Saison."""
    covered = {int(g["season"]) for g in export}
    return games([dict(g, status=FINAL, source=EXPORT_QUELLE) for g in export]
                 + [m for m in matchups if int(m["season"]) not in covered], ts)


def top_game(game_list: list[dict], ts: list[dict]) -> dict | None:
    """Höchster Einzelscore aus den Spielen mit Status final; live/partial zählen nie. None ohne finales Spiel.

    Der Wert gilt als „verifiziert (<Quelle>)“; dazu der Hinweis, dass ein höherer, unverifizierter Wert bekannt ist.
    """
    eras = {t["season"]: t["aera"] for t in ts}
    sides = [(g[f"pts_{s}"], g, s, o) for g in game_list if g["rekordfaehig"] for s, o in (("a", "b"), ("b", "a"))]
    if not sides:
        return None
    value = max(pts for pts, *_ in sides)
    best = [(g, s, o) for pts, g, s, o in sides if pts == value]
    holders = []
    for g, s, o in best:
        holders.append({"season": g["season"], "week": g["week"], "round": g["round"], "aera": eras.get(g["season"]),
                        "slot": g[f"slot_{s}"], "team_name": g[f"name_{s}"],
                        "gegner_slot": g[f"slot_{o}"], "gegner_name": g[f"name_{o}"], "gegner_pts": g[f"pts_{o}"],
                        "sieg": g["winner_slot"] == g[f"slot_{s}"]})
    sources = sorted({g["source"] for g, *_ in best if g["source"]})
    return {"id": "hoechstes_einzelspiel", "kriterium": "pts", "wert": value,
            "status": f"{VERIFIED} ({', '.join(sources)})" if sources else VERIFIED,
            "hinweis": HINWEIS_HOECHSTES_SPIEL, "halter": holders}


# ---------------------------------------------------------------- Wochen 2018–2022 (nfl.com-Export)
# Quelle: DSGVO-Auskunft nfl.com, einmalig importiert mit scripts/nfl_export.py (data/history/README.md). Eigene
# Statistik der nfl.com-Ära: nie mit den Rekorden der ESPN-Saisons ab 2026 mischen (Statistik-Neustart, Scoring seit
# 18.09.2026 anders). In compute_history unter „wochen“; die App zeigt es noch nicht.

RS, PO = "RS", "PO"
REGULAR = "Regular Season"
WOCHEN_REKORDE = ("hoechster_score", "niedrigster_score", "groesster_sieg", "knappstes_ergebnis", "hoechste_bank")
TOP_N = 5
HUGH_JASS_DATEI = "hugh_jass_2023_2025.csv"


def read_commented(name: str) -> list[dict]:
    """data/history/<name> mit Kopfzeilen „# …“ (Umfang der Datei) als Zeilen; die Kommentarzeilen fallen weg."""
    with open(ef.REPO_DIR / "data" / rawdata.HISTORY_DIR / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def _count(text: str) -> int | None:
    return int(text) if text != "" else None


def week_rows(rows: list[dict]) -> list[dict]:
    """team_weeks.csv typisiert: Punkte und Bank als Decimal; All-Play und Ergebnis gibt es nur in der Regular Season
    (in den Playoffs None)."""
    return [{"season": int(r["season"]), "week": int(r["week"]), "phase": r["phase"], "slot": int(r["slot"]),
             "pts": dec(r["pts"]), "bench": dec(r["bench_pts"]), "allplay_w": _count(r["allplay_w"]),
             "allplay_l": _count(r["allplay_l"]), "allplay_t": _count(r["allplay_t"]), "result": r["result"] or None}
            for r in rows]


def game_sides(games: list[dict], weeks: list[dict], ts: list[dict]) -> list[dict]:
    """Je Spiel aus games.csv zwei Team-Wochen im Format von records.py (team_id = Slot, opponent_id, pf, pa,
    result W/L/T, bench) mit Saison, Phase, Runde und den Teamnamen der Saison.

    Wochen ohne Spiel in games.csv sind kein Spiel: Byes der Divisionssieger, die Woche der Verlierer der Runde 1 vor
    dem Spiel um Platz 5 und die Trostrunde (Format unbekannt).
    """
    bench = {(w["season"], w["week"], w["slot"]): w["bench"] for w in weeks}
    names = {(t["season"], t["slot"]): t["team_name"] for t in ts}
    sides = []
    for g in games:
        season, week = int(g["season"]), int(g["week"])
        a, b = int(g["slot_a"]), int(g["slot_b"])
        pts = {a: dec(g["pts_a"]), b: dec(g["pts_b"])}
        for me, other in ((a, b), (b, a)):
            result = "W" if pts[me] > pts[other] else "L" if pts[me] < pts[other] else "T"
            sides.append({"season": season, "week": week, "phase": RS if g["round"] == REGULAR else PO,
                          "round": g["round"], "team_id": me, "team_name": names.get((season, me)),
                          "opponent_id": other, "opponent_name": names.get((season, other)),
                          "pf": pts[me], "pa": pts[other], "result": result, "bench": bench[(season, week, me)]})
    return sorted(sides, key=lambda s: (s["season"], s["week"], s["team_id"]))


def h2h_wochen(sides: list[dict], slots: list[int]) -> dict[str, list[dict]]:
    """H2H je Franchise-Paar a < b über alle Saisons des Exports, Regular Season und Playoffs getrennt
    (records.h2h: spiele, w_a, l_a, t, pf_diff = Σ PF a − Σ PF b; Paare ohne Spiel mit Nullen)."""
    return {phase: records.h2h([s for s in sides if s["phase"] == phase], team_ids=slots) for phase in (RS, PO)}


def top(candidates: list, value, n: int = TOP_N, highest: bool = True) -> list:
    """Die n besten Kandidaten nach value; wer mit dem n-ten gleichauf liegt, kommt mit (Reihenfolge der Eingabe
    bei Gleichstand bleibt)."""
    ordered = sorted(candidates, key=value, reverse=highest)
    if len(ordered) <= n:
        return ordered
    cutoff = value(ordered[n - 1])
    return [c for c in ordered if (value(c) >= cutoff if highest else value(c) <= cutoff)]


def _side_entry(s: dict, value: Decimal) -> dict:
    keep = ("season", "week", "round", "team_id", "team_name", "opponent_id", "opponent_name", "pf", "pa")
    return dict({k: s[k] for k in keep}, wert=value)


def _game_entry(s: dict) -> dict:
    """Spiel aus Sicht des Siegers: team_ids/namen/punkte = [Sieger, Verlierer], wert = Differenz."""
    return {"season": s["season"], "week": s["week"], "round": s["round"],
            "team_ids": [s["team_id"], s["opponent_id"]], "namen": [s["team_name"], s["opponent_name"]],
            "punkte": [s["pf"], s["pa"]], "wert": s["pf"] - s["pa"], "unentschieden": s["result"] == "T"}


def wochen_rekorde(sides: list[dict], n: int = TOP_N) -> dict[str, dict[str, list[dict]]]:
    """Wochenrekorde je Phase (RS, PO), je Rekord die n besten Einträge (Gleichstand an der Grenze kommt mit).

    Nur Spiele mit Gegner (game_sides). Team-Woche: höchster und niedrigster Score, höchste Bankpunkte. Spiel aus Sicht
    des Siegers: größter Sieg (ohne Unentschieden), knappstes Ergebnis (Unentschieden = 0 zählt mit).
    """
    result = {}
    for phase in (RS, PO):
        mine = [s for s in sides if s["phase"] == phase]
        games = records.game_rows(mine)
        margin = lambda s: s["pf"] - s["pa"]
        result[phase] = {
            "hoechster_score": [_side_entry(s, s["pf"]) for s in top(mine, lambda s: s["pf"], n)],
            "niedrigster_score": [_side_entry(s, s["pf"]) for s in top(mine, lambda s: s["pf"], n, highest=False)],
            "groesster_sieg": [_game_entry(s) for s in top([s for s in games if s["result"] == "W"], margin, n)],
            "knappstes_ergebnis": [_game_entry(s) for s in top(games, margin, n, highest=False)],
            "hoechste_bank": [_side_entry(s, s["bench"]) for s in top(mine, lambda s: s["bench"], n)],
        }
    return result


def allplay_saisons(weeks: list[dict], ts: list[dict]) -> list[dict]:
    """All-Play je Saison und Slot (nur Regular Season): Summe der Wochenvergleiche aus dem Export und
    All-Play % = (W + 0,5·T) / (W + L + T) · 100, dazu die echte Bilanz. Sortiert nach Saison, All-Play % absteigend,
    Slot."""
    teams = {(t["season"], t["slot"]): t for t in ts}
    sums = {}
    for w in weeks:
        if w["phase"] != RS:
            continue
        s = sums.setdefault((w["season"], w["slot"]), {"allplay_w": 0, "allplay_l": 0, "allplay_t": 0, "spiele": 0})
        for k in ("allplay_w", "allplay_l", "allplay_t"):
            s[k] += w[k]
        s["spiele"] += 1
    result = []
    for (season, slot), s in sums.items():
        t = teams[(season, slot)]
        vergleiche = s["allplay_w"] + s["allplay_l"] + s["allplay_t"]
        result.append(dict(s, season=season, slot=slot, team_name=t["team_name"], w=t["w"], l=t["l"],
                           allplay_pct=(s["allplay_w"] + HALF * s["allplay_t"]) / vergleiche * HUNDRED))
    return sorted(result, key=lambda r: (r["season"], -r["allplay_pct"], r["slot"]))


def wochen_spiele(games: list[dict], weeks: list[dict]) -> list[dict]:
    """Spiele des Exports für die Wochenansicht der App: je Spiel aus games.csv Saison, Woche, Runde, Herleitung
    (in den Playoffs: Bracket, Screenshot, Bestätigt, Seed-Regel oder Endplatz) und beide Seiten mit Punkten und
    Bankpunkten; winner_slot None bei Unentschieden. Teamnamen stehen in team_seasons (Saison, Slot)."""
    bench = {(w["season"], w["week"], w["slot"]): w["bench"] for w in weeks}
    result = []
    for g in games:
        season, week, a, b = int(g["season"]), int(g["week"]), int(g["slot_a"]), int(g["slot_b"])
        result.append({"season": season, "week": week, "round": g["round"], "herleitung": g["herleitung"],
                       "slot_a": a, "pts_a": dec(g["pts_a"]), "bench_a": bench[(season, week, a)],
                       "slot_b": b, "pts_b": dec(g["pts_b"]), "bench_b": bench[(season, week, b)],
                       "winner_slot": int(g["winner_slot"]) if g["winner_slot"] else None})
    return sorted(result, key=lambda s: (s["season"], s["week"], s["slot_a"]))


def wochen_ohne_gegner(games: list[dict], weeks: list[dict]) -> list[dict]:
    """Team-Wochen ohne Spiel in games.csv (nur Playoff-Wochen: Bye der Divisionssieger, Woche der Verlierer der
    Runde 1 vor dem Spiel um Platz 5, Trostrunde) mit Punkten und Bank – Punkte ohne Gegner, kein Rekord."""
    played = {(int(g["season"]), int(g["week"]), int(g[k])) for g in games for k in ("slot_a", "slot_b")}
    return [{"season": w["season"], "week": w["week"], "phase": w["phase"], "slot": w["slot"], "pts": w["pts"],
             "bench": w["bench"]} for w in weeks if (w["season"], w["week"], w["slot"]) not in played]


def hugh_jass_wochen(rows: list[dict]) -> list[dict]:
    """hugh_jass_2023_2025.csv typisiert (nur Slot 2, nur Regular Season, ohne Gegner)."""
    return [{"season": int(r["season"]), "week": int(r["week"]), "slot": int(r["slot"]), "pf": dec(r["pts"]),
             "pa": dec(r["pts_against"]), "result": r["result"]} for r in rows]


# ---------------------------------------------------------------- Einstieg

def compute_history(ssn: rawdata.Season) -> dict:
    """Liga-Historie für die App: alltime, seasons, team_seasons, champions, rekorde, spiele, wochen (Decimal ungerundet).

    rekorde = {"abgeleitet": [je Ära …], "hoechstes_einzelspiel": {…} oder None, "kuratiert": [aus rekorde.csv]}.
    Keine Manager, keine Regeländerungen.
    wochen = nfl.com-Ära 2018–2022: saisons, spiele (Paarungen je Woche) und ohne_gegner (Playoff-Wochen ohne Spiel),
    h2h und rekorde je Phase (RS, PO), allplay je Team-Saison, dazu hugh_jass_2023_2025 (nur dieses Team, ohne Gegner).
    """
    rows = ssn.history("team_seasons")
    formats = {int(f["season"]): f for f in ssn.history("seasons")}
    ts = team_seasons(rows, formats)
    names_2026 = {t["id"]: t["name"] for t in ssn.teams()}
    game_list = games(ssn.history("matchups_hist"), ts)
    weeks = week_rows(ssn.history("team_weeks"))
    game_rows = ssn.history("games")
    sides = game_sides(game_rows, weeks, ts)
    return {
        "alltime": alltime(ts, ssn.history("franchises"), names_2026),
        "seasons": seasons(list(formats.values()), ts),
        "team_seasons": ts,
        "champions": champions(ts),
        "rekorde": {"abgeleitet": derived_records(ts), "hoechstes_einzelspiel": top_game(
            record_games(game_rows, ssn.history("matchups_hist"), ts), ts),
            "kuratiert": kuratierte_rekorde(ssn.history("rekorde"))},
        "spiele": game_list,
        "wochen": {
            "saisons": sorted({w["season"] for w in weeks}),
            "spiele": wochen_spiele(game_rows, weeks),
            "ohne_gegner": wochen_ohne_gegner(game_rows, weeks),
            "h2h": h2h_wochen(sides, sorted({w["slot"] for w in weeks})),
            "rekorde": wochen_rekorde(sides),
            "allplay": allplay_saisons(weeks, ts),
            "hugh_jass_2023_2025": hugh_jass_wochen(read_commented(HUGH_JASS_DATEI)),
        },
    }
