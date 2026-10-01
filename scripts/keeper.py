"""Keeper-Bilanz (Keeper-Tab): Herkunft je Kaderspieler, Punkte nach Herkunft je Team, Ertrag des Drafts (Stufe 1),
Altersprofil je Team aus den nflverse-Stammdaten (Stufe 2) und Marktwert aus FantasyCalc (Stufe 3).

Die Liga behält 12 von 24 Kaderspielern über den Winter (mSettings draftSettings.keeperCount, Keeper am Draft-Ende
ohne Kosten). Dieses Modul zeigt, woher die Punkte eines Teams kommen: von Keepern, aus dem Draft der Saison oder
von späteren Zugängen. Regeln: CLAUDE.md „Rechenregeln“ (Keeper-Bilanz).

Herkunft = Nachspielen des Archivs. Ausgangspunkt ist der Draft (mDraftDetail mit Keeper-Kennzeichen), danach jede
ausgeführte Bewegung (ADD/DROP) aus mTransactions2 nach dem Draft-Ende. Je Spieler entsteht eine Zeitleiste aus
Abschnitten (Team, Art, Beginn, Periode, Pick, Ende). Ein Trade hat im Archiv keine Spieler: Steht ein Spieler bei
einem Team, zu dem ihn keine Bewegung geführt hat, kam er per Trade; der Tageslauf liefert dazu das Datum
(pool/latest.json, Kopf trades aus mRoster acquisitionType TRADE).
Wochen ordnet die ESPN-Periode der Bewegung zu (scoringPeriodId), nicht die Uhrzeit: Ein Zugang in Periode w zählt
ab Woche w, ein Abgang in Periode w beendet den Abschnitt nach Woche w.
Marktwert (Stufe 3): Tauschwerte aus Dynasty-Ligen mit rund 300 gehaltenen Spielern; die BWG hält 120. Die Keeper-Linie
ist der Wert des 120.-wertvollsten Kaderspielers – oberhalb passen die Werte, darunter überzeichnen sie. K und D/ST
haben keinen Wert. Kein Wert fließt in Score, Power Ranking oder Simulation.

Reine Funktionen, ungerundete Decimal; gerundet wird erst beim Export. memberId & Co. gibt dieses Modul nie heraus.
"""

from datetime import date, timedelta
from decimal import Decimal

import espn_fetch as ef
import fantasycalc
import nflverse
import players
import rawdata
import records
from lineup import QB, RB, TE, WR, is_starter
from zahlen import HUNDRED, ZERO, round_to

KEEPER, DRAFT, WAIVER, FREEAGENT, TRADE = "keeper", "draft", "waiver", "free_agent", "trade"
ARTEN = (KEEPER, DRAFT, WAIVER, FREEAGENT, TRADE)
# Punkte je Team in vier Gruppen: Waiver-Claims und Free-Agent-Zugänge zusammen als „zugang“
GRUPPE = {KEEPER: "keeper", DRAFT: "draft", WAIVER: "zugang", FREEAGENT: "zugang", TRADE: "trade"}
GRUPPEN = ("keeper", "draft", "zugang", "trade")
# Kern = ohne K und D/ST: kein Kicker ist Keeper und nur wenige D/ST, ihr Anteil misst sonst vor allem das
KERN = (QB, RB, WR, TE)
# Altersprofil: „jung“ unter 26, „alt“ ab 30 (Faustgrenzen, keine Positionskurve); verglichen wie angezeigt, also
# mit dem auf eine Stelle gerundeten Alter – sonst stünde ein Spieler mit „26,0“ in der Liste und zählte als unter 26
JUNG_UNTER, ALT_AB, ALTER_STELLEN = 26, 30, 1


# ---------------------------------------------------------------- Zeitleisten

