"""Wetter (Session 6): Prognose je Spiel der laufenden Woche und Ist-Wetter je gespieltem Spiel aus Open-Meteo.

Quelle: Open-Meteo Forecast-API (frei, ohne Schlüssel; Modellwerte, kein Stationsmesswert – Probe-Lauf 29.09.2026).
Je Spiel die Stundenwerte ab der Kickoff-Stunde und drei Stunden danach: Temperatur, Wind (Mittel und Böen),
Regenwahrscheinlichkeit (nur Prognose), Niederschlag, Schnee. Spielort je Spiel aus data/raw/<saison>/nfl/stadien.json
(Heimstadion oder Auslandsspiel), Anstoß aus dem NFL-Spielplan (proTeamSchedules_wl). Nur W1–17, kein W18.

Ablage (Beschlüsse Stephan 29.09.2026, docs/auftraege/session6_vorbereitung.md):
    wetter/prognose/wNN_<UTC>.json   je Lauf eine Datei, nur für die laufende Woche; beim ersten Lauf einer neuen Woche
                                     löscht das Script die Dateien der Vorwoche (die Git-Historie behält sie)
    wetter/ist_<saison>.json          tatsächliches Wetter je Spiel, dauerhaft; ein Spiel kommt hinein, sobald sein
                                     Anstoß vier Stunden zurückliegt, und wird nie überschrieben
Dachspiele (dach fest oder beweglich) bekommen dieselben Werte – ob sie angezeigt werden, entscheidet die App.
Für die App verdichtet compute_wetter die vier Stunden je Spiel (Ø Temperatur und Wind, höchste Böe, Σ Niederschlag).
"""

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import espn_fetch as ef
from zahlen import dec, round_to

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
# Open-Meteo-Variable → Schlüssel in den Dateien; Regenwahrscheinlichkeit nur in der Prognose
VARIABLES = {"temperature_2m": "temp", "wind_speed_10m": "wind", "wind_gusts_10m": "boeen",
             "precipitation_probability": "regen_wahrsch", "precipitation": "niederschlag", "snowfall": "schnee"}
FORECAST_ONLY = ("regen_wahrsch",)
EINHEITEN = {"temp": "°C", "wind": "km/h", "boeen": "km/h", "regen_wahrsch": "%", "niederschlag": "mm", "schnee": "cm"}
HOURS = 4                         # Kickoff-Stunde und drei Stunden danach
IST_DELAY = timedelta(hours=4)    # Ist-Wetter erst, wenn der Anstoß vier Stunden zurückliegt (Spiel vorbei)
LAST_WEEK = ef.MAX_WEEK           # W1–17, kein W18 (Beschluss Stephan 29.09.2026)
DACH = ("offen", "fest", "beweglich")
QUELLE = ("Open-Meteo Forecast-API (api.open-meteo.com/v1/forecast): Modellwerte je Stunde ab der Kickoff-Stunde "
          "und drei Stunden danach, kein Stationsmesswert")
SITE_KEYS = ("stadion", "ort", "lat", "lon", "dach", "zeitzone")


# ---------------------------------------------------------------- Pfade und Grundlagen

def wetter_dir(season: int) -> Path:
    return ef.RAW_DIR / str(season) / "wetter"


def prognose_dir(season: int) -> Path:
    return wetter_dir(season) / "prognose"


def ist_path(season: int) -> Path:
    return wetter_dir(season) / f"ist_{season}.json"


def stadien_path(season: int) -> Path:
    return ef.RAW_DIR / str(season) / "nfl" / "stadien.json"


def load_stadien(season: int) -> dict:
    """Stadion-Tabelle: {"stadien": {proTeamId: {...}}, "auslandsspiele": {spiel_id: {...}}}; prüft die Dach-Werte."""
    data = ef.load_json(stadien_path(season))
    stadien = {int(team_id): site for team_id, site in data["stadien"].items()}
    ausland = {a["spiel_id"]: a for a in data.get("auslandsspiele", [])}
    for site in list(stadien.values()) + list(ausland.values()):
        if site.get("dach") not in DACH or not all(k in site for k in SITE_KEYS):
            raise ef.FetchError(f"{ef.rel(stadien_path(season))}: Eintrag {site.get('stadion')!r} unvollständig oder Dach ungültig")
    return {"stadien": stadien, "auslandsspiele": ausland}


