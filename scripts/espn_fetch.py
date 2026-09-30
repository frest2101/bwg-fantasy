"""ESPN-Abruf (Baustein 1): Rohdaten der BWG Fantasy Liga je Woche als JSON ablegen.

Nutzt nur die öffentlichen Lese-Endpoints von ESPN und speichert jede Antwort
byte-genau unter data/raw/<saison>/wNN/<view>.json, das Transaktions-Archiv
unter data/raw/<saison>/transactions/. Ausnahmen (Auszüge statt Rohantwort):
kona_league_communication ohne Chat-Themen, wNN/ros.json (Projektionen der Restwochen), pool/latest.json (Pool-Auszug).

Ablage je Saison (--due):
    wNN/  mSettings, mTeam, mMatchupScore, mRoster        Kern: bestimmen, ob die Woche final ist
    wNN/  kona_player_info, ros.json, mStandings           Stand beim Abschluss der Woche (Spielerpool, ROS, ESPN-Simulation)
    nfl/proTeamSchedules_wl.json                           NFL-Spielplan mit Byes, wird aktualisiert
    draft/mDraftDetail.json                                Draft und Keeper, einmalig
    basis/kona_dst_<vorjahr>.json, proTeamSchedules_wl_<vorjahr>.json   D/ST-Grundlage des Vorjahrs, einmalig
    fantasypros/sitemap.json                               FantasyPros-Adressen je Position (scripts/fantasypros.py), wird aktualisiert
Tageslauf (--transactions --pool --wetter, Action stündlich vormittags und abends):
    transactions/                                          Transaktions-Archiv (mTransactions2 je Periode, Aktivitäten)
    pool/latest.json                                       Pool-Auszug: Status, Besitz, Verletzung, Waiver-Frist, Projektion;
                                                           dazu die Waiver-Reihenfolge der Teams (mTeam.waiverRank)
    wetter/prognose/wNN_<UTC>.json, wetter/ist_<saison>.json   Wetter je Spiel (scripts/wetter.py, Open-Meteo)
    news/<UTC>.json                                        News je Spieler (scripts/news.py, --news, vorbereitet, aus)

Aufrufe:
    python scripts/espn_fetch.py --weeks 1 2 3            # Kern-Views abrufen, Vorhandenes bleibt stehen
    python scripts/espn_fetch.py --weeks 3 --force        # vorhandene Dateien überschreiben
    python scripts/espn_fetch.py --due                    # alles Fällige (Action dienstags), siehe cmd_due
    python scripts/espn_fetch.py --transactions --pool --wetter   # Tageslauf (Action stündlich), siehe cmd_daily
    python scripts/espn_fetch.py --transactions           # nur das Transaktions-Archiv fortschreiben
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
SEASON_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
BASE_URL = SEASON_URL + "/segments/0/leagues/{league}"
# Kern-Views je Woche → Schlüssel, der in einer brauchbaren Antwort vorhanden und nicht leer sein muss.
# Nur sie entscheiden, ob eine Woche final ist; weitere Dateien je Woche kommen dazu, ohne das zu ändern.
VIEWS = {
    "mSettings": "settings",
    "mTeam": "teams",
    "mMatchupScore": "schedule",
    "mRoster": "teams",
}
KEYS = dict(VIEWS, mStandings="teams")
TX_VIEW, COMM_VIEW = "mTransactions2", "kona_league_communication"
KONA_VIEW = "kona_player_info"
TEAM_VIEW = "mTeam"        # Tageslauf: nur waiverRank je Team (Waiver-Reihenfolge)
KONA_FILE, ROS_FILE, STANDINGS_FILE = f"{KONA_VIEW}.json", "ros.json", "mStandings.json"
POOL_FILE = "latest.json"   # Pool-Auszug des Tageslaufs unter pool/ (je Lauf überschrieben, Historie in Git)
MIN_POOL = 300              # ein vollständiger Spielerpool hat rund 1050 aktive Spieler
DST_POSITION, NFL_TEAMS, NFL_GAMES = 16, 32, 17
STAT_ACTUAL, STAT_PROJECTION, SPLIT_WEEK, STAT_PLAYED = 0, 1, 1, "210"  # statSourceId, statSplitTypeId, „hat gespielt“
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


def pool_dir(season: int) -> Path:
    return RAW_DIR / str(season) / "pool"


def season_files(season: int) -> dict[str, Path]:
    """Dateien je Saison, die nicht an einer Woche hängen."""
    base = RAW_DIR / str(season)
    return {"schedule": base / "nfl" / "proTeamSchedules_wl.json",
            "draft": base / "draft" / "mDraftDetail.json",
            "prior_schedule": base / "basis" / f"proTeamSchedules_wl_{season - 1}.json",
            "prior_dst": base / "basis" / f"kona_dst_{season - 1}.json",
            "prior_positions": base / "basis" / f"positionen_{season - 1}.json"}


def league_url(season: int) -> str:
    return BASE_URL.format(season=season, league=LEAGUE_ID)


def rel(path: Path) -> str:
    """Pfad relativ zum Repo, für lesbare Meldungen."""
    return path.relative_to(REPO_DIR).as_posix()


def to_points(value) -> Decimal:
    """ESPN-Punkte auf zwei Stellen, round half up.

    Über str(), damit Binär-Artefakte wie 479.58000000000004 nicht mitgerundet werden.
    """
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- Abruf

def get_json(session: requests.Session, url: str, params: dict, headers: dict | None = None) -> tuple[bytes, dict]:
    """Eine GET-Anfrage mit Prüfung auf HTTP-Status, leere Antwort und JSON-Objekt; gibt Rohbytes und Daten zurück."""
    try:
        resp = session.get(url, params=params, headers=headers, timeout=TIMEOUT)
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
    """Holt einen Liga-View für eine Woche, prüft die Antwort und gibt die Rohbytes zurück."""
    content, data = get_json(session, league_url(season), {"view": view, "scoringPeriodId": week})
    key = KEYS[view]
    if not data.get(key):
        raise FetchError(f"Antwort ohne Inhalt in '{key}'")
    check_echo(data, season, week)
    return content


def kona_filter(stat_weeks: list[int], rank_week: int | None = None) -> dict:
    """X-Fantasy-Filter für den ganzen Spielerpool mit Wochenwerten (Ist und Projektion) der genannten Wochen.

    Ohne sortPercOwned antwortet ESPN auf limit mit HTTP 400 (FILTER_LIMIT_MISSING_SORT). Wochen-Ränge gibt es nur als PPR.
    """
    players = {"limit": 2000, "filterActive": {"value": True},
               "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
               "filterStatsForCurrentSeasonScoringPeriodId": {"value": stat_weeks}}
    if rank_week is not None:
        players["filterRanksForScoringPeriodIds"] = {"value": [rank_week]}
        players["filterRanksForRankTypes"] = {"value": ["PPR"]}
    return {"X-Fantasy-Filter": json.dumps({"players": players})}


def check_pool(data: dict) -> list[dict]:
    """Ein brauchbarer Spielerpool: genug Spieler und alle 32 D/ST."""
    players = data.get("players")
    if not isinstance(players, list) or len(players) < MIN_POOL:
        raise FetchError(f"Spielerpool unvollständig ({len(players) if isinstance(players, list) else 0} Spieler)")
    dst = sum(1 for p in players if p.get("player", {}).get("defaultPositionId") == DST_POSITION)
    if dst != NFL_TEAMS:
        raise FetchError(f"Spielerpool mit {dst} statt {NFL_TEAMS} D/ST")
    return players


def fetch_kona_week(session: requests.Session, season: int, week: int) -> bytes:
    """Spielerpool mit Ist und Projektion der Woche und den Experten-Rängen dieser Woche (byte-genau).

    Besitz, Verletzung und Pool-Status sind der Stand beim Abruf – ESPN führt davon keine Historie.
    """
    content, data = get_json(session, league_url(season), {"view": KONA_VIEW}, kona_filter([week], rank_week=week))
    players = check_pool(data)
    if not any(s.get("seasonId") == season and s.get("scoringPeriodId") == week
               for p in players for s in p["player"].get("stats", [])):
        raise FetchError(f"Spielerpool ohne Werte für Woche {week}")
    return content


def ros_extract(data: dict, season: int, after_week: int) -> bytes:
    """Auszug der Projektionen je Restwoche (after_week+1 … 17) aus einer kona-Antwort, sortiert nach Spieler-ID.

    Ausnahme vom Byte-Prinzip (Entscheidung Stephan 28.09.2026): die Rohantwort ist 6,2 MB groß, zu 97 % Roh-Statistik;
    gebraucht wird nur appliedTotal je Woche. ESPNs Saisonwert (statSplitTypeId 0) ist schon ROS inklusive NFL-W18
    und wird deshalb nicht verwendet.
    """
    weeks = range(after_week + 1, MAX_WEEK + 1)
    players = {}
    for entry in check_pool(data):
        proj = {s["scoringPeriodId"]: s.get("appliedTotal", 0) for s in entry["player"].get("stats", [])
                if (s.get("seasonId"), s.get("statSourceId"), s.get("statSplitTypeId")) == (season, STAT_PROJECTION, SPLIT_WEEK)
                and s.get("scoringPeriodId") in weeks}
        if proj:
            players[entry["id"]] = {str(w): proj[w] for w in sorted(proj)}
    if len(players) < MIN_POOL:
        raise FetchError(f"ROS-Auszug mit nur {len(players)} Spielern")
    out = {"season": season, "after_week": after_week, "weeks": list(weeks),
           "quelle": "kona_player_info, statSourceId 1, statSplitTypeId 1: appliedTotal je Woche",
           "players": {str(pid): players[pid] for pid in sorted(players)}}
    return (json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def fetch_ros(session: requests.Session, season: int, week: int) -> bytes | None:
    """ROS-Stand nach Woche week; nach der letzten Woche gibt es keinen."""
    if week >= MAX_WEEK:
        return None
    rest = list(range(week + 1, MAX_WEEK + 1))
    _, data = get_json(session, league_url(season), {"view": KONA_VIEW}, kona_filter(rest))
    return ros_extract(data, season, week)


def fetch_schedule(session: requests.Session, season: int) -> bytes:
    """NFL-Spielplan einer Saison: je Team Bye-Woche und Spiele je Woche (Gegner, Anstoß)."""
    content, data = get_json(session, SEASON_URL.format(season=season), {"view": "proTeamSchedules_wl"})
    teams = (data.get("settings") or {}).get("proTeams")
    if not isinstance(teams, list) or sum(1 for t in teams if t.get("id")) != NFL_TEAMS:
        raise FetchError(f"NFL-Spielplan {season} ohne {NFL_TEAMS} Teams")
    return content


def fetch_draft(session: requests.Session, season: int) -> bytes | None:
    """Draft und Keeper der Saison; vor dem Draft gibt es nichts zu holen."""
    content, data = get_json(session, league_url(season), {"view": "mDraftDetail"})
    if (data.get("id"), data.get("seasonId")) != (LEAGUE_ID, season):
        raise FetchError("mDraftDetail passt nicht zu Liga und Saison")
    draft = data.get("draftDetail") or {}
    if not draft.get("drafted"):
        return None
    if not draft.get("picks"):
        raise FetchError("Draft ohne Picks")
    return content


def fetch_prior_dst(session: requests.Session, season: int, today: date) -> bytes:
    """Alle 32 D/ST mit ihren Wochenwerten des Vorjahrs (Liga-Scoring) – Grundlage „Off. zugelassen Vorjahr“.

    filterStatsForTopScoringPeriodIds liefert die letzten N Spiele je Spieler über die Saisongrenze hinweg;
    N deckt alle 17 Vorjahresspiele plus die bisherigen Spiele dieser Saison ab.
    """
    games = NFL_GAMES + max(calendar_week(season, today), 0) + 2
    players = {"limit": 50, "filterSlotIds": {"value": [DST_POSITION]},
               "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
               "filterStatsForTopScoringPeriodIds": {"value": games, "additionalValue": [f"00{season - 1}"]}}
    content, data = get_json(session, league_url(season), {"view": KONA_VIEW},
                             {"X-Fantasy-Filter": json.dumps({"players": players})})
    entries = data.get("players")
    if not isinstance(entries, list) or len(entries) != NFL_TEAMS:
        raise FetchError(f"D/ST-Vorjahr: {len(entries) if isinstance(entries, list) else 0} statt {NFL_TEAMS} D/ST")
    for entry in entries:
        played = sum(1 for s in entry["player"].get("stats", [])
                     if (s.get("seasonId"), s.get("statSourceId"), s.get("statSplitTypeId")) == (season - 1, STAT_ACTUAL, SPLIT_WEEK)
                     and (s.get("stats") or {}).get(STAT_PLAYED) == 1)
        if played != NFL_GAMES:
            raise FetchError(f"D/ST-Vorjahr: {entry['player'].get('fullName')} mit {played} statt {NFL_GAMES} Spielen")
    return content


def save_atomic(path: Path, content: bytes) -> None:
    """Schreibt erst eine .tmp-Datei und benennt sie dann um – kein halbes JSON bei Abbruch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def fetch_week(session: requests.Session, season: int, week: int, force: bool, snapshot: bool = False) -> int:
    """Holt eine Woche und gibt die Zahl der Fehler zurück – alles oder nichts je Woche.

    Erst werden alle Dateien geholt, geschrieben wird nur, wenn alle geklappt haben. Sonst könnte ein final
    geschriebenes mMatchupScore neben einem veralteten mRoster liegen, und --due hielte die Woche für erledigt.
    mMatchupScore (trägt die Final-Markierung) wird als Letztes geschrieben. snapshot: dazu Spielerpool,
    ROS-Auszug und ESPN-Standings der Woche – das, was nur „jetzt“ zu haben ist.
    """
    print(f"Woche {week}")
    jobs = {f"{view}.json": (lambda v=view: fetch_view(session, season, week, v)) for view in VIEWS}
    if snapshot:
        jobs[STANDINGS_FILE] = lambda: fetch_view(session, season, week, "mStandings")
        jobs[KONA_FILE] = lambda: fetch_kona_week(session, season, week)
        jobs[ROS_FILE] = lambda: fetch_ros(session, season, week)
    fetched, errors = {}, 0
    for name, job in jobs.items():
        path = week_dir(season, week) / name
        if path.exists() and not force:
            print(f"  {name:<22} übersprungen – {rel(path)} existiert (--force zum Überschreiben)")
            continue
        try:
            content = job()
        except FetchError as exc:
            errors += 1
            print(f"  {name:<22} FEHLER – {exc}", file=sys.stderr)
            continue
        if content is not None:
            fetched[name] = content
    if errors:
        print(f"  Woche {week} nicht geschrieben – vorhandene Dateien bleiben unverändert.", file=sys.stderr)
        return errors
    for name in sorted(fetched, key=lambda n: n == "mMatchupScore.json"):
        path = week_dir(season, week) / name
        try:
            save_atomic(path, fetched[name])
        except OSError as exc:
            print(f"  {name:<22} FEHLER beim Schreiben – {exc}", file=sys.stderr)
            return errors + 1
        print(f"  {name:<22} {len(fetched[name]):>10,} Bytes -> {rel(path)}")
    try:
        matchups = load_week_matchups(season, week)
        if not matchups:  # z. B. Playoff-Woche, bevor ESPN das Bracket anlegt
            print(f"  Hinweis: ESPN führt für Woche {week} noch keine Paarungen – der Wochenabruf (--due) holt sie nach.")
        elif not all(m["final"] for m in matchups):
            print(f"  Hinweis: Woche {week} ist noch nicht abgeschlossen, Punkte vorläufig – "
                  f"der Wochenabruf (--due) holt sie nach.")
    except (FetchError, KeyError, ValueError):
        pass  # Fehler wurden oben schon gemeldet
    return errors