def timelines(picks: list[dict], entries: list[dict], draft_end: int | None) -> dict[int, list[dict]]:
    """Zeitleiste je Spieler aus Draft und Archiv: Liste von Abschnitten in zeitlicher Folge.

    Abschnitt = {team, art, datum (Epoch-ms), periode, pick (overallPickNumber oder None), ende (Periode des
    Abgangs oder None = offen)}. Der Draft eröffnet je Pick einen Abschnitt in Periode 0 (art keeper oder draft).
    Danach zählen nur ausgeführte Bewegungen nach dem Draft-Ende (die Vorsaison-Moves betreffen den alten Kader):
    DROP schließt den offenen Abschnitt, ADD schließt ihn ebenfalls (falls der Drop im Archiv fehlt) und eröffnet
    einen neuen (art waiver bei einem Claim, sonst free_agent). entries wie rawdata.Season.transactions()
    (nach Datum sortiert).
    """
    lines: dict[int, list[dict]] = {}
    for p in sorted(picks, key=lambda p: p["overallPickNumber"]):
        lines.setdefault(p["playerId"], []).append(
            {"team": p["teamId"], "art": KEEPER if p["keeper"] else DRAFT, "datum": draft_end, "periode": 0,
             "pick": p["overallPickNumber"], "ende": None})
    for t in entries:
        if t.get("status") != records.EXECUTED or t.get("type") not in records.MOVE_TYPES + records.LINEUP_TYPES:
            continue
        date = records.tx_date(t)
        if draft_end is not None and (date or 0) <= draft_end:
            continue
        period = t.get("scoringPeriodId") or 0
        for i in t.get("items") or []:
            if i.get("type") not in records.PLAYER_ITEMS:
                continue
            line = lines.setdefault(i["playerId"], [])
            if line and line[-1]["ende"] is None:
                line[-1]["ende"] = period
            if i["type"] == "ADD":
                line.append({"team": i["toTeamId"], "art": WAIVER if t["type"] == "WAIVER" else FREEAGENT,
                             "datum": date, "periode": period, "pick": None, "ende": None})
    return lines


def origin(line: list[dict], team: int, week: int | None = None) -> dict | None:
    """Abschnitt, der den Spieler zu team geführt hat: in Woche week (Zugang bis zur Woche, Abgang nicht vor ihr),
    ohne week der offene Abschnitt (Stand heute). None = keiner, der Spieler kam per Trade."""
    for seg in reversed(line):
        if seg["team"] != team:
            continue
        if week is None:
            if seg["ende"] is None:
                return seg
        elif seg["periode"] <= week and (seg["ende"] is None or seg["ende"] >= week):
            return seg
    return None


def last_at(line: list[dict], team: int) -> dict | None:
    """Jüngster Abschnitt des Spielers bei team, auch ein geschlossener; None, wenn es dort nie einen gab."""
    return next((seg for seg in reversed(line) if seg["team"] == team), None)


def traded_pick(line: list[dict]) -> dict | None:
    """Offener Draft-Abschnitt eines per Trade gekommenen Spielers: Er steht im Archiv noch beim abgebenden Team."""
    last = line[-1] if line else None
    return last if last and last["ende"] is None and last["pick"] is not None else None


# ---------------------------------------------------------------- Punkte nach Herkunft

def shares(parts: dict[str, Decimal]) -> dict:
    """{summe, pts, anteil}: Anteile in Prozent der Summe; None je Gruppe ohne Punkte insgesamt."""
    total = sum(parts.values(), ZERO)
    return {"summe": total, "pts": dict(parts),
            "anteil": {g: (v / total * HUNDRED if total else None) for g, v in parts.items()}}


def points_by_origin(ssn: rawdata.Season, weeks: list[int], lines: dict[int, list[dict]]) -> tuple[dict, dict, dict]:
    """Starter-Punkte der Wochen nach Herkunft: je Team alle Positionen, je Team nur der Kern (QB, RB, WR, TE), und
    je Draft-Pick Starts und Punkte für das Team des Picks, solange der Abschnitt des Picks läuft.

    Team und Slot je Woche aus mRoster der Woche (die historische Aufstellung); die Summe über die Gruppen ist
    die PF des Teams. Rückgabe (team_id → Gruppe → Punkte, dasselbe für den Kern, Pick → {"starts", "pf"}).
    """
    pf: dict[int, dict[str, Decimal]] = {}
    kern: dict[int, dict[str, Decimal]] = {}
    ertrag: dict[int, dict] = {}
    for week in weeks:
        for r in ssn.roster(week):
            pf.setdefault(r.team_id, dict.fromkeys(GRUPPEN, ZERO))
            kern.setdefault(r.team_id, dict.fromkeys(GRUPPEN, ZERO))
            if not is_starter(r.slot):
                continue
            seg = origin(lines.get(r.player_id, []), r.team_id, week)
            group = GRUPPE[seg["art"]] if seg else GRUPPE[TRADE]
            pf[r.team_id][group] += r.actual
            if r.pos in KERN:
                kern[r.team_id][group] += r.actual
            if seg and seg["pick"] is not None:
                e = ertrag.setdefault(seg["pick"], {"starts": 0, "pf": ZERO})
                e["starts"] += 1
                e["pf"] += r.actual
    return pf, kern, ertrag


