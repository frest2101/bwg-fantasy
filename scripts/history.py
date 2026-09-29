"""Liga-Historie 2015–2025 für die App (Baustein 4): All-Time, Saisons, PF+, Champions, abgeleitete Rekorde.

Quelle ist der einmalige Notion-Export unter data/history/*.csv (ohne Manager, siehe dortige README).
Schlüssel ist der Franchise-Slot 1–10 (= mTeam-ID). Punkte als ungerundete Decimal, gerundet wird erst beim Export.

Ära: Alt-Scoring 2015–2017 ergibt deutlich weniger Punkte als das BWG-Scoring ab 2018; die Regular Season hatte
2016–2020 13 Spiele, sonst 14. Saisonübergreifende Punkt-Rekorde werden deshalb je Ära und je Spiel verglichen,
PF+ (relativ zum Ligaschnitt der Saison) ist ohnehin vergleichbar.
"""

import statistics
from decimal import Decimal

import rawdata
from zahlen import HUNDRED, ZERO, dec

# scoring_era aus seasons.csv → kurzes Ära-Kennzeichen; ein neuer Wert muss hier bewusst eingetragen werden
ERAS = {"alt (2015–2017)": "alt", "BWG-Scoring ab 2018": "bwg"}
ERA_TEXT = {key: text for text, key in ERAS.items()}
LOWEST_PF_ERAS = ("bwg",)       # „wenigste PF“ nur seit 2018 (Auftrag Session 4)
FINAL, VERIFIED = "final", "verifiziert"
# Frage 11 c: 338,43 liegt nicht im Repo und kommt erst mit den kuratierten Rekorden
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


# ---------------------------------------------------------------- Einstieg

def compute_history(ssn: rawdata.Season) -> dict:
    """Liga-Historie für die App: alltime, seasons, team_seasons, champions, rekorde, spiele (Decimal ungerundet).

    rekorde = {"abgeleitet": [je Ära …], "hoechstes_einzelspiel": {…} oder None}. Keine Manager, keine Regeländerungen.
    """
    rows = ssn.history("team_seasons")
    formats = {int(f["season"]): f for f in ssn.history("seasons")}
    ts = team_seasons(rows, formats)
    names_2026 = {t["id"]: t["name"] for t in ssn.teams()}
    game_list = games(ssn.history("matchups_hist"), ts)
    return {
        "alltime": alltime(ts, ssn.history("franchises"), names_2026),
        "seasons": seasons(list(formats.values()), ts),
        "team_seasons": ts,
        "champions": champions(ts),
        "rekorde": {"abgeleitet": derived_records(ts), "hoechstes_einzelspiel": top_game(game_list, ts)},
        "spiele": game_list,
    }
