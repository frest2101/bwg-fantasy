"""Marktwerte von FantasyCalc für den Keeper-Tab (Stufe 3, Freigabe Stephan 01.10.2026).

FantasyCalc (https://fantasycalc.com) errechnet aus Trades in Dynasty-Ligen einen Tauschwert je Spieler. Die
Nutzungsbedingungen (Stand 24.02.2024) erlauben die Nutzung auf anderen Webseiten: nicht kommerziell, mit gut sichtbarer
Nennung „FantasyCalc“ und Link auf jeder Seite mit den Daten (auch für abgeleitete Werte), Zwischenspeichern erwünscht
(am besten ein Abruf je Tag, laut API-Doku höchstens einer je Stunde); verboten ist, wesentliche Teile ihres Angebots
wiederzugeben oder zu ersetzen. Kein Eindruck von Partnerschaft oder Billigung: Nennung neutral („Werte: FantasyCalc“).
Beschlüsse Stephan 01.10.2026: keine Mail an FantasyCalc, nur die genutzten Felder, keine Pick-Werte, ein Abruf je Tag.

- Abruf (Tageslauf, espn_fetch.py --marktwert): eine Anfrage an den dokumentierten Endpunkt values/current
  mit den Parametern der Liga (Dynasty, Superflex, 10 Teams, PPR), rund 330 KB. Höchstens einmal je UTC-Tag: Stammt
  der gespeicherte Auszug vom selben Tag, fragt der Lauf nicht. Abgelegt wird nur ein Auszug für die Spieler des
  ESPN-Pools unter fantasycalc/latest.json – je ESPN-ID Wert, Rang, Positionsrang, Trend 30 Tage und Redraft-Wert,
  eine Zeile je Spieler, ohne Namen und ohne Picks, Werte unverändert. stand ist die Abrufzeit und wird bei jedem
  gelungenen Abruf neu geschrieben, auch wenn sich kein Wert geändert hat – er ist die Tagessperre (anders als beim
  Pool-Auszug, dessen stand die letzte Änderung ist).
- Zuordnung nur über espnId (Text in der Antwort); Einträge ohne espnId fallen weg. Rund 30 Namen weichen von ESPN ab
  (ohne „Jr.“, Spitznamen) – die App zeigt die ESPN-Namen.
- overallRank zählt die Spieler 1 … n ohne die Picks (lückenlos und eindeutig; ein Pick trägt den Rang des nächsten
  Spielers) und wird unverändert übernommen, nicht neu gezählt. K und D/ST haben keinen Wert.
- Lesen (compute.py → keeper.py): werte() gibt die Werte je ESPN-ID; redraftValue 0 heißt „kein Redraft-Wert“ → None.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import requests

import espn_fetch as ef
import nflverse

# dokumentierter Endpunkt (fantasycalc.com/api-docs; seit spätestens 09.10.2026 dazu /players, hier nicht genutzt) – nur
# dokumentierte Endpunkte dürfen programmatisch abgerufen werden
URL = "https://api.fantasycalc.com/values/current"
PARAMETER = {"isDynasty": "true", "numQbs": 2, "numTeams": 10, "ppr": 1}   # Liga: Dynasty-Werte, Superflex, 10 Teams, PPR
QUELLE = "FantasyCalc (https://fantasycalc.com), Dynasty-Werte values/current; Auszug für die Spieler des ESPN-Pools"
LABEL = "fantasycalc/latest.json"
PICK = "PICK"                 # player.position eines Draft-Picks: Picks werden nicht gespeichert
# Feld der Antwort → Feld im Auszug; die ersten vier sind Pflicht, redraftValue darf fehlen oder leer sein
FELDER = {"value": "wert", "overallRank": "rang", "positionRank": "pos_rang", "trend30Day": "trend30",
          "redraftValue": "redraft"}
PFLICHT = ("value", "overallRank", "positionRank", "trend30Day")
MIN_PLAYERS = 200             # eine vollständige Liste hat rund 400 Spieler (01.10.2026: 396)
MIN_SHARE = Decimal("0.8")    # so viele der Listenspieler mit espnId muss der ESPN-Pool kennen (01.10.2026: 392 von 393)


def path(season: int) -> Path:
    return ef.RAW_DIR / str(season) / "fantasycalc" / "latest.json"


# ---------------------------------------------------------------- Abruf (Tageslauf)

def whole(value) -> bool:
    """Ganze Zahl (bool zählt nicht)."""
    return isinstance(value, int) and not isinstance(value, bool)


def espn_id(player: dict) -> int | None:
    """ESPN-ID aus player.espnId (Text); None ohne oder bei unlesbarer Angabe."""
    raw = player.get("espnId")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        pid = int(str(raw).strip())
    except ValueError:
        return None
    return pid if pid > 0 else None


def extract(rows, ids: set[int], stand: str) -> dict:
    """Auszug aus der Antwort für die ESPN-IDs ids: Kopf quelle, stand, parameter; je ESPN-ID {wert, rang, pos_rang,
    trend30, redraft}, nach ID sortiert.

    Unbrauchbar (FetchError, der alte Auszug bleibt stehen): keine Liste, Eintrag ohne player, weniger als MIN_PLAYERS
    Spieler, ein Spieler ohne Wert, Rang, Positionsrang oder Trend als ganze Zahl, Ränge der Spieler nicht genau 1 … n,
    oder der ESPN-Pool kennt weniger als MIN_SHARE der Listenspieler mit espnId. Führt die Liste eine ESPN-ID doppelt,
    gilt der besser gerankte Eintrag.
    """
    if not isinstance(rows, list):
        raise ef.FetchError("FantasyCalc: Antwort ist keine Liste")
    players = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("player"), dict):
            raise ef.FetchError("FantasyCalc: Eintrag ohne player")
        if row["player"].get("position") != PICK:
            players.append(row)
    if len(players) < MIN_PLAYERS:
        raise ef.FetchError(f"FantasyCalc: nur {len(players)} Spieler in der Liste")
    broken = sum(1 for r in players if not all(whole(r.get(k)) for k in PFLICHT)
                 or not (r.get("redraftValue") is None or whole(r["redraftValue"])))
    if broken:
        raise ef.FetchError(f"FantasyCalc: {broken} Spieler ohne Wert, Rang, Positionsrang oder Trend")
    if sorted(r["overallRank"] for r in players) != list(range(1, len(players) + 1)):
        raise ef.FetchError("FantasyCalc: Ränge der Spieler nicht 1 … n ohne Lücke und Doppel")
    known = [(espn_id(r["player"]), r) for r in players]
    known = sorted(((pid, r) for pid, r in known if pid is not None), key=lambda kv: kv[1]["overallRank"])
    hits: dict[int, dict] = {}
    for pid, row in known:
        if pid in ids and pid not in hits:
            hits[pid] = {new: row.get(old) for old, new in FELDER.items()}
    if not hits or len(hits) < MIN_SHARE * len(known):
        raise ef.FetchError(f"FantasyCalc: nur {len(hits)} von {len(known)} Spielern mit ESPN-ID im ESPN-Pool")
    return {"quelle": QUELLE, "stand": stand, "parameter": PARAMETER,
            "spieler": {str(pid): hits[pid] for pid in sorted(hits)}}


def dumps(data: dict) -> bytes:
    """JSON mit einer Zeile je Spieler – der Git-Verlauf zeigt, wessen Wert sich ändert."""
    head = ",\n".join(f"{json.dumps(k)}:{json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "spieler")
    rows = ",\n".join(f"{json.dumps(pid)}:{json.dumps(p, separators=(',', ':'))}" for pid, p in data["spieler"].items())
    return f'{{\n{head},\n"spieler":{{\n{rows}\n}}\n}}\n'.encode("utf-8")


def fetch(session: requests.Session, ids: set[int], stand: str) -> bytes:
    """Fragt values/current ab und gibt den Auszug für ids als Dateiinhalt zurück."""
    try:
        resp = session.get(URL, params=PARAMETER, timeout=ef.TIMEOUT)
    except requests.RequestException as exc:
        raise ef.FetchError(f"FantasyCalc: Netzwerkfehler: {exc}") from exc
    if resp.status_code != 200:
        raise ef.FetchError(f"FantasyCalc: HTTP {resp.status_code}")
    try:
        rows = resp.json()
    except ValueError as exc:
        raise ef.FetchError(f"FantasyCalc: Antwort nicht lesbar ({exc})") from exc
    return dumps(extract(rows, ids, stand))


def fetched_today(season: int, now: datetime) -> str | None:
    """Stand des gespeicherten Auszugs, wenn er vom selben UTC-Tag stammt wie now; sonst None – auch ohne Auszug oder
    bei unlesbarer Datei (dann holt der Lauf neu)."""
    target = path(season)
    if not target.exists():
        return None
    try:
        stand = ef.load_json(target).get("stand")
    except (ef.FetchError, AttributeError):
        return None
    return stand if isinstance(stand, str) and stand[:10] == now.strftime("%Y-%m-%d") else None


def update(session: requests.Session, season: int, now: datetime) -> list[str]:
    """Tageslauf: höchstens ein Abruf je UTC-Tag; gibt Warnungen zurück (ein Ausfall macht den Lauf nicht rot).

    Fängt jeden Fehler selbst wie nflverse (als Skript gestartet ist espn_fetch zweimal geladen, ein Fang dort griffe
    nicht): Der bisherige Auszug bleibt stehen, und weil sein stand von einem früheren Tag ist, versucht es der nächste
    Lauf erneut. Ohne Spielerpool (vor dem ersten Abruf der Saison) gibt es nichts zuzuordnen: kein Abruf, keine Warnung.
    """
    target = path(season)
    try:
        today = fetched_today(season, now)
        if today:
            print(f"  {LABEL:<34} heute schon abgerufen (Stand {today})")
            return []
        ids = nflverse.pool_ids(season)
        if not ids:
            print(f"  {LABEL:<34} noch kein Spielerpool")
            return []
        content = fetch(session, ids, now.strftime("%Y-%m-%dT%H%MZ"))
        ef.save_atomic(target, content)
    except Exception as exc:  # noqa: BLE001 – Nebenteil, siehe Docstring
        reason = exc if isinstance(exc, ef.FetchError) else f"{type(exc).__name__}: {exc}"
        print(f"  {LABEL:<34} FEHLER – {reason}", file=sys.stderr)
        return [f"Marktwert: {reason} – der bisherige Auszug bleibt, der nächste Lauf versucht es erneut"]
    print(f"  {LABEL:<34} {len(content):>10,} Bytes -> {ef.rel(target)}")
    return []


# ---------------------------------------------------------------- Lesen (reine Funktionen)

def werte(data: dict | None) -> dict[int, dict]:
    """Auszug als ESPN-ID → {"wert", "rang", "pos_rang", "trend30", "redraft"} (ganze Zahlen; redraft None, wenn
    FantasyCalc keinen Redraft-Wert führt, also bei 0 oder leer); leer ohne Auszug."""
    return {int(pid): dict(p, redraft=p.get("redraft") or None)
            for pid, p in ((data or {}).get("spieler") or {}).items()}
