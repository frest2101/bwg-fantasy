"""Rohdaten-Zugriff für das Rechenwerk (Baustein 4): jede Datei einmal laden, je Woche verdichten.

mRoster und kona_player_info sind je Woche rund 3 MB groß (geparst ≈ 10 MB). Sie werden sofort auf kleine Zeilen
(RosterRow, PoolRow) verdichtet, damit bis W14 nicht alle Rohdaten gleichzeitig im Speicher liegen.
Punkte als ungerundete Decimal. Personenbezogene Felder (members, owners, outlooks) gibt dieses Modul nie heraus.

Stand-Dateien (ros.json, mStandings.json) und der Spielerpool kommen immer aus der Woche `through`, nie aus einer
jüngeren – so bleiben Rechnungen mit --through N reproduzierbar, auch wenn später Wochen dazukommen. Einzige
Ausnahme: teams() (Namen, Divisionen, Waiver-Prio, Moves) ist bewusst der jüngste mTeam-Abruf („Stand heute“).
"""

import csv
from pathlib import Path
from typing import NamedTuple

import espn_fetch as ef
import fantasycalc
import fantasypros
import nflverse
import wetter
from zahlen import ZERO, dec

STAT_ACTUAL, STAT_PROJECTION, SPLIT_WEEK = 0, 1, 1   # statSourceId, statSplitTypeId
SPLIT_SEASON = 0                                     # statSplitTypeId des Saison-Eintrags
HISTORY_DIR = "history"                              # data/history/*.csv


class RosterRow(NamedTuple):
    """Ein Kaderplatz eines Fantasy-Teams in einer Woche (aus mRoster mit scoringPeriodId)."""
    team_id: int
    slot: int                 # lineupSlotId
    player_id: int
    pos: int                  # defaultPositionId
    name: str
    pro_team: int             # proTeamId (NFL-Team) zum Abrufzeitpunkt
    actual: object            # Decimal: Ist-Punkte der Woche, 0 ohne Eintrag
    projection: object        # Decimal: Wochenprojektion, 0 ohne Eintrag
    played: bool              # stats["210"] == 1 im Ist-Eintrag
    injury: str | None        # player.injuryStatus, Stand des Abrufs
    prior_pts: object = None  # Decimal: Saison-Ist des Vorjahrs im Liga-Scoring; None ohne Eintrag (Rookie)
    prior_games: int | None = None   # Spiele des Vorjahrs (Stat 210 des Saison-Eintrags)


class PoolRow(NamedTuple):
    """Ein Spieler aus dem ganzen Pool (kona_player_info der Woche)."""
    player_id: int
    name: str
    pos: int
    pro_team: int
    on_team: int              # Fantasy-Team, 0 = keins
    status: str | None        # ONTEAM, WAIVERS, FREEAGENT (Stand des Abrufs)
    injury: str | None
    owned: float | None       # ownership.percentOwned (Stand des Abrufs)
    actual: object            # Decimal oder None, wenn kein Ist-Eintrag der Woche
    projection: object        # Decimal oder None
    played: bool
    game_team: int = 0        # proTeamId des Ist-Eintrags (NFL-Team im Spiel der Woche), 0 ohne Ist-Eintrag


class NflTeam(NamedTuple):
    id: int
    abbrev: str               # Kürzel groß, z. B. ATL
    bye: int                  # byeWeek laut ESPN (0 = unbekannt)
    opponents: dict           # Woche → Gegner-ID; eine Woche ohne Eintrag ist spielfrei (Bye)


def week_stat(player: dict, season: int, week: int, source: int) -> dict | None:
    """Wochen-Eintrag (Ist oder Projektion) eines Spielers, None ohne Eintrag."""
    for s in player.get("stats", []):
        if (s.get("seasonId"), s.get("scoringPeriodId"), s.get("statSourceId"), s.get("statSplitTypeId")) \
                == (season, week, source, SPLIT_WEEK):
            return s
    return None


def played(stat: dict | None) -> bool:
    """„Hat gespielt“ = stats["210"] == 1; ESPN legt Ist-Einträge auch für Inaktive an."""
    return bool(stat) and (stat.get("stats") or {}).get(ef.STAT_PLAYED) == 1


