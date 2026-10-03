"""Tests Liga-Historie für die App (scripts/history.py) gegen docs/referenz_historie.md und an konstruierten Daten.

Die Sollwerte der Summen und Champions werden aus der Referenzdatei gelesen, nicht abgeschrieben.
Aufruf: python -m pytest
"""

import json
import re
from decimal import Decimal

import pytest

import espn_fetch as ef
import history
import rawdata
from zahlen import round_to, rounded

REFERENZ = ef.REPO_DIR / "docs" / "referenz_historie.md"
# Schlüssel, die in keiner Ausgabe vorkommen dürfen (Manager, Besitzer, Regeländerungen, ESPN-Texte)
VERBOTEN = {"manager", "managers", "members", "owners", "owner", "primaryowner", "memberid", "firstname", "lastname",
            "displayname", "outlooks", "seasonoutlook", "regeln", "regelaenderungen", "rule_changes", "notes"}


def table(heading: str) -> list[list[str]]:
    """Datenzeilen der Markdown-Tabelle unter „## <heading>…“ (ohne Kopf und Trennlinie)."""
    for block in REFERENZ.read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        if title.startswith(heading):
            rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in body.splitlines()
                    if line.startswith("|")]
            return rows[2:]
    raise LookupError(f"Abschnitt „{heading}“ fehlt in {REFERENZ.name}")


def num(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def keys(value) -> set[str]:
    """Alle Schlüssel eines verschachtelten dict/list-Baums."""
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value)) if value else set()
    return set()


@pytest.fixture(scope="module")
def ssn():
    return rawdata.Season(2026, 2)


@pytest.fixture(scope="module")
def hist(ssn):
    return history.compute_history(ssn)


@pytest.fixture(scope="module")
def alltime(hist):
    return {a["slot"]: a for a in hist["alltime"]}


@pytest.fixture(scope="module")
def team_seasons(hist):
    return {(t["season"], t["slot"]): t for t in hist["team_seasons"]}


# ---------------------------------------------------------------- PF+

def test_pf_plus_schnitt_je_saison_100(hist):
    by_season: dict[int, list[Decimal]] = {}
    for t in hist["team_seasons"]:
        by_season.setdefault(t["season"], []).append(t["pf_plus"])
    assert sorted(by_season) == list(range(2015, 2026))
    for season, values in by_season.items():
        assert abs(sum(values) / len(values) - 100) < Decimal("1e-20"), season


@pytest.mark.parametrize("season, slot, expected", [(2018, 2, "131.0"), (2016, 2, "119.4")])
def test_pf_plus_referenz(team_seasons, season, slot, expected):
    assert round_to(team_seasons[(season, slot)]["pf_plus"], 1) == Decimal(expected)


def test_pf_plus_formel(hist):
    for t in hist["team_seasons"]:
        same = [o["pf"] for o in hist["team_seasons"] if o["season"] == t["season"]]
        assert t["pf_plus"] == 100 * t["pf"] / (sum(same) / len(same))


def test_ligaschnitt_je_saison(hist):
    by_season = {s["season"]: s for s in hist["seasons"]}
    assert sorted(by_season) == list(range(2015, 2026))  # 2026 hat noch keine Team-Saisons
    for s in by_season.values():
        assert abs(s["ligaschnitt_pf_spiel"] * s["rs_games"] - s["ligaschnitt_pf"]) < Decimal("1e-20")


# ---------------------------------------------------------------- All-Time

@pytest.mark.parametrize("row", table("Summen je Franchise"), ids=lambda r: f"Slot {r[0]}")
def test_alltime_gegen_referenz(hist, alltime, row):
    slot, n, w, l, pf, pa, division, div_rank, final_rank, playoffs, scoring = row
    a = alltime[int(slot)]
    assert (a["saisons"], a["w"], a["l"], a["playoffs"], a["scoring_titel"]) \
        == (int(n), int(w), int(l), int(playoffs), int(scoring))
    assert (a["pf"], a["pa"]) == (num(pf), num(pa))
    assert a["platz_avg"] * a["saisons"] == int(final_rank)
    # Division und Div-Platz der Team-Saisons (Grundlage der Divisionssiege) gegen Σ Division und Σ Div-Platz
    mine = [t for t in hist["team_seasons"] if t["slot"] == int(slot)]
    assert (sum(t["division"] for t in mine), sum(t["div_rank"] for t in mine)) == (int(division), int(div_rank))