def cmd_fetch(season: int, weeks: list[int], force: bool) -> int:
    """Kern-Views der genannten Wochen (Handabruf für Test oder Notfall – Wochen holt der Wochenabruf).

    --due ergänzt für finale Wochen nur den Spielerpool; ROS-Auszug und mStandings entstehen nur, wenn --due die
    jüngste Woche selbst holt.
    """
    with requests.Session() as session:
        errors = sum(fetch_week(session, season, week, force) for week in weeks)
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
    return [week for week in range(1, last_past_week(season, today) + 1) if not is_final(season, week)]


def last_past_week(season: int, today: date) -> int:
    return min(calendar_week(season, today) - 1, MAX_WEEK)


def refresh_season_files(session: requests.Session, season: int, today: date) -> int:
    """Saisondateien: NFL-Spielplan und FantasyPros-Sitemap bei jedem Lauf (Verlegungen, neue Spieler), Draft und
    D/ST-Vorjahr einmalig. Gibt Fehler zurück."""
    import fantasypros  # erst hier: das Modul importiert espn_fetch
    files = season_files(season)
    jobs = [(files["schedule"], True, lambda: fetch_schedule(session, season)),
            (files["draft"], False, lambda: fetch_draft(session, season)),
            (files["prior_schedule"], False, lambda: fetch_schedule(session, season - 1)),
            (files["prior_dst"], False, lambda: fetch_prior_dst(session, season, today))]
    errors = 0
    for path, refresh, job in jobs:
        if path.exists() and not refresh:
            continue
        try:
            content = job()
        except FetchError as exc:
            errors += 1
            print(f"  {path.name:<34} FEHLER – {exc}", file=sys.stderr)
            continue
        if content is None:
            print(f"  {path.name:<34} noch nicht verfügbar")
        elif path.exists() and path.read_bytes() == content:
            print(f"  {path.name:<34} unverändert")
        else:
            save_atomic(path, content)
            print(f"  {path.name:<34} {len(content):>10,} Bytes -> {rel(path)}")
    return errors + fantasypros.update(session, season)  # fängt seine Fehler selbst (siehe dort)


