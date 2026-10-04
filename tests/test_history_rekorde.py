"""Tests kuratierte Rekorde (data/history/rekorde.csv, aus der Notion-DB Rekorde nach redaktioneller Durchsicht 04.10.2026).

Die Texte sind von Hand redigiert; die Tests binden die ableitbaren Kernwerte an die übrigen Dateien in data/history und
halten Personenbezüge, Chat-Quellen und Dateinamen draußen (das Repo ist öffentlich). Meldungen nennen nie den Fund.
Aufruf: python -m pytest
"""

import csv
import json
import re
from collections import defaultdict
from decimal import Decimal

import pytest

import espn_fetch as ef
import history
import rawdata

HISTORY = ef.REPO_DIR / "data" / "history"
KATEGORIEN = {"Saison", "Bilanz", "Titel", "Playoffs", "Rivalry", "Serie", "Woche"}
# Wörter, die auf Chat, Dateien, Personen als Quelle oder Unterstellungen zeigen (Durchsicht 04.10.2026)
VERBOTEN = re.compile(r"IMG_|\.jpe?g|\.png|WhatsApp|Chat|Regelchronik|Erinnerung|Notiz|Tanking|absichtlich|Brüder"
                      r"|\bAsse\b(?!'s)", re.IGNORECASE)