def test_titel_wie_champions_der_referenz(alltime):
    titles: dict[int, list[int]] = {}
    for season, slot, _team in table("Champions"):
        titles.setdefault(int(slot), []).append(int(season))
    for slot, a in alltime.items():
        assert a["titel"] == len(titles.get(slot, [])), slot
        assert a["titel_saisons"] == titles.get(slot, [])


def test_zaehler_gegen_referenz(hist):
    counts = {name: int(value) for name, value in table("Zähler")}
    total = {k: sum(a[k] for a in hist["alltime"]) for k in ("titel", "divisionssiege", "scoring_titel", "letzte")}
    assert total == {"titel": counts["Titel"], "divisionssiege": counts["Divisionssiege"],
                     "scoring_titel": counts["Scoring-Titel"], "letzte": counts["Letzte"]}


def test_w_pct_ist_w_durch_w_plus_l(hist):
    assert history.w_pct(95, 54) == Decimal(95) / Decimal(149) * 100
    assert round_to(history.w_pct(95, 54)) == Decimal("63.76")
    for a in hist["alltime"]:
        assert a["w_pct"] == Decimal(a["w"]) / (a["w"] + a["l"]) * 100
    for t in hist["team_seasons"]:
        assert t["w_pct"] == Decimal(t["w"]) / (t["w"] + t["l"]) * 100
    assert history.w_pct(0, 0) == 0  # ohne Spiel kein Fehler


def test_alltime_weitere_kennzahlen(hist, alltime):
    for slot, a in alltime.items():
        mine = [t for t in hist["team_seasons"] if t["slot"] == slot]
        assert a["finals"] == sum(t["final_rank"] <= 2 for t in mine)
        assert abs(a["pf_plus_avg"] - sum(t["pf_plus"] for t in mine) / len(mine)) < Decimal("1e-20")
    # nachgerechnet im Bauplan (bericht_architektur): Ø PF+ Hugh Jass 109,63, cool runnings 109,23
    assert round_to(alltime[2]["pf_plus_avg"]) == Decimal("109.63")
    assert round_to(alltime[4]["pf_plus_avg"]) == Decimal("109.23")


def test_alltime_sortierung_und_namen(ssn, hist):
    order = [(a["titel"], a["w_pct"]) for a in hist["alltime"]]
    assert order == sorted(order, key=lambda o: (-o[0], -o[1]))
    assert [a["slot"] for a in hist["alltime"]][:4] == [2, 4, 3, 1]  # 5 Titel, dann je 2 nach W %
    assert sorted(a["slot"] for a in hist["alltime"]) == list(range(1, 11))
    names = {t["id"]: t["name"] for t in ssn.teams()}
    for a in hist["alltime"]:
        assert a["name_2026"] == names[a["slot"]]
        assert a["namenskette"].split(" → ")[-1] == a["name_2026"]


def test_alltime_gleichstand_nach_slot():
    """Gleiche Titel und gleiche W % → Slot entscheidet (deterministisch); konstruierte Team-Saisons."""
    ts = [{"season": 2020, "slot": s, "w": 7, "l": 6, "pf": Decimal(2000), "pa": Decimal(1900),
           "pf_plus": Decimal(100), "final_rank": r, "div_rank": 1, "playoffs": True, "scoring_titel": False,
           "letzter": False} for s, r in ((3, 2), (1, 3), (2, 1))]
    franchises = [{"slot": str(s), "name_chain": f"T{s}"} for s in (3, 2, 1)]
    assert [a["slot"] for a in history.alltime(ts, franchises, {})] == [2, 1, 3]