# ---------------------------------------------------------------- Kader heute

def current_roster(ssn: rawdata.Season) -> tuple[dict[int, int], str | None]:
    """Kader heute: Spieler-ID → team_id und der Stand dazu. Tagesstand (pool/latest.json), solange es ihn gibt;
    sonst der Spielerpool der Woche through, ohne ihn mRoster der Woche (Stand None = Wochenstand)."""
    pool = ssn.pool_latest()
    if pool:
        return {p["id"]: p["onTeamId"] for p in pool["players"] if p.get("onTeamId")}, pool.get("stand")
    weekly = ssn.pool(ssn.through)
    if weekly is not None:
        return {r.player_id: r.on_team for r in weekly if r.on_team}, None
    return {r.player_id: r.team_id for r in ssn.roster(ssn.through)}, None


def espn_trades(ssn: rawdata.Season) -> dict[int, tuple[int, int | None]] | None:
    """Per Trade gekommene Kaderspieler laut Tagesstand (Kopf trades): Spieler-ID → (team_id, Datum Epoch-ms);
    None, solange der Tageslauf das Feld nicht geliefert hat."""
    trades = (ssn.pool_latest() or {}).get("trades")
    if trades is None:
        return None
    return {int(pid): (team, date) for pid, (team, date) in trades.items()}


def prior_season(ssn: rawdata.Season, weeks: list[int]) -> dict[int, tuple]:
    """Saison-Ist des Vorjahrs je Spieler (Punkte im Liga-Scoring, Spiele) aus mRoster der Wochen; eine jüngere
    Woche überschreibt eine ältere. Punkte None = kein Vorjahres-Eintrag (Rookie). Nur Spieler, die in einer der
    Wochen in einem Kader standen – für alle anderen ist das Vorjahr unbekannt."""
    out = {}
    for week in sorted(weeks):
        for r in ssn.roster(week):
            out[r.player_id] = (r.prior_pts, r.prior_games)
    return out


def roster_origins(roster: dict[int, int], lines: dict[int, list[dict]], picks: dict[int, dict],
                   trades: dict[int, tuple[int, int | None]] | None, prior: dict[int, tuple],
                   draft_end: int | None) -> tuple[list[dict], list[str]]:
    """Herkunft je Kaderspieler heute, sortiert nach (team, id), dazu Warnungen.

    art = Art des offenen Abschnitts beim Team. Ist der Kaderstand älter als das Archiv (der Pool-Abruf eines
    Tageslaufs scheiterte, das Archiv kennt den Abgang schon; oder Wochenstand ohne Tagesstand), gilt der jüngste
    geschlossene Abschnitt beim Team – sonst stünde ein eben entlassener Spieler als Trade da. trade nur, wenn das
    Archiv den Spieler nie zu diesem Team geführt hat. Nennt der Tagesstand den Spieler als Trade, gilt
    das (auch wenn das Archiv ihn anders führt), mit dem Datum von ESPN. pick, runde und von (Team des Picks) stehen
    bei Keepern und Draft-Picks und bei getauschten Spielern, die seit dem Draft ununterbrochen in einem Kader
    stehen. seit = Beginn beim Team: Draft-Ende, Datum des Zugangs, Datum des Trades (None ohne Tagesstand);
    bei Keepern None (vor dem Draft, im Archiv nicht belegt). vj_pts, vj_g, vj_avg (Punkte je Spiel) und rookie
    (kein Vorjahres-Eintrag) aus prior_season, alle None ohne Angabe.
    """
    rows, warnings = [], []
    for pid, team in sorted(roster.items(), key=lambda kv: (kv[1], kv[0])):
        line = lines.get(pid, [])
        seg = origin(line, team) or last_at(line, team)
        by_espn = trades.get(pid) if trades else None
        if by_espn and by_espn[0] == team:
            art, since, source = TRADE, by_espn[1], traded_pick(line) if seg is None else None
        elif seg is None:
            art, since, source = TRADE, None, traded_pick(line)
            if trades is not None:
                warnings.append(f"Spieler {pid} bei Team {team}: kein Zugang im Archiv und laut ESPN kein Trade")
        else:
            art, source = seg["art"], seg if seg["pick"] is not None else None
            since = None if art == KEEPER else draft_end if art == DRAFT else seg["datum"]
        pick = picks.get(source["pick"]) if source else None
        vj = prior.get(pid)
        rows.append({"id": pid, "team": team, "art": art,
                     "pick": pick["overallPickNumber"] if pick else None, "runde": pick["roundId"] if pick else None,
                     "von": pick["teamId"] if pick else None, "seit": since,
                     "vj_pts": vj[0] if vj else None, "vj_g": vj[1] if vj else None,
                     "vj_avg": vj[0] / vj[1] if vj and vj[0] is not None and vj[1] else None,
                     "rookie": vj[0] is None if vj else None})
    return rows, warnings


