"""ESPN-Abruf (Baustein 1): Rohdaten der BWG Fantasy Liga je Woche als JSON ablegen.

Nutzt nur die öffentlichen Lese-Endpoints von ESPN und speichert jede Antwort
byte-genau unter data/raw/<saison>/wNN/<view>.json, das Transaktions-Archiv
unter data/raw/<saison>/transactions/ (Ausnahme: kona_league_communication ohne Chat-Themen).

Aufrufe:
    python scripts/espn_fetch.py --weeks 1 2 3            # abrufen, Vorhandenes bleibt stehen
    python scripts/espn_fetch.py --weeks 3 --force        # vorhandene Dateien überschreiben
    python scripts/espn_fetch.py --due                    # vergangene Wochen, die lokal fehlen oder nicht final sind
    python scripts/espn_fetch.py --transactions           # Transaktions-Archiv fortschreiben
    python scripts/espn_fetch.py --summary                # Matchups aller lokalen Wochen ausgeben
    python scripts/espn_fetch.py --summary --weeks 1 2    # nur bestimmte Wochen
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
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
TX_VIEW, COMM_VIEW = "mTransactions2", "kona_league_communication"
MAX_WEEK = 17  # W1–14 Regular Season, W15–17 Playoffs
WEEK1_START = {2026: date(2026, 9, 8)}  # Dienstag, an dem NFL-Woche 1 beginnt; jede Woche läuft Di–Mo
TIMEOUT = 30  # Sekunden je Anfrage

REPO_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_DIR / "data" / "raw"


class FetchError(Exception):
    """Abruf, Prüfung oder Lesen einer ESPN-Antwort ist fehlgeschlagen."""


def week_dir(season: int, week: int) -> Path:
    return RAW_DIR / str(season) / f"w{week:02d}"


def tx_dir(season: int) -> Path:
    return RAW_DIR / str(season) / "transactions"


def rel(path: Path) -> str:
    """Pfad relativ zum Repo, für lesbare Meldungen."""
    return path.relative_to(REPO_DIR).as_posix()


def to_points(value) -> Decimal:
    """ESPN-Punkte auf zwei Stellen, round half up.

    Über str(), damit Binär-Artefakte wie 479.58000000000004 nicht mitgerundet werden.
    """
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- Abruf

def get_json(session: requests.Session, season: int, params: dict) -> tuple[bytes, dict]:
    """Eine Liga-Anfrage mit Prüfung auf HTTP-Status, leere Antwort und JSON-Objekt; gibt Rohbytes und Daten zurück."""
    url = BASE_URL.format(season=season, league=LEAGUE_ID)
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT)
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
    if not isinstance(data, dict):
        raise FetchError("Antwort ist kein JSON-Objekt")
    return resp.content, data


def check_echo(data: dict, season: int, period: int) -> None:
    """Die Antwort muss Liga, Saison und angefragte Periode zurückmelden."""
    echo = (data.get("id"), data.get("seasonId"), data.get("scoringPeriodId"))
    if echo != (LEAGUE_ID, season, period):
        raise FetchError(f"Antwort passt nicht (Liga, Saison, Woche) = {echo}, erwartet {(LEAGUE_ID, season, period)}")


def fetch_view(session: requests.Session, season: int, week: int, view: str) -> bytes:
    """Holt einen View für eine Woche, prüft die Antwort und gibt die Rohbytes zurück."""
    content, data = get_json(session, season, {"view": view, "scoringPeriodId": week})
    key = VIEWS[view]
    if not data.get(key):
        raise FetchError(f"Antwort ohne Inhalt in '{key}'")
    check_echo(data, season, week)
    return content


def save_atomic(path: Path, content: bytes) -> None:
    """Schreibt erst eine .tmp-Datei und benennt sie dann um – kein halbes JSON bei Abbruch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def cmd_fetch(season: int, weeks: list[int], force: bool) -> int:
    """Holt je Woche erst alle Views und schreibt nur, wenn alle geklappt haben (alles oder nichts je Woche).

    Sonst könnte ein final geschriebenes mMatchupScore neben einem veralteten mRoster liegen, und --due
    hielte die Woche für erledigt. mMatchupScore (trägt die Final-Markierung) wird als Letztes geschrieben.
    """
    errors = 0
    with requests.Session() as session:
        for week in weeks:
            print(f"Woche {week}")
            fetched, week_errors = {}, 0
            for view in VIEWS:
                path = week_dir(season, week) / f"{view}.json"
                if path.exists() and not force:
                    print(f"  {view:<14} übersprungen – {rel(path)} existiert (--force zum Überschreiben)")
                    continue
                try:
                    fetched[view] = fetch_view(session, season, week, view)
                except FetchError as exc:
                    week_errors += 1
                    print(f"  {view:<14} FEHLER – {exc}", file=sys.stderr)
            if week_errors:
                errors += week_errors
                print(f"  Woche {week} nicht geschrieben – vorhandene Dateien bleiben unverändert.", file=sys.stderr)
                continue
            for view in sorted(fetched, key=lambda v: v == "mMatchupScore"):
                path = week_dir(season, week) / f"{view}.json"
                try:
                    save_atomic(path, fetched[view])
                except OSError as exc:
                    errors += 1
                    print(f"  {view:<14} FEHLER beim Schreiben – {exc}", file=sys.stderr)
                    break
                print(f"  {view:<14} {len(fetched[view]):>10,} Bytes -> {rel(path)}")
            try:
                matchups = load_week_matchups(season, week)
                if not matchups:  # z. B. Playoff-Woche, bevor ESPN das Bracket anlegt
                    print(f"  Hinweis: ESPN führt für Woche {week} noch keine Paarungen – "
                          f"der Wochenabruf (--due) holt sie nach.")
                elif not all(m["final"] for m in matchups):
                    print(f"  Hinweis: Woche {week} ist noch nicht abgeschlossen, Punkte vorläufig – "
                          f"der Wochenabruf (--due) holt sie nach.")
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

    Je Matchup: id, home, away (Teamname, away None bei Bye), home_id, away_id,
    home_points, away_points (Decimal, zwei Stellen) und final (False, solange ESPN kein Ergebnis führt).
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
                row[side], row[f"{side}_id"], row[f"{side}_points"] = None, None, None
                continue
            row[f"{side}_id"] = team["teamId"]
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