def test_namenskette():
    assert history.namenskette("TeamK20 → SaureGurken", "SaureGurken") == "TeamK20 → SaureGurken"
    # erfundener Testname für eine Umbenennung in ESPN während der Saison
    assert history.namenskette("TeamK20 → SaureGurken", "Testname") == "TeamK20 → SaureGurken → Testname"
    assert history.namenskette("Hugh Jass", None) == "Hugh Jass"


# ---------------------------------------------------------------- Saisons, Team-Saisons, Champions

def test_team_seasons_und_aera(hist):
    assert len(hist["team_seasons"]) == 108
    assert [(t["season"], t["slot"]) for t in hist["team_seasons"]] \
        == sorted((t["season"], t["slot"]) for t in hist["team_seasons"])
    for t in hist["team_seasons"]:
        assert t["aera"] == ("alt" if t["season"] <= 2017 else "bwg")
        assert t["rs_games"] == (13 if 2016 <= t["season"] <= 2020 else 14) == t["w"] + t["l"]


def test_seasons_format_ohne_regeln(ssn, hist):
    csv_rows = {int(f["season"]): f for f in ssn.history("seasons")}
    allowed = {"season", "platform", "teams", "rs_games", "scoring_era", "aera", "qb_format", "keeper_mode",
               "divisions", "playoff_format", "ligaschnitt_pf", "ligaschnitt_pf_spiel"}
    names = {(t["season"], t["slot"]): t["team_name"] for t in hist["team_seasons"]}
    for s in hist["seasons"]:
        assert set(s) == allowed
        f = csv_rows[s["season"]]
        assert (s["platform"], s["teams"], s["rs_games"], s["scoring_era"]) \
            == (f["platform"], int(f["teams"]), int(f["rs_games"]), f["scoring_era"])
        # Divisionen aus den Team-Saisons stimmen mit den Namen in seasons.csv überein
        for d in s["divisions"]:
            expected = sorted(n.strip() for n in f[f"division_{d['division']}"].split(","))
            assert sorted(names[(s["season"], slot)] for slot in d["slots"]) == expected
    assert hist["seasons"][0]["qb_format"] is None and hist["seasons"][-1]["qb_format"] == "QB + Superflex"


@pytest.mark.parametrize("row", table("Champions"), ids=lambda r: r[0])
def test_champions_wie_referenz(hist, team_seasons, row):
    season, slot, team = row
    champion = next(c for c in hist["champions"] if c["season"] == int(season))
    assert (champion["slot"], champion["team_name"]) == (int(slot), team)
    t = team_seasons[(int(season), int(slot))]
    assert (champion["w"], champion["l"], champion["pf"], champion["pf_plus"], champion["scoring_titel"],
            champion["aera"]) == (t["w"], t["l"], t["pf"], t["pf_plus"], t["scoring_titel"], t["aera"])


def test_elf_champions(hist):
    assert [c["season"] for c in hist["champions"]] == list(range(2015, 2026))
    assert len(hist["champions"]) == len(table("Champions")) == 11


# ---------------------------------------------------------------- Rekorde

def record(hist, record_id: str, era: str) -> dict:
    return next(r for r in hist["rekorde"]["abgeleitet"] if (r["id"], r["aera"]) == (record_id, era))


def test_abgeleitete_rekorde(hist):
    ids = [(r["aera"], r["id"]) for r in hist["rekorde"]["abgeleitet"]]
    assert ids == [("alt", "beste_bilanz"), ("alt", "meiste_pf"), ("alt", "beste_pf_plus"),
                   ("bwg", "beste_bilanz"), ("bwg", "meiste_pf"), ("bwg", "beste_pf_plus"), ("bwg", "wenigste_pf")]
    # Gleichstand: alle Halter
    assert [(h["season"], h["slot"]) for h in record(hist, "beste_bilanz", "alt")["halter"]] == [(2015, 2), (2015, 4)]
    assert [(h["season"], h["slot"]) for h in record(hist, "beste_bilanz", "bwg")["halter"]] == [(2018, 2), (2019, 3)]
    best_plus = record(hist, "beste_pf_plus", "bwg")
    assert [(h["season"], h["slot"]) for h in best_plus["halter"]] == [(2018, 2)]
    assert round_to(best_plus["wert"], 1) == Decimal("131.0")
    assert [(h["season"], h["slot"]) for h in record(hist, "beste_pf_plus", "alt")["halter"]] == [(2016, 2)]


