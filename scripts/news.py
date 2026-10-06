"""News je Spieler (Session 6, Stufe 2 – vorbereitet, bleibt aus: Beschluss Stephan 30.09.2026).

Quelle laut Probe-Lauf 29.09.2026: ESPN-Site-API, Fantasy-News je Spieler
(site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId=<id>&days=<n>): je Meldung Typ (Rotowire-Meldung
oder ESPN-Story), Schlagzeile, Datum und – bei Stories – ein Web-Link. Der Zugriff ist undokumentiert.

Sparsam über lastNewsDate (Beschluss Stephan 29.09.2026): abgefragt werden nur Spieler, deren lastNewsDate im aktuellen
Pool-Auszug von dem Stand abweicht, den dieses Modul selbst in news/lastNewsDate.json führt (je Spieler das Datum, bis
zu dem seine Meldungen geholt sind). Beim ersten Lauf ist der Stand leer, also kommen alle Kaderspieler und die Free
Agents der App (app/data/players.json) dran; fehlgeschlagene oder wegen MAX_PLAYERS zurückgestellte Spieler bleiben
Kandidaten, bis ihr Abruf gelingt. Ablage data/raw/<saison>/news/<UTC>.json nur mit neuen Meldungen und nur mit
Spieler-ID, Meldungs-ID, Typ, Schlagzeile, Datum, Link – nie der Text.

Stufe 2 bleibt aus (Beschluss Stephan 30.09.2026, CLAUDE.md „Gelernt“): Die Rotowire-„Schlagzeile“ ist der ganze Text
ohne Web-Link, das wäre Fremdtext im öffentlichen Repo. Der Tageslauf ruft --news nicht auf; nicht erneut vorschlagen.
"""

import json
from pathlib import Path

import requests

import espn_fetch as ef

NEWS_URL = "https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players"
DAYS = 7                 # Zeitraum je Abfrage; schon archivierte Meldungen werden nicht erneut gespeichert
MAX_PLAYERS = 400        # Obergrenze je Lauf; der Rest bleibt Kandidat für den nächsten Lauf
STATE_FILE = "lastNewsDate.json"   # je Spieler das lastNewsDate, bis zu dem die Meldungen geholt sind
KEYS = ("player_id", "id", "typ", "schlagzeile", "datum", "link")


def news_dir(season: int) -> Path:
    return ef.RAW_DIR / str(season) / "news"


def state_path(season: int) -> Path:
    return news_dir(season) / STATE_FILE


def load_state(season: int) -> dict[int, int]:
    """Gemerkter Stand je Spieler-ID; leer beim ersten Lauf."""
    path = state_path(season)
    return {int(pid): date for pid, date in ef.load_json(path).items()} if path.exists() else {}


def interesting_ids(season: int, pool: dict) -> set[int]:
    """Spieler, die uns interessieren: alle Kaderspieler laut Pool-Auszug plus die Spieler der App (players.json:
    Kader, mit Spiel, die besten Free Agents je Position). Ohne players.json nur die Kaderspieler."""
    ids = {p["id"] for p in pool["players"] if p.get("onTeamId")}
    app_players = ef.REPO_DIR / "app" / "data" / "players.json"
    if app_players.exists():
        ids |= {p["id"] for p in ef.load_json(app_players).get("players", [])}
    return ids


def candidates(state: dict[int, int], current: dict, interesting: set[int]) -> list[int]:
    """Interessante Spieler mit lastNewsDate, das vom gemerkten Stand abweicht (neu, geändert, noch nicht geholt),
    sortiert nach ID."""
    return sorted(p["id"] for p in current["players"]
                  if p["id"] in interesting and p.get("lastNewsDate") and state.get(p["id"]) != p["lastNewsDate"])


def extract(feed: list[dict], player_id: int) -> list[dict]:
    """Nur Verweise je Meldung: Spieler-ID (der abgefragte Spieler), Meldungs-ID, Typ, Schlagzeile, Datum, Web-Link
    (None bei Rotowire-Meldungen, die nur in der ESPN-App verlinkt sind)."""
    rows = []
    for item in feed:
        if not isinstance(item, dict) or "id" not in item:
            continue
        link = ((item.get("links") or {}).get("web") or {}).get("href")
        rows.append({"player_id": player_id, "id": item["id"], "typ": item.get("type"),
                     "schlagzeile": item.get("headline"), "datum": item.get("published"), "link": link})
    return rows