def backfill_kona(session: requests.Session, season: int, week: int) -> int:
    """Spielerpool einer finalen Woche nachholen, ohne die übrigen Dateien der Woche anzufassen.

    Punkte und Projektionen der Woche liefert ESPN rückwirkend; Besitz, Verletzung und Pool-Status sind der Stand
    beim Nachholen, nicht der von damals.
    """
    path = week_dir(season, week) / KONA_FILE
    try:
        content = fetch_kona_week(session, season, week)
    except FetchError as exc:
        print(f"  W{week:02d} {KONA_FILE:<22} FEHLER – {exc}", file=sys.stderr)
        return 1
    save_atomic(path, content)
    print(f"  W{week:02d} {KONA_FILE:<22} {len(content):>10,} Bytes -> {rel(path)} (nachgeholt)")
    return 0


def warn(message: str) -> None:
    """Warnung, die den Lauf nicht rot macht; in der GitHub Action erscheint sie als Hinweis am Lauf."""
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") == "true" else "Warnung: "
    print(prefix + message)


def cmd_due(season: int, today: date) -> int:
    """Alles Fällige: Saisondateien, nicht finale Wochen, fehlende Spielerpools finaler Wochen.

    Finale Wochen werden nie überschrieben – auch nicht, wenn später eine Datei je Woche dazukommt.
    Stand-Dateien (ROS-Auszug, mStandings) gibt es nur für die jüngste vergangene Woche: ESPN liefert sie nur
    „jetzt“, bei nachgeholten älteren Wochen stünde sonst ein späterer Stand unter der alten Woche.
    Nur Fehler bei fälligen Wochen machen den Lauf rot; Saisondateien und Nachholen erzeugen Warnungen,
    damit ein kurzer ESPN-Fehler dort nicht den Commit einer korrekt geholten Woche verhindert.
    """
    try:
        check_season_open(season, today)
        weeks = due_weeks(season, today)
        last_past = last_past_week(season, today)
        backfill = [w for w in range(1, last_past + 1)
                    if w not in weeks and not (week_dir(season, w) / KONA_FILE).exists()]
    except FetchError as exc:
        print(f"FEHLER – {exc}", file=sys.stderr)
        return 1
    errors = side_errors = 0
    with requests.Session() as session:
        print("Saisondateien")
        side_errors += refresh_season_files(session, season, today)
        if weeks:
            print(f"Fällig: Woche {', '.join(map(str, weeks))}")
        for week in weeks:
            if week == last_past:
                errors += fetch_week(session, season, week, force=True, snapshot=True)
            else:  # nachgeholte ältere Woche: Kern plus Spielerpool, aber keine Stand-Dateien von heute
                week_errors = fetch_week(session, season, week, force=True)
                errors += week_errors
                if not week_errors:
                    side_errors += backfill_kona(session, season, week)
        if backfill:
            print(f"Spielerpool nachholen: Woche {', '.join(map(str, backfill))}")
        for week in backfill:
            side_errors += backfill_kona(session, season, week)
    if not weeks and not backfill:
        print(f"Keine Woche fällig: alle Wochen vor dem {today:%d.%m.%Y} liegen final und vollständig vor.")
    if side_errors:
        warn(f"{side_errors} Fehler bei Saisondateien oder beim Nachholen – der nächste Lauf versucht es erneut")
    if errors:
        print(f"\n{errors} Fehler – betroffene Wochen wurden nicht geschrieben.", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- Transaktions-Archiv (Teil des Tageslaufs)

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
    Diese Datei ist deshalb – wie wNN/ros.json – nicht byte-genau, sondern kompakt neu geschrieben.
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
            answer_latest = (data.get("status") or {}).get("latestScoringPeriod")
            if isinstance(answer_latest, int) and period > answer_latest:
                print(f"  p{period:02d}  übersprungen – liegt nach der laufenden Periode {answer_latest} der Antwort")
                continue
            if "transactions" not in data:
                # Periode ohne Einträge (z. B. direkt nach dem Periodenwechsel): ESPN lässt die Liste ganz weg.
                # Keine Datei anlegen; eine schon archivierte Periode mit Einträgen bleibt stehen (wie beim Schrumpfen).
                if path.exists() and load_json(path)["transactions"]:
                    warnings.append(f"{TX_VIEW} p{period}: ESPN liefert für die archivierte Periode keine Liste – "
                                    f"{rel(path)} bleibt stehen")
                print(f"  p{period:02d}     0 Einträge  keine Liste (noch keine Transaktionen)")
                continue
            if not isinstance(data["transactions"], list):
                raise FetchError("Antwort mit 'transactions', aber ohne Liste")
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
    """Nur das Transaktions-Archiv (bisheriger Aufruf); der Tageslauf nutzt cmd_daily."""
    return cmd_daily(season, now, transactions=True)


# ---------------------------------------------------------------- Pool-Auszug (Tageslauf, Session 6)

POOL_KEYS = ("id", "status", "onTeamId", "injuryStatus", "percentOwned", "percentChange", "percentStarted",
             "waiverProcessDate", "lastNewsDate", "proj_naechste_woche")


def pool_week(season: int, today: date) -> int:
    """Woche, deren Spiele als Nächstes anstehen: die Kalenderwoche (Di–Mo); vor der Saison W1, nach W17 W17."""
    return min(max(calendar_week(season, today), 1), MAX_WEEK)


def pool_extract(data: dict, season: int, week: int, stamp: str) -> dict:
    """Pool-Auszug aus einer kona-Antwort: je Spieler Status, Fantasy-Team, Verletzung, Besitz ESPN-weit (Anteil,
    Änderung, gestartet), Waiver-Frist, letzte ESPN-News und die Wochenprojektion der Woche week.

    Rund 80 KB statt 2,8 MB; Besitz, Verletzung und Status sind der Stand des Abrufs (ESPN führt keine Historie).
    Kein members-Feld, keine Texte – die Datei bleibt öffentlich unbedenklich.
    """
    rows = []
    for entry in check_pool(data):
        player = entry["player"]
        own = player.get("ownership") or {}
        proj = next((s.get("appliedTotal") for s in player.get("stats", [])
                     if (s.get("seasonId"), s.get("scoringPeriodId"), s.get("statSourceId"), s.get("statSplitTypeId"))
                     == (season, week, STAT_PROJECTION, SPLIT_WEEK)), None)
        rows.append({"id": entry["id"], "status": entry.get("status"), "onTeamId": entry.get("onTeamId", 0),
                     "injuryStatus": player.get("injuryStatus"), "percentOwned": own.get("percentOwned"),
                     "percentChange": own.get("percentChange"), "percentStarted": own.get("percentStarted"),
                     "waiverProcessDate": entry.get("waiverProcessDate"), "lastNewsDate": player.get("lastNewsDate"),
                     "proj_naechste_woche": proj})
    rows.sort(key=lambda r: r["id"])
    return {"season": season, "woche": week, "stand": stamp,
            "quelle": f"{KONA_VIEW} mit filterStatsForCurrentSeasonScoringPeriodId = [{week}], Auszug je Spieler; "
                      f"waiver_reihenfolge = waiverRank je Team aus {TEAM_VIEW} (1 = zuerst), "
                      f"waiver_reihenfolge_stand = Abrufzeit ihrer letzten Änderung; "
                      f"stand = Abrufzeit (UTC) des letzten Laufs, der etwas geändert hat",
            "players": rows}


def pool_dumps(extract: dict) -> bytes:
    """JSON mit einer Zeile je Spieler – Diffs zwischen zwei Läufen bleiben lesbar."""
    head = ",\n".join(f"{json.dumps(k)}:{json.dumps(v, ensure_ascii=False)}" for k, v in extract.items() if k != "players")
    rows = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in extract["players"])
    return f'{{\n{head},\n"players":[\n{rows}\n]\n}}\n'.encode("utf-8")


