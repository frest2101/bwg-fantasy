"""Spieler-Stammdaten von nflverse für das Altersprofil im Keeper-Tab (Stufe 2, Freigabe Stephan 01.10.2026).

ESPNs Fantasy-API führt weder Alter noch Erfahrung. Die Spielerliste von nflverse (Release „players“ des Repos
nflverse/nflverse-data, Lizenz CC BY 4.0) führt je Spieler die ESPN-ID, das Geburtsdatum, die Rookie-Saison und den
NFL-Draft; sie trifft über die ESPN-ID alle Kaderspieler der Liga (geprüft 30.09.2026: 213/213, Pool 1012/1018).

- Abruf (Wochenabruf, espn_fetch.py --due bei den Saisondateien): eine Anfrage, players.csv.gz mit rund 2,5 MB.
  Abgelegt wird nur ein Auszug für die Spieler des ESPN-Pools unter nflverse/players.json: je ESPN-ID Geburtsdatum,
  Rookie-Saison und Draft (Jahr, Runde, Pick) – rund 70 KB, eine Zeile je Spieler. Die Werte stehen dort unverändert.
- Lesen (compute.py → keeper.py): stammdaten() wendet die Korrekturen KORREKTUR an, age() rechnet das Alter zum
  Stichtag. Erfahrung wird nicht übernommen, sondern gerechnet (Saison − Rookie-Saison + 1): Die Erfahrungsfelder der
  Quellen zählen verschieden (nflverse und ESPN springen von 0 auf 2).
- Lizenz: Namensnennung mit Verweis auf die Lizenz und Hinweis auf die Änderung (Auszug) – im Kopf der Datei, im README
  und in der App. nflverse stellt die Liste aus NFL-, ESPN-, PFR- und OTC-Daten zusammen.
"""

import csv
import gzip
import io
import json
import sys
import zlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import requests

import espn_fetch as ef

URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv.gz"
QUELLE = "nflverse players (https://github.com/nflverse/nflverse-data, Release players), Auszug für die Spieler des ESPN-Pools"
LIZENZ = "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)"
COLUMNS = ("espn_id", "birth_date", "rookie_season", "draft_year", "draft_round", "draft_pick", "last_season")
MIN_SHARE = Decimal("0.8")   # so viele der gesuchten Spieler muss die Liste mindestens treffen, sonst gilt sie als kaputt
DAYS_PER_YEAR = Decimal("365.25")
# Geburtsdaten, die nflverse falsch führt (ESPN-ID → Datum). Geprüft 30.09.2026 gegen ESPNs Athleten-Daten,
# DynastyProcess und Sleeper, jeweils drei zu eins; gilt, bis nflverse dasselbe Datum liefert (dann Eintrag streichen).
KORREKTUR = {4569603: "2001-01-04",   # Malik Washington, WR MIA (nflverse: 2000-10-20)
             4882093: "2003-02-14"}   # Bhayshul Tuten, RB JAX (nflverse: 2002-02-14)


def path(season: int) -> Path:
    return ef.RAW_DIR / str(season) / "nflverse" / "players.json"


# ---------------------------------------------------------------- Abruf (Wochenabruf)

def pool_ids(season: int) -> set[int]:
    """ESPN-IDs, für die der Auszug Stammdaten sucht: alle Spieler des Tagesstands (pool/latest.json) und des
    Spielerpools der jüngsten lokalen Woche; D/ST (negative IDs) haben kein Alter und fallen weg."""
    ids: set[int] = set()
    latest = ef.pool_dir(season) / ef.POOL_FILE
    if latest.exists():
        ids |= {p["id"] for p in ef.load_json(latest).get("players", [])}
    weeks = ef.local_weeks(season)
    kona = ef.week_dir(season, weeks[-1]) / ef.KONA_FILE if weeks else None
    if kona and kona.exists():
        ids |= {p["id"] for p in ef.load_json(kona).get("players", [])}
    return {i for i in ids if i > 0}


def number(text: str) -> int | None:
    """Ganze Zahl aus einem CSV-Feld („2022“, „7.0“); None bei leerem oder unlesbarem Feld."""
    try:
        return int(float(text))
    except (TypeError, ValueError, OverflowError):
        return None