def rows(name: str) -> list[dict]:
    with open(HISTORY / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


REKORDE = {r["id"]: r for r in rows("rekorde.csv")}
TS = rows("team_seasons.csv")
GAMES = rows("games.csv")


def zahl(d: Decimal) -> str:
    return f"{d:.2f}".replace(".", ",")


def bilanz(t: dict) -> str:
    return f"{t['w']}-{t['l']}"


def quote(t: dict) -> Decimal:
    return Decimal(t["w"]) / (Decimal(t["w"]) + Decimal(t["l"]))


# ---------------------------------------------------------------- Form

def test_form_der_eintraege():
    assert len(REKORDE) == 22
    for rid, r in REKORDE.items():
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", rid), rid
        assert r["kategorie"] in KATEGORIEN, rid
        assert r["ableitbar"] in ("0", "1") and r["verifiziert"] in ("0", "1"), rid
        assert all(1 <= int(s) <= 10 for s in r["slots"].split("|") if s), rid
        assert all(2015 <= int(s) <= 2025 for s in r["saisons"].split("|") if s), rid
        assert all(len(r[k]) <= 400 for k in ("rekord", "wert", "details", "quelle")), rid   # check_public MAX_TEXT
        assert r["rekord"] and r["wert"] and r["quelle"], rid


def test_keine_chat_quellen_dateinamen_oder_unterstellungen():
    for rid, r in REKORDE.items():
        text = " ".join(r[k] for k in ("rekord", "wert", "details", "quelle"))
        assert not VERBOTEN.search(text), rid


def test_keine_vornamen_der_manager():
    """Vornamen prüft check_public nicht (sie stecken in Spielernamen); in den Rekordtexten gibt es keine Spieler,
    hier darf also kein Vorname eines Managers stehen. Teamnamen wie „SaschaM“ bleiben erlaubt (keine Wortgrenze)."""
    members = json.loads((ef.week_dir(2026, 1) / "mTeam.json").read_text(encoding="utf-8"))["members"]
    vornamen = {m["firstName"] for m in members if m.get("firstName")}
    for rid, r in REKORDE.items():
        text = " ".join(r[k] for k in ("rekord", "wert", "details", "quelle"))
        assert not any(re.search(rf"\b{re.escape(v)}\b", text) for v in vornamen), rid


# ---------------------------------------------------------------- Werte gegen data/history

def test_saisonrekorde_wie_team_seasons():
    meiste = max(TS, key=lambda t: Decimal(t["pf"]))
    assert REKORDE["meiste-punkte-in-einer-regular-season"]["wert"].startswith(zahl(Decimal(meiste["pf"])))
    assert (meiste["season"], meiste["slot"]) == ("2018", "2")
    bwg = [t for t in TS if int(t["season"]) >= 2018]
    wenigste = min(bwg, key=lambda t: Decimal(t["pf"]))
    assert REKORDE["wenigste-punkte-seit-scoring-umstellung-2018"]["wert"] == zahl(Decimal(wenigste["pf"]))


@pytest.mark.parametrize("rid, auswahl, best", [
    ("beste-regular-season-bilanz", lambda t: True, max),
    ("playoff-team-mit-schlechtester-bilanz", lambda t: t["playoffs"] == "1", min),
    ("vizemeister-mit-schlechtester-bilanz", lambda t: t["final_rank"] == "2", min),
    ("champion-mit-schlechtester-bilanz", lambda t: t["final_rank"] == "1", min),
])
def test_bilanzrekorde_wie_team_seasons(rid, auswahl, best):
    kandidaten = [t for t in TS if auswahl(t)]
    ziel = best(quote(t) for t in kandidaten)
    assert REKORDE[rid]["wert"] in {bilanz(t) for t in kandidaten if quote(t) == ziel}


def test_titel_und_playoffs_wie_team_seasons():
    titel = defaultdict(int)
    for t in TS:
        titel[t["slot"]] += t["final_rank"] == "1"
    assert REKORDE["meiste-titel"]["wert"].startswith(f"{max(titel.values())} ") and max(titel, key=titel.get) == "2"
    glo = [t for t in TS if t["slot"] == "8"]
    assert REKORDE["nie-champion-trotz-konstanter-playoffs"]["wert"] == (
        f"{sum(t['final_rank'] == '1' for t in glo)} Titel, {sum(t['final_rank'] in ('1', '2') for t in glo)} Finals, "
        f"{sum(t['playoffs'] == '1' for t in glo)} Playoff-Teilnahmen")
    hjs = [t for t in TS if t["slot"] == "2"]
    assert REKORDE["konstanz-hugh-jass"]["wert"] == (
        f"{sum(t['playoffs'] == '1' for t in hjs)} von {len(hjs)} Jahren Playoffs, "
        f"nie schlechter als Platz {max(int(t['final_rank']) for t in hjs)}")
    sas = {t["season"]: t["final_rank"] for t in TS if t["slot"] == "6"}
    assert (sas["2024"], sas["2025"]) == ("2", "2") and REKORDE["zwei-finals-in-folge-ohne-titel"]["wert"] == "2024, 2025"


def test_wochenrekorde_wie_games():
    seiten = [(Decimal(g[f"pts_{s}"]), g) for g in GAMES for s in ("a", "b")]
    assert REKORDE["team-wochenrekord-2018-2022"]["wert"] == zahl(max(p for p, _ in seiten))
    po = [p for p, g in seiten if g["round"] != "Regular Season"]
    assert REKORDE["hoechstes-playoff-ergebnis-2018-2022"]["wert"] == zahl(max(po))


def test_laengste_siegesserie_wie_games():
    """Über alle Spiele mit Gegner 2018–2022 in Reihenfolge (Saison, Woche); Byes unterbrechen nicht."""
    spiele = defaultdict(list)
    for g in sorted(GAMES, key=lambda g: (int(g["season"]), int(g["week"]))):
        for s, o in (("a", "b"), ("b", "a")):
            spiele[g[f"slot_{s}"]].append(g["winner_slot"] == g[f"slot_{s}"])
    def laengste(folge):
        best = lauf = 0
        for sieg in folge:
            lauf = lauf + 1 if sieg else 0
            best = max(best, lauf)
        return best
    serien = {slot: laengste(f) for slot, f in spiele.items()}
    assert REKORDE["laengste-siegesserie-2018-2022"]["wert"] == str(max(serien.values()))
    assert max(serien, key=serien.get) == "2"


# ---------------------------------------------------------------- Ausgabe

def test_kuratiert_in_compute_history():
    hist = history.compute_history(rawdata.Season(2026, 2))
    kuratiert = hist["rekorde"]["kuratiert"]
    assert [k["id"] for k in kuratiert] == list(REKORDE)
    k = next(k for k in kuratiert if k["id"] == "beste-regular-season-bilanz")
    assert (k["slots"], k["saisons"], k["ableitbar"], k["verifiziert"]) == ([2, 3], [2018, 2019], True, True)