# ---------------------------------------------------------------- Fällige Wochen (Action dienstags)

def calendar_week(season: int, day: date) -> int:
    """NFL-Woche, in der ein Tag liegt (Woche n läuft Di–Mo); vor dem Saisonstart 0 oder negativ."""
    start = WEEK1_START.get(season)
    if start is None:
        raise FetchError(f"Wochenkalender für Saison {season} fehlt (WEEK1_START)")
    return (day - start).days // 7 + 1


def is_final(season: int, week: int) -> bool:
    """Liegt die Woche lokal mit allen Views vor und sind alle ihre Paarungen abgeschlossen?

    Bye-Einträge (Playoffs, ohne Gegner) zählen nicht: ob ESPN dort je einen Sieger setzt, ist offen –
    sonst würde eine Playoff-Woche mit Bye jeden Dienstag neu geholt.
    """
    folder = week_dir(season, week)
    if not all((folder / f"{view}.json").exists() for view in VIEWS):
        return False
    try:
        games = [m for m in load_week_matchups(season, week) if m["away_id"] is not None]
    except (FetchError, KeyError, ValueError):
        return False
    return bool(games) and all(m["final"] for m in games)


def check_season_open(season: int, today: date) -> None:
    """Ab dem 1. August des Folgejahres ist die Saison vorbei: dann lieber rot als still weiterlaufen."""
    if today >= date(season + 1, 8, 1):
        raise FetchError(f"Saison {season} ist vorbei – für {season + 1} DEFAULT_SEASON und WEEK1_START umstellen "
                         f"(CLAUDE.md, Abschnitt Saisonwechsel)")


def due_weeks(season: int, today: date) -> list[int]:
    """Vergangene Wochen (Montag vor today oder früher), die lokal fehlen oder noch nicht final sind.

    Finale Wochen werden nie neu geholt: ESPN liefert bei jedem Abruf andere Bytes (Ownership, Status),
    das gäbe Commits ohne Inhalt.
    """
    last_past = min(calendar_week(season, today) - 1, MAX_WEEK)
    return [week for week in range(1, last_past + 1) if not is_final(season, week)]


def cmd_due(season: int, today: date) -> int:
    try:
        check_season_open(season, today)
        weeks = due_weeks(season, today)
    except FetchError as exc:
        print(f"FEHLER – {exc}", file=sys.stderr)
        return 1
    if not weeks:
        print(f"Nichts fällig: alle Wochen vor dem {today:%d.%m.%Y} liegen final vor.")
        return 0
    print(f"Fällig: Woche {', '.join(map(str, weeks))}")
    return cmd_fetch(season, weeks, force=True)


# ---------------------------------------------------------------- Transaktions-Archiv (Action täglich)