def test_pf_rekorde_je_spiel_und_era(hist):
    for r in hist["rekorde"]["abgeleitet"]:
        mine = [t for t in hist["team_seasons"] if t["aera"] == r["aera"]]
        assert r["saisons"] == sorted({t["season"] for t in mine})
        values = [t[r["kriterium"]] for t in mine]
        assert r["wert"] == (min(values) if r["id"] == "wenigste_pf" else max(values))
        assert all(h[r["kriterium"]] == r["wert"] for h in r["halter"])
    lowest = record(hist, "wenigste_pf", "bwg")
    assert lowest["kriterium"] == "pf_spiel" and min(lowest["saisons"]) == 2018


# unabhängig aus den CSV nachgerechnet (Prüfung 29.09.): Wert je Spiel, Halter (Saison, Slot), PF der Saison
@pytest.mark.parametrize("record_id, era, wert, halter", [
    ("meiste_pf", "alt", "176.54", [(2017, 4, "2295.00")]),
    ("meiste_pf", "bwg", "271.75", [(2018, 2, "3532.75")]),
    # nach Saisonsumme wäre es 2019 SpicyBears (2108,58 in 13 Spielen = 162,20 je Spiel)
    ("wenigste_pf", "bwg", "161.20", [(2021, 5, "2256.80")]),
], ids=lambda v: v if isinstance(v, str) else None)
def test_pf_rekorde_nachgerechnet(hist, record_id, era, wert, halter):
    r = record(hist, record_id, era)
    assert r["kriterium"] == "pf_spiel"
    assert round_to(r["wert"]) == Decimal(wert)
    assert [(h["season"], h["slot"], h["pf"]) for h in r["halter"]] == [(s, slot, Decimal(pf)) for s, slot, pf in halter]


def test_hoechstes_einzelspiel_verifiziert(hist):
    top = hist["rekorde"]["hoechstes_einzelspiel"]
    assert top["wert"] == Decimal("338.43")          # seit dem nfl.com-Export belegt (2018 W2), nicht das Allzeit-Hoch
    assert top["status"] == "verifiziert (nfl.com-Export)"
    assert top["hinweis"] == "ein höherer, unverifizierter Wert ist bekannt"
    (holder,) = top["halter"]
    assert (holder["season"], holder["week"], holder["slot"], holder["gegner_slot"], holder["sieg"]) \
        == (2018, 2, 2, 5, True)
    assert holder["team_name"] == "Hugh Jass" and holder["aera"] == "bwg"


def test_spiele_status(hist):
    assert len(hist["spiele"]) == 8
    for g in hist["spiele"]:
        assert g["rekordfaehig"] == (g["status"] == "final")
    assert {g["status"] for g in hist["spiele"] if not g["rekordfaehig"]} == {"live", "partial"}


def game(season, pts_a, pts_b, status, week=1, slot_a=1, slot_b=2):
    return {"season": str(season), "week": str(week), "round": "Regular Season", "slot_a": str(slot_a),
            "slot_b": str(slot_b), "pts_a": pts_a, "pts_b": pts_b,
            "winner_slot": str(slot_a if Decimal(pts_a) > Decimal(pts_b) else slot_b), "status": status,
            "source": "Screenshot"}