def season_games(schedule: dict) -> list[dict]:
    """Alle NFL-Spiele W1–17 aus proTeamSchedules_wl, jedes einmal: id, woche, heim, gast, kickoff (UTC), tbd.

    tbd: ESPN führt den Anstoß noch als offen (startTimeTBD, Flex-Spiele der späten Wochen); solche Spiele bekommen
    keine Wetterwerte, bis die Zeit feststeht.
    """
    games = {}
    for team in schedule["settings"]["proTeams"]:
        for entries in (team.get("proGamesByScoringPeriod") or {}).values():
            for g in entries:
                if 1 <= g["scoringPeriodId"] <= LAST_WEEK:
                    games[g["id"]] = {"id": g["id"], "woche": g["scoringPeriodId"], "heim": g["homeProTeamId"],
                                      "gast": g["awayProTeamId"],
                                      "kickoff": datetime.fromtimestamp(g["date"] / 1000, tz=timezone.utc),
                                      "tbd": bool(g.get("startTimeTBD"))}
    return sorted(games.values(), key=lambda g: (g["woche"], g["kickoff"], g["id"]))


def game_site(game: dict, stadien: dict) -> dict:
    """Spielort eines Spiels: Auslandsspiel (nach Spiel-ID) oder Heimstadion; dazu neutral (bool)."""
    special = stadien["auslandsspiele"].get(game["id"])
    site = special if special else stadien["stadien"].get(game["heim"])
    if site is None:
        raise ef.FetchError(f"Spiel {game['id']} (W{game['woche']}): kein Stadion für Heimteam {game['heim']} in stadien.json")
    return {k: site[k] for k in SITE_KEYS} | {"neutral": special is not None}


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def prognose_week(games: list[dict], now: datetime) -> int | None:
    """Woche der Prognose: die erste Woche W1–17 mit einem Spiel, das noch nicht vorbei ist (Anstoß + IST_DELAY > now).

    Aus dem NFL-Spielplan statt aus dem Kalender: so bleibt in der Montagnacht (MNF, Anstoß 00:15 UTC Dienstag) die
    laufende Woche erhalten, und nach dem letzten Spiel der W17 gibt es keine Woche mehr (Offseason). Spiele mit
    offenem Anstoß zählen nicht.
    """
    return min((g["woche"] for g in games if not g["tbd"] and g["kickoff"] + IST_DELAY > now), default=None)


# ---------------------------------------------------------------- Abruf

def hour_window(kickoff: datetime) -> tuple[str, str]:
    """Erste und letzte Stunde des Fensters (Kickoff-Stunde … +3 h) als Open-Meteo-Zeitangabe (UTC)."""
    start = kickoff.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%dT%H:%M"), (start + timedelta(hours=HOURS - 1)).strftime("%Y-%m-%dT%H:%M")