def fetch_player_news(session: requests.Session, player_id: int, days: int = DAYS) -> list[dict]:
    try:
        resp = session.get(NEWS_URL, params={"playerId": player_id, "days": days}, timeout=ef.TIMEOUT)
    except requests.RequestException as exc:
        raise ef.FetchError(f"Netzwerkfehler: {exc}") from exc
    if resp.status_code != 200:
        raise ef.FetchError(f"HTTP {resp.status_code}: {resp.text[:200]!r}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ef.FetchError(f"kein gültiges JSON: {exc}") from exc
    feed = data.get("feed") if isinstance(data, dict) else None
    if not isinstance(feed, list):
        raise ef.FetchError("Antwort ohne Liste 'feed'")
    return extract(feed, player_id)


def known_pairs(season: int) -> set[tuple[int, object]]:
    """(Spieler-ID, Meldungs-ID) aller archivierten Meldungen – eine Meldung zu zwei Spielern zählt je Spieler."""
    pairs = set()
    for path in sorted(news_dir(season).glob("????-??-??T????Z.json")):
        pairs |= {(m["player_id"], m["id"]) for m in ef.load_json(path).get("meldungen", [])}
    return pairs


def dumps(obj: dict) -> bytes:
    lines = []
    for key, value in obj.items():
        if key == "meldungen":
            rows = ",\n".join(json.dumps(m, ensure_ascii=False, separators=(",", ":")) for m in value)
            lines.append(f'"meldungen":[\n{rows}\n]' if value else '"meldungen":[]')
        else:
            lines.append(f"{json.dumps(key)}:{json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
    return ("{\n" + ",\n".join(lines) + "\n}\n").encode("utf-8")


def run(session: requests.Session, season: int, current_pool: dict, stamp: str) -> tuple[int, list[str]]:
    """Tageslauf-Teil News: neue Meldungen der Kandidaten nach news/<stamp>.json, Stand je Spieler fortschreiben.

    Rückgabe (Fehler, Warnungen). Ein fehlgeschlagener Spieler ist eine Warnung; sein Stand bleibt alt, der nächste
    Lauf versucht es erneut. Mehr als MAX_PLAYERS Kandidaten: der Rest wartet auf den nächsten Lauf (Warnung).
    """
    state = load_state(season)
    ids = candidates(state, current_pool, interesting_ids(season, current_pool))
    if not ids:
        print("  keine Spieler mit neuem lastNewsDate")
        return 0, []
    deferred, ids = ids[MAX_PLAYERS:], ids[:MAX_PLAYERS]
    dates = {p["id"]: p["lastNewsDate"] for p in current_pool["players"]}
    known, fresh, failed = known_pairs(season), [], 0
    for pid in ids:
        try:
            rows = fetch_player_news(session, pid)
        except ef.FetchError as exc:
            failed += 1
            print(f"  Spieler {pid}  FEHLER – {exc}")
            continue
        for m in rows:
            if (m["player_id"], m["id"]) not in known:
                known.add((m["player_id"], m["id"]))
                fresh.append(m)
        state[pid] = dates[pid]
    fresh.sort(key=lambda m: (m["datum"] or "", m["player_id"], str(m["id"])))
    warnings = []
    if failed:
        warnings.append(f"News: {failed} Spieler nicht abgefragt – der nächste Lauf versucht es erneut")
    if deferred:
        warnings.append(f"News: {len(deferred)} Spieler über der Grenze von {MAX_PLAYERS} je Lauf zurückgestellt")
    if len(ids) > failed:
        ef.save_atomic(state_path(season), (json.dumps({str(pid): state[pid] for pid in sorted(state)}, indent=0) + "\n").encode("utf-8"))
    if fresh:
        path = news_dir(season) / f"{stamp}.json"
        ef.save_atomic(path, dumps({"season": season, "stand": stamp, "quelle": NEWS_URL, "spieler": len(ids) - failed,
                                    "meldungen": fresh}))
        print(f"  {len(ids)} Spieler abgefragt, {len(fresh)} neue Meldungen -> {ef.rel(path)}")
    else:
        print(f"  {len(ids)} Spieler abgefragt, keine neuen Meldungen")
    return 0, warnings