def test_rekordspiele_export_ersetzt_screenshots():
    """Erfundene Werte: In einer Saison des Exports zählt nur dessen Endstand, auch wenn ein Screenshot dort höher
    liegt (Stand vor einer Korrektur); in einer Saison ohne Export zählt der Screenshot."""
    ts = [{"season": s, "slot": slot, "team_name": f"T{slot}", "aera": "bwg"} for s in (2020, 2024) for slot in (1, 2)]
    export = [{"season": "2020", "week": "16", "round": "Final", "slot_a": "2", "slot_b": "1", "pts_a": "233.63",
               "pts_b": "229.27", "winner_slot": "2", "herleitung": "Endplatz"}]
    shots = [dict(export[0], pts_a="333.73", status="final", source="Screenshot"),
             {"season": "2024", "week": "17", "round": "Final", "slot_a": "2", "slot_b": "1", "pts_a": "261.17",
              "pts_b": "190.50", "winner_slot": "2", "status": "final", "source": "Screenshot"}]
    got = history.record_games(export, shots, ts)
    assert sorted((g["season"], g["pts_a"], g["source"]) for g in got) == [
        (2020, Decimal("233.63"), "nfl.com-Export"), (2024, Decimal("261.17"), "Screenshot")]
    top = history.top_game(got, ts)
    assert (top["wert"], top["status"]) == (Decimal("261.17"), "verifiziert (Screenshot)")


def test_live_und_partial_nie_rekord():
    ts = [{"season": 2020, "slot": s, "team_name": f"T{s}", "aera": "bwg"} for s in (1, 2, 3, 4)]
    games = history.games([game(2020, "400.00", "100.00", "live"),
                           game(2020, "150.00", "380.50", "partial", week=2, slot_a=3, slot_b=4),
                           game(2020, "250.10", "260.20", "final", week=3)], ts)
    top = history.top_game(games, ts)
    assert top["wert"] == Decimal("260.20")
    assert [(h["slot"], h["week"], h["sieg"]) for h in top["halter"]] == [(2, 3, True)]
    # nur live/partial → kein Rekord
    assert history.top_game(history.games([game(2020, "400.00", "100.00", "live")], ts), ts) is None


def test_einzelspiel_gleichstand_und_quelle():
    ts = [{"season": 2021, "slot": s, "team_name": f"T{s}", "aera": "bwg"} for s in (1, 2, 3, 4)]
    rows = [game(2021, "300.00", "200.00", "final"), game(2021, "120.00", "300.00", "final", week=2, slot_a=3, slot_b=4)]
    rows[1]["source"] = ""
    top = history.top_game(history.games(rows, ts), ts)
    assert [(h["week"], h["slot"]) for h in top["halter"]] == [(1, 1), (2, 4)]
    assert top["status"] == "verifiziert (Screenshot)"


def test_unbekannte_aera():
    assert history.era_key("BWG-Scoring ab 2018") == "bwg"
    with pytest.raises(ValueError):
        history.era_key("neue Ära 2030")


# ---------------------------------------------------------------- Ausgabe

def test_keine_manager_in_der_ausgabe(hist):
    found = {k for k in keys(hist) if k.lower() in VERBOTEN or "manager" in k.lower()}
    assert not found
    data = ef.load_json(ef.week_dir(2026, ef.local_weeks(2026)[-1]) / "mTeam.json")
    # voller Name, Nachname und Anzeigename wie im Öffentlichkeits-Check (ganzes Wort, ab 3 Zeichen)
    names = [n for m in data.get("members", [])
             for n in (f"{m.get('firstName', '')} {m.get('lastName', '')}".strip(), m.get("lastName", ""),
                       m.get("displayName", "")) if len(n) >= 3]
    if not names:
        pytest.skip("keine Manager-Namen in mTeam zum Abgleich")
    text = json.dumps(rounded(hist), ensure_ascii=False)
    hits = sum(1 for n in names if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text, re.IGNORECASE))
    assert not hits, f"{hits} Manager-Namen in der Ausgabe (Namen werden nicht ausgegeben)"


def test_export_serialisierbar_und_deterministisch(ssn, hist):
    text = json.dumps(rounded(hist), ensure_ascii=False, sort_keys=False)
    assert "Decimal" not in text
    assert json.dumps(rounded(history.compute_history(rawdata.Season(2026, 2))), ensure_ascii=False) == text
    assert set(hist) == {"alltime", "seasons", "team_seasons", "champions", "rekorde", "spiele", "wochen"}
