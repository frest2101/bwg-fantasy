"""ESPN-Abruf (Baustein 1): Rohdaten der BWG Fantasy Liga je Woche als JSON ablegen.

Nutzt nur die öffentlichen Lese-Endpoints von ESPN und speichert jede Antwort
byte-genau unter data/raw/<saison>/wNN/<view>.json.

Aufrufe:
    python scripts/espn_fetch.py --weeks 1 2 3            # abrufen, Vorhandenes bleibt stehen
    python scripts/espn_fetch.py --weeks 3 --force        # vorhandene Dateien überschreiben
    python scripts/espn_fetch.py --summary                # Matchups aller lokalen Wochen ausgeben
    python scripts/espn_fetch.py --summary --weeks 1 2    # nur bestimmte Wochen
"""

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import requests

LEAGUE_ID = 1166555857
DEFAULT_SEASON = 2026
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league}"
# View → Schlüssel, der in einer brauchbaren Antwort vorhanden und nicht leer sein muss
VIEWS = {
    "mSettings": "settings",
    "mTeam": "teams",
    "mMatchupScore": "schedule",
    "mRoster": "teams",
}
MAX_WEEK = 17  # W1–14 Regular Season, W15–17 Playoffs
TIMEOUT = 30  # Sekunden je Anfrage

REPO_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_DIR / "data" / "raw"


class FetchError(Exception):
    """Abruf, Prüfung oder Lesen einer ESPN-Antwort ist fehlgeschlagen."""


def week_dir(season: int, week: int) -> Path:
    return RAW_DIR / str(season) / f"w{week:02d}"


def rel(path: Path) -> str:
    """Pfad relativ zum Repo, für lesbare Meldungen."""
    return path.relative_to(REPO_DIR).as_posix()


def to_points(value) -> Decimal:
    """ESPN-Punkte auf zwei Stellen, round half up.

    Über str(), damit Binär-Artefakte wie 479.58000000000004 nicht mitgerundet werden.
    """
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- Abruf

def fetch_view(session: requests.Session, season: int, week: int, view: str) -> bytes:
    """Holt einen View für eine Woche, prüft die Antwort und gibt die Rohbytes zurück."""
    url = BASE_URL.format(season=season, league=LEAGUE_ID)
    try:
        resp = session.get(url, params={"view": view, "scoringPeriodId": week}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise FetchError(f"Netzwerkfehler: {exc}") from exc
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}: {resp.text[:200]!r}")
    if not resp.content.strip():
        raise FetchError("leere Antwort")
    try:
        data = json.loads(resp.content)
    except ValueError as exc:
        raise FetchError(f"kein gültiges JSON: {exc}") from exc
    key = VIEWS[view]
    if not isinstance(data, dict) or not data.get(key):
        raise FetchError(f"Antwort ohne Inhalt in '{key}'")
    echo = (data.get("id"), data.get("seasonId"), data.get("scoringPeriodId"))
    if echo != (LEAGUE_ID, season, week):
        raise FetchError(f"Antwort passt nicht (Liga, Saison, Woche) = {echo}, erwartet {(LEAGUE_ID, season, week)}")
    return resp.content