# ---------------------------------------------------------------- Altersprofil (Stufe 2)

def add_ages(kader: list[dict], stamm: dict[int, dict], day: date, season: int) -> None:
    """Trägt je Kaderzeile alter (Jahre am Stichtag day, ungerundet) und nfl_jahr (Saison − Rookie-Saison + 1) aus
    den nflverse-Stammdaten ein, None ohne Eintrag. Mit Rookie-Saison ersetzt nfl_jahr == 1 die Rookie-Näherung
    aus dem Vorjahres-Eintrag (sie kennt nur Spieler, die in einer gewerteten Woche im Kader standen)."""
    for k in kader:
        s = stamm.get(k["id"])
        k["alter"] = nflverse.age(s["geb"], day) if s else None
        k["nfl_jahr"] = nflverse.nfl_year(s["rookie"], season) if s else None
        if k["nfl_jahr"] is not None:
            k["rookie"] = k["nfl_jahr"] == 1


def has_age(row: dict) -> bool:
    """Zählt im Altersprofil: Alter und Position bekannt (ohne Position kein Positionsschnitt)."""
    return row["alter"] is not None and row["pos"] is not None


def position_ages(rows: list[dict]) -> dict[int, dict]:
    """Ø Alter je Position über die Kaderspieler mit Alter: Position → {"n", "alter"}; D/ST haben kein Alter."""
    by_pos: dict[int, list[Decimal]] = {}
    for r in rows:
        if has_age(r):
            by_pos.setdefault(r["pos"], []).append(r["alter"])
    return {pos: {"n": len(v), "alter": sum(v, ZERO) / len(v)} for pos, v in sorted(by_pos.items())}


def age_profile(rows: list[dict], weight: dict[int, Decimal], pos_age: dict[int, dict]) -> dict | None:
    """Altersprofil einer Gruppe von Kaderzeilen (ein Team oder die Liga); None ohne einen Spieler mit Alter.

    kader = Ø Alter; ros = mit den Gewichten weight (Restpunkte laut ESPN-Projektion) gewichtet – das Alter der
    Spieler, von denen die Punkte kommen sollen; bereinigt = Ø (Alter − Liga-Schnitt der Position, pos_age), weil
    Quarterbacks und Kicker im Schnitt älter sind; bereinigt_ros = dasselbe gewichtet. Beide ros-Werte None ohne
    Gewichte. jung = Alter unter JUNG_UNTER, alt = ab ALT_AB, verglichen wie angezeigt (auf eine Stelle, round half
    up); rookies und zweites_jahr nach nfl_jahr.
    """
    aged = [r for r in rows if has_age(r)]
    if not aged:
        return None
    n = len(aged)
    dev = {r["id"]: r["alter"] - pos_age[r["pos"]]["alter"] for r in aged}
    w = {r["id"]: weight.get(r["id"]) or ZERO for r in aged}
    total = sum(w.values(), ZERO)
    shown = {r["id"]: round_to(r["alter"], ALTER_STELLEN) for r in aged}
    weighted = lambda value: sum((w[r["id"]] * value(r) for r in aged), ZERO) / total if total > 0 else None  # noqa: E731
    return {"n": n, "kader": sum((r["alter"] for r in aged), ZERO) / n, "ros": weighted(lambda r: r["alter"]),
            "bereinigt": sum(dev.values(), ZERO) / n, "bereinigt_ros": weighted(lambda r: dev[r["id"]]),
            "jung": sum(1 for r in aged if shown[r["id"]] < JUNG_UNTER),
            "alt": sum(1 for r in aged if shown[r["id"]] >= ALT_AB),
            "rookies": sum(1 for r in aged if r["nfl_jahr"] == 1),
            "zweites_jahr": sum(1 for r in aged if r["nfl_jahr"] == 2)}