def fetch_hours(session: requests.Session, lat: float, lon: float, kickoff: datetime, forecast: bool = True) -> dict:
    """Stundenwerte eines Spielorts im Kickoff-Fenster: {"zeit": [...], "temp": [...], ...} mit je HOURS Werten.

    forecast=False (Ist-Wetter) lässt die Regenwahrscheinlichkeit weg – sie ist eine Prognosegröße.
    Open-Meteo erlaubt start_hour rund drei Monate zurück und gut zwei Wochen voraus (Probe 29.09.2026).
    """
    keys = {var: key for var, key in VARIABLES.items() if forecast or key not in FORECAST_ONLY}
    start, end = hour_window(kickoff)
    params = {"latitude": lat, "longitude": lon, "timezone": "UTC", "hourly": ",".join(keys),
              "start_hour": start, "end_hour": end}
    try:
        resp = session.get(OPEN_METEO, params=params, timeout=ef.TIMEOUT)
    except requests.RequestException as exc:
        raise ef.FetchError(f"Netzwerkfehler: {exc}") from exc
    if resp.status_code != 200:
        raise ef.FetchError(f"HTTP {resp.status_code}: {resp.text[:200]!r}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ef.FetchError(f"kein gültiges JSON: {exc}") from exc
    hourly = data.get("hourly") if isinstance(data, dict) else None
    if not isinstance(hourly, dict) or len(hourly.get("time") or []) != HOURS:
        raise ef.FetchError(f"Antwort ohne {HOURS} Stundenwerte")
    out = {"zeit": [t + "Z" for t in hourly["time"]]}
    for var, key in keys.items():
        values = hourly.get(var)
        if not isinstance(values, list) or len(values) != HOURS:
            raise ef.FetchError(f"Antwort ohne '{var}'")
        out[key] = values
    return out


def dumps(obj: dict) -> bytes:
    """JSON mit einer Zeile je Spiel (Liste „spiele“), sonst kompakt – Diffs bleiben lesbar."""
    lines = []
    for key, value in obj.items():
        if key == "spiele":
            rows = ",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in value)
            lines.append(f'"spiele":[\n{rows}\n]' if value else '"spiele":[]')
        else:
            lines.append(f"{json.dumps(key)}:{json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
    return ("{\n" + ",\n".join(lines) + "\n}\n").encode("utf-8")


# ---------------------------------------------------------------- Prognose der laufenden Woche

def prognose_extract(session: requests.Session, season: int, week: int, games: list[dict], stadien: dict, stamp: str) -> dict:
    """Prognose für alle Spiele der Woche – alles oder nichts, damit keine halbe Woche als Datei steht."""
    spiele = []
    for g in games:
        site = game_site(g, stadien)
        # tbd: Anstoß bei ESPN noch offen – kickoff ist dann ESPNs Platzhalter (Sonntag 08:01 UTC), stunden None
        row = {"id": g["id"], "woche": g["woche"], "kickoff": iso(g["kickoff"]), "tbd": g["tbd"],
               "heim": g["heim"], "gast": g["gast"]}
        row.update(site)
        row["stunden"] = None if g["tbd"] else fetch_hours(session, site["lat"], site["lon"], g["kickoff"])
        spiele.append(row)
    return {"season": season, "woche": week, "stand": stamp, "quelle": QUELLE, "einheiten": EINHEITEN, "spiele": spiele}


def clear_prognose(season: int) -> list[Path]:
    """Löscht alle Prognosedateien (nach dem letzten Spiel der Saison); Rückgabe der gelöschten Dateien."""
    removed = sorted(prognose_dir(season).glob("w[0-9][0-9]_*.json"))
    for path in removed:
        path.unlink()
    return removed


def same_without_stand(old: dict, new: dict) -> bool:
    return {k: v for k, v in old.items() if k != "stand"} == {k: v for k, v in new.items() if k != "stand"}


def write_prognose(season: int, extract: dict, stamp: str) -> tuple[Path | None, list[Path]]:
    """Schreibt wNN_<stamp>.json, wenn sich die Prognose geändert hat; löscht Dateien anderer Wochen.

    Die Vorwoche wird erst gelöscht, wenn die neue Prognose vollständig vorliegt – scheitert Open-Meteo, bleibt die
    alte stehen (ihr Feld „woche“ sagt, zu welcher Woche sie gehört). Rückgabe (geschriebene Datei oder None, gelöschte).
    """
    folder, week = prognose_dir(season), extract["woche"]
    removed = [p for p in sorted(folder.glob("w[0-9][0-9]_*.json")) if not p.name.startswith(f"w{week:02d}_")]
    for path in removed:
        path.unlink()
    previous = ef.latest(folder, f"w{week:02d}_*.json")
    if previous is not None and same_without_stand(ef.load_json(previous), extract):
        return None, removed
    path = folder / f"w{week:02d}_{stamp}.json"
    ef.save_atomic(path, dumps(extract))
    return path, removed


# ---------------------------------------------------------------- Ist-Wetter (dauerhaft)

def ist_due(games: list[dict], existing: set[int], now: datetime) -> list[dict]:
    """Spiele, deren Anstoß mindestens IST_DELAY zurückliegt, mit fester Zeit und ohne Eintrag im Ist-Archiv."""
    return [g for g in games if g["id"] not in existing and not g["tbd"] and g["kickoff"] + IST_DELAY <= now]


def update_ist(session: requests.Session, season: int, games: list[dict], stadien: dict, now: datetime,
               stamp: str) -> tuple[int, int]:
    """Holt das Ist-Wetter fälliger Spiele und hängt es an ist_<saison>.json an; Rückgabe (neu, Fehler).

    Vorhandene Einträge werden nie überschrieben; ein fehlgeschlagenes Spiel holt der nächste Lauf nach.
    """
    path = ist_path(season)
    einheiten = {k: v for k, v in EINHEITEN.items() if k not in FORECAST_ONLY}
    data = ef.load_json(path) if path.exists() else {"season": season, "quelle": QUELLE, "einheiten": einheiten, "spiele": []}
    existing = {s["id"] for s in data["spiele"]}
    added = errors = 0
    for g in ist_due(games, existing, now):
        site = game_site(g, stadien)
        try:
            stunden = fetch_hours(session, site["lat"], site["lon"], g["kickoff"], forecast=False)
        except ef.FetchError as exc:
            errors += 1
            print(f"  Ist W{g['woche']:02d} Spiel {g['id']}  FEHLER – {exc}")
            continue
        row = {"id": g["id"], "woche": g["woche"], "kickoff": iso(g["kickoff"]), "heim": g["heim"], "gast": g["gast"]}
        row.update(site)
        row.update(abgerufen=stamp, stunden=stunden)
        data["spiele"].append(row)
        added += 1
    if added:
        data["spiele"].sort(key=lambda s: (s["woche"], s["kickoff"], s["id"]))
        ef.save_atomic(path, dumps(data))
    return added, errors


# ---------------------------------------------------------------- Einstieg für den Tageslauf

def run(session: requests.Session, season: int, now: datetime, stamp: str) -> tuple[int, list[str]]:
    """Tageslauf-Teil Wetter: Prognose der laufenden Woche und Ist-Wetter fälliger Spiele. Rückgabe (Fehler, Warnungen).

    Fehler (rot) nur bei fehlenden Grundlagen (Stadion-Tabelle, NFL-Spielplan); Open-Meteo-Ausfälle sind Warnungen,
    weil der nächste Lauf spätestens eine Stunde später neu versucht.
    """
    try:
        stadien = load_stadien(season)
        games = season_games(ef.load_json(ef.season_files(season)["schedule"]))
    except (ef.FetchError, KeyError, ValueError) as exc:
        print(f"  FEHLER – {exc}")
        return 1, []
    warnings = []
    week = prognose_week(games, now)
    if week is not None:
        try:
            extract = prognose_extract(session, season, week, [g for g in games if g["woche"] == week], stadien, stamp)
            path, removed = write_prognose(season, extract, stamp)
            for old in removed:
                print(f"  {old.name:<28} gelöscht (Vorwoche)")
            if path is None:
                print(f"  Prognose W{week:02d}           unverändert ({len(extract['spiele'])} Spiele)")
            else:
                print(f"  {path.name:<28} {len(extract['spiele'])} Spiele -> {ef.rel(path)}")
        except ef.FetchError as exc:
            warnings.append(f"Wetter-Prognose W{week}: {exc} – vorhandene Prognose bleibt stehen")
    else:
        for old in clear_prognose(season):
            print(f"  {old.name:<28} gelöscht (Saison vorbei)")
        print(f"  kein offenes Spiel W1–{LAST_WEEK} – keine Prognose")
    try:
        added, errors = update_ist(session, season, games, stadien, now, stamp)
    except ef.FetchError as exc:
        return 1, warnings + [f"Ist-Wetter: {exc}"]
    print(f"  {ist_path(season).name:<28} {added} Spiel(e) neu" + (f", {errors} Fehler" if errors else ""))
    if errors:
        warnings.append(f"Ist-Wetter: {errors} Spiel(e) nicht abgerufen – der nächste Lauf versucht es erneut")
    return 0, warnings


# ---------------------------------------------------------------- Rechenwerk (App-Daten)

AGG = {"temp": "mean", "wind": "mean", "boeen": "max", "regen_wahrsch": "max", "niederschlag": "sum", "schnee": "sum"}
# Markierung als Faustregel aus der Literatur (Auftrag Session 8, Punkt 5; session6_vorbereitung.md §5): Wind ab 25 km/h,
# Böen ab 40 km/h, Regenwahrscheinlichkeit ab 60 %, jeder Schnee (> 0 cm)
SCHWELLEN = {"wind": 25, "boeen": 40, "regen_wahrsch": 60, "schnee": 0}
JSON_PLACES = 1                   # Stellen der Werte in wetter.json (app_export.PRECISION), Grundlage der Anzeige


def aggregate(stunden: dict | None) -> dict:
    """Vier Stunden je Spiel verdichtet: Ø Temperatur und Wind, höchste Böe und Regenwahrscheinlichkeit,
    Σ Niederschlag und Schnee; None ohne Werte. Ergebnis als Decimal (gerundet wird beim Export)."""
    out = {}
    for key, how in AGG.items():
        values = [dec(v) for v in (stunden or {}).get(key) or [] if v is not None]
        if not values:
            out[key] = None
        elif how == "mean":
            out[key] = statistics.mean(values)
        elif how == "max":
            out[key] = max(values)
        else:
            out[key] = sum(values, dec(0))
    return out


def markierung(spiel: dict) -> list[str]:
    """Schlüssel der Werte ab der Schwelle (SCHWELLEN), in deren Reihenfolge; leer bei offenem Anstoß (tbd) und bei
    Dachspielen (dach nicht „offen“).

    Verglichen wird der Wert so, wie die App ihn zeigt: Wind, Böen und Regenwahrscheinlichkeit mit einer Stelle wie in
    wetter.json, dann ganzzahlig (je round half up) ≥ Schwelle; Schnee mit einer Stelle > 0. Fehlende Werte (Ist ohne
    Regenwahrscheinlichkeit) zählen nicht.
    """
    if spiel.get("tbd") or spiel.get("dach") != "offen":
        return []
    marks = []
    for key, limit in SCHWELLEN.items():
        value = spiel.get(key)
        if value is None:
            continue
        shown = round_to(value, JSON_PLACES)
        if (shown > limit) if key == "schnee" else (round_to(shown, 0) >= limit):
            marks.append(key)
    return marks


def compute_wetter(prognose: dict | None, ist: dict | None, abbrev: dict[int, str]) -> dict | None:
    """App-Sicht des Wetters: jüngste Prognose der laufenden Woche und das Ist-Archiv, je Spiel verdichtet und mit der
    Markierung ab den Schwellen (markierung, Kopf „schwellen“).

    stand = jüngster Abruf (Prognose-Stand oder letzter Ist-Abruf). None, solange es keine Wetterdaten gibt.
    """
    if not prognose and not ist:
        return None

    def row(s: dict, forecast: bool) -> dict:
        values = aggregate(s.get("stunden"))
        if not forecast:
            values = {k: v for k, v in values.items() if k not in FORECAST_ONLY}
        tbd = bool(s.get("tbd"))  # Anstoß offen: ESPNs Platzhalterzeit nicht als Kickoff ausgeben
        out = {"id": s["id"], "woche": s["woche"], "kickoff": None if tbd else s["kickoff"], "tbd": tbd,
               "heim": abbrev.get(s["heim"]), "gast": abbrev.get(s["gast"]),
               "stadion": s["stadion"], "ort": s["ort"], "dach": s["dach"], "neutral": s["neutral"]} | values
        return out | {"markierung": markierung(out)}

    stands = ([prognose["stand"]] if prognose else []) + [s["abgerufen"] for s in (ist or {}).get("spiele", [])]
    if not stands:
        return None  # Ist-Datei ohne Spiele und keine Prognose
    return {"stand": max(stands), "woche": prognose["woche"] if prognose else None, "einheiten": EINHEITEN,
            "schwellen": SCHWELLEN,
            "prognose": [row(s, True) for s in prognose["spiele"]] if prognose else [],
            "ist": [row(s, False) for s in ist["spiele"]] if ist else []}