def season_stat(player: dict, season: int) -> dict | None:
    """Saison-Ist eines Spielers (statSourceId 0, statSplitTypeId 0, scoringPeriodId 0), None ohne Eintrag.

    mRoster trägt den Eintrag auch für das Vorjahr, appliedTotal im Liga-Scoring der laufenden Saison (geprüft
    30.09.2026: 222/222 gegen die Rohstats). Wer im Vorjahr ausfiel, hat einen Eintrag ohne Spiele; Rookies haben keinen.
    """
    for s in player.get("stats", []):
        if (s.get("seasonId"), s.get("scoringPeriodId"), s.get("statSourceId"), s.get("statSplitTypeId")) \
                == (season, 0, STAT_ACTUAL, SPLIT_SEASON):
            return s
    return None


def roster_rows(data: dict, season: int, week: int) -> list[RosterRow]:
    """Alle Kaderplätze aller Teams einer mRoster-Antwort, sortiert nach Team und Spieler."""
    rows = []
    for team in data["teams"]:
        for entry in team["roster"]["entries"]:
            player = entry["playerPoolEntry"]["player"]
            actual, projection = (week_stat(player, season, week, s) for s in (STAT_ACTUAL, STAT_PROJECTION))
            prior = season_stat(player, season - 1)
            rows.append(RosterRow(team["id"], entry["lineupSlotId"], player.get("id", 0), player["defaultPositionId"],
                                  player.get("fullName", ""), player.get("proTeamId", 0),
                                  dec(actual.get("appliedTotal", 0)) if actual else ZERO,
                                  dec(projection.get("appliedTotal", 0)) if projection else ZERO,
                                  played(actual), player.get("injuryStatus"),
                                  dec(prior.get("appliedTotal", 0)) if prior else None,
                                  int((prior.get("stats") or {}).get(ef.STAT_PLAYED) or 0) if prior else None))
    return sorted(rows, key=lambda r: (r.team_id, r.player_id))


def pool_rows(data: dict, season: int, week: int) -> list[PoolRow]:
    """Ganzer Spielerpool einer kona_player_info-Antwort, sortiert nach Spieler-ID."""
    rows = []
    for entry in data["players"]:
        player = entry["player"]
        actual, projection = (week_stat(player, season, week, s) for s in (STAT_ACTUAL, STAT_PROJECTION))
        rows.append(PoolRow(entry["id"], player.get("fullName", ""), player["defaultPositionId"],
                            player.get("proTeamId", 0), entry.get("onTeamId", 0), entry.get("status"),
                            player.get("injuryStatus"), (player.get("ownership") or {}).get("percentOwned"),
                            dec(actual["appliedTotal"]) if actual and "appliedTotal" in actual else None,
                            dec(projection["appliedTotal"]) if projection and "appliedTotal" in projection else None,
                            played(actual), (actual or {}).get("proTeamId") or 0))
    return sorted(rows, key=lambda r: r.player_id)