def ros_weights(spieler: dict) -> tuple[dict[int, Decimal], str | None]:
    """Gewichte für das Altersprofil: Restpunkte je Spieler laut ESPN-Projektion – bis W14 der Regular Season
    ("ros"), danach der Playoff-Wochen ("ros_po"); leer und None ohne ROS-Auszug und nach W17."""
    after = spieler.get("ros_after_week")
    if after is None or after >= players.LAST_PLAYOFF_WEEK:
        return {}, None
    key = "ros" if after < players.LAST_REGULAR_WEEK else "ros_po"
    return {pid: p[key] for pid, p in spieler["players"].items() if p.get(key) is not None}, key


# ---------------------------------------------------------------- Marktwert (Stufe 3)

# Werte je Spieler (fantasycalc.werte) → Felder je Zeile; dazu wert_ue = Wert − Keeper-Linie
WERT_FELDER = {"wert": "wert", "rang": "wert_rang", "pos_rang": "wert_posrang", "trend30": "wert_trend",
               "redraft": "wert_redraft"}


def keeper_line(values: list[int], count: int | None) -> int | None:
    """Keeper-Linie: Wert des count-wertvollsten Kaderspielers der Liga (count = Keeper je Team × Teams, also 120);
    None ohne count oder wenn weniger Kaderspieler einen Wert haben."""
    ranked_values = sorted(values, reverse=True)
    return ranked_values[count - 1] if count and len(ranked_values) >= count else None


def value_fields(w: dict | None, line: int | None) -> dict:
    """Felder einer Zeile aus den Werten w eines Spielers (None ohne Wert): WERT_FELDER und wert_ue (None ohne Linie)."""
    out = {new: (w[old] if w else None) for old, new in WERT_FELDER.items()}
    out["wert_ue"] = w["wert"] - line if w and line is not None else None
    return out


def value_profile(rows: list[dict], line: int | None, count: int | None) -> dict | None:
    """Marktwert eines Teams aus seinen Kaderzeilen (mit wert und alter); None ohne Spieler mit Wert.

    n = Spieler mit Wert; kern = Σ der count wertvollsten (die Summe, nicht die Spieler); ueber_linie = Σ der Beträge
    über der Keeper-Linie (nur positive); n_linie = Spieler mit Wert ≥ Linie (beide None ohne Linie); alter = Ø Alter
    gewichtet mit dem Wert (None ohne Alter).
    """
    valued = [r for r in rows if r["wert"] is not None]
    if not valued:
        return None
    aged = [r for r in valued if r["alter"] is not None]
    total = sum(r["wert"] for r in aged)
    return {"n": len(valued), "kern": sum(sorted((r["wert"] for r in valued), reverse=True)[:count or 0]),
            "ueber_linie": sum(max(r["wert"] - line, 0) for r in valued) if line is not None else None,
            "n_linie": sum(1 for r in valued if r["wert"] >= line) if line is not None else None,
            "alter": sum((Decimal(r["wert"]) * r["alter"] for r in aged), ZERO) / total if total > 0 else None}


def league_values(profiles: list[dict | None], rows: list[dict]) -> dict | None:
    """Marktwert der Liga: kern und ueber_linie als Ø je Team (Teams mit Wert), n und n_linie als Summe, alter über
    alle Kaderspieler mit Wert und Alter; None ohne ein Team mit Wert."""
    teams = [p for p in profiles if p]
    if not teams:
        return None
    mean = lambda key: sum((Decimal(p[key]) for p in teams), ZERO) / len(teams) if teams[0][key] is not None else None  # noqa: E731
    return {"n": sum(p["n"] for p in teams), "kern": mean("kern"), "ueber_linie": mean("ueber_linie"),
            "n_linie": sum(p["n_linie"] for p in teams) if teams[0]["n_linie"] is not None else None,
            "alter": value_profile(rows, None, 0)["alter"]}