def current_period(status_data: dict, season: int) -> int:
    """Laufende Scoring-Periode aus einer mStatus-Antwort: latestScoringPeriod, höchstens finalScoringPeriod.

    Bewusst nicht transactionScoringPeriod: eine Periode nach der laufenden liefert ESPN mit dem Inhalt der
    laufenden (geprüft 28.09.2026) – sie würde falsch archiviert. Einträge für die nächste Periode
    (FUTURE_ROSTER) stehen ohnehin in der laufenden.
    """
    if (status_data.get("id"), status_data.get("seasonId")) != (LEAGUE_ID, season):
        raise FetchError("mStatus passt nicht zu Liga und Saison")
    status = status_data.get("status") or {}
    latest_period = status.get("latestScoringPeriod", status_data.get("scoringPeriodId"))
    if not isinstance(latest_period, int):
        raise FetchError("mStatus ohne Scoring-Periode")
    return min(latest_period, status.get("finalScoringPeriod", MAX_WEEK))


def activity_only(data: dict) -> tuple[bytes, dict]:
    """kona_league_communication ohne Chat: nur Themen vom Typ ACTIVITY_* (Transaktionen, Einstellungen).

    Entscheidung Stephan 28.09.2026: Chat-Texte der Manager gehören nicht ins öffentliche Archiv.
    Diese Datei ist deshalb als einzige nicht byte-genau, sondern kompakt neu geschrieben.
    """
    topics = (data.get("communication") or {}).get("topics")
    if not isinstance(topics, list):
        raise FetchError("Antwort ohne Liste 'communication.topics'")
    kept = [t for t in topics if str(t.get("type", "")).startswith("ACTIVITY_")]
    filtered = dict(data, communication=dict(data["communication"], topics=kept))
    return json.dumps(filtered, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), filtered


def archive_state(old: list[dict] | None, new: list[dict]) -> str:
    """Vergleich Archiv ↔ neue Antwort über die Eintrags-IDs: neu, gleich, geändert oder geschrumpft.

    „geschrumpft“ heißt: archivierte Einträge fehlen in der neuen Antwort (ESPN hat gelöscht).
    Reihenfolge zählt nicht, Statuswechsel eines Eintrags zählen als „geändert“.
    """
    if old is None:
        return "neu"
    old_by_id, new_by_id = ({e["id"]: e for e in entries} for entries in (old, new))
    if not old_by_id.keys() <= new_by_id.keys():
        return "geschrumpft"
    return "gleich" if old_by_id == new_by_id else "geändert"


def latest(folder: Path, pattern: str) -> Path | None:
    """Jüngste Datei zu einem Muster; Zeitstempel im Namen sortieren chronologisch."""
    files = sorted(folder.glob(pattern))
    return files[-1] if files else None


def archive_transactions(season: int, fetch, stamp: str) -> tuple[int, list[str]]:
    """Schreibt das Transaktions-Archiv fort und gibt (Fehlerzahl, Warnungen) zurück.

    fetch(params) liefert (Rohbytes, Daten) einer Liga-Anfrage. mTransactions2 wird je Periode
    0 … laufend geholt (ohne scoringPeriodId kommt nur die laufende) und in mTransactions2_pNN.json
    ersetzt, sobald sich Einträge ändern. Fehlen archivierte Einträge, bleibt die Datei stehen und die
    neue Antwort kommt als mTransactions2_pNN_<stamp>.json daneben. kona_league_communication
    (höchstens 50 Themen, gleitend) wird ohne Chat (activity_only) bei jeder Änderung als eigene Datei
    mit Zeitstempel abgelegt.
    """
    folder = tx_dir(season)
    errors, warnings = 0, []
    _, status_data = fetch({"view": "mStatus"})
    current = current_period(status_data, season)
    print(f"Laufende Periode laut ESPN: {current}")

    for period in range(current + 1):
        path = folder / f"{TX_VIEW}_p{period:02d}.json"
        try:
            content, data = fetch({"view": TX_VIEW, "scoringPeriodId": period})
            check_echo(data, season, period)
            if not isinstance(data.get("transactions"), list):
                raise FetchError("Antwort ohne Liste 'transactions'")
            answer_latest = (data.get("status") or {}).get("latestScoringPeriod")
            if isinstance(answer_latest, int) and period > answer_latest:
                print(f"  p{period:02d}  übersprungen – liegt nach der laufenden Periode {answer_latest} der Antwort")
                continue
            new = data["transactions"]
            state = archive_state(load_json(path)["transactions"] if path.exists() else None, new)
            if state in ("neu", "geändert"):
                save_atomic(path, content)
            elif state == "geschrumpft":
                warnings.append(f"{TX_VIEW} p{period}: ESPN liefert archivierte Einträge nicht mehr – "
                                f"{rel(path)} bleibt stehen, neue Antwort daneben")
                side = latest(folder, f"{TX_VIEW}_p{period:02d}_*.json")
                if side is None or archive_state(load_json(side)["transactions"], new) != "gleich":
                    save_atomic(folder / f"{TX_VIEW}_p{period:02d}_{stamp}.json", content)
        except (FetchError, OSError, KeyError) as exc:
            errors += 1
            print(f"  p{period:02d}  FEHLER – {exc}", file=sys.stderr)
            continue
        print(f"  p{period:02d}  {len(new):>4} Einträge  {state}")

    try:
        _, data = fetch({"view": COMM_VIEW})
        content, data = activity_only(data)
        topics = data["communication"]["topics"]
        previous = latest(folder, f"{COMM_VIEW}_*.json")
        state = archive_state(load_json(previous)["communication"]["topics"] if previous else None, topics)
        if state != "gleich":
            save_atomic(folder / f"{COMM_VIEW}_{stamp}.json", content)
        print(f"  {COMM_VIEW}  {len(topics)} Themen  {'unverändert' if state == 'gleich' else 'neue Datei'}")
    except (FetchError, OSError, KeyError) as exc:
        errors += 1
        print(f"  {COMM_VIEW}  FEHLER – {exc}", file=sys.stderr)
    return errors, warnings