def nfl_schedule(data: dict) -> dict[int, NflTeam]:
    """NFL-Spielplan (proTeamSchedules_wl) je Team: Kürzel, Bye-Woche, Gegner je Woche. Team 0 (FA) entfällt."""
    teams = {}
    for t in data["settings"]["proTeams"]:
        if not t.get("id"):
            continue
        opponents = {}
        for week, games in (t.get("proGamesByScoringPeriod") or {}).items():
            for g in games:
                opponents[int(week)] = g["awayProTeamId"] if g["homeProTeamId"] == t["id"] else g["homeProTeamId"]
        teams[t["id"]] = NflTeam(t["id"], t["abbrev"].upper(), t.get("byeWeek") or 0, dict(sorted(opponents.items())))
    return teams


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class Season:
    """Zugriff auf die Rohdaten einer Saison bis zur Woche `through` (jede Datei höchstens einmal geladen)."""

    def __init__(self, season: int, through: int):
        self.season, self.through = season, through
        self._memo: dict = {}

    def _get(self, key, load):
        if key not in self._memo:
            self._memo[key] = load()
        return self._memo[key]

    def _optional(self, path: Path):
        return ef.load_json(path) if path.exists() else None

    def at(self, through: int) -> "Season":
        """Dieselbe Saison mit anderer Stand-Woche (Playoff-Stand, Stufe 4): Einstellungen, Spielplan, ROS und Standings
        kommen aus der Woche through; die Wochendateien (Kader, Pool) teilt sie mit dieser, nichts wird doppelt geladen."""
        other = Season(self.season, through)
        other._memo = self._memo
        return other

    # -------------------------------------------------------- Liga
    def settings(self) -> dict:
        """mSettings der Woche through (settings-Block)."""
        return self._get(("settings", self.through),
                         lambda: ef.load_json(ef.week_dir(self.season, self.through) / "mSettings.json")["settings"])

    def matchups(self, week: int) -> list[dict]:
        """Paarungen einer Woche (espn_fetch.load_week_matchups)."""
        return self._get(("matchups", week), lambda: ef.load_week_matchups(self.season, week))

    def schedule(self) -> list[dict]:
        """Ganzer Liga-Spielplan (mMatchupScore.schedule) aus der Woche through, inklusive offener Paarungen."""
        return self._get(("schedule", self.through),
                         lambda: ef.load_json(ef.week_dir(self.season, self.through) / "mMatchupScore.json")["schedule"])

    def teams(self) -> list[dict]:
        """Teams laut jüngstem mTeam-Abruf, nur Ligafelder (ohne owners, members, logo), sortiert nach id."""
        def load():
            latest = ef.local_weeks(self.season)[-1]
            keep = ("id", "name", "abbrev", "divisionId", "waiverRank", "transactionCounter", "playoffSeed")
            teams = ef.load_json(ef.week_dir(self.season, latest) / "mTeam.json")["teams"]
            return sorted(({k: t.get(k) for k in keep} for t in teams), key=lambda t: t["id"])
        return self._get("teams", load)

    def roster(self, week: int) -> list[RosterRow]:
        """Kader aller Teams in einer Woche (historische Aufstellung laut mRoster der Woche)."""
        return self._get(("roster", week),
                         lambda: roster_rows(ef.load_json(ef.week_dir(self.season, week) / "mRoster.json"), self.season, week))

    # -------------------------------------------------------- Spielerpool und Stand-Dateien
    def pool(self, week: int) -> list[PoolRow] | None:
        """Spielerpool mit Ist und Projektion der Woche; None, solange kona_player_info fehlt.

        Besitz, Verletzung und Status sind der Stand beim Abruf (bei nachgeholten Wochen der Nachholtag).
        """
        def load():
            data = self._optional(ef.week_dir(self.season, week) / ef.KONA_FILE)
            return pool_rows(data, self.season, week) if data else None
        return self._get(("pool", week), load)

    def ratings(self, week: int) -> dict | None:
        """ESPN positionAgainstOpponent aus kona der Woche (nur als Test verwenden)."""
        def load():
            data = self._optional(ef.week_dir(self.season, week) / ef.KONA_FILE)
            return data.get("positionAgainstOpponent") if data else None
        return self._get(("ratings", week), load)

    def ros(self) -> dict | None:
        """ROS-Auszug nach Woche through: {"after_week", "weeks", "players": {pid: {"4": x, …}}}; None, wenn er fehlt."""
        return self._get(("ros", self.through), lambda: self._optional(ef.week_dir(self.season, self.through) / ef.ROS_FILE))

    def standings(self) -> dict | None:
        """ESPN-Simulation (mStandings) nach Woche through, nur zum Vergleich; None, wenn sie fehlt."""
        return self._get(("standings", self.through),
                         lambda: self._optional(ef.week_dir(self.season, self.through) / ef.STANDINGS_FILE))

    # -------------------------------------------------------- Tageslauf (Pool-Auszug, Wetter) – Stand des jüngsten Laufs
    def pool_latest(self) -> dict | None:
        """Pool-Auszug des Tageslaufs (pool/latest.json): Status, Besitz, Verletzung, Waiver-Frist, Projektion der
        nächsten Woche, letzte ESPN-News je Spieler; None, solange der Tageslauf ihn nicht geschrieben hat."""
        return self._get("pool_latest", lambda: self._optional(ef.pool_dir(self.season) / ef.POOL_FILE))

    def wetter_prognose(self) -> dict | None:
        """Jüngste Wetterprognose (wetter/prognose/wNN_<UTC>.json, nur die laufende Woche); None ohne Datei."""
        def load():
            path = ef.latest(wetter.prognose_dir(self.season), "w[0-9][0-9]_*.json")
            return ef.load_json(path) if path else None
        return self._get("wetter_prognose", load)

    def wetter_ist(self) -> dict | None:
        """Ist-Wetter aller gespielten Spiele (wetter/ist_<saison>.json); None ohne Datei."""
        return self._get("wetter_ist", lambda: self._optional(wetter.ist_path(self.season)))

    def fantasypros(self) -> dict | None:
        """FantasyPros-Adressen je Position (fantasypros/sitemap.json, Wochenabruf); None, solange er sie nicht holte."""
        return self._get("fantasypros", lambda: self._optional(fantasypros.path(self.season)))

    def nflverse(self) -> dict | None:
        """Spieler-Stammdaten von nflverse (nflverse/players.json, Wochenabruf); None, solange er sie nicht holte."""
        return self._get("nflverse", lambda: self._optional(nflverse.path(self.season)))

    def marktwert(self) -> dict | None:
        """Marktwerte von FantasyCalc (fantasycalc/latest.json, Tageslauf, Stand des jüngsten Abrufs); None, solange
        der Tageslauf sie nicht holte."""
        return self._get("marktwert", lambda: self._optional(fantasycalc.path(self.season)))

    # -------------------------------------------------------- Saisondateien
    def nfl(self) -> dict[int, NflTeam]:
        return self._get("nfl", lambda: nfl_schedule(ef.load_json(ef.season_files(self.season)["schedule"])))

    def prior_nfl(self) -> dict[int, NflTeam] | None:
        return self._get("prior_nfl", lambda: (lambda d: nfl_schedule(d) if d else None)(
            self._optional(ef.season_files(self.season)["prior_schedule"])))

    def prior_dst(self) -> dict | None:
        """Rohantwort der 32 D/ST mit Wochenwerten des Vorjahrs (basis/kona_dst_<vorjahr>.json)."""
        return self._get("prior_dst", lambda: self._optional(ef.season_files(self.season)["prior_dst"]))

    def prior_positions(self) -> dict | None:
        """Auszug Positionen des Vorjahrs (basis/positionen_<vorjahr>.json, espn_fetch.positions_extract): je NFL-Team,
        Position und Woche Punkte im Liga-Scoring und Zahl der Spieler mit Einsatz; None, solange er fehlt."""
        return self._get("prior_positions", lambda: self._optional(ef.season_files(self.season)["prior_positions"]))

    def draft(self) -> list[dict]:
        """Draft-Picks inklusive Keeper (mDraftDetail), ohne memberId; leer, solange die Datei fehlt."""
        def load():
            data = self._optional(ef.season_files(self.season)["draft"])
            picks = (data or {}).get("draftDetail", {}).get("picks", [])
            keep = ("overallPickNumber", "roundId", "roundPickNumber", "teamId", "playerId", "keeper")
            return [{k: p.get(k) for k in keep} for p in picks]
        return self._get("draft", load)

    def draft_end(self) -> int | None:
        """Ende des Drafts (draftDetail.completeDate, Epoch-ms); None, solange die Datei fehlt oder der Draft läuft."""
        def load():
            data = self._optional(ef.season_files(self.season)["draft"])
            return (data or {}).get("draftDetail", {}).get("completeDate")
        return self._get("draft_end", load)

    def transactions(self) -> list[dict]:
        """Alle archivierten Transaktionen (mTransactions2_p*.json), je id die zuletzt archivierte Fassung.

        Neben einer geschrumpften Periode liegt die neue Antwort als mTransactions2_pNN_<Zeit>.json; die
        Vereinigung über id verliert so keinen Eintrag. Sortiert nach (processDate oder proposedDate, id).
        """
        def load():
            merged = {}
            for path in sorted(ef.tx_dir(self.season).glob(f"{ef.TX_VIEW}_p*.json")):
                for t in ef.load_json(path).get("transactions", []):
                    merged[t["id"]] = t
            return sorted(merged.values(), key=lambda t: (t.get("processDate") or t.get("proposedDate") or 0, t["id"]))
        return self._get("transactions", load)

    def history(self, name: str) -> list[dict]:
        """Eine Tabelle der Liga-Historie (data/history/<name>.csv) als Liste von Zeilen."""
        return self._get(("history", name), lambda: read_csv(ef.REPO_DIR / "data" / HISTORY_DIR / f"{name}.csv"))