def extract(text: str, ids: set[int]) -> dict:
    """Auszug aus players.csv für die ESPN-IDs ids: je Spieler {"geb": JJJJ-MM-TT oder None, "rookie": Saison oder
    None, "draft": [Jahr, Runde, Pick] oder None (ungedraftet)}, nach ID sortiert.

    Führt die Liste eine ESPN-ID doppelt, gilt die Zeile mit der jüngeren letzten Saison. Fehlen Spalten oder trifft
    die Liste weniger als MIN_SHARE der gesuchten Spieler, gilt sie als unbrauchbar (FetchError) – der alte Auszug
    bleibt dann stehen.
    """
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ef.FetchError(f"nflverse players: Spalten fehlen ({', '.join(missing)})")
    best: dict[int, tuple[int, dict]] = {}
    for row in reader:
        pid = number(row["espn_id"])
        if pid not in ids:
            continue
        last = number(row["last_season"]) or 0
        if pid not in best or last > best[pid][0]:
            birth = (row["birth_date"] or "").strip()   # kurze Zeile: fehlende Felder sind None
            try:
                date.fromisoformat(birth)
            except ValueError:
                birth = None
            draft = [number(row[c]) for c in ("draft_year", "draft_round", "draft_pick")]
            best[pid] = (last, {"geb": birth, "rookie": number(row["rookie_season"]),
                                "draft": draft if draft[0] is not None else None})
    if len(best) < MIN_SHARE * len(ids):
        raise ef.FetchError(f"nflverse players: nur {len(best)} von {len(ids)} Spielern gefunden")
    return {"quelle": QUELLE, "lizenz": LIZENZ, "spieler": {str(pid): best[pid][1] for pid in sorted(best)}}


def dumps(data: dict) -> bytes:
    """JSON mit einer Zeile je Spieler – der Git-Verlauf zeigt, wer dazukommt oder sich ändert."""
    head = ",\n".join(f"{json.dumps(k)}:{json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "spieler")
    rows = ",\n".join(f"{json.dumps(pid)}:{json.dumps(p, separators=(',', ':'))}" for pid, p in data["spieler"].items())
    return f'{{\n{head},\n"spieler":{{\n{rows}\n}}\n}}\n'.encode("utf-8")


def fetch(session: requests.Session, ids: set[int]) -> bytes:
    """Lädt players.csv.gz und gibt den Auszug für ids als Dateiinhalt zurück."""
    try:
        resp = session.get(URL, timeout=ef.TIMEOUT)
    except requests.RequestException as exc:
        raise ef.FetchError(f"nflverse players: Netzwerkfehler: {exc}") from exc
    if resp.status_code != 200:
        raise ef.FetchError(f"nflverse players: HTTP {resp.status_code}")
    try:
        text = gzip.decompress(resp.content).decode("utf-8")
    except (OSError, EOFError, zlib.error, UnicodeDecodeError) as exc:
        raise ef.FetchError(f"nflverse players: Antwort nicht lesbar ({exc})") from exc
    return dumps(extract(text, ids))


def update(session: requests.Session, season: int) -> int:
    """Wochenabruf: Auszug holen und nur bei Änderung schreiben; gibt die Zahl der Fehler zurück (Warnung im Lauf).

    Fängt seine Fehler selbst wie fantasypros (siehe dort: als Skript gestartet ist espn_fetch zweimal geladen) –
    und zwar jeden: Die Stammdaten sind ein Nebenteil und laufen vor dem Holen der fälligen Woche; eine Liste oder ein
    Pool-Auszug in unerwarteter Form darf den Wochenabruf nicht abbrechen (Befund Gegenprüfung 01.10.2026).
    Ohne Spielerpool (vor dem ersten Abruf der Saison) gibt es nichts zu suchen: kein Abruf, kein Fehler.
    """
    target = path(season)
    try:
        ids = pool_ids(season)
        if not ids:
            print(f"  {target.name:<34} noch kein Spielerpool")
            return 0
        content = fetch(session, ids)
    except Exception as exc:  # noqa: BLE001 – Nebenteil, siehe Docstring
        reason = exc if isinstance(exc, ef.FetchError) else f"{type(exc).__name__}: {exc}"
        print(f"  {target.name:<34} FEHLER – {reason}", file=sys.stderr)
        return 1
    if target.exists() and target.read_bytes() == content:
        print(f"  {target.name:<34} unverändert")
    else:
        ef.save_atomic(target, content)
        print(f"  {target.name:<34} {len(content):>10,} Bytes -> {ef.rel(target)}")
    return 0


# ---------------------------------------------------------------- Lesen (reine Funktionen)

def stammdaten(data: dict | None) -> dict[int, dict]:
    """Auszug als ESPN-ID → {"geb": date oder None, "rookie": Saison oder None, "draft": [Jahr, Runde, Pick] oder
    None}, Korrekturen KORREKTUR angewandt; leer ohne Auszug."""
    out = {}
    for pid, p in ((data or {}).get("spieler") or {}).items():
        birth = KORREKTUR.get(int(pid), p.get("geb"))
        out[int(pid)] = {"geb": date.fromisoformat(birth) if birth else None, "rookie": p.get("rookie"),
                         "draft": p.get("draft")}
    return out


def age(birth: date | None, day: date) -> Decimal | None:
    """Alter in Jahren am Stichtag day (Tage / 365,25, ungerundet); None ohne Geburtsdatum."""
    return Decimal((day - birth).days) / DAYS_PER_YEAR if birth else None


def nfl_year(rookie_season: int | None, season: int) -> int | None:
    """Wievielte NFL-Saison: Saison − Rookie-Saison + 1 (Rookie = 1); None ohne Angabe oder bei einer Rookie-Saison
    in der Zukunft."""
    return season - rookie_season + 1 if rookie_season is not None and rookie_season <= season else None