def value_rows(werte: dict[int, dict], pool: dict[int, dict], kader: list[dict], stamm: dict[int, dict], day,
               line: int | None) -> dict[int, dict]:
    """Alle Spieler mit Marktwert, die der Wochenpool kennt, je ESPN-ID (Grundlage für Waiver-Tab und die Datei für
    das Claude-Projekt): value_fields, team (heute, 0 = frei), art (Herkunft bei Kaderspielern, sonst None) und
    alter (am Stichtag day; Kaderspieler wie add_ages, None ohne Stammdaten)."""
    roster = {k["id"]: k for k in kader}
    out = {}
    for pid in sorted(werte):
        if pid not in pool:
            continue
        k, s = roster.get(pid), stamm.get(pid)
        out[pid] = value_fields(werte[pid], line) | {
            "team": k["team"] if k else 0, "art": k["art"] if k else None,
            "alter": k["alter"] if k else (nflverse.age(s["geb"], day) if s else None)}
    return out


# ---------------------------------------------------------------- Einstieg

def compute_keeper(ssn: rawdata.Season, weeks: list[int], spieler: dict, names: dict[int, str]) -> dict | None:
    """Keeper-Bilanz der Saison; None, solange es keinen abgeschlossenen Draft gibt.

    teams (nach team_id) und liga: keeper / keeper_da (Keeper-Picks und wie viele davon noch als Keeper im Kader
    stehen), picks / picks_da (Draft-Picks der Saison genauso), kader (Spieler heute je Art), pf und kern
    ({summe, pts, anteil} je Gruppe keeper, draft, zugang, trade; kern ohne K und D/ST), altersprofil (age_profile
    des Kaders heute, None ohne nflverse-Stammdaten; liga zusätzlich positionen = position_ages).
    kader: Herkunft je Kaderspieler heute (roster_origins), dazu name, pos, nfl, g und avg (Saison) aus dem Wochenpool,
    vj_delta = avg − vj_avg (Punkte je Spiel gegen das Vorjahr, None ohne einen der beiden Werte) sowie alter und
    nfl_jahr (add_ages). Kopf: alter_stichtag (Dienstag nach der letzten gewerteten Woche) und alter_gewicht
    ("ros" oder "ros_po", None ohne ROS-Auszug), beide None ohne Stammdaten.
    Marktwert (Stufe 3, FantasyCalc): je Kaderzeile value_fields (wert … wert_ue); je Team marktwert (value_profile),
    liga.marktwert (league_values); Kopf keeper_linie und marktwert_stand (Abrufzeit des Auszugs); werte = alle
    Spieler mit Wert (value_rows). Ohne Auszug sind alle Werte None und werte leer.
    picks: alle Picks mit Ertrag – da (der Spieler steht heute beim Team des Picks und wird dort als dieser Keeper-
    bzw. Draft-Pick geführt, also nicht entlassen und nicht getauscht), team_jetzt (0 = frei), g, pts und avg
    (Saison des Spielers, None ohne Eintrag im Wochenpool), starts und pf (für das Team des Picks, solange der
    Abschnitt lief).
    spieler = players.compute_players (Saisonwerte je Spieler), names = Spielernamen je ID (records.player_names).
    """
    draft = ssn.draft()
    draft_end = ssn.draft_end()
    if not draft or draft_end is None:   # ohne Draft-Ende zählten die Vorsaison-Moves mit
        return None
    lines = timelines(draft, ssn.transactions(), draft_end)
    pf, kern, ertrag = points_by_origin(ssn, weeks, lines)
    roster, stand = current_roster(ssn)
    picks = {p["overallPickNumber"]: p for p in draft}
    kader, warnings = roster_origins(roster, lines, picks, espn_trades(ssn), prior_season(ssn, weeks), draft_end)
    art_now = {(k["id"], k["team"]): k for k in kader}
    pool = spieler["players"]
    for k in kader:   # Stammdaten und Saison aus dem Wochenpool; None für Spieler, die er nicht kennt
        info = pool.get(k["id"])
        avg = info["avg"] if info else None
        k.update(name=names.get(k["id"]) or (info["name"] if info else None), pos=info["pos"] if info else None,
                 nfl=info["nfl"] if info else None, g=info["games"] if info else None, avg=avg,
                 vj_delta=avg - k["vj_avg"] if avg is not None and k["vj_avg"] is not None else None)
    # Alter zum Dienstag nach der letzten gewerteten Woche (kein „heute“: die Rechnung bleibt reproduzierbar)
    stamm = nflverse.stammdaten(ssn.nflverse())
    day = ef.WEEK1_START[ssn.season] + timedelta(weeks=weeks[-1])
    add_ages(kader, stamm, day, ssn.season)
    pos_age = position_ages(kader)
    weight, weight_key = ros_weights(spieler)
    # Marktwert (Stufe 3): Keeper-Linie = Wert des (Keeper je Team × Teams)-wertvollsten Kaderspielers heute
    team_ids = [t["id"] for t in ssn.teams()]
    keeper_zahl = (ssn.settings().get("draftSettings") or {}).get("keeperCount")
    market = ssn.marktwert()
    werte = fantasycalc.werte(market)
    line = keeper_line([werte[k["id"]]["wert"] for k in kader if k["id"] in werte],
                       keeper_zahl * len(team_ids) if keeper_zahl else None)
    for k in kader:
        k.update(value_fields(werte.get(k["id"]), line))

    pick_rows = []
    for no in sorted(picks):
        p = picks[no]
        pid, team = p["playerId"], p["teamId"]
        now = art_now.get((pid, team))
        info, e = pool.get(pid), ertrag.get(no, {"starts": 0, "pf": ZERO})
        pick_rows.append({"pick": no, "runde": p["roundId"], "runden_pick": p["roundPickNumber"], "team_id": team,
                          "player_id": pid, "name": names.get(pid) or (info["name"] if info else None),
                          "pos": info["pos"] if info else None, "keeper": bool(p["keeper"]),
                          "da": bool(now and now["pick"] == no and now["art"] in (KEEPER, DRAFT)),
                          "team_jetzt": roster.get(pid, 0),
                          "g": info["games"] if info else None, "pts": info["pts"] if info else None,
                          "avg": info["avg"] if info else None, "starts": e["starts"], "pf": e["pf"]})

    def summary(team_ids: list[int]) -> dict:
        mine = [r for r in pick_rows if r["team_id"] in team_ids]
        keepers, drafted = [r for r in mine if r["keeper"]], [r for r in mine if not r["keeper"]]
        now = [k for k in kader if k["team"] in team_ids]
        total = lambda src: {g: sum((src.get(t, {}).get(g, ZERO) for t in team_ids), ZERO) for g in GRUPPEN}  # noqa: E731
        return {"keeper": len(keepers), "keeper_da": sum(1 for r in keepers if r["da"]),
                "picks": len(drafted), "picks_da": sum(1 for r in drafted if r["da"]),
                "kader": {art: sum(1 for k in now if k["art"] == art) for art in ARTEN},
                "pf": shares(total(pf)), "kern": shares(total(kern)),
                "altersprofil": age_profile(now, weight, pos_age),
                "marktwert": value_profile(now, line, keeper_zahl) if werte else None}

    rules = players.roster_rules(ssn.settings())
    teams = [{"team_id": tid} | summary([tid]) for tid in team_ids]
    liga = summary(team_ids)
    if liga["altersprofil"]:
        liga["altersprofil"]["positionen"] = pos_age
    liga["marktwert"] = league_values([t["marktwert"] for t in teams], kader) if werte else None
    return {"through_week": weeks[-1], "stand": stand, "draft_datum": draft_end,
            "keeper_zahl": keeper_zahl, "kader_plaetze": rules["plaetze"] - rules["ir"],
            "alter_stichtag": day.isoformat() if stamm else None, "alter_gewicht": weight_key if stamm else None,
            "marktwert_stand": (market or {}).get("stand") if werte else None, "keeper_linie": line,
            "teams": teams, "liga": liga, "kader": kader, "picks": pick_rows, "warnungen": warnings,
            # alle Spieler mit Marktwert (Waiver-Tab, Datei für das Claude-Projekt); leer ohne Auszug
            "werte": value_rows(werte, pool, kader, stamm, day, line)}