def same_pool(old: dict | None, new: dict) -> bool:
    """Gleicher Inhalt bis auf den Stand (der ändert sich mit jedem Abruf)."""
    return old is not None and {k: v for k, v in old.items() if k != "stand"} == {k: v for k, v in new.items() if k != "stand"}


def fetch_pool(session: requests.Session, season: int, week: int) -> dict:
    """Ganzer Spielerpool mit den Wochenwerten (Ist und Projektion) der Woche week, ungeprüft (pool_extract prüft)."""
    _, data = get_json(session, league_url(season), {"view": KONA_VIEW}, kona_filter([week]))
    return data


def fetch_waiver_order(session: requests.Session, season: int) -> dict[str, int]:
    """Waiver-Reihenfolge laut mTeam (ein Aufruf): team_id (als Text, wie im JSON) → waiverRank, 1 = zuerst.

    Nur die Ränge – members, owners und Namen bleiben draußen, der Pool-Auszug ist öffentlich. Die Ränge müssen
    eine Reihenfolge 1 … n bilden, sonst gilt die Antwort als unbrauchbar (FetchError).
    """
    _, data = get_json(session, league_url(season), {"view": TEAM_VIEW})
    if (data.get("id"), data.get("seasonId")) != (LEAGUE_ID, season):
        raise FetchError(f"{TEAM_VIEW} passt nicht zu Liga und Saison: {(data.get('id'), data.get('seasonId'))}")
    teams = data.get("teams")
    if not isinstance(teams, list) or not teams:
        raise FetchError(f"{TEAM_VIEW} ohne Teams")
    order = {}
    for t in teams:
        if not isinstance(t.get("id"), int) or not isinstance(t.get("waiverRank"), int):
            raise FetchError(f"{TEAM_VIEW} ohne waiverRank (Team {t.get('id')})")
        order[str(t["id"])] = t["waiverRank"]
    if sorted(order.values()) != list(range(1, len(order) + 1)):
        raise FetchError(f"waiverRank ist keine Reihenfolge 1 … {len(order)}: {sorted(order.values())}")
    return dict(sorted(order.items(), key=lambda kv: int(kv[0])))


