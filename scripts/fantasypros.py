"""FantasyPros-Adressen je Spieler für den Verweis im Spielerprofil (Beschluss Stephan 30.09.2026).

FantasyPros führt Spieler unter /nfl/players/<adresse>.php. Die Adresse folgt nicht verlässlich aus dem Namen:
Namensvettern tragen die Position (josh-allen-qb, dj-moore-wr), Bindestriche verschmelzen (amonra-stbrown,
jacory-croskeymerritt), Namenszusätze stehen mal dabei, mal nicht (marvin-harrison-jr, deebo-samuel). Maßgeblich
sind deshalb die Positions-Sitemaps, die robots.txt für Maschinen ausweist:

- Abruf (Wochenabruf, espn_fetch.py --due bei den Saisondateien): sechs Anfragen mit 5 s Abstand (Crawl-delay),
  abgelegt wird nur die Liste der Spieler-Adressen je Position unter fantasypros/sitemap.json – keine Seiteninhalte.
- Zuordnung (compute.py → app_export.py): slug_for() sucht den ESPN-Namen in einigen Schreibweisen in der Sitemap
  seiner Position; es zählt nur ein eindeutiger Treffer. Sonst None – die App verlinkt dann die DuckDuckGo-Suche
  statt einer geratenen Adresse. D/ST verlinkt die App über ihre eigene Tabelle (FP_DST in v_spieler.js).
"""

import json
import re
import time
import unicodedata
from pathlib import Path

import requests

import espn_fetch as ef

SITEMAP_URL = "https://www.fantasypros.com/sitemaps/nfl-sitemap.php"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
# Plausibilität je Position (30.09.2026: QB 128, RB 210, WR 325, TE 199, K 50, DST 32) – weniger heißt kaputte Antwort
MIN_PLAYERS = {"QB": 32, "RB": 64, "WR": 96, "TE": 32, "K": 25, "DST": 32}
PAUSE = 5  # Sekunden zwischen zwei Abrufen (robots.txt: Crawl-delay 5)
PLAYER_LOC = re.compile(r"<loc>https://www\.fantasypros\.com/nfl/players/([a-z0-9-]+)\.php</loc>")
SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)
SAINT = re.compile(r"\bSt\.?\s+")  # „St. Brown“ führt FantasyPros zusammengezogen (amonra-stbrown)


def path(season: int) -> Path:
    return ef.RAW_DIR / str(season) / "fantasypros" / "sitemap.json"


# ---------------------------------------------------------------- Abruf (Wochenabruf)

def fetch_position(session: requests.Session, position: str) -> list[str]:
    """Spieler-Adressen einer Positions-Sitemap, sortiert und ohne Unterseiten (?week=…, /stats/, /news/ …)."""
    try:
        resp = session.get(SITEMAP_URL, params={"position": position}, timeout=ef.TIMEOUT)
    except requests.RequestException as exc:
        raise ef.FetchError(f"FantasyPros-Sitemap {position}: Netzwerkfehler: {exc}") from exc
    if resp.status_code != 200:
        raise ef.FetchError(f"FantasyPros-Sitemap {position}: HTTP {resp.status_code}")
    slugs = sorted(set(PLAYER_LOC.findall(resp.text)))
    if len(slugs) < MIN_PLAYERS[position]:
        raise ef.FetchError(f"FantasyPros-Sitemap {position}: nur {len(slugs)} Spieler (erwartet ≥ {MIN_PLAYERS[position]})")
    return slugs


def fetch(session: requests.Session) -> bytes:
    """Alle sechs Positions-Sitemaps als Auszug {"quelle", "positionen": {Position: [Adresse, …]}}; eine Adresse je
    Zeile, damit der Git-Verlauf zeigt, welche Spieler dazukommen oder wegfallen."""
    positions = {}
    for i, position in enumerate(POSITIONS):
        if i:
            time.sleep(PAUSE)
        positions[position] = fetch_position(session, position)
    data = {"quelle": f"{SITEMAP_URL}?position=<Position>", "positionen": positions}
    return (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# ---------------------------------------------------------------- Zuordnung (reine Funktionen)

def slug(name: str) -> str:
    """Adresse nach FantasyPros-Art: ohne Akzente, klein, Apostrophe und Punkte weg, alles andere wird Bindestrich."""
    plain = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"['.]", "", plain)).strip("-")


def variants(name: str) -> set[str]:
    """Schreibweisen eines Namens: wie geschrieben, Bindestriche verschmolzen (Amon-Ra → amonra), „St. X“ → stx."""
    joined = name.replace("-", "")
    return {slug(form) for form in (name, joined, SAINT.sub("St", joined))} - {""}


def index(data: dict | None) -> dict[str, set[str]]:
    """Sitemap-Auszug als Menge je Position (App-Kürzel QB, RB, WR, TE, K; D/ST fehlt bewusst); leer ohne Auszug."""
    positions = (data or {}).get("positionen") or {}
    return {pos: set(positions[pos]) for pos in ("QB", "RB", "WR", "TE", "K") if positions.get(pos)}


def slug_for(name: str | None, pos: str | None, known: dict[str, set[str]]) -> str | None:
    """FantasyPros-Adresse eines Spielers oder None, wenn sie nicht eindeutig ist.

    Gesucht wird in der Sitemap seiner Position, je Schreibweise auch mit angehängter Position (josh-allen-qb).
    Zuerst der volle Name mit Zusatz (kenneth-walker-iii schlägt kenneth-walker), dann ohne Zusatz (deebo-samuel für
    Deebo Samuel Sr.). Mehr als ein Treffer (isaiah-williams und isaiah-williams-wr) ist mehrdeutig: None.
    """
    slugs = known.get(pos or "")
    if not slugs or not name:
        return None
    suffix = f"-{pos.lower()}"
    for form in dict.fromkeys((name, SUFFIX.sub("", name))):
        hits = {c for v in variants(form) for c in (v, v + suffix) if c in slugs}
        if hits:
            return hits.pop() if len(hits) == 1 else None
    return None