def save_atomic(path: Path, content: bytes) -> None:
    """Schreibt erst eine .tmp-Datei und benennt sie dann um – kein halbes JSON bei Abbruch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def cmd_fetch(season: int, weeks: list[int], force: bool) -> int:
    errors = 0
    with requests.Session() as session:
        for week in weeks:
            print(f"Woche {week}")
            for view in VIEWS:
                path = week_dir(season, week) / f"{view}.json"
                if path.exists() and not force:
                    print(f"  {view:<14} übersprungen – {rel(path)} existiert (--force zum Überschreiben)")
                    continue
                try:
                    content = fetch_view(session, season, week, view)
                    save_atomic(path, content)
                except (FetchError, OSError) as exc:
                    errors += 1
                    print(f"  {view:<14} FEHLER – {exc}", file=sys.stderr)
                    continue
                print(f"  {view:<14} {len(content):>10,} Bytes -> {rel(path)}")
            try:
                matchups = load_week_matchups(season, week)
                if not matchups:  # z. B. Playoff-Woche, bevor ESPN das Bracket anlegt
                    print(f"  Hinweis: ESPN führt für Woche {week} noch keine Paarungen – "
                          f"später mit --weeks {week} --force neu holen.")
                elif not all(m["final"] for m in matchups):
                    print(f"  Hinweis: Woche {week} ist noch nicht abgeschlossen, Punkte vorläufig – "
                          f"später mit --weeks {week} --force neu holen.")
            except (FetchError, KeyError, ValueError):
                pass  # Fehler wurden oben schon gemeldet
    if errors:
        print(f"\n{errors} Fehler – betroffene Dateien wurden nicht geschrieben.", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- Summary

def load_json(path: Path):
    try:
        return json.loads(path.read_bytes())
    except FileNotFoundError:
        raise FetchError(f"{rel(path)} fehlt – erst abrufen") from None
    except ValueError as exc:
        raise FetchError(f"{rel(path)} ist kein gültiges JSON: {exc}") from exc


def load_week_matchups(season: int, week: int) -> list[dict]:
    """Liest die Matchups einer Woche aus den lokalen Rohdaten.

    Je Matchup: id, home, away (Teamname, away None bei Bye), home_points,
    away_points (Decimal, zwei Stellen) und final (False, solange ESPN kein Ergebnis führt).
    """
    folder = week_dir(season, week)
    settings = load_json(folder / "mSettings.json")["settings"]
    names = {t["id"]: t["name"] for t in load_json(folder / "mTeam.json")["teams"]}
    schedule = load_json(folder / "mMatchupScore.json")["schedule"]

    # mMatchupScore enthält den ganzen Spielplan; matchupPeriods ordnet Perioden den NFL-Wochen zu, z. B. {"1": [1]}
    periods = settings["scheduleSettings"]["matchupPeriods"]
    period = next((int(mp) for mp, wks in periods.items() if week in wks), None)
    if period is None:
        raise FetchError(f"Woche {week} gehört laut mSettings zu keiner Matchup-Periode")

    matchups = []
    for m in schedule:
        if m["matchupPeriodId"] != period:
            continue
        final = m.get("winner") != "UNDECIDED"
        row = {"id": m["id"], "final": final}
        for side in ("home", "away"):
            team = m.get(side)
            if team is None:
                row[side], row[f"{side}_points"] = None, None
                continue
            row[side] = names.get(team["teamId"], f"Team {team['teamId']}")
            # totalPoints ist erst nach Abschluss gefüllt; bis dahin steht der Zwischenstand in totalPointsLive
            points = team["totalPoints"] if final else team.get("totalPointsLive", 0)
            row[f"{side}_points"] = to_points(points)
        matchups.append(row)
    return matchups


def local_weeks(season: int) -> list[int]:
    season_dir = RAW_DIR / str(season)
    return sorted(int(p.name[1:]) for p in season_dir.glob("w[0-9][0-9]") if p.is_dir())


def cmd_summary(season: int, weeks: list[int] | None) -> int:
    weeks = weeks or local_weeks(season)
    if not weeks:
        print(f"Keine lokalen Daten unter {rel(RAW_DIR / str(season))} – erst abrufen.", file=sys.stderr)
        return 1
    errors = 0
    for week in weeks:
        try:
            matchups = load_week_matchups(season, week)
        except (FetchError, KeyError, ValueError) as exc:
            errors += 1
            reason = f"fehlender Schlüssel {exc}" if isinstance(exc, KeyError) else exc
            print(f"\nWoche {week}: FEHLER – {reason}", file=sys.stderr)
            continue
        if not matchups:
            print(f"\nWoche {week}  (vorläufig – ESPN führt noch keine Paarungen)")
            continue
        status = "" if all(m["final"] for m in matchups) else "  (vorläufig – Woche läuft noch)"
        print(f"\nWoche {week}{status}   Heim : Gast")
        width = max(len(m["home"]) for m in matchups)
        for m in matchups:
            if m["away"] is None:
                print(f"  {m['home']:>{width}}  {m['home_points']:>7}   Bye")
            else:
                print(f"  {m['home']:>{width}}  {m['home_points']:>7} : {m['away_points']:<7}  {m['away']}")
    return 1 if errors else 0


# ---------------------------------------------------------------- Aufruf

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESPN-Rohdaten der BWG Fantasy Liga je Woche abrufen (nur lesend).")
    parser.add_argument("--weeks", type=int, nargs="+", metavar="N", help=f"Wochen 1–{MAX_WEEK}, z. B. --weeks 1 2 3")
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON, help=f"Saison (Standard: {DEFAULT_SEASON})")
    parser.add_argument("--force", action="store_true", help="vorhandene Dateien überschreiben")
    parser.add_argument("--summary", action="store_true",
                        help="nicht abrufen, sondern Matchups aus den lokalen Dateien ausgeben")
    args = parser.parse_args(argv)
    if args.weeks:
        bad = [w for w in args.weeks if not 1 <= w <= MAX_WEEK]
        if bad:
            parser.error(f"ungültige Woche(n) {bad}, erlaubt 1–{MAX_WEEK}")
        args.weeks = sorted(set(args.weeks))
    if args.summary and args.force:
        parser.error("--force passt nicht zu --summary (Summary ruft nichts ab)")
    if not args.summary and not args.weeks:
        parser.error("--weeks fehlt, z. B. --weeks 1 2 3")
    return args


def main(argv: list[str] | None = None) -> int:
    # nie an Sonderzeichen scheitern (auch bei Umleitung) und Fehler in richtiger Reihenfolge zeigen
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
    sys.stderr.reconfigure(errors="replace")
    args = parse_args(argv)
    if args.summary:
        return cmd_summary(args.season, args.weeks)
    return cmd_fetch(args.season, args.weeks, args.force)


if __name__ == "__main__":
    sys.exit(main())