def update_pool(session: requests.Session, season: int, now: datetime, stamp: str) -> tuple[int, dict | None]:
    """Holt den Pool-Auszug samt Waiver-Reihenfolge (mTeam) und schreibt pool/latest.json, wenn sich außer dem
    Stand etwas geändert hat.

    Rückgabe (Fehler, aktueller Auszug oder None bei Fehler); bei unverändertem Inhalt ist es der gespeicherte Auszug
    mit seinem alten Stand. Den aktuellen Auszug braucht --news. Scheitert nur der mTeam-Aufruf, bleibt die
    Reihenfolge des letzten Laufs stehen (Warnung, kein Fehler): der Pool-Auszug ist das Hauptprodukt.
    waiver_reihenfolge_stand ist die Abrufzeit des Laufs, der die Reihenfolge zuletzt geändert hat – so sieht die App,
    wie alt sie wirklich ist, auch wenn der Pool selbst in einem Lauf mit mTeam-Ausfall neu geschrieben wurde.
    """
    path = pool_dir(season) / POOL_FILE
    try:
        week = pool_week(season, now.date())
        previous = None
        if path.exists():
            try:
                previous = load_json(path)
                if not isinstance(previous, dict) or "stand" not in previous or not isinstance(previous.get("players"), list):
                    raise FetchError("kein Pool-Auszug")
            except FetchError as exc:
                warn(f"{rel(path)} unlesbar ({exc}) – wird neu geschrieben")
                previous = None
        extract = pool_extract(fetch_pool(session, season, week), season, week, stamp)
        old_order, old_stand = (previous or {}).get("waiver_reihenfolge"), (previous or {}).get("waiver_reihenfolge_stand")
        try:
            order = fetch_waiver_order(session, season)
            extract["waiver_reihenfolge"] = order
            extract["waiver_reihenfolge_stand"] = old_stand if order == old_order and old_stand else stamp
        except FetchError as exc:
            warn(f"Waiver-Reihenfolge ({TEAM_VIEW}) nicht abrufbar, Stand des letzten Laufs bleibt: {exc}")
            extract["waiver_reihenfolge"], extract["waiver_reihenfolge_stand"] = old_order, old_stand
        if same_pool(previous, extract):
            print(f"  {POOL_FILE:<22} unverändert (W{week}, {len(extract['players'])} Spieler, Stand {previous['stand']})")
            return 0, previous
        save_atomic(path, pool_dumps(extract))
    except (FetchError, KeyError, OSError) as exc:
        print(f"  {POOL_FILE:<22} FEHLER – {exc}", file=sys.stderr)
        return 1, None
    print(f"  {POOL_FILE:<22} W{week}, {len(extract['players']):,} Spieler -> {rel(path)}")
    return 0, extract