def cmd_transactions(season: int, now: datetime) -> int:
    stamp = now.strftime("%Y-%m-%dT%H%MZ")
    with requests.Session() as session:
        try:
            check_season_open(season, now.date())
            errors, warnings = archive_transactions(season, lambda params: get_json(session, season, params), stamp)
        except FetchError as exc:
            print(f"FEHLER – {exc}", file=sys.stderr)
            return 1
    for warning in warnings:
        # in der GitHub Action erscheint die Warnung als Hinweis am Lauf
        prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") == "true" else "Warnung: "
        print(prefix + warning)
    if errors:
        print(f"\n{errors} Fehler – betroffene Dateien wurden nicht geschrieben.", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- Aufruf

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESPN-Rohdaten der BWG Fantasy Liga je Woche abrufen (nur lesend).")
    parser.add_argument("--weeks", type=int, nargs="+", metavar="N", help=f"Wochen 1–{MAX_WEEK}, z. B. --weeks 1 2 3")
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON, help=f"Saison (Standard: {DEFAULT_SEASON})")
    parser.add_argument("--force", action="store_true", help="vorhandene Dateien überschreiben")
    parser.add_argument("--summary", action="store_true",
                        help="nicht abrufen, sondern Matchups aus den lokalen Dateien ausgeben")
    parser.add_argument("--due", action="store_true",
                        help="alle vergangenen Wochen abrufen, die lokal fehlen oder nicht final sind (überschreibt)")
    parser.add_argument("--transactions", action="store_true",
                        help="Transaktions-Archiv fortschreiben (mTransactions2 je Periode, kona_league_communication)")
    args = parser.parse_args(argv)
    if args.weeks:
        bad = [w for w in args.weeks if not 1 <= w <= MAX_WEEK]
        if bad:
            parser.error(f"ungültige Woche(n) {bad}, erlaubt 1–{MAX_WEEK}")
        args.weeks = sorted(set(args.weeks))
    modes = [flag for flag, on in (("--summary", args.summary), ("--due", args.due),
                                   ("--transactions", args.transactions)) if on]
    if len(modes) > 1:
        parser.error(f"{' und '.join(modes)} schließen sich aus")
    if (args.due or args.transactions) and (args.weeks or args.force):
        parser.error(f"{modes[0]} wählt selbst, was es holt – ohne --weeks und --force aufrufen")
    if args.summary and args.force:
        parser.error("--force passt nicht zu --summary (Summary ruft nichts ab)")
    if not modes and not args.weeks:
        parser.error("--weeks fehlt, z. B. --weeks 1 2 3")
    return args


def main(argv: list[str] | None = None) -> int:
    # nie an Sonderzeichen scheitern (auch bei Umleitung) und Fehler in richtiger Reihenfolge zeigen
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
    sys.stderr.reconfigure(errors="replace")
    args = parse_args(argv)
    if args.summary:
        return cmd_summary(args.season, args.weeks)
    if args.due:
        return cmd_due(args.season, datetime.now(timezone.utc).date())
    if args.transactions:
        return cmd_transactions(args.season, datetime.now(timezone.utc))
    return cmd_fetch(args.season, args.weeks, args.force)


if __name__ == "__main__":
    sys.exit(main())