# ---------------------------------------------------------------- Tageslauf (Action stündlich)

def cmd_daily(season: int, now: datetime, transactions: bool = False, pool: bool = False, wetter: bool = False,
              news: bool = False) -> int:
    """Tageslauf: Transaktions-Archiv, Pool-Auszug, Wetter und – vorbereitet, noch aus – News je Spieler.

    Jeder Teil läuft für sich, geschriebene Rohdaten bleiben auch stehen, wenn ein anderer Teil scheitert. Fehler bei
    ESPN (Transaktionen, Pool) und fehlende Grundlagen machen den Lauf rot; Ausfälle von Open-Meteo und der News-
    Abfrage sind Warnungen, denn der nächste Lauf folgt spätestens eine Stunde später.
    """
    stamp = now.strftime("%Y-%m-%dT%H%MZ")
    errors, warnings = 0, []
    try:
        check_season_open(season, now.date())
    except FetchError as exc:
        print(f"FEHLER – {exc}", file=sys.stderr)
        return 1
    with requests.Session() as session:
        if transactions:
            print("Transaktionen")
            try:
                tx_errors, tx_warnings = archive_transactions(
                    season, lambda params: get_json(session, league_url(season), params), stamp)
            except FetchError as exc:
                tx_errors, tx_warnings = 1, []
                print(f"  FEHLER – {exc}", file=sys.stderr)
            errors, warnings = errors + tx_errors, warnings + tx_warnings
        current = None
        if pool:
            print("Pool-Auszug")
            pool_errors, current = update_pool(session, season, now, stamp)
            errors += pool_errors
        if wetter:
            import wetter as wetter_module  # erst hier: das Modul importiert espn_fetch
            print("Wetter")
            w_errors, w_warnings = wetter_module.run(session, season, now, stamp)
            errors, warnings = errors + w_errors, warnings + w_warnings
        if news and current is not None:
            import news as news_module  # erst hier: das Modul importiert espn_fetch
            print("News")
            n_errors, n_warnings = news_module.run(session, season, current, stamp)
            errors, warnings = errors + n_errors, warnings + n_warnings
    for warning in warnings:
        warn(warning)
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
                        help="alles Fällige: Saisondateien, nicht finale Wochen samt Stand-Dateien, fehlende Spielerpools")
    parser.add_argument("--transactions", action="store_true",
                        help="Tageslauf: Transaktions-Archiv fortschreiben (mTransactions2 je Periode, kona_league_communication)")
    parser.add_argument("--pool", action="store_true",
                        help="Tageslauf: Pool-Auszug pool/latest.json (Status, Besitz, Verletzung, Waiver-Frist, Projektion, Waiver-Reihenfolge)")
    parser.add_argument("--wetter", action="store_true",
                        help="Tageslauf: Wetterprognose der laufenden Woche und Ist-Wetter gespielter Spiele (Open-Meteo)")
    parser.add_argument("--news", action="store_true",
                        help="Tageslauf: News je Spieler mit geändertem lastNewsDate (nur mit --pool; Stufe 2, noch aus)")
    args = parser.parse_args(argv)
    if args.weeks:
        bad = [w for w in args.weeks if not 1 <= w <= MAX_WEEK]
        if bad:
            parser.error(f"ungültige Woche(n) {bad}, erlaubt 1–{MAX_WEEK}")
        args.weeks = sorted(set(args.weeks))
    daily = [flag for flag, on in (("--transactions", args.transactions), ("--pool", args.pool),
                                   ("--wetter", args.wetter), ("--news", args.news)) if on]
    modes = [flag for flag, on in (("--summary", args.summary), ("--due", args.due)) if on] + daily[:1]
    if len(modes) > 1:
        parser.error(f"{' und '.join(modes)} schließen sich aus")
    if (args.due or daily) and (args.weeks or args.force):
        parser.error(f"{modes[0]} wählt selbst, was es holt – ohne --weeks und --force aufrufen")
    if args.news and not args.pool:
        parser.error("--news braucht --pool (Grundlage ist der aktuelle Pool-Auszug mit lastNewsDate je Spieler)")
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
    if args.transactions or args.pool or args.wetter or args.news:
        return cmd_daily(args.season, datetime.now(timezone.utc), args.transactions, args.pool, args.wetter, args.news)
    return cmd_fetch(args.season, args.weeks, args.force)


if __name__ == "__main__":
    sys.exit(main())
